#!/usr/bin/env python3
"""Authenticated Pinterest home feed and explicit, user-triggered saves."""
import contextlib
import fcntl
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlencode, quote
import requests
import pinterest
import downloads

ROOT = downloads.STATE_DIR
COOKIE_FILE = ROOT / 'pinterest-cookies.txt'
ACCOUNT = ROOT / 'account.json'
FEED = ROOT / 'feed.json'
MY_BOARDS = ROOT / 'my-boards.json'
SAVES = ROOT / 'saved-pins.json'


def write(path, data):
    downloads.atomic(path, data)
    path.chmod(0o600)


def load_script(html, name):
    m = re.search(r'<script[^>]*id="' + name + r'"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m[1]) if m else {}


class Client:
    def __init__(self):
        if not COOKIE_FILE.is_file():
            raise RuntimeError('Войдите в Pinterest через настройки приложения')
        jar = http.cookiejar.MozillaCookieJar(str(COOKIE_FILE))
        try:
            jar.load(ignore_discard=True, ignore_expires=False)
        except (OSError, http.cookiejar.LoadError):
            raise RuntimeError('Не удалось прочитать сессию Pinterest. Войдите заново.') from None
        self.session = requests.Session()
        for cookie in jar:
            if cookie.domain.lstrip('.') == 'pinterest.com' or cookie.domain.endswith('.pinterest.com'):
                self.session.cookies.set_cookie(cookie)
        if not any(c.name == '_pinterest_sess' for c in self.session.cookies):
            raise RuntimeError('Сессия Pinterest истекла. Войдите заново.')
        agent_file = ROOT / 'user-agent.txt'
        agent = agent_file.read_text().strip() if agent_file.is_file() else 'Mozilla/5.0'
        self.session.headers.update({'User-Agent': agent, 'Referer': 'https://www.pinterest.com/',
                                     'X-Requested-With': 'XMLHttpRequest', 'X-Pinterest-AppState': 'active',
                                     'X-Pinterest-PWS-Handler': 'www/index.js'})

    def request(self, method, path, **kwargs):
        try:
            r = self.session.request(method, 'https://www.pinterest.com' + path,
                                     timeout=(10, 35), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise RuntimeError('Pinterest недоступен. Проверьте соединение; запрос не повторялся автоматически.') from None
        if r.status_code in (301, 302, 401, 403):
            raise RuntimeError('Pinterest требует повторный вход или проверку аккаунта. Откройте «Войти в Pinterest».')
        if r.status_code >= 400:
            raise RuntimeError('Pinterest отклонил запрос (HTTP ' + str(r.status_code) + ').')
        return r

    def home(self):
        html = self.request('GET', '/').text
        context = load_script(html, '__PWS_DATA__').get('context', {})
        state = load_script(html, '__PWS_INITIAL_PROPS__').get('initialReduxState', {})
        if not context.get('is_authenticated') and not state.get('session', {}).get('isAuthenticated'):
            raise RuntimeError('Вход ещё не выполнен. Завершите авторизацию на странице Pinterest.')
        user = context.get('user', {})
        username = user.get('username')
        if not username:
            uid = str(state.get('session', {}).get('userId', ''))
            username = state.get('users', {}).get(uid, {}).get('username')
        if not username or not re.fullmatch(r'[A-Za-z0-9_]+', username):
            raise RuntimeError('Не удалось определить аккаунт Pinterest')
        return username, state

    def api(self, resource, options, write_request=False):
        if (resource, write_request) not in {('UserHomefeedResource', False), ('HomefeedResource', False),
                                            ('BoardsFeedResource', False), ('RepinResource', True)}:
            raise ValueError('Unsupported resource')
        body = {'source_url': '/', 'data': json.dumps({'options': options, 'context': {}}, separators=(',', ':'))}
        if write_request:
            csrf = next((c.value for c in self.session.cookies if c.name == 'csrftoken'), None)
            if not csrf:
                csrf = secrets.token_hex(16)
                self.session.cookies.set('csrftoken', csrf, domain='.pinterest.com', path='/')
            r = self.request('POST', '/resource/' + resource + '/create/', data=body,
                             headers={'X-CSRFToken': csrf, 'Origin': 'https://www.pinterest.com'})
        else:
            r = self.request('GET', '/resource/' + resource + '/get/?' + urlencode(body, quote_via=quote))
        try:
            result = r.json()
        except ValueError:
            raise RuntimeError('Pinterest вернул неожиданный ответ') from None
        response = result.get('resource_response', {})
        if response.get('status') != 'success':
            raise RuntimeError('Pinterest не подтвердил действие. Проверьте вход и права на доску.')
        return result


def connect():
    client = Client()
    username, state = client.home()
    previous = pinterest.read(ACCOUNT)
    if previous.get('username') != username:
        write(FEED, {})
        write(MY_BOARDS, {})
        write(SAVES, {})
    account = dict(connected=True, username=username, updated=time.time(), error='')
    write(ACCOUNT, account)
    return account


def my_boards(client=None, username=None):
    client = client or Client()
    username = username or pinterest.read(ACCOUNT).get('username')
    if not username:
        username, _ = client.home()
    options = dict(username=username, field_set_key='profile_grid_item', sort='last_pinned_to', filter_stories=False)
    found = {}; marks = set()
    for _ in range(50):
        result = client.api('BoardsFeedResource', options)
        response = result['resource_response']
        batch = response.get('data', [])
        if isinstance(batch, dict): batch = batch.get('results', [])
        for b in batch:
            owner = b.get('owner', {}).get('username', username)
            if b.get('type') != 'board' or (owner.lower() != username.lower() and not b.get('collaborated_by_me')):
                continue
            if b.get('archived_by_me_at'):
                continue
            found[str(b['id'])] = dict(id=str(b['id']), name=b['name'], url=b['url'], profile=owner,
                                       count=b.get('pin_count', 0), modifiedAt=pinterest.board_time(b.get('board_order_modified_at')))
        bookmarks = result.get('resource', {}).get('options', {}).get('bookmarks', [])
        mark = response.get('bookmark') or (bookmarks[0] if bookmarks else None)
        if not mark or mark == '-end-': break
        if mark in marks: raise RuntimeError('Pinterest повторил страницу досок. Обновите список.')
        marks.add(mark); options['bookmarks'] = [mark]
    else:
        raise RuntimeError('Слишком много страниц досок. Pinterest не завершил список.')
    data = dict(boards=sorted(found.values(), key=lambda b: b['name'].casefold()), username=username, error='')
    downloads.observe_boards(data['boards'])
    write(MY_BOARDS, data)
    return data


def pin_item(pin):
    if pin.get('type') not in (None, 'pin') or not re.fullmatch(r'[A-Za-z0-9_-]+', str(pin.get('id', ''))):
        return None
    images = pin.get('images') or {}
    image = images.get('736x') or images.get('474x') or images.get('orig') or {}
    url = image.get('url', '')
    if not re.fullmatch(r'https://i\.pinimg\.com/[^\s]+', url): return None
    return dict(id=str(pin['id']), image=url,
                title=(pin.get('title') or pin.get('grid_title') or pin.get('description') or 'Pinterest')[:200],
                page='https://www.pinterest.com/pin/' + str(pin['id']) + '/')


def result_page(result):
    response = result['resource_response']; items = response.get('data', [])
    if isinstance(items, dict): items = items.get('results', items.get('pins', []))
    bookmarks = result.get('resource', {}).get('options', {}).get('bookmarks', [])
    mark = response.get('bookmark') or (bookmarks[0] if bookmarks else None)
    return items, mark


def feed(action='refresh'):
    client = Client(); old = pinterest.read(FEED)
    if action == 'next' and old.get('bookmark') and old['bookmark'] != '-end-':
        options = dict(old.get('options', {}), bookmarks=[old['bookmark']])
        result = client.api(old.get('resource', 'UserHomefeedResource'), options)
        items, mark = result_page(result)
        resource = old.get('resource', 'UserHomefeedResource')
    else:
        username, state = client.home()
        write(ACCOUNT, dict(connected=True, username=username, updated=time.time(), error=''))
        resource = 'UserHomefeedResource'; options = dict(field_set_key='hf_grid', in_nux=False, prepend=False, page_size=20)
        resources = state.get('resources', {})
        found = next(((name, feeds) for name, feeds in resources.items() if name in ('UserHomefeedResource', 'HomefeedResource') and feeds), None)
        if found:
            resource, feeds = found
            key, initial = next(iter(feeds.items()))
            options = dict(json.loads(key)); items = initial.get('data', []); mark = initial.get('nextBookmark')
            if isinstance(items, dict): items = items.get('results', [])
        else:
            items, mark = result_page(client.api(resource, options))
        # Some home-feed resources hold sparse references; Redux contains the images.
        known_pins = state.get('pins', {})
        items = [known_pins.get(str(p.get('id')), p) if isinstance(p, dict) and not p.get('images') else p for p in items]
    pins = [p for pin in items if isinstance(pin, dict) and (p := pin_item(pin))]
    if not pins:
        raise RuntimeError('Pinterest не вернул изображения ленты. Попробуйте обновить или войти заново.')
    data = dict(items=pins[:20], bookmark=mark, resource=resource, options=options,
                page=old.get('page', 1) + 1 if action == 'next' else 1, updated=time.time(), error='')
    write(FEED, data)
    return dict(ok=True)


def save_pin(cfg):
    pin_id, board_id = str(cfg.get('pinId', '')), str(cfg.get('boardId', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]+', pin_id) or not board_id.isdigit():
        raise ValueError('Некорректный пин или доска')
    account = pinterest.read(ACCOUNT)
    client = Client()
    own = pinterest.read(MY_BOARDS)
    if own.get('username') != account.get('username') or not own.get('boards'):
        own = my_boards(client)
    target = next((b for b in own['boards'] if b['id'] == board_id), None)
    if not target:
        raise RuntimeError('Выберите доску подключённого аккаунта')
    result = client.api('RepinResource', dict(board_id=board_id, pin_id=pin_id, description='', link=''), True)
    saved = result['resource_response'].get('data') or {}
    if not isinstance(saved, dict) or not saved.get('id'):
        raise RuntimeError('Pinterest не подтвердил сохранение пина. Проверьте доску перед повтором.')
    downloads.mark_changed(board_id)
    # Update the chooser/catalog immediately; a refresh obtains the authoritative count.
    for board in own['boards']:
        if board['id'] == board_id:
            board['count'] = board.get('count', 0) + 1
            board['modifiedAt'] = time.time()
    write(MY_BOARDS, own)
    record = pinterest.read(SAVES)
    targets = record.setdefault(pin_id, {})
    targets[board_id] = dict(id=str(saved['id']), board=target['name'], at=time.time())
    write(SAVES, record)
    for name in ('boards-' + target['profile'].lower() + '.json', 'boards.json'):
        path = pinterest.ROOT / name
        cache = pinterest.read(path)
        if cache:
            cache['updated'] = 0
            pinterest.save(path, cache)
    return dict(ok=True, board=target['name'], id=str(saved['id']))


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    ROOT.chmod(0o700)
    action = sys.argv[1]
    try:
        if action == 'connect': result = connect()
        elif action == 'boards': result = my_boards()
        elif action in ('refresh', 'next'): result = feed(action)
        elif action == 'save':
            with (ROOT / 'pin-save.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = save_pin(json.loads(sys.argv[2]))
        elif action == 'logout':
            COOKIE_FILE.unlink(missing_ok=True)
            for path in (ACCOUNT, FEED, MY_BOARDS, SAVES): write(path, {})
            result = dict(ok=True)
        else: raise ValueError('Неизвестное действие')
        result['requestId'] = time.time_ns()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        message = str(error) if isinstance(error, (RuntimeError, ValueError)) else 'Не удалось выполнить действие Pinterest. Попробуйте ещё раз.'
        if action == 'connect': write(ACCOUNT, dict(connected=False, error=message, updated=time.time()))
        elif action in ('refresh', 'next'):
            data = pinterest.read(FEED); data['error'] = message; write(FEED, data)
        elif action == 'boards':
            data = pinterest.read(MY_BOARDS); data['error'] = message; write(MY_BOARDS, data)
        print(json.dumps(dict(ok=False, error=message, requestId=time.time_ns()), ensure_ascii=False))


if __name__ == '__main__': main()
