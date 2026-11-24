# -*- coding: utf-8 -*-
"""Новый 3D-проект одной командой: .wrl мебели (+ .wrl стен) -> готовая папка в репозитории.

Пример:
  python tools/make_viewer.py "C:/…/постирочная.wrl" --code p15 --title "Постирочная" ^
         --walls "C:/…/Постирочная — стены по замеру.wrl" --colors H1145,H3309,U702,W1100 --push

Создаёт папку <код>-<название латиницей>/ (например p15-postirochnaya) с файлами
model.glb, model.json, index.html и textures/ (образцы цветов фасадов).
Имя клиента и адрес в папку и ссылку не попадают — только код и название изделия.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import wrl2glb  # noqa: E402

SITE = 'https://vbsspace.github.io/3d/'
LAT = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
               ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't',
                'u', 'f', 'kh', 'ts', 'ch', 'sh', 'shch', '', 'y', '', 'e', 'yu', 'ya']))


def slugify(s):
    s = ''.join(LAT.get(c, c) for c in s.lower())
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:40] or 'proekt'


def find_walls(model):
    """Ищет «… — стены по замеру.wrl» рядом с моделью и во вложенных папках."""
    d = os.path.dirname(os.path.abspath(model))
    stem = os.path.splitext(os.path.basename(model))[0].lower()
    hits = glob.glob(os.path.join(d, '*стены по замеру*.wrl')) + glob.glob(os.path.join(d, '*', '*стены по замеру*.wrl'))
    for h in hits:
        if os.path.basename(os.path.dirname(h)).lower().startswith(stem[:6]) or os.path.basename(h).lower().startswith(stem[:6]):
            return h
    return hits[0] if len(hits) == 1 else None


def color_options(spec, out_dir, cat):
    """«H1145,U702,Графит=#3a3a3a» -> варианты для model.json; текстуры копируются в textures/."""
    from PIL import Image
    opts = []
    if not spec:
        return opts
    os.makedirs(os.path.join(out_dir, 'textures'), exist_ok=True)
    for item in [x.strip() for x in spec.split(',') if x.strip()]:
        if '=' in item:
            name, col = item.split('=', 1)
            opts.append({'name': name.strip(), 'color': col.strip()})
            continue
        code = item
        hits = glob.glob(os.path.join(wrl2glb.BAZIS_TEX, '**', code + '.jpg'), recursive=True)
        if not hits:
            print('  нет текстуры для', code, '— пропускаю')
            continue
        rec = cat.get(code.lower())
        m = re.search(r'«([^»]+)»', rec[0]) if rec else None
        name = '%s (%s)' % (m.group(1), code) if m else code
        im = Image.open(hits[0]).convert('RGB')
        s = min(1.0, 2048 / max(im.size))
        if s < 1:
            im = im.resize((int(im.size[0] * s), int(im.size[1] * s)), Image.LANCZOS)
        if max(im.size) < 64:
            im = im.resize((64, 64))
        dst = os.path.join(out_dir, 'textures', code + '.jpg')
        im.save(dst, 'JPEG', quality=88, optimize=True, progressive=True)
        opts.append({'name': name, 'texture': 'textures/%s.jpg' % code})
    return opts


# популярные декоры EGGER для автоподбора вариантов цвета
WOODS = ['H1145', 'H3309', 'H3131', 'H1176', 'H1180', 'H1344']
PLAINS = ['W1100', 'U702', 'U727', 'U999', 'U113']


def auto_colors(data):
    """Подбирает 3 варианта к декору фасадов: к дереву — другое дерево, белый и серый; к однотону — белый, дерево, тёмный."""
    key = data['facade'].get('material')
    if not key:
        # фасадов нет — берём самый частый декор деталей
        by_name = {v['name']: k for k, v in data['materials'].items() if k.startswith('tex:')}
        cnt = {}
        for p in data['parts']:
            for m in (p.get('material') or '').split(', '):
                if m in by_name:
                    cnt[by_name[m]] = cnt.get(by_name[m], 0) + 1
        key = max(cnt, key=cnt.get) if cnt else None
    if not key:
        return None, ''
    cur = key[4:].upper()
    if cur[:1] in ('H', 'K', 'F'):
        picks = [next(w for w in WOODS if w != cur), 'W1100', 'U702']
    else:
        picks = ['W1100' if cur != 'W1100' else 'U113', 'H1145', 'U999' if cur not in ('U999', 'U968') else 'U702']
    return key, ','.join(x for x in picks if x != cur)


def viewer_version():
    """Короткий отпечаток файлов просмотрщика — меняется при каждой правке, браузер берёт свежие файлы."""
    import hashlib
    h = hashlib.sha1()
    vdir = os.path.join(REPO, 'viewer')
    for f in sorted(os.listdir(vdir)):
        if f.endswith(('.js', '.css')):
            h.update(open(os.path.join(vdir, f), 'rb').read())
    return h.hexdigest()[:8]


def refresh_all_pages():
    """Перегенерировать index.html всех проектов (после правок просмотрщика)."""
    for d in sorted(os.listdir(REPO)):
        f = os.path.join(REPO, d, 'model.json')
        if os.path.isfile(f):
            title = json.load(open(f, encoding='utf-8')).get('title') or d
            write_index(os.path.join(REPO, d), title, d)
            print('обновлено:', d)


def write_index(out_dir, title, folder):
    with open(os.path.join(HERE, 'template.html'), encoding='utf-8') as f:
        html = f.read()
    url = SITE + folder + '/'
    # без снимка проекта — фирменная карточка BVSspace
    og = ('<meta property="og:image" content="%sviewer/og.jpg">\n'
          '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">') % SITE
    if os.path.exists(os.path.join(out_dir, 'preview.jpg')):
        og = ('<meta property="og:image" content="%spreview.jpg">\n'
              '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
              '<meta name="twitter:card" content="summary_large_image">') % url
    html = html.replace('{{TITLE}}', title).replace('{{URL}}', url).replace('{{OG_IMAGE}}', og).replace('{{V}}', viewer_version())
    with open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)
    return url


def main():
    ap = argparse.ArgumentParser(description='Новый 3D-проект для клиента')
    ap.add_argument('model', help='.wrl мебели из Базиса')
    ap.add_argument('--code', required=True, help='код проекта, например p16')
    ap.add_argument('--title', required=True, help='название изделия: «Кухня», «Шкаф в прихожую»')
    ap.add_argument('--walls', help='.wrl стен по замеру (по умолчанию ищется рядом)')
    ap.add_argument('--slug', help='латиница для ссылки (по умолчанию из названия)')
    ap.add_argument('--colors', default='auto', help='варианты цвета фасадов: auto (по умолчанию), none, или коды декоров через запятую (H1145,U702) / Имя=#цвет')
    ap.add_argument('--door-angle', type=float, default=wrl2glb.DOOR_ANGLE)
    ap.add_argument('--eye', help='точка «как в жизни» вручную: x,z в мм (координаты Базиса)')
    ap.add_argument('--push', action='store_true', help='сразу закоммитить и отправить на GitHub')
    a = ap.parse_args()

    code = a.code.lower().strip()
    if not re.match(r'^[a-z0-9]+$', code):
        sys.exit('Код проекта — только латиница и цифры, например p16')
    folder = '%s-%s' % (code, a.slug or slugify(a.title))
    out = os.path.join(REPO, folder)
    walls = a.walls or find_walls(a.model)
    print('Проект:', folder)
    print('Модель:', a.model)
    print('Стены: ', walls or '— нет')
    data, _ = wrl2glb.build(a.model, walls, out, a.title, code, door_angle=a.door_angle)

    cat = wrl2glb.load_catalog()
    colors = (a.colors or 'auto').strip()
    if colors.lower() == 'none':
        colors = ''
    elif colors.lower() == 'auto':
        key, colors = auto_colors(data)
        if key:
            data['facade']['material'] = key
            print('Цвета фасадов (автоматически):', colors)
    data['facade']['options'] = color_options(colors, out, cat)
    if a.eye:
        x, z = [float(v) for v in a.eye.split(',')]
        data['eye']['pos'] = [x, 1600, z]
    with open(os.path.join(out, 'model.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    url = write_index(out, a.title, folder)
    print('\nГотово. Ссылка для клиента (после публикации):\n  ' + url)
    print('Проверить у себя:  python tools/serve.py  ->  http://localhost:8000/%s/' % folder)
    if a.push:
        subprocess.check_call(['git', 'add', folder], cwd=REPO)
        if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=REPO).returncode:
            subprocess.check_call(['git', 'commit', '-q', '-m', '3D: %s (%s)' % (a.title, code)], cwd=REPO)
            subprocess.check_call(['git', 'push', '-q'], cwd=REPO)
            print('Опубликовано. GitHub Pages обновится через 1–2 минуты.')
        else:
            print('Модель не изменилась — публиковать нечего.')


if __name__ == '__main__':
    if sys.argv[1:] == ['--refresh-pages']:
        refresh_all_pages()
    else:
        main()
