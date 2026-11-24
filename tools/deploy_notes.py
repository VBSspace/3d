# -*- coding: utf-8 -*-
"""Обновить функцию замечаний в Yandex Cloud.

  python tools/deploy_notes.py            — выложить новый код backend/index.py, настройки не трогать
  python tools/deploy_notes.py --secrets  — ввести токен Telegram-бота и код мастера
                                            (вводятся скрыто, на экран и в файлы не попадают)

Нужен установленный и настроенный yc (yc init).
"""
import argparse
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
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


def ask_secrets(env):
    print('\nТокен бота: откройте чат с @BotFather, скопируйте последний токен и вставьте сюда.')
    print('(при вставке символы не отображаются — это нормально, просто нажмите Enter)')
    token = getpass.getpass('Токен бота: ').strip()
    if token:
        try:
            me = tg(token, 'getMe')['result']
        except Exception:
            sys.exit('Telegram не принял токен. Проверьте, что скопировали его целиком.')
        chats = {}
        for u in tg(token, 'getUpdates').get('result', []):
            c = (u.get('message') or {}).get('chat') or {}
            if c.get('type') == 'private':
                chats[c['id']] = c.get('username') or c.get('first_name') or ''
        if not chats:
            sys.exit('Бот @%s пока никто не запускал. Откройте его в Telegram, нажмите «Старт» и запустите скрипт ещё раз.'
                     % me['username'])
        chat = next((cid for cid, u in chats.items() if u.lower() == 'bvs04'), next(iter(chats)))
        tg(token, 'sendMessage', chat_id=chat,
           text='✅ Бот подключён. Сюда будут приходить новые замечания клиентов с 3D-моделей BVSspace.')
        env['TG_BOT_TOKEN'] = token
        env['TG_CHAT_ID'] = str(chat)
        print('Бот @%s подключён — проверьте Telegram, там должно быть сообщение.' % me['username'])
    print('\nКод мастера — по нему вы отвечаете на замечания и отмечаете «Решено».')
    code = getpass.getpass('Придумайте код (или просто Enter — придумаю сам): ').strip()
    if not code:
        code = secrets.token_urlsafe(12)
    elif len(code) < 8 or not all(ch.isascii() and (ch.isalnum() or ch in '-_') for ch in code):
        sys.exit('Код: от 8 символов, только латинские буквы, цифры, «-» и «_».')
    env['ADMIN_CODE'] = code
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--secrets', action='store_true', help='ввести токен бота и код мастера')
    a = ap.parse_args()
    env = {**BASE_ENV, **current_env()}
    code = ask_secrets(env) if a.secrets else None
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
    if code:
        print('\nВаша ссылка мастера (сохраните её в Избранное Telegram, никому не пересылайте):')
        print('  https://vbsspace.github.io/3d/p15-postirochnaya/#admin=' + code)
        print('Достаточно открыть её один раз на каждом своём устройстве — дальше режим мастера запомнится.')


if __name__ == '__main__':
    main()
