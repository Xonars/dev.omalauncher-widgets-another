#!/usr/bin/env python3
"""APK-only HTTP server and serialized controller; Python standard library only."""
import argparse
import fcntl
import html
import http.server
import ipaddress
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.parse

BASE = Path(__file__).resolve().parent
CACHE = Path.home() / '.cache/omalauncher-apk-share'
CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
STATE = CACHE / 'state.json'
PORT = 8765


def save(data):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(data))
    temp.replace(STATE)


def read():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {'status': 'Stopped', 'error': '', 'directory': str(Path.home()), 'bind': '127.0.0.1'}


def identity(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def alive(data):
    if not (data.get('pid') and data.get('identity') and identity(data['pid']) == data['identity']):
        return False
    try:
        return not Path(f"/proc/{data['pid']}/stat").read_text().split(') ', 1)[1].startswith('Z')
    except OSError:
        return False


def files(root):
    result = []
    def failure(error):
        raise error
    for parent, dirs, names in os.walk(root, followlinks=False, onerror=failure):
        dirs[:] = [d for d in dirs if not Path(parent, d).is_symlink()]
        for name in names:
            p = Path(parent, name)
            if p.suffix.lower() != '.apk':
                continue
            try:
                s = p.lstat()
                if not stat.S_ISREG(s.st_mode) or p.suffix.lower() != '.apk':
                    continue
                rel = p.relative_to(root).as_posix()
                result.append({'name': name, 'path': rel, 'full_path': str(p.absolute()), 'size': s.st_size, 'mtime': s.st_mtime,
                               'url': '/apk/' + urllib.parse.quote(rel, safe='/')})
            except FileNotFoundError:
                continue
    return sorted(result, key=lambda f: (-f['mtime'], f['path']))


def serve(root, bind):
    # Held for the entire lifetime; also prevents duplicate backend instances.
    lock = open(CACHE / 'server.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rootfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.respond(False)

        def do_GET(self):
            self.respond(True)

        def respond(self, body):
            path = urllib.parse.urlsplit(self.path).path
            if path == '/':
                try:
                    rows = files(root)
                    content = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                               '<title>APK Share</title><style>body{background:#15171c;color:#eee;font:16px sans-serif;'
                               'max-width:850px;margin:30px auto;padding:16px}a{color:#8ab4f8}li{margin:20px 0;overflow-wrap:anywhere}</style>'
                               '<h1>APK Share</h1><p>Download an APK · reload to refresh</p><ul>' + ''.join(
                                   '<li><a href="' + html.escape(f['url'], quote=True) + '">' + html.escape(f['path']) + '</a><br>'
                                   + f"{f['size'] / 1048576:.2f} MiB · " + time.strftime('%Y-%m-%d %H:%M', time.localtime(f['mtime'])) + '</li>'
                                   for f in rows) + '</ul>').encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    if body:
                        self.wfile.write(content)
                except OSError:
                    self.send_error(500, 'Cannot read APK directory')
                return
            fd = None
            try:
                if not path.startswith('/apk/'):
                    raise ValueError()
                rel = urllib.parse.unquote(path[5:], errors='strict')
                parts = rel.split('/')
                if any(p in ('', '.', '..') or '\x00' in p for p in parts) or not parts[-1].lower().endswith('.apk'):
                    raise ValueError()
                # Resolve every component through directory descriptors. Symlinks are
                # forbidden even if swapped between listing and download.
                fd = os.dup(rootfd)
                for part in parts[:-1]:
                    nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = nxt
                apk = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                os.close(fd)
                fd = apk
                s = os.fstat(fd)
                if not stat.S_ISREG(s.st_mode):
                    raise ValueError()
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.android.package-archive')
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(parts[-1], safe=''))
                self.send_header('Content-Length', str(s.st_size))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                if body:
                    remaining = s.st_size
                    while remaining:
                        chunk = os.read(fd, min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (OSError, ValueError, UnicodeError):
                self.send_error(404)
            finally:
                if fd is not None:
                    os.close(fd)

    class Server(http.server.ThreadingHTTPServer):
        address_family = socket.AF_INET6 if ':' in bind else socket.AF_INET
        daemon_threads = True
        allow_reuse_address = True

    server = Server((bind, PORT), Handler)
    save({'status': 'Running', 'pid': os.getpid(), 'identity': identity(os.getpid()),
          'directory': str(root), 'bind': bind, 'error': ''})
    server.serve_forever()


def stop(data):
    if alive(data):
        os.kill(data['pid'], signal.SIGTERM)
        for _ in range(50):
            # Zombies have already released sockets and locks.
            try:
                zombie = Path(f"/proc/{data['pid']}/stat").read_text().split(') ', 1)[1].startswith('Z')
            except OSError:
                zombie = True
            if not alive(data) or zombie:
                break
            time.sleep(.05)
        else:
            raise RuntimeError('Server did not stop; retry Stop')
    data.update(status='Stopped', pid=None, identity=None, error='')
    save(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'list', 'start', 'stop', '_serve'])
    parser.add_argument('--directory', default='~')
    parser.add_argument('--bind', default='127.0.0.1')
    args = parser.parse_args()
    if args.action == '_serve':
        serve(Path(args.directory), args.bind)
        return
    lock = open(CACHE / 'control.lock', 'a')
    if args.action in ('start', 'stop'):
        fcntl.flock(lock, fcntl.LOCK_EX)
    data = read()
    try:
        if args.action == 'stop':
            stop(data)
        elif args.action == 'start':
            root = Path(args.directory).expanduser().resolve(strict=True)
            if not root.is_dir():
                raise ValueError('Choose an existing directory')
            ipaddress.ip_address(args.bind)
            if not (alive(data) and data['directory'] == str(root) and data['bind'] == args.bind):
                stop(data)
                save(dict(data, status='Stopped', error=''))
                with open(CACHE / 'server.log', 'w') as log:
                    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_serve', '--directory', str(root), '--bind', args.bind],
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
                for _ in range(60):
                    data = read()
                    if data.get('pid') == proc.pid and alive(data):
                        break
                    if proc.poll() is not None:
                        raise RuntimeError((CACHE / 'server.log').read_text()[-1200:])
                    time.sleep(.05)
                else:
                    proc.terminate()
                    raise RuntimeError('Server startup timed out')
            data.update(status='Running', error='')
            save(data)
        elif args.action == 'list':
            root = Path(args.directory).expanduser().resolve(strict=True)
            if not root.is_dir():
                raise ValueError('Directory does not exist')
            result = files(root)
            print(json.dumps({'files': result[:150], 'count': len(result), 'directory': str(root), 'installer_available': shutil.which('omalauncher-install') is not None, 'error': ''}))
            return
        elif data.get('status') == 'Running' and not alive(data):
            data.update(status='Error', error='Server process exited; press Start to restart')
        host = data.get('bind', '127.0.0.1')
        data['url'] = f"http://{'[' + host + ']' if ':' in host else host}:8765/"
    except Exception as exc:
        data.update(status='Error', error=str(exc))
        if args.action == 'list':
            data.update(files=[], count=0)
        else:
            save(data)
    print(json.dumps(data))


if __name__ == '__main__':
    main()
