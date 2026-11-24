# -*- coding: utf-8 -*-
"""Конвертер: .wrl из Базиса (+ .wrl стен по замеру) -> model.glb + model.json.

  python wrl2glb.py МЕБЕЛЬ.wrl [--room СТЕНЫ.wrl] --out ПАПКА [--title "Постирочная"]

model.glb  — геометрия в метрах (Y вверх), одна нода на деталь (имя ноды = id детали),
             текстуры внутри, сжатие Draco (KHR_draco_mesh_compression).
model.json — детали (имя по-русски, габарит, материал, блок), дерево блоков,
             двери (ось петель a–b, угол), выдвижные (направление, ход), помещение.
"""
import argparse
import glob
import io
import json
import math
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wrl_reader  # noqa: E402
from translit import rus  # noqa: E402

BAZIS_TEX = os.path.expanduser(r'~\Documents\Bazis\Текстуры')

SKIP_NODE = re.compile(r'^(Otverstie|Liniya_styka|Gabaritnaya_ramka|Otv\.)', re.I)
HARDWARE = re.compile(r'^(Petlya|Podpyatnik|Opora|Ruchka|Napravlyayushch|Zashch|Zamok|Shtanga|'
                      r'Kreplenie|Konfirmat|Evrovint|Ekstsentrik|Polkoderzhatel|Ogranichitel|Dovodchik|'
                      r'Kronshteyn|Nozhka|Profil|Truba|Shtangoderzhatel|Tolkatel|Push|Tip)', re.I)
DOOR = re.compile(r'^Dver', re.I)
SLIDE = re.compile(r'(Yashchik|Yashik|Vydvizhn|otkatn|Vykatn)', re.I)
PLATE = re.compile(r'^(Krestoobr|.*otvetnaya_planka)', re.I)
PANELISH = re.compile(r'^(Bok|Dno|Fasad|Frontal|Polk|Stoyk|Krysh|Stenk|St\._|Zadn|Peregorod|Tsokol|'
                      r'Kryshk|Gorizontal|Vertikal|Planka_fasad|Lits)', re.I)
ROOM_NODE = re.compile(r'^Pomeshchenie', re.I)
APPLIANCES = re.compile(r'^(Tekhnika|Bytovaya_tekhnika)$', re.I)

DOOR_ANGLE = 75          # градусов
SLIDE_PART = 0.8         # ход выдвижного = 80 % глубины
TEX_MAX = 2048           # пикселей по большей стороне (текстуры декоров не уменьшаются)


# ---------------------------------------------------------------- материалы

def load_catalog():
    """Каталоги Базиса (*.xml) -> {имя файла текстуры без расширения: (название, мм X, мм Y)}."""
    cat = {}
    for f in glob.glob(os.path.join(BAZIS_TEX, '**', '*.xml'), recursive=True):
        try:
            root = ET.parse(f).getroot()
        except Exception:
            continue
        for m in root.iter('Material'):
            tex = (m.findtext('Texture') or '').replace('\\', '/')
            if not tex:
                continue
            stem = os.path.splitext(os.path.basename(tex))[0]
            name = m.findtext('Name') or stem
            try:
                ox = float(m.findtext('OffsetX') or 1000) or 1000
                oy = float(m.findtext('OffsetY') or 1000) or 1000
            except ValueError:
                ox = oy = 1000
            cat.setdefault(stem.lower(), (name, ox, oy))
    return cat


def pretty_material(stem, cat):
    """«U211» -> «EGGER U211 «Миндаль бежевый»»."""
    rec = cat.get(stem.lower())
    if not rec:
        return stem
    name = rec[0]
    m = re.search(r'«[^»]+»', name)
    brand = 'EGGER' if 'EGGER' in name.upper() else ''
    for b in ('Кроношпан', 'KRONOSPAN', 'Lamarty', 'BOYARD'):
        if b.lower() in name.lower():
            brand = b
    code = stem
    return ' '.join(x for x in (brand, code, m.group(0) if m else '') if x)


def find_texture(url, wrl_dir):
    """url из .wrl («постирочная_Textures\\U211.jpg») -> путь к файлу."""
    url = url.replace('\\', '/')
    base = os.path.basename(url)
    cands = [os.path.join(wrl_dir, url)]
    for d in glob.glob(os.path.join(wrl_dir, '*_Textures')) + glob.glob(os.path.join(wrl_dir, '*', '*_Textures')):
        cands.append(os.path.join(d, base))
    for c in cands:
        if os.path.isfile(c):
            return c
    hits = glob.glob(os.path.join(BAZIS_TEX, '**', base), recursive=True)
    return hits[0] if hits else None


def jpeg_bytes(path):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    s = min(1.0, TEX_MAX / max(w, h))
    if s < 1:
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    # размеры кратные 4 не обязательны для WebGL2, но малые текстуры увеличим до 64
    if max(im.size) < 64:
        im = im.resize((64, 64), Image.NEAREST)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=88, optimize=True, progressive=True)
    return buf.getvalue(), im.size


def hexcolor(c):
    return '#%02x%02x%02x' % tuple(int(round(max(0, min(1, v)) * 255)) for v in c)


# ---------------------------------------------------------------- геометрия

def shape_tris(shp):
    """-> (T,3,3) координаты треугольников, мм, мировые."""
    tri = wrl_reader.triangulate(shp['ci'])
    if not len(tri):
        return np.zeros((0, 3, 3))
    idx = shp['ci'][tri]
    idx = np.clip(idx, 0, len(shp['pts']) - 1)
    return shp['pts'][idx]


def decimate(T, cell):
    """Кластеризация вершин: сетка cell мм, вырожденные треугольники отбрасываются."""
    if cell <= 0 or not len(T):
        return T
    P = T.reshape(-1, 3)
    q = np.round(P / cell).astype(np.int64)
    _, inv, cnt = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    sums = np.zeros((cnt.size, 3))
    np.add.at(sums, inv, P)
    C = sums / cnt[:, None]
    I = inv.reshape(-1, 3)
    ok = (I[:, 0] != I[:, 1]) & (I[:, 1] != I[:, 2]) & (I[:, 0] != I[:, 2])
    I = I[ok]
    # убрать дубликаты треугольников
    key = np.sort(I, axis=1)
    _, first = np.unique(key, axis=0, return_index=True)
    I = I[np.sort(first)]
    return C[I]


def face_normals(T):
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    a = np.linalg.norm(n, axis=1)
    return n, a


def build_primitive(T, Minv, uvinfo, crease_deg=35.0):
    """Треугольники (мм) -> индексированная сетка (м): pos, nrm, uv|None, idx."""
    n, a = face_normals(T)
    keep = a > 1e-6
    T, n, a = T[keep], n[keep], a[keep]
    if not len(T):
        return None
    fn = n / a[:, None]
    P = T.reshape(-1, 3)
    # сглаживание нормалей с порогом излома
    key = np.round(P * 100).astype(np.int64)
    _, pid = np.unique(key, axis=0, return_inverse=True)
    pid = pid.reshape(-1)
    acc = np.zeros((pid.max() + 1, 3))
    np.add.at(acc, pid, np.repeat(n, 3, axis=0))   # взвешено площадью
    sn = acc[pid]
    sn /= np.maximum(np.linalg.norm(sn, axis=1, keepdims=True), 1e-12)
    cf = np.repeat(fn, 3, axis=0)
    use_s = (sn * cf).sum(1) > math.cos(math.radians(crease_deg))
    N = np.where(use_s[:, None], sn, cf)
    UV = None
    if uvinfo is not None:
        W, H, grain = uvinfo
        L = np.c_[P, np.ones(len(P))] @ Minv.T
        L = L[:, :3]
        ln = fn @ Minv[:3, :3].T
        dom = np.argmax(np.abs(ln), axis=1)
        dom = np.repeat(dom, 3)
        UV = np.zeros((len(P), 2))
        for k in range(3):
            m = dom == k
            if not m.any():
                continue
            others = [i for i in range(3) if i != k]
            if grain in others:
                va = grain
                ua = others[0] if others[1] == grain else others[1]
            else:
                ua, va = others
            UV[m, 0] = L[m, ua] / W
            UV[m, 1] = L[m, va] / H
    # склейка одинаковых вершин
    cols = [np.round(P * 100), np.round(N * 1000)]
    if UV is not None:
        cols.append(np.round(UV * 4096))
    K = np.hstack(cols).astype(np.int64)
    _, uniq, inv = np.unique(K, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    pos = (P[uniq] / 1000.0).astype(np.float32)
    nrm = N[uniq].astype(np.float32)
    uv = UV[uniq].astype(np.float32) if UV is not None else None
    idx = inv.astype(np.uint32)
    return pos, nrm, uv, idx


# ---------------------------------------------------------------- GLB

class GLB:
    def __init__(self, draco=True):
        self.draco = draco
        self.bin = bytearray()
        self.g = {'asset': {'version': '2.0', 'generator': 'bvsspace wrl2glb'},
                  'scene': 0, 'scenes': [{'nodes': [0]}],
                  'nodes': [{'name': 'model', 'children': []}],
                  'meshes': [], 'materials': [], 'accessors': [], 'bufferViews': [],
                  'buffers': [], 'images': [], 'textures': [], 'samplers': [
                      {'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}]}
        if draco:
            self.g['extensionsUsed'] = ['KHR_draco_mesh_compression']
            self.g['extensionsRequired'] = ['KHR_draco_mesh_compression']
        self.matidx = {}

    def view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin)
        self.bin += data
        bv = {'buffer': 0, 'byteOffset': off, 'byteLength': len(data)}
        if target:
            bv['target'] = target
        self.g['bufferViews'].append(bv)
        return len(self.g['bufferViews']) - 1

    def accessor(self, arr, typ, bv=True, minmax=False, ctype=5126):
        acc = {'componentType': ctype, 'count': int(arr.shape[0]), 'type': typ}
        if bv:
            target = 34963 if typ == 'SCALAR' else 34962
            acc['bufferView'] = self.view(arr.tobytes(), target)
        if minmax:
            acc['min'] = [float(x) for x in arr.min(0)]
            acc['max'] = [float(x) for x in arr.max(0)]
        self.g['accessors'].append(acc)
        return len(self.g['accessors']) - 1

    def material(self, key, spec):
        if key in self.matidx:
            return self.matidx[key]
        m = {'name': key, 'pbrMetallicRoughness': {
            'baseColorFactor': list(spec['color']) + [spec.get('opacity', 1.0)],
            'metallicFactor': spec.get('metal', 0.0), 'roughnessFactor': spec.get('rough', 0.75)}}
        if spec.get('jpeg'):
            bv = self.view(spec['jpeg'])
            self.g['images'].append({'bufferView': bv, 'mimeType': 'image/jpeg', 'name': key})
            self.g['textures'].append({'sampler': 0, 'source': len(self.g['images']) - 1})
            m['pbrMetallicRoughness']['baseColorTexture'] = {'index': len(self.g['textures']) - 1}
        if spec.get('opacity', 1.0) < 1:
            m['alphaMode'] = 'BLEND'
            m['doubleSided'] = True
        self.g['materials'].append(m)
        self.matidx[key] = len(self.g['materials']) - 1
        return self.matidx[key]

    def mesh(self, name, prims):
        out = []
        for pos, nrm, uv, idx, mat in prims:
            if self.draco:
                import DracoPy
                faces = idx.reshape(-1, 3)
                kw = dict(quantization_bits=14, compression_level=7,
                          normals=nrm.astype(np.float64), normal_quantization_bits=10)
                if uv is not None:
                    kw['tex_coord'] = uv.astype(np.float64)
                    kw['tex_coord_quantization_bits'] = 12
                data = DracoPy.encode(pos.astype(np.float64), faces, **kw)
                bv = self.view(data)
                # номера атрибутов внутри Draco узнаём декодированием
                tname = {0: 'POSITION', 1: 'NORMAL', 3: 'TEXCOORD_0'}
                ids = {}
                for at in DracoPy.decode(data).attributes:
                    if at['attribute_type'] in tname:
                        ids[tname[at['attribute_type']]] = int(at['unique_id'])
                attrs = {}
                attrs['POSITION'] = self.accessor(pos, 'VEC3', bv=False, minmax=True)
                attrs['NORMAL'] = self.accessor(nrm, 'VEC3', bv=False)
                if uv is not None:
                    attrs['TEXCOORD_0'] = self.accessor(uv, 'VEC2', bv=False)
                ind = self.accessor(idx, 'SCALAR', bv=False, ctype=5125)
                out.append({'attributes': attrs, 'indices': ind, 'material': mat, 'mode': 4,
                            'extensions': {'KHR_draco_mesh_compression': {
                                'bufferView': bv, 'attributes': ids}}})
            else:
                attrs = {'POSITION': self.accessor(pos, 'VEC3', minmax=True),
                         'NORMAL': self.accessor(nrm, 'VEC3')}
                if uv is not None:
                    attrs['TEXCOORD_0'] = self.accessor(uv, 'VEC2')
                ind = self.accessor(idx, 'SCALAR', ctype=5125)
                out.append({'attributes': attrs, 'indices': ind, 'material': mat, 'mode': 4})
        self.g['meshes'].append({'name': name, 'primitives': out})
        self.g['nodes'].append({'name': name, 'mesh': len(self.g['meshes']) - 1})
        self.g['nodes'][0]['children'].append(len(self.g['nodes']) - 1)

    def save(self, path):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.g['buffers'] = [{'byteLength': len(self.bin)}]
        js = json.dumps(self.g, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        while len(js) % 4:
            js += b' '
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, total))
            f.write(struct.pack('<II', len(js), 0x4E4F534A))
            f.write(js)
            f.write(struct.pack('<II', len(self.bin), 0x004E4942))
            f.write(self.bin)


# ---------------------------------------------------------------- разбор модели

def build(model_wrl, room_wrl, out_dir, title='', code='', draco=True, door_angle=DOOR_ANGLE,
          log=print):
    os.makedirs(out_dir, exist_ok=True)
    cat = load_catalog()
    log('Читаю', os.path.basename(model_wrl))
    sc = wrl_reader.read(model_wrl)
    nodes = sc.nodes
    wrl_dir = os.path.dirname(os.path.abspath(model_wrl))

    def children_of(uid):
        return [u for u, n in nodes.items() if n['parent'] == uid]

    # ---- 1. какие фигуры к какой детали
    parts = {}          # key -> dict(name, node_uid, shapes, kind, block_uid)
    inline_room = []    # помещение внутри модели (если нет отдельного файла стен)
    order = []
    for shp in sc.shapes:
        path = shp['path']
        if any(SKIP_NODE.match(n) for n, _ in path):
            continue
        # помещение, импортированное прямо в модель мебели: берём стены из отдельного файла
        if any(ROOM_NODE.match(n) for n, _ in path):
            if room_wrl and os.path.isfile(room_wrl):
                continue
            inline_room.append(shp)
            continue
        if not path:
            continue
        # корень «Model» не считаем
        p = [(n, u) for n, u in path if n != 'Model']
        if not p:
            continue
        kind = 'panel'
        cut = len(p)
        sub = ''
        if APPLIANCES.match(p[0][0]):
            cut = min(2, len(p))
            kind = 'appliance'
        else:
            for i, (n, u) in enumerate(p):
                # группа фурнитуры, внутри которой есть ящик/фасад/панели корпуса, — не деталь, идём глубже
                if HARDWARE.match(n) and not any(PANELISH.match(nn) or SLIDE.search(nn) or DOOR.match(nn)
                                                 for nn, _ in p[i + 1:]):
                    cut = i + 1
                    kind = 'hardware'
                    if any(PLATE.match(nn) for nn, _ in p[i + 1:]):
                        sub = 'plate'
                    break
        part_path = p[:cut]
        name_uid = part_path[-1][1]
        key = (name_uid, sub)
        if key not in parts:
            nm = part_path[-1][0]
            parts[key] = {'raw': nm, 'uid': name_uid, 'shapes': [], 'kind': kind, 'sub': sub,
                          'path': part_path}
            order.append(key)
        parts[key]['shapes'].append(shp)

    # ---- 2. материалы
    def mat_of(shp, part):
        if shp['tex']:
            stem = os.path.splitext(os.path.basename(shp['tex']))[0]
            return 'tex:' + stem
        c = shp['color']
        if c == (0.0, 1.0, 0.0):      # «зелёная» фурнитура Базиса
            raw = part['raw'].lower()
            return 'black' if ('chern' in raw or 'black' in raw) else 'steel'
        return 'col:' + hexcolor(c) + (':t%.2f' % shp['transp'] if shp['transp'] > 0 else '')

    mat_specs = {}
    tex_files = {}

    def spec_for(mkey, shp):
        if mkey in mat_specs:
            return mat_specs[mkey]
        if mkey.startswith('tex:'):
            stem = mkey[4:]
            path = find_texture(shp['tex'], wrl_dir)
            rec = cat.get(stem.lower())
            W, H = (rec[1], rec[2]) if rec else (1000.0, 1000.0)
            spec = {'color': (1, 1, 1), 'rough': 0.7, 'W': W, 'H': H, 'label': pretty_material(stem, cat)}
            if 'сталь' in stem.lower() or 'хром' in stem.lower() or 'steel' in stem.lower():
                spec.update(color=(0.78, 0.79, 0.8), metal=0.9, rough=0.3)
                spec.pop('W')
            elif path:
                spec['jpeg'], spec['px'] = jpeg_bytes(path)
                tex_files[stem] = path
            else:
                log('  нет текстуры', stem)
        elif mkey == 'steel':
            spec = {'color': (0.75, 0.76, 0.78), 'metal': 0.85, 'rough': 0.35, 'label': 'Металл'}
        elif mkey == 'black':
            spec = {'color': (0.06, 0.06, 0.06), 'rough': 0.6, 'label': 'Пластик чёрный'}
        else:
            c = shp['color']
            spec = {'color': c, 'rough': 0.55, 'label': ''}
            if shp['transp'] > 0:
                spec['opacity'] = round(1 - shp['transp'], 3)
        mat_specs[mkey] = spec
        return spec

    # ---- 3. блоки (именованные узлы, не являющиеся деталями)
    part_uids = {pp['uid'] for pp in parts.values()}
    used_uids = set()
    for pp in parts.values():
        for _, u in pp['path']:
            used_uids.add(u)
    block_ids = {}
    blocks = []
    for u in sorted(used_uids):
        n = nodes[u]
        if u in part_uids or n['name'] == 'Model':
            continue
        block_ids[u] = 'b%d' % (len(blocks) + 1)
        blocks.append({'id': block_ids[u], 'uid': u, 'name': rus(n['name']), 'raw': n['name']})
    for b in blocks:
        par = nodes[b['uid']]['parent']
        while par is not None and par not in block_ids:
            par = nodes[par]['parent']
        b['parent'] = block_ids.get(par)

    def block_of(pp):
        for n, u in reversed(pp['path'][:-1]):
            if u in block_ids:
                return block_ids[u]
        return None

    # ---- 4. геометрия деталей
    glb = GLB(draco=draco)
    out_parts = []
    world_min = np.full(3, np.inf)
    world_max = np.full(3, -np.inf)
    fur_min = np.full(3, np.inf)
    fur_max = np.full(3, -np.inf)
    part_bbox = {}
    pid_of_key = {}
    total_tris = 0
    for i, key in enumerate(order):
        pp = parts[key]
        pid = 'p%d' % (i + 1)
        pid_of_key[key] = pid
        M = nodes[pp['uid']]['M']
        Minv = np.linalg.inv(M)
        groups = {}
        for shp in pp['shapes']:
            mk = mat_of(shp, pp)
            T = shape_tris(shp)
            if len(T):
                groups.setdefault(mk, [shp, []])[1].append(T)
        allT = np.concatenate([np.concatenate(v[1]) for v in groups.values()]) if groups else None
        if allT is None or not len(allT):
            continue
        P = allT.reshape(-1, 3)
        bmin, bmax = P.min(0), P.max(0)
        L = (np.c_[P, np.ones(len(P))] @ Minv.T)[:, :3]
        lsize = L.max(0) - L.min(0)
        # направление волокна (в .wrl его нет): корпус — вдоль длинной стороны,
        # фасады — вертикально, как принято в мебели
        grain = int(np.argmax(lsize))
        is_facade = pp['kind'] == 'panel' and (pp['raw'].lower().startswith('fasad') or
                                               any(DOOR.match(n) for n, _ in pp['path'][:-1]))
        if is_facade:
            up_local = np.abs(Minv[:3, :3] @ np.array([0.0, 1.0, 0.0]))   # мировая вертикаль в осях детали
            thin = int(np.argmin(lsize))
            cand = int(np.argmax(up_local))
            if cand != thin and up_local[cand] > 0.7:
                grain = cand
        diag = float(np.linalg.norm(bmax - bmin))
        ntri = len(allT)
        cell = 0.0
        if pp['kind'] == 'hardware' and ntri > 1500:
            cell = max(0.8, diag / 120)
        elif pp['kind'] == 'appliance' and ntri > 20000:
            cell = max(1.5, diag / 450)
        elif ntri > 20000:
            cell = max(1.0, diag / 400)
        prims = []
        labels = []
        for mk, (shp0, Ts) in groups.items():
            T = np.concatenate(Ts)
            if cell:
                T = decimate(T, cell)
            spec = spec_for(mk, shp0)
            uvinfo = (spec['W'], spec['H'] * (spec['px'][1] / spec['px'][0]) * (spec['W'] / spec['H']), grain) \
                if spec.get('jpeg') else None
            if uvinfo:
                # картинка покрывает W мм по ширине, высота — по пропорциям картинки
                uvinfo = (spec['W'], spec['W'] * spec['px'][1] / spec['px'][0], grain)
            prim = build_primitive(T, Minv, uvinfo)
            if prim is None:
                continue
            total_tris += len(prim[3]) // 3
            mi = glb.material(mk, spec)
            prims.append(prim + (mi,))
            if spec.get('label'):
                labels.append(spec['label'])
        if not prims:
            continue
        glb.mesh(pid, prims)
        world_min = np.minimum(world_min, bmin)
        world_max = np.maximum(world_max, bmax)
        if pp['kind'] != 'appliance':
            fur_min = np.minimum(fur_min, bmin)
            fur_max = np.maximum(fur_max, bmax)
        part_bbox[pid] = (bmin, bmax)
        raw = pp['raw']
        name = rus(raw)
        if pp['sub'] == 'plate':
            name = 'Ответная планка петли'
        elif raw.lower().startswith('petlya'):
            name = 'Петля ' + ('Blum CLIP top BLUMOTION' if 'BLUMOTION' in raw else '').strip()
        name = re.sub(r'\s+(\d+(\.\d+)?)\s*×\s*(\d+(\.\d+)?)(\s*×\s*\d+(\.\d+)?)?$', '', name) or name
        size = sorted([int(round(v)) for v in lsize], reverse=True)
        kind = pp['kind']
        if kind == 'panel' and (raw.lower().startswith('fasad') or
                                any(DOOR.match(n) or n.lower().startswith('fasad') for n, _ in pp['path'][:-1])):
            kind = 'facade'
        out_parts.append({'id': pid, 'name': name, 'size': size, 'kind': kind,
                          'material': ', '.join(dict.fromkeys(labels)) or None,
                          'block': block_of(pp), '_key': key, '_path': pp['path']})
        if (i + 1) % 20 == 0:
            log('  деталей: %d' % (i + 1))

    # ---- 5. двери и выдвижные
    front_default = np.array([0.0, 0.0, 1.0])
    movers = []
    mover_of_uid = {}

    def parts_under(uid):
        res = []
        for p in out_parts:
            if any(u == uid for _, u in p['_path']):
                res.append(p)
        return res

    def bbox_of(plist):
        mn = np.full(3, np.inf)
        mx = np.full(3, -np.inf)
        for p in plist:
            a, b = part_bbox[p['id']]
            mn = np.minimum(mn, a)
            mx = np.maximum(mx, b)
        return mn, mx

    # выдвижные (сначала — чтобы двери внутри знали родителя)
    for u, n in sorted(nodes.items()):
        if SLIDE.search(n['name']) and u not in part_uids:
            plist = parts_under(u)
            if not plist:
                continue
            # вложенный выдвижной внутри другого — допускается
            mn, mx = bbox_of(plist)
            depth = float((mx - mn) @ np.abs(front_default))
            mid = 'm%d' % (len(movers) + 1)
            mover_of_uid[u] = mid
            # лицо ящика — передняя тонкая панель
            front = [p for p in plist if p['kind'] == 'panel'
                     and (part_bbox[p['id']][1] - part_bbox[p['id']][0]) @ np.abs(front_default) < 30]
            if front:
                max(front, key=lambda p: part_bbox[p['id']][1] @ front_default)['kind'] = 'facade'
            movers.append({'id': mid, 'type': 'slide', 'name': rus(n['name']), 'uid': u,
                           'dir': front_default.tolist(), 'dist': round(depth * SLIDE_PART),
                           'parts': [p['id'] for p in plist]})

    def door_axis(u, n):
        plist = parts_under(u)
        fac = [p for p in plist if p['kind'] in ('facade', 'panel')]
        if not fac:
            return None
        fac.sort(key=lambda p: -np.prod(np.maximum(part_bbox[p['id']][1] - part_bbox[p['id']][0], 1)))
        fmin, fmax = part_bbox[fac[0]['id']]
        ext = fmax - fmin
        nrm = int(np.argmin(ext))
        fc = (fmin + fmax) / 2
        # где «перед»: от центра блока-родителя к фасаду
        par = n['parent']
        front = front_default.copy()
        if par is not None:
            sib = parts_under(par)
            sib = [p for p in sib if p not in plist]
            if sib:
                bmn, bmx = bbox_of(sib)
                bc = (bmn + bmx) / 2
                d = fc[nrm] - bc[nrm]
                if abs(d) > 1:
                    front = np.zeros(3)
                    front[nrm] = 1.0 if d > 0 else -1.0
        if front[nrm] == 0:
            front = np.zeros(3)
            front[nrm] = 1.0
        hinges = [p for p in plist if p['name'].startswith('Петля')]
        in_plane = [k for k in range(3) if k != nrm]
        if len(hinges) >= 1:
            hmn, hmx = bbox_of(hinges)
            hext = hmx - hmn
            line = in_plane[int(np.argmax([hext[k] for k in in_plane]))]
            side = [k for k in in_plane if k != line][0]
            hmean = (hmn[side] + hmx[side]) / 2
            edge = fmax[side] if hmean > fc[side] else fmin[side]
            how = 'петли'
        else:
            up = np.array([0.0, 1.0, 0.0])
            right = np.cross(up, front)
            line = 1 if nrm != 1 else 2
            side = [k for k in in_plane if k != line][0]
            raw = n['name'].lower()
            sgn = right[side] if right[side] != 0 else 1.0
            if 'lev' in raw:
                sgn = -sgn
            edge = fmax[side] if sgn > 0 else fmin[side]
            how = 'край фасада'
        back = fmin[nrm] if front[nrm] > 0 else fmax[nrm]
        a = np.zeros(3)
        b = np.zeros(3)
        a[side] = b[side] = edge
        a[nrm] = b[nrm] = back
        a[line] = fmin[line]
        b[line] = fmax[line]
        # направление: поворот на +угол вокруг a->b уводит свободный край вперёд
        axis = (b - a) / np.linalg.norm(b - a)
        r = fc - a
        r = r - axis * (r @ axis)
        if np.cross(axis, r) @ front < 0:
            a, b = b, a
        return plist, a, b, how

    for u, n in sorted(nodes.items()):
        if DOOR.match(n['name']) and u not in part_uids:
            res = door_axis(u, n)
            if not res:
                continue
            plist, a, b, how = res
            par = n['parent']
            parent_mover = None
            while par is not None:
                if par in mover_of_uid:
                    parent_mover = mover_of_uid[par]
                    break
                par = nodes[par]['parent']
            mid = 'm%d' % (len(movers) + 1)
            movers.append({'id': mid, 'type': 'door', 'name': rus(n['name']), 'uid': u,
                           'a': [round(float(x), 1) for x in a], 'b': [round(float(x), 1) for x in b],
                           'angle': door_angle, 'by': how,
                           'parts': [p['id'] for p in plist if not (p['kind'] == 'hardware' and
                                                                    p['name'].startswith('Ответная'))],
                           'parent': parent_mover})
    # у выдвижного: детали, принадлежащие дверям внутри, двигаются вместе с дверью
    for m in movers:
        if m['type'] == 'slide':
            m.setdefault('parent', None)
            par = nodes[m['uid']]['parent']
            while par is not None:
                if par in mover_of_uid and mover_of_uid[par] != m['id']:
                    m['parent'] = mover_of_uid[par]
                    break
                par = nodes[par]['parent']
            inner = set()
            for d in movers:
                if d['type'] == 'door' and d.get('parent') == m['id']:
                    inner |= set(d['parts'])
            m['parts'] = [p for p in m['parts'] if p not in inner]
    for m in movers:
        m.pop('uid', None)

    # ---- 6. помещение
    room_parts = []
    room_shapes, names = [], []
    if room_wrl and os.path.isfile(room_wrl):
        log('Читаю помещение', os.path.basename(room_wrl))
        room_shapes = wrl_reader.read(room_wrl).shapes
        names = room_names(room_wrl)
    elif inline_room:
        log('Помещение взято из модели')
        room_shapes = inline_room
    if room_shapes:
        for j, shp in enumerate(room_shapes):
            T = shape_tris(shp)
            if not len(T):
                continue
            ext = T.reshape(-1, 3).max(0) - T.reshape(-1, 3).min(0)
            big = sorted(ext)
            is_wall = shp['transp'] > 0.3 or (big[0] < 30 and big[1] > 900 and big[2] > 900)
            mk = 'room_wall' if is_wall else 'room:' + hexcolor(shp['color'])
            spec = {'color': shp['color'], 'rough': 0.9, 'label': ''}
            if is_wall:
                spec['opacity'] = 0.25          # 75 % прозрачности
            mi = glb.material(mk, spec)
            prim = build_primitive(T, np.eye(4), None, crease_deg=20)
            if prim is None:
                continue
            rid = 'r%d' % (j + 1)
            glb.mesh(rid, [prim + (mi,)])
            P = T.reshape(-1, 3)
            bmin, bmax = P.min(0), P.max(0)
            c = (bmin + bmax) / 2
            nm = 'Стена' if is_wall else 'Элемент помещения'
            if shp.get('path'):
                nm = short_room_name(rus(shp['path'][-1][0])) or nm
            if names:
                best = min(names, key=lambda q: float(np.sum((np.array(q[1]) - c) ** 2)))
                nm = short_room_name(best[0]) or nm
            world_min = np.minimum(world_min, bmin)
            world_max = np.maximum(world_max, bmax)
            room_parts.append({'id': rid, 'name': nm, 'kind': 'wall' if is_wall else 'room',
                               'size': sorted([int(round(v)) for v in (bmax - bmin)], reverse=True),
                               'min': [round(float(v), 1) for v in bmin], 'max': [round(float(v), 1) for v in bmax]})

    # ---- 7. точка «как в жизни»: вход = сторона комнаты без стены
    eye = eye_point(room_parts, fur_min, fur_max)

    glb_path = os.path.join(out_dir, 'model.glb')
    glb.save(glb_path)

    facade_mat = None
    cnt = {}
    for p in out_parts:
        if p['kind'] == 'facade' and p['material']:
            cnt[p['material']] = cnt.get(p['material'], 0) + 1
    if cnt:
        facade_mat = max(cnt, key=cnt.get)
    facade_key = None
    for mk, sp in mat_specs.items():
        if sp.get('label') == facade_mat and mk.startswith('tex:'):
            facade_key = mk

    for p in out_parts:
        p.pop('_key', None)
        p.pop('_path', None)
    data = {
        'schema': 'bvs-viewer/1',
        'title': title,
        'code': code,
        'units': 'mm', 'up': 'Y',
        'bbox': {'min': [round(float(v), 1) for v in fur_min], 'max': [round(float(v), 1) for v in fur_max]},
        'sceneBox': {'min': [round(float(v), 1) for v in world_min], 'max': [round(float(v), 1) for v in world_max]},
        'parts': out_parts,
        'blocks': [{k: v for k, v in b.items() if k in ('id', 'name', 'parent')} for b in blocks],
        'movers': movers,
        'room': room_parts,
        'eye': eye,
        'materials': {mk: {'name': sp.get('label') or mk, 'texture': os.path.basename(tex_files.get(mk[4:], '')) or None}
                      for mk, sp in mat_specs.items()},
        'facade': {'material': facade_key, 'options': []},
    }
    with open(os.path.join(out_dir, 'model.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log('Готово: деталей %d, дверей %d, выдвижных %d, треугольников %d, GLB %.1f МБ' % (
        len(out_parts), sum(m['type'] == 'door' for m in movers), sum(m['type'] == 'slide' for m in movers),
        total_tris, os.path.getsize(glb_path) / 1e6))
    return data, tex_files


def room_names(room_wrl):
    """Имена элементов помещения из «… — импорт помещения с именами.js» (если есть рядом)."""
    d = os.path.dirname(room_wrl)
    for js in glob.glob(os.path.join(d, '*импорт помещения*.js')):
        raw = open(js, 'rb').read()
        for enc in ('utf-8', 'cp1251'):
            try:
                txt = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        m = re.search(r'var P = (\[.*?\]);', txt, re.S)
        if m:
            try:
                return [(q['n'], q['c']) for q in json.loads(m.group(1))]
            except Exception:
                pass
    return []


def short_room_name(n):
    n = re.split(r'[\d(,;]', n)[0].strip(' —-')
    return n[:40]


def eye_point(room_parts, fmin, fmax):
    """Точка «как в жизни»: глаза на 1,6 м, в проёме входа.

    Вход = самый широкий разрыв (>= 600 мм) в измеренной стене; если разрывов нет —
    сторона комнаты без стены (обычно «за спиной» при замере).
    """
    fc = (fmin + fmax) / 2
    walls = [r for r in room_parts if r['kind'] == 'wall']
    target = np.array([fc[0], min(1250.0, fc[1]), fc[2]])
    if not walls:
        pos = np.array([fc[0], 1600.0, fmax[2] + 2200])
        return {'pos': [round(float(v)) for v in pos], 'target': [round(float(v)) for v in target]}
    rmin = np.min([r['min'] for r in walls], axis=0)
    rmax = np.max([r['max'] for r in walls], axis=0)
    # стороны: (ось нормали, 0/1 = min/max) -> список отрезков стен вдоль другой оси
    segs = {('x', 0): [], ('x', 1): [], ('z', 0): [], ('z', 1): []}
    for r in walls:
        mn, mx = np.array(r['min']), np.array(r['max'])
        ext = mx - mn
        if ext[0] < 30:
            s = ('x', 0) if abs(mn[0] - rmin[0]) < abs(mn[0] - rmax[0]) else ('x', 1)
            segs[s].append((mn[2], mx[2]))
        elif ext[2] < 30:
            s = ('z', 0) if abs(mn[2] - rmin[2]) < abs(mn[2] - rmax[2]) else ('z', 1)
            segs[s].append((mn[0], mx[0]))
    best = None
    for s, lst in segs.items():
        if s == ('z', 0):
            continue                      # за спиной мебели (у задней стены) не встаём
        along = 2 if s[0] == 'x' else 0
        lo, hi = rmin[along], rmax[along]
        if not lst:
            gap = (hi - lo, (lo + hi) / 2, False)
        else:
            lst.sort()
            gaps = []
            cur = lo
            for a, b in lst:
                if a - cur > 0:
                    gaps.append((a - cur, (a + cur) / 2))
                cur = max(cur, b)
            if hi - cur > 0:
                gaps.append((hi - cur, (hi + cur) / 2))
            if not gaps:
                continue
            g = max(gaps)
            gap = (g[0], g[1], True)
        # боковой проём годится, только если он перед мебелью
        if s[0] == 'x' and gap[1] < fmax[2]:
            continue
        # приоритет: настоящий проём в стене шириной от 600 мм
        score = (gap[2] and gap[0] >= 600, gap[0])
        if best is None or score > best[0]:
            best = (score, s, gap)
    if best is None:
        best = (None, ('z', 1), (rmax[0] - rmin[0], fc[0], False))
    _, s, gap = best
    ax = 0 if s[0] == 'x' else 2
    along = 2 if ax == 0 else 0
    pos = np.zeros(3)
    pos[1] = 1600.0
    pos[along] = gap[1]
    edge = rmax[ax] if s[1] == 1 else rmin[ax]
    pos[ax] = edge + (550 if s[1] == 1 else -550)      # стоим на пороге, чуть снаружи
    if s == ('z', 1):
        pos[2] = max(pos[2], fmax[2] + 2000)          # не ближе 2 м к фасадам
        pos[0] = fc[0]
    return {'pos': [round(float(v)) for v in pos], 'target': [round(float(v)) for v in target]}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('model')
    ap.add_argument('--room')
    ap.add_argument('--out', required=True)
    ap.add_argument('--title', default='')
    ap.add_argument('--code', default='')
    ap.add_argument('--no-draco', action='store_true')
    a = ap.parse_args()
    build(a.model, a.room, a.out, a.title, a.code, draco=not a.no_draco)
