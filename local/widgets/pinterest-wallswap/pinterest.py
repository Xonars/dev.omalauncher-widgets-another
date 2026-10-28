#!/usr/bin/env python3
"""Public Pinterest boards and board pins, with pagination and local caching."""
import json, os, random, re, subprocess, sys, time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, quote

ROOT = Path.home() / '.cache/pinterest-wallswap'
ROOT.mkdir(parents=True, exist_ok=True)
def profiles(cfg):
    values = cfg.get('profiles', ['xonars'])
    if isinstance(values, str): values = re.split(r'[,;\s]+', values)
    result = []
    for value in values:
        value = value.strip().strip('/').lstrip('@').lower()
        if not value: continue
        if not re.fullmatch(r'[a-z0-9_]{1,64}', value):
            raise ValueError('Укажите имена профилей через запятую, без ссылок')
        if value not in result: result.append(value)
    if not result: raise ValueError('Добавьте хотя бы один профиль')
    return result


def save(path, data):
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', dir=ROOT, delete=False) as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(f.name, path)

def read(path):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return {}

def fetch(url):
    if not url.startswith('https://www.pinterest.com/'):
        raise ValueError('Unexpected Pinterest URL')
    p = subprocess.run(['curl', '--compressed', '--fail', '--silent', '--show-error',
        '--proto', '=https', '--max-time', '25', '--max-filesize', '12000000',
        '-A', 'Mozilla/5.0', '-H', 'X-Requested-With: XMLHttpRequest',
        '-H', 'X-Pinterest-PWS-Handler: www/[username].js', url], capture_output=True)
    if p.returncode: raise RuntimeError('Pinterest недоступен: ' + p.stderr.decode(errors='replace')[:120])
    return p.stdout.decode()

def initial(path):
    html = fetch('https://www.pinterest.com' + path)
    m = re.search(r'<script[^>]*id="__PWS_INITIAL_PROPS__"[^>]*>(.*?)</script>', html, re.S)
    if not m: raise RuntimeError('Pinterest не отдал данные; возможно, требуется вход')
    return json.loads(m[1])['initialReduxState']

def resource(name, options, path):
    query = urlencode({'source_url': path, 'data': json.dumps({'options': options, 'context': {}}, separators=(',', ':'))}, quote_via=quote)
    d = json.loads(fetch('https://www.pinterest.com/resource/' + name + '/get/?' + query))
    r = d.get('resource_response', {})
    if r.get('status') != 'success': raise RuntimeError('Pinterest отклонил загрузку следующей страницы')
    bookmark = d.get('resource', {}).get('options', {}).get('bookmarks', [])
    return r.get('data', []), r.get('bookmark') or (bookmark[0] if bookmark else '-end-')

def board_time(value):
    try: return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, AttributeError): return 0


def profile_boards(profile, force=False):
    path = ROOT / ('boards-' + profile + '.json'); old = read(path)
    if profile == 'xonars' and not old: old = read(ROOT / 'boards.json')
    if not force and time.time() - old.get('updated', 0) < 21600 and all('modifiedAt' in b for b in old.get('boards', [])): return old
    try:
        r = initial('/' + profile + '/')
        k, feed = next(iter(r['resources']['BoardsFeedResource'].items()))
        options = dict(json.loads(k)); items = list(feed['data']); mark = feed.get('nextBookmark')
        seen = set(); complete = True; warning = ''
        for _ in range(30):
            if not mark or mark == '-end-': break
            if mark in seen: complete = False; break
            seen.add(mark); options['bookmarks'] = [mark]
            try: batch, mark = resource('BoardsFeedResource', options, '/' + profile + '/')
            except Exception as e: complete = False; warning = str(e); break
            items.extend(batch)
        else: complete = False
        result = {}
        for b in items:
            if b.get('type') == 'board' and b.get('url', '').startswith('/' + profile + '/'):
                result[b['id']] = {'id': b['id'], 'name': b['name'], 'url': b['url'], 'count': b.get('pin_count', 0), 'profile': profile, 'revision': b.get('board_order_modified_at', ''), 'modifiedAt': board_time(b.get('board_order_modified_at'))}
        if not result: raise RuntimeError('В профиле не найдены публичные доски')
        if not complete:
            for b in old.get('boards', []): result.setdefault(b['id'], b)
        data = {'boards': sorted(result.values(), key=lambda b: b['name'].casefold()), 'complete': complete, 'error': warning, 'updated': time.time()}
        save(path, data); return data
    except Exception as e:
        return dict(old, error=str(e), complete=False)

def boards(force=False, cfg=None):
    result = []; errors = []; complete = True
    for profile in profiles(cfg or {}):
        data = profile_boards(profile, force)
        result.extend(dict(b, profile=profile) for b in data.get('boards', []))
        if data.get('error'): errors.append(profile + ': ' + data['error'])
        complete = complete and data.get('complete', False)
    import downloads
    downloads.observe_boards(result)
    return dict(boards=result, complete=complete, error='; '.join(errors))

def candidates(cfg):
    data = boards(cfg=cfg); selected = cfg.get('boards', [])
    pool = [b for b in data.get('boards', []) if not selected or b['id'] in selected]
    if not pool: raise RuntimeError(data.get('error') or 'Выбранные доски недоступны')
    b = random.choice(pool); path = ROOT / ('pins-' + b['id'] + '.json'); cached = read(path)
    if time.time() - cached.get('updated', 0) > 21600:
        r = initial(b['url']); k, feed = next(iter(r['resources']['BoardFeedResource'].items()))
        cached = {'pins': list(r['pins'].values()), 'options': dict(json.loads(k)), 'bookmark': feed.get('nextBookmark'), 'updated': time.time()}
    elif cached.get('bookmark') and cached['bookmark'] != '-end-' and len(cached['pins']) < 1000:
        options = dict(cached['options'], bookmarks=[cached['bookmark']])
        try:
            batch, mark = resource('BoardFeedResource', options, b['url'])
            cached['pins'].extend(batch); cached['bookmark'] = mark
        except Exception: pass  # Existing pins remain usable offline.
    unique = {p.get('id'): p for p in cached['pins'] if p.get('type') == 'pin'}
    cached['pins'] = list(unique.values()); save(path, cached)
    for p in cached['pins']:
        image = p.get('images', {}).get('orig', {})
        url = image.get('url', '')
        if not re.fullmatch(r'https://i\.pinimg\.com/[^\s]+\.(?:jpg|jpeg|png|webp)', url): continue
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(p.get('id', ''))): continue
        title = p.get('title') or p.get('grid_title') or b['name']
        row = [url, title, 'Pinterest · ' + b['profile'] + ' / ' + b['name'], 'https://www.pinterest.com/pin/' + p['id'] + '/', image.get('width', ''), image.get('height', '')]
        print('\t'.join(str(v).replace('\t', ' ').replace('\n', ' ').replace('\r', ' ') for v in row))

if __name__ == '__main__':
    try:
        if sys.argv[1] == 'boards': print(json.dumps(boards('--refresh' in sys.argv, json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != '--refresh' else {}), ensure_ascii=False))
        else: candidates(json.loads(sys.argv[2]))
    except Exception as e:
        print(str(e), file=sys.stderr); sys.exit(1)
