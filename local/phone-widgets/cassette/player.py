#!/usr/bin/env python3
"""Token-free mpv IPC bridge for Cassette OWL."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CACHE = Path.home() / '.cache/cassette-owl'
CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
SOCKET = str(CACHE / 'mpv.sock')
ERROR = CACHE / 'error.json'
NOW_PLAYING = CACHE / 'now-playing.json'
LOCK = CACHE / 'player.lock'
MUSIC = (Path.home() / 'Music/Cassette').resolve()
EMPTY_STATE = {'connected': False, 'idle': True, 'paused': False,
               'position': 0, 'duration': 0, 'volume': 100}

def write_json(path, value):
    """Atomically replace a small state file so readers never see half JSON."""
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.chmod(temp, 0o600)
    temp.replace(path)

def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback

def metadata(args, start=2, local=False):
    values = list(args[start:start + 4]) + ['', '', '', '']
    return {'id': values[0], 'title': values[1], 'artist': values[2],
            'cover': values[3], 'local': local}

def local_path(value):
    """Return a media path only when it is a direct child of our download folder."""
    path = Path(value).expanduser().resolve()
    if path.parent != MUSIC or path.suffix.lower() not in ('.mp3', '.m4a', '.ogg', '.opus', '.flac', '.wav'):
        raise ValueError('Недопустимый локальный файл')
    return path

def local_tracks():
    MUSIC.mkdir(mode=0o700, parents=True, exist_ok=True)
    tracks = []
    for path in sorted(MUSIC.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file() or path.suffix.lower() not in ('.mp3', '.m4a', '.ogg', '.opus', '.flac', '.wav'):
            continue
        stem = path.stem
        artist, title = (stem.split(' - ', 1) + [''])[:2] if ' - ' in stem else ('', stem)
        try:
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                capture_output=True, text=True, timeout=5, check=False)
            duration_ms = round(float(probe.stdout.strip() or 0) * 1000)
        except (ValueError, subprocess.SubprocessError):
            duration_ms = 0
        tracks.append({
            'id': 'local:' + path.name,
            'local': True,
            'path': str(path),
            'title': title or stem,
            'artists': [{'name': artist or 'Локальный файл'}],
            'durationMs': duration_ms,
        })
    return tracks

def ipc(command):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(2)
        sock.connect(SOCKET)
        sock.sendall((json.dumps({'command': command}) + '\n').encode())
        data = b''
        while b'\n' not in data:
            part = sock.recv(65536)
            if not part:
                raise RuntimeError('Плеер отключился')
            data += part
        for line in data.splitlines():
            reply = json.loads(line)
            if 'error' in reply:
                if reply['error'] != 'success':
                    return None
                return reply.get('data')

def ensure_player():
    try:
        ipc(['get_property', 'idle-active'])
        return
    except (OSError, RuntimeError):
        pass
    # Several OWL actions can arrive together. Only one may start the daemon.
    with LOCK.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            ipc(['get_property', 'idle-active'])
            return
        except (OSError, RuntimeError):
            pass
        Path(SOCKET).unlink(missing_ok=True)
        subprocess.Popen(['mpv', '--idle=yes', '--no-video', '--no-terminal',
            '--audio-display=no', '--input-ipc-server=' + SOCKET],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        for _ in range(50):
            time.sleep(.1)
            try:
                ipc(['get_property', 'idle-active'])
                return
            except (OSError, RuntimeError):
                pass
    raise RuntimeError('Не удалось запустить mpv')

def trusted_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Недопустимый адрес аудио')
    host = (p.hostname or '').lower()
    if not any(host == d or host.endswith('.' + d) for d in ('yandex.net', 'yandex.ru', 'yandex.com')):
        raise ValueError('Адрес аудио не принадлежит Яндексу')
    return url

class YandexRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, trusted_url(newurl))

def resolve(url):
    opener = urllib.request.build_opener(YandexRedirect())
    with opener.open(trusted_url(url), timeout=20) as response:
        xml = response.read(65537)
    if len(xml) > 65536:
        raise ValueError('Слишком большой ответ download-info')
    root = ET.fromstring(xml)
    host, path, ts, salt = [root.findtext(k) for k in ('host', 'path', 'ts', 's')]
    if not all((host, path, ts, salt)):
        raise ValueError('Не удалось получить ссылку на аудио')
    digest = hashlib.md5(('XGRlBW9FXlekgbPrRHuSiA' + path.lstrip('/') + salt).encode()).hexdigest()
    return trusted_url(f'https://{host}/get-mp3/{digest}/{ts}/{path.lstrip("/")}')

def main(args):
    if not args:
        raise ValueError('Не указана команда')
    action = args[0]
    if action == 'library':
        print(json.dumps(local_tracks(), ensure_ascii=False))
        return
    if action == 'status':
        try:
            state = {k: ipc(['get_property', prop]) for k, prop in
                [('idle', 'idle-active'), ('paused', 'pause'), ('position', 'time-pos'),
                 ('duration', 'duration'), ('volume', 'volume'), ('path', 'path')]}
            state.pop('path', None)
            state['connected'] = True
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            state = dict(EMPTY_STATE)
        state.update(read_json(NOW_PLAYING, {}))
        state['error'] = read_json(ERROR, {}).get('error', '')
        print(json.dumps(state, ensure_ascii=False))
        return
    if action == 'resolve':
        if len(args) < 2:
            raise ValueError('Не указан адрес аудио')
        print(resolve(args[1]))
        return
    ensure_player()
    if action == 'play':
        if len(args) < 2:
            raise ValueError('Не указан адрес аудио')
        url = resolve(args[1])
        ipc(['loadfile', url, 'replace'])
        ipc(['set_property', 'pause', False])
        write_json(NOW_PLAYING, metadata(args))
    elif action == 'play-local':
        if len(args) < 2:
            raise ValueError('Не указан локальный файл')
        ipc(['loadfile', str(local_path(args[1])), 'replace'])
        ipc(['set_property', 'pause', False])
        write_json(NOW_PLAYING, metadata(args, local=True))
    elif action == 'toggle':
        ipc(['cycle', 'pause'])
    elif action == 'play-control':
        ipc(['set_property', 'pause', False])
    elif action == 'pause-control':
        ipc(['set_property', 'pause', True])
    elif action == 'seek':
        if len(args) < 2:
            raise ValueError('Не указана позиция')
        ipc(['seek', float(args[1]), 'absolute'])
    elif action == 'volume':
        if len(args) < 2:
            raise ValueError('Не указана громкость')
        ipc(['set_property', 'volume', max(0, min(100, float(args[1])))])
    elif action == 'stop':
        ipc(['stop'])
        NOW_PLAYING.unlink(missing_ok=True)
    elif action == 'download':
        url = resolve(args[1])
        target = Path.home() / 'Music/Cassette'
        target.mkdir(parents=True, exist_ok=True)
        name = ''.join(c for c in args[2] if c.isalnum() or c in ' ._-')[:150].strip('.') or 'track'
        dest = target / (name + '.mp3')
        temp = dest.with_name(f'.{dest.name}.{os.getpid()}.part')
        opener = urllib.request.build_opener(YandexRedirect())
        try:
            with opener.open(url, timeout=30) as response, temp.open('wb') as out:
                while chunk := response.read(131072):
                    out.write(chunk)
            temp.replace(dest)
        finally:
            temp.unlink(missing_ok=True)
        print('Сохранено: ' + str(dest))
    else:
        raise ValueError('Неизвестная команда')
    ERROR.unlink(missing_ok=True)

if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as exc:
        # Never expose signed media URLs in UI or logs.
        message = 'Ошибка аудио: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        write_json(ERROR, {'error': message})
        print(message, file=sys.stderr)
        raise SystemExit(1)
