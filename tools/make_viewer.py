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
        s = min(1.0, 1024 / max(im.size))
        if s < 1:
            im = im.resize((int(im.size[0] * s), int(im.size[1] * s)), Image.LANCZOS)
        if max(im.size) < 64:
            im = im.resize((64, 64))
        dst = os.path.join(out_dir, 'textures', code + '.jpg')
        im.save(dst, 'JPEG', quality=82, optimize=True, progressive=True)
        opts.append({'name': name, 'texture': 'textures/%s.jpg' % code})
    return opts


def write_index(out_dir, title, folder):
    with open(os.path.join(HERE, 'template.html'), encoding='utf-8') as f:
        html = f.read()
    url = SITE + folder + '/'
    og = ''
    if os.path.exists(os.path.join(out_dir, 'preview.jpg')):
        og = ('<meta property="og:image" content="%spreview.jpg">\n'
              '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
              '<meta name="twitter:card" content="summary_large_image">') % url
    html = html.replace('{{TITLE}}', title).replace('{{URL}}', url).replace('{{OG_IMAGE}}', og)
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
    ap.add_argument('--colors', help='варианты цвета фасадов: коды декоров через запятую (H1145,U702) или Имя=#цвет')
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
    data['facade']['options'] = color_options(a.colors, out, cat)
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
        subprocess.check_call(['git', 'commit', '-m', '3D: %s (%s)' % (a.title, code)], cwd=REPO)
        subprocess.check_call(['git', 'push'], cwd=REPO)
        print('Опубликовано. GitHub Pages обновится через 1–2 минуты.')


if __name__ == '__main__':
    main()
