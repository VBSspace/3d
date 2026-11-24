# -*- coding: utf-8 -*-
"""Ссылка для клиента в одно действие.

Перетащите .wrl мебели на ярлык «3D-ссылка для клиента» (или запустите ярлык и перетащите файл в окно).
Всё остальное определяется само: название (из имени файла), код проекта (новый или тот же, если проект
уже был), стены по замеру (рядом с файлом), варианты цвета фасадов. Ссылка копируется в буфер обмена
и открывается в браузере, когда сайт обновится.
"""
import json
import os
import re
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import make_viewer  # noqa: E402

SITE = 'https://vbsspace.github.io/3d/'


def clean_path(v):
    return v.strip().strip('&').strip().strip('"').strip("'").strip()


def title_from_file(path):
    t = os.path.splitext(os.path.basename(path))[0]
    t = re.sub(r'[_]+', ' ', t)
    t = re.split(r'\s+—\s+(мебель|модель)|,\s*ред\.', t, flags=re.I)[0]
    t = re.sub(r'\s+', ' ', t).strip(' -—')
    return (t[:1].upper() + t[1:]) if t else ''


def existing_projects():
    """{название (в нижнем регистре): (код, папка)} по уже выложенным проектам."""
    res = {}
    for d in os.listdir(REPO):
        f = os.path.join(REPO, d, 'model.json')
        m = re.match(r'^(p\d+)-', d)
        if m and os.path.isfile(f):
            try:
                t = json.load(open(f, encoding='utf-8')).get('title', '')
            except Exception:
                continue
            res[t.strip().lower()] = (m.group(1), d)
    return res


def next_code():
    nums = [int(m.group(1)) for d in os.listdir(REPO) for m in [re.match(r'^p(\d+)-', d)] if m]
    return 'p%d' % (max(nums) + 1 if nums else 1)


def client_words(path):
    """Слова из папок «Проекты\\<Клиент …>\\…» — чтобы имя клиента не попало в ссылку."""
    parts = os.path.normpath(path).split(os.sep)
    words = set()
    for i, p in enumerate(parts):
        if p.lower() == 'проекты' and i + 1 < len(parts) - 1:
            words |= {w.lower() for w in re.findall(r'[А-ЯЁA-Z][а-яёa-z]{2,}', parts[i + 1])}
    return words


def wait_pages(sha, limit=240):
    """Ждём, пока GitHub Pages опубликует коммит (нужен gh)."""
    t0 = time.time()
    while time.time() - t0 < limit:
        r = subprocess.run(['gh', 'run', 'list', '-R', 'VBSspace/3d', '--workflow', 'pages-build-deployment',
                            '--limit', '1', '--json', 'status,conclusion,headSha'],
                           capture_output=True, text=True, encoding='utf-8')
        try:
            run = json.loads(r.stdout)[0]
            if run['headSha'].startswith(sha) and run['status'] == 'completed':
                return run['conclusion'] == 'success'
        except Exception:
            pass
        print('.', end='', flush=True)
        time.sleep(6)
    return False


def main():
    print('=' * 62)
    print('  BVSspace — 3D-ссылка для клиента')
    print('=' * 62)
    model = clean_path(sys.argv[1]) if len(sys.argv) > 1 else ''
    while not (model.lower().endswith('.wrl') and os.path.isfile(model)):
        if model:
            print('  Это не файл .wrl.')
        print('\n  Перетащите файл .wrl мебели из Базиса в это окно и нажмите Enter.')
        model = clean_path(input('  > '))

    walls = make_viewer.find_walls(model) or ''
    title = title_from_file(model)
    projects = existing_projects()

    # имя клиента в название не пускаем
    bad = client_words(model)
    if any(w in title.lower() for w in bad):
        print('\n  В названии файла похоже есть имя клиента — в ссылку оно не попадёт.')
        title = ''

    print('\n  Файл:     ' + os.path.basename(model))
    print('  Стены:    ' + (os.path.basename(walls) if walls else 'нет (будет без комнаты)'))
    if title:
        print('  Название: ' + title + '   (так увидит клиент)')
        t = input('\n  Enter — создать ссылку. Или напишите другое название: ').strip()
        title = t or title
    while not title:
        title = input('\n  Название изделия (например: Кухня, Шкаф в прихожую): ').strip()

    found = projects.get(title.lower())
    code = found[0] if found else next_code()
    print('\n  ' + ('Обновляю проект %s — ссылка останется прежней.' % code if found else 'Новый проект %s.' % code))
    print('  Собираю модель и выкладываю… (до минуты)\n')

    args = [sys.executable, os.path.join(HERE, 'make_viewer.py'), model, '--code', code, '--title', title, '--push']
    if found:
        args += ['--slug', found[1].split('-', 1)[1]]
    if walls:
        args += ['--walls', walls]
    r = subprocess.run(args, cwd=REPO)
    if r.returncode:
        print('\n  Не получилось — пришлите скриншот этого окна Claude.')
        return
    folder = found[1] if found else '%s-%s' % (code, make_viewer.slugify(title))
    link = SITE + folder + '/'
    subprocess.run(['powershell', '-NoProfile', '-Command', "Set-Clipboard -Value '%s'" % link], capture_output=True)

    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip()
    print('\n  Жду, пока сайт обновится', end='', flush=True)
    ok = wait_pages(sha[:7]) if sha else False
    print()
    print('\n' + '=' * 62)
    print('  ГОТОВО. Ссылка уже скопирована — вставьте её клиенту:')
    print('  ' + link)
    if ok:
        print('  Сайт обновлён, открываю ссылку для проверки.')
        webbrowser.open(link + '?v=' + sha[:7])
    else:
        print('  Сайт обновится через 1–2 минуты.')
    print('=' * 62)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    except Exception:
        import traceback
        traceback.print_exc()
        print('\n  Что-то пошло не так — пришлите скриншот этого окна Claude.')
