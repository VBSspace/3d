# -*- coding: utf-8 -*-
"""Замечания на 3D-модели — Yandex Cloud Function (Python 3.12, только стандартная библиотека).

Хранение: Yandex Object Storage, один файл notes/<проект>.json на проект.
Доступ к бакету — через IAM-токен сервисного аккаунта функции (context.token),
поэтому статических ключей нет нигде.

Переменные окружения функции (задаются в консоли Yandex Cloud, НЕ в коде страницы):
  BUCKET           имя бакета Object Storage
  ADMIN_CODE       секретный код мастера (ссылка мастера: …/p15-xxx/#admin=КОД)
  TG_BOT_TOKEN     токен Telegram-бота (от @BotFather)
  TG_CHAT_ID       ваш chat_id (узнать: python tools/tg_chat_id.py ТОКЕН)
  SITE_URL         https://vbsspace.github.io/3d/
  ALLOWED_ORIGINS  https://vbsspace.github.io
"""
import datetime
import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_NOTES = 300
PROJECT_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')


def env(k, d=''):
    return os.environ.get(k, d)


# ---------------------------------------------------------------- хранилища

class S3Store:
    """Object Storage через IAM-токен функции."""

    def __init__(self, bucket, token):
        self.base = 'https://storage.yandexcloud.net/%s/notes/' % bucket
        self.token = token

    def _req(self, method, name, data=None):
        req = urllib.request.Request(self.base + name + '.json', data=data, method=method)
        req.add_header('X-YaCloud-SubjectToken', self.token)
        if data is not None:
            req.add_header('Content-Type', 'application/json; charset=utf-8')
        return urllib.request.urlopen(req, timeout=10)

    def load(self, project):
        try:
            with self._req('GET', project) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {'notes': []}
            raise

    def save(self, project, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self._req('PUT', project, body).close()


class FileStore:
    """Локальные файлы — для проверки на компьютере (tools/serve.py)."""

    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def load(self, project):
        p = os.path.join(self.folder, project + '.json')
        if not os.path.exists(p):
            return {'notes': []}
        with open(p, encoding='utf-8') as f:
            return json.load(f)

    def save(self, project, data):
        with open(os.path.join(self.folder, project + '.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- Telegram

def _send_telegram(text):
    """Прямо в Telegram (из Yandex Cloud сейчас недоступно — оставлено на случай, если заработает)."""
    token, chat = env('TG_BOT_TOKEN'), env('TG_CHAT_ID')
    data = urllib.parse.urlencode({'chat_id': chat, 'text': text, 'disable_web_page_preview': 'true'}).encode()
    urllib.request.urlopen('https://api.telegram.org/bot%s/sendMessage' % token, data=data, timeout=4).close()


def _send_via_github(text):
    """Через GitHub Actions: workflow .github/workflows/notify.yml отправит сообщение в Telegram."""
    body = json.dumps({'event_type': 'note', 'client_payload': {'text': text}}).encode('utf-8')
    req = urllib.request.Request('https://api.github.com/repos/%s/dispatches' % env('GH_REPO', 'VBSspace/3d'),
                                 data=body, method='POST')
    req.add_header('Authorization', 'Bearer ' + env('GH_DISPATCH_TOKEN'))
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'bvsspace-notes')
    urllib.request.urlopen(req, timeout=8).close()


def notify(project, note, site):
    link = '%s%s/#note=%d' % (site, project, note['n'])
    text = ('📍 Новое замечание №%d — %s\n'
            'Место: %s\n\n«%s»\n%s\n%s') % (
        note['n'], project, note.get('partName') or '—', note['text'],
        ('— ' + note['author']) if note.get('author') else '', link)
    try:
        if env('GH_DISPATCH_TOKEN'):
            _send_via_github(text)
        elif env('TG_BOT_TOKEN') and env('TG_CHAT_ID'):
            _send_telegram(text)
        else:
            return 'not configured'
        return 'ok'
    except urllib.error.HTTPError as e:  # уведомление не должно ломать сохранение
        print('notify error', e.code)
        return 'error %s' % e.code
    except Exception as e:
        print('notify error', type(e).__name__)
        return 'error ' + type(e).__name__


# ---------------------------------------------------------------- логика

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def _clean_num_list(v, n):
    if not isinstance(v, list) or len(v) != n:
        return None
    try:
        return [round(float(x), 3) for x in v]
    except (TypeError, ValueError):
        return None


def handle(method, project, body, store, admin_code, site):
    """-> (статус, dict)."""
    if not PROJECT_RE.match(project or ''):
        return 400, {'error': 'project'}
    is_admin = bool(admin_code) and hmac.compare_digest(str(body.get('admin') or ''), admin_code)
    if method == 'GET':
        return 200, {'notes': store.load(project).get('notes', [])}
    if method != 'POST':
        return 405, {'error': 'method'}
    action = body.get('action')
    if action == 'whoami':
        return 200, {'admin': is_admin}

    data = store.load(project)
    notes = data.setdefault('notes', [])

    if action == 'add':
        if body.get('hp'):                      # ловушка для ботов
            return 200, {'note': {'n': 0}, 'notes': notes}
        src = body.get('note') or {}
        text = str(src.get('text') or '').strip()[:2000]
        if not text:
            return 400, {'error': 'text'}
        if len(notes) >= MAX_NOTES:
            return 429, {'error': 'too many notes'}
        p = _clean_num_list(src.get('p'), 3)
        if p is None:
            return 400, {'error': 'point'}
        view = src.get('view') or {}
        vpos, vtgt = _clean_num_list(view.get('pos'), 3), _clean_num_list(view.get('target'), 3)
        note = {
            'n': max([x['n'] for x in notes] or [0]) + 1,
            'part': re.sub(r'[^a-z0-9]', '', str(src.get('part') or ''))[:12],
            'partName': str(src.get('partName') or '')[:120],
            'p': p,
            'text': text,
            'author': str(src.get('author') or '').strip()[:60],
            'created': _now(),
            'status': 'open',
            'replies': [],
        }
        if vpos and vtgt:
            note['view'] = {'pos': vpos, 'target': vtgt}
        notes.append(note)
        store.save(project, data)
        notified = notify(project, note, site) == 'ok'
        return 200, {'note': note, 'notes': notes, 'notified': notified}

    if action in ('reply', 'status', 'delete'):
        if not is_admin:
            return 403, {'error': 'admin only'}
        try:
            num = int(body.get('n'))
        except (TypeError, ValueError):
            return 400, {'error': 'n'}
        note = next((x for x in notes if x['n'] == num), None)
        if not note:
            return 404, {'error': 'not found'}
        if action == 'reply':
            t = str(body.get('text') or '').strip()[:2000]
            if not t:
                return 400, {'error': 'text'}
            note.setdefault('replies', []).append({'text': t, 'author': 'BVSspace', 'at': _now()})
        elif action == 'status':
            note['status'] = 'resolved' if body.get('status') == 'resolved' else 'open'
            note['statusAt'] = _now()
        else:
            notes.remove(note)
        store.save(project, data)
        return 200, {'notes': notes}

    return 400, {'error': 'action'}


# ---------------------------------------------------------------- вход Yandex Cloud Functions

def handler(event, context):
    origin = (event.get('headers') or {}).get('Origin') or (event.get('headers') or {}).get('origin') or ''
    allowed = [o.strip() for o in env('ALLOWED_ORIGINS', 'https://vbsspace.github.io').split(',') if o.strip()]
    cors = {
        'Access-Control-Allow-Origin': origin if origin in allowed else allowed[0],
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
        'Vary': 'Origin',
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
    }
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 204, 'headers': cors, 'body': ''}
    qs = event.get('queryStringParameters') or {}
    raw = event.get('body') or ''
    if event.get('isBase64Encoded') and raw:
        import base64
        raw = base64.b64decode(raw).decode('utf-8', errors='replace')
    try:
        body = json.loads(raw) if raw else {}
        if not isinstance(body, dict):
            body = {}
    except ValueError:
        body = {}
    token = (getattr(context, 'token', None) or {}).get('access_token', '')
    store = S3Store(env('BUCKET'), token)
    try:
        code, res = handle(method, qs.get('project', ''), body, store, env('ADMIN_CODE'),
                           env('SITE_URL', 'https://vbsspace.github.io/3d/'))
    except Exception as e:
        print('error', repr(e))
        code, res = 500, {'error': 'server'}
    return {'statusCode': code, 'headers': cors, 'body': json.dumps(res, ensure_ascii=False)}
