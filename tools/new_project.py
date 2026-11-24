# -*- coding: utf-8 -*-
"""Пошаговое создание ссылки для клиента (запускается двойным щелчком по «Сделать ссылку для клиента.bat»)."""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def ask(text, default=''):
    v = input(text + (' [%s]' % default if default else '') + ': ').strip().strip('"').strip("'").strip('&').strip()
    return v or default


def next_code():
    nums = [int(m.group(1)) for d in os.listdir(REPO) for m in [re.match(r'^p(\d+)-', d)] if m]
    return 'p%d' % (max(nums) + 1 if nums else 1)


def main():
    print('=' * 60)
    print('  BVSspace — новая 3D-ссылка для клиента')
    print('=' * 60)
    print('\n1) Перетащите мышкой файл .wrl мебели из Базиса в это окно и нажмите Enter.')
    model = ask('   Файл мебели')
    while not (model.lower().endswith('.wrl') and os.path.isfile(model)):
        print('   Это не файл .wrl. Попробуйте ещё раз.')
        model = ask('   Файл мебели')

    import make_viewer
    walls = make_viewer.find_walls(model)
    if walls:
        print('\n   Стены по замеру найдены: ' + os.path.basename(walls))
        if ask('   Использовать их? (Enter — да, н — нет)').lower().startswith('н'):
            walls = ''
    if not walls:
        print('\n   Если есть «… — стены по замеру.wrl», перетащите его сюда. Нет — просто Enter.')
        w = ask('   Файл стен')
        walls = w if w.lower().endswith('.wrl') and os.path.isfile(w) else ''

    print('\n2) Название изделия — его увидит клиент. Без имени и адреса! Например: Кухня, Шкаф в прихожую.')
    title = ''
    while not title:
        title = ask('   Название')

    code = next_code()
    print('\n3) Код проекта. Для нового проекта нажмите Enter (%s).' % code)
    print('   Если обновляете старый проект — введите его код, например p15.')
    code = ask('   Код', code).lower()

    print('\n4) Варианты цвета фасадов для клиента — коды декоров через запятую, например: H1145,U702,W1100')
    print('   Не нужно — просто Enter.')
    colors = ask('   Цвета')

    folder = '%s-%s' % (code, make_viewer.slugify(title))
    print('\nСобираю проект «%s» (%s)… это займёт до минуты.\n' % (title, folder))
    args = [sys.executable, os.path.join(HERE, 'make_viewer.py'), model, '--code', code, '--title', title, '--push']
    if walls:
        args += ['--walls', walls]
    if colors:
        args += ['--colors', colors]
    r = subprocess.run(args, cwd=REPO)
    if r.returncode:
        print('\nЧто-то пошло не так — пришлите скриншот этого окна Claude.')
        return
    link = 'https://vbsspace.github.io/3d/%s/' % folder
    subprocess.run(['powershell', '-NoProfile', '-Command', 'Set-Clipboard -Value "%s"' % link], capture_output=True)
    print('\n' + '=' * 60)
    print('  ГОТОВО. Ссылка для клиента (уже скопирована — просто вставьте в чат):')
    print('  ' + link)
    print('  Откроется через 1–2 минуты.')
    print('=' * 60)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    input('\nНажмите Enter, чтобы закрыть окно…')
