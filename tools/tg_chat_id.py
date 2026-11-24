# -*- coding: utf-8 -*-
"""Узнать свой chat_id для уведомлений.

1. Создайте бота у @BotFather, получите токен.
2. Откройте своего бота в Telegram (с аккаунта @BVS04) и нажмите «Старт».
3. python tools/tg_chat_id.py ТОКЕН   -> напечатает chat_id. Токен никуда не сохраняется.
"""
import json
import sys
import urllib.request

if len(sys.argv) < 2:
    sys.exit(__doc__)
with urllib.request.urlopen('https://api.telegram.org/bot%s/getUpdates' % sys.argv[1], timeout=15) as r:
    data = json.load(r)
seen = set()
for u in data.get('result', []):
    chat = (u.get('message') or u.get('my_chat_member') or {}).get('chat') or {}
    if chat.get('id') and chat['id'] not in seen:
        seen.add(chat['id'])
        print('chat_id = %s   (@%s %s)' % (chat['id'], chat.get('username', ''), chat.get('first_name', '')))
if not seen:
    print('Сообщений нет. Откройте бота в Telegram, нажмите «Старт» и запустите ещё раз.')
