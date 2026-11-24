# -*- coding: utf-8 -*-
"""Обновить функцию замечаний в Yandex Cloud.

  python tools/deploy_notes.py            — выложить новый код backend/index.py, настройки не трогать
  python tools/deploy_notes.py --secrets  — подключить Telegram-бота: токен берётся из буфера обмена,
                                            код мастера создаётся сам и приходит вам в Telegram

Нужен установленный и настроенный yc (yc init).
"""
import argparse
import re
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

FUNCTION = 'bvs-notes'
SERVICE_ACCOUNT = 'notes-fn'
BASE_ENV = {'BUCKET': 'bvsspace-notes', 'SITE_URL': 'https://vbsspace.github.io/3d/',
            'ALLOWED_ORIGINS': 'https://vbsspace.github.io'}
HERE = os.path.dirname(os.path.abspath(__file__))
YC = shutil.which('yc') or os.path.expanduser(r'~\yandex-cloud\bin\yc.exe')


def yc(*args):
    r = subprocess.run([YC, *args, '--format', 'json'], capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        sys.exit('Ошибка yc: ' + (r.stderr or r.stdout).strip().splitlines()[-1])
    return json.loads(r.stdout) if r.stdout.strip() else {}


def current_env():
    try:
        v = yc('serverless', 'function', 'version', 'get-by-tag', '--function-name', FUNCTION, '--tag', '$latest')
        return v.get('environment') or {}
    except SystemExit:
        return {}


def tg(token, method, **params):
    url = 'https://api.telegram.org/bot%s/%s' % (token, method)
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=15) as r:
        return json.load(r)


def clipboard():
    r = subprocess.run(['powershell', '-NoProfile', '-Command', 'Get-Clipboard'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return (r.stdout or '').strip()


def clear_clipboard():
    subprocess.run(['powershell', '-NoProfile', '-Command', "Set-Clipboard -Value ' '"], capture_output=True)


def ask_secrets(env):
    print('\n1) В Telegram, в чате с @BotFather, найдите последний токен (новый можно получить: /revoke → @bvsspace_notes_bot).')
    print('2) Выделите токен мышкой и нажмите Ctrl+C (скопировать).')
    print('3) Вернитесь сюда и нажмите Enter. Вставлять ничего не нужно — токен возьмётся из буфера обмена.')
    token = None
    for _ in range(5):
        input('\nСкопировали токен? Нажмите Enter… ')
        t = clipboard()
        if not re.fullmatch(r'\d{6,}:[A-Za-z0-9_-]{30,}', t):
            print('В буфере обмена не токен. Выделите в Telegram всю строку вида 123456:ABC… и нажмите Ctrl+C.')
            continue
        try:
            me = tg(t, 'getMe')['result']
        except Exception:
            print('Telegram не принял этот токен — возможно, он уже заменён. Скопируйте самый последний.')
            continue
        token = t
        break
    if not token:
        sys.exit('Не получилось. Запустите скрипт ещё раз.')
    clear_clipboard()
    print('Токен принят.')
    chats = {}
    for attempt in range(60):
        for u in tg(token, 'getUpdates').get('result', []):
            c = (u.get('message') or {}).get('chat') or {}
            if c.get('type') == 'private':
                chats[c['id']] = c.get('username') or c.get('first_name') or ''
        if chats:
            break
        if attempt == 0:
            print('\nТеперь откройте в Telegram https://t.me/%s и нажмите «Старт» (или напишите боту «привет»).'
                  % me['username'])
            print('Жду…')
        time.sleep(3)
    if not chats:
        sys.exit('Не дождался сообщения боту. Нажмите у @%s «Старт» и запустите скрипт ещё раз.' % me['username'])
    chat = next((cid for cid, u in chats.items() if u.lower() == 'bvs04'), next(iter(chats)))
    tg(token, 'sendMessage', chat_id=chat,
       text='✅ Бот подключён. Сюда будут приходить новые замечания клиентов с 3D-моделей BVSspace.')
    env['TG_BOT_TOKEN'] = token
    env['TG_CHAT_ID'] = str(chat)
    print('Бот @%s подключён — в Telegram пришло проверочное сообщение.' % me['username'])
    code = env.get('ADMIN_CODE') or secrets.token_urlsafe(12).replace('-', 'x').replace('_', 'z')
    env['ADMIN_CODE'] = code
    return code


GH_REPO = 'VBSspace/3d'
PAT_URL = ('https://github.com/settings/personal-access-tokens/new?name=bvs-notes'
           '&description=BVSspace%3A+%D1%83%D0%B2%D0%B5%D0%B4%D0%BE%D0%BC%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F'
           '&target_name=VBSspace&expires_in=none&contents=write')


def gh_api(token, path):
    req = urllib.request.Request('https://api.github.com' + path)
    req.add_header('Authorization', 'Bearer ' + token)
    req.add_header('Accept', 'application/vnd.github+json')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def ask_github(env):
    """Telegram недоступен из Yandex Cloud — уведомления идут через GitHub Actions."""
    if not env.get('TG_BOT_TOKEN') or not env.get('TG_CHAT_ID'):
        sys.exit('Сначала подключите бота: python tools/deploy_notes.py --secrets')
    print('\nНужен ключ GitHub, которым функция будет запускать отправку уведомления.')
    print('1) Сейчас откроется страница GitHub «New fine-grained personal access token».')
    print('2) В «Repository access» выберите «Only select repositories» → 3d.')
    print('3) В «Permissions» → «Contents» должно стоять «Read and write» (обычно уже стоит).')
    print('4) Внизу нажмите «Generate token», затем скопируйте ключ (github_pat_…) кнопкой-копированием.')
    input('\nНажмите Enter, чтобы открыть страницу… ')
    import webbrowser
    webbrowser.open(PAT_URL)
    pat = None
    for _ in range(5):
        input('\nСкопировали ключ github_pat_…? Нажмите Enter… ')
        t = clipboard()
        if not re.fullmatch(r'github_pat_[A-Za-z0-9_]{40,}', t):
            print('В буфере обмена не ключ GitHub. Скопируйте строку, которая начинается с github_pat_.')
            continue
        try:
            gh_api(t, '/repos/' + GH_REPO)
        except Exception:
            print('GitHub не принял ключ — проверьте, что выбран репозиторий 3d.')
            continue
        pat = t
        break
    if not pat:
        sys.exit('Не получилось. Запустите ещё раз: python tools/deploy_notes.py --github')
    clear_clipboard()
    # токен бота и chat_id — в секреты репозитория (их видит только GitHub Actions)
    for name in ('TG_BOT_TOKEN', 'TG_CHAT_ID'):
        r = subprocess.run(['gh', 'secret', 'set', name, '--repo', GH_REPO], input=env[name],
                           capture_output=True, text=True, encoding='utf-8')
        if r.returncode:
            sys.exit('Не удалось сохранить секрет %s в GitHub: %s' % (name, (r.stderr or '').strip()[:200]))
    env['GH_DISPATCH_TOKEN'] = pat
    env['GH_REPO'] = GH_REPO
    print('Ключ принят, данные бота сохранены в секретах GitHub.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--secrets', action='store_true', help='ввести токен бота и код мастера')
    ap.add_argument('--github', action='store_true', help='уведомления через GitHub Actions (ключ github_pat_)')
    a = ap.parse_args()
    env = {**BASE_ENV, **current_env()}
    code = ask_secrets(env) if a.secrets else None
    if a.github:
        ask_github(env)
    sa = yc('iam', 'service-account', 'get', SERVICE_ACCOUNT)['id']
    src = tempfile.mkdtemp()
    shutil.copy(os.path.join(os.path.dirname(HERE), 'backend', 'index.py'), src)
    print('\nВыкладываю функцию…')
    yc('serverless', 'function', 'version', 'create', '--function-name', FUNCTION,
       '--runtime', 'python312', '--entrypoint', 'index.handler', '--memory', '128m',
       '--execution-timeout', '10s', '--source-path', src, '--service-account-id', sa,
       '--environment', ','.join('%s=%s' % kv for kv in env.items()))
    shutil.rmtree(src, ignore_errors=True)
    print('Готово.')
    if a.github:
        body = json.dumps({'event_type': 'note', 'client_payload': {
            'text': '✅ Уведомления о замечаниях подключены (через GitHub). Сюда будут приходить замечания клиентов.'}}).encode()
        req = urllib.request.Request('https://api.github.com/repos/%s/dispatches' % GH_REPO, data=body, method='POST')
        req.add_header('Authorization', 'Bearer ' + env['GH_DISPATCH_TOKEN'])
        req.add_header('Accept', 'application/vnd.github+json')
        try:
            urllib.request.urlopen(req, timeout=15).close()
            print('Проверьте Telegram: через 20–40 секунд придёт тестовое сообщение «✅ Уведомления… подключены».')
        except Exception as e:
            print('Не удалось запустить проверку через GitHub:', e)
    if code:
        link = 'https://vbsspace.github.io/3d/p15-postirochnaya/#admin=' + code
        try:
            tg(env['TG_BOT_TOKEN'], 'sendMessage', chat_id=env['TG_CHAT_ID'],
               text='🔑 Ваша ссылка мастера (никому не пересылайте). Откройте её один раз на телефоне и '
                    'на компьютере — там появятся кнопки «Ответить» и «Решено»:\n' + link)
            print('\nСсылка мастера отправлена вам в Telegram от бота. Закрепите это сообщение.')
        except Exception:
            print('\nВаша ссылка мастера (никому не пересылайте):\n  ' + link)


if __name__ == '__main__':
    main()
