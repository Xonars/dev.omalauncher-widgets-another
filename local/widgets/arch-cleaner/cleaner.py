#!/usr/bin/env python3
"""Conservative cache cleaner for the Arch home-screen widget."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HOME = Path.home()
BASE = HOME / '.cache/arch-cleaner'
BASE.mkdir(parents=True, exist_ok=True)
STATUS = BASE / 'status.json'
LABELS = ['Pacman', 'npm', 'pip', 'uv', 'yay', 'Go', 'Временные файлы', 'Миниатюры', 'Корзина', 'Журналы', 'PRoot']

def save(data):
    tmp = BASE / 'status.tmp'
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(STATUS)

def read():
    try:
        return json.loads(STATUS.read_text())
    except (OSError, ValueError):
        return {}

def command(args):
    p = subprocess.run(args, capture_output=True, timeout=120)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace')[-500:] or 'Команда завершилась с ошибкой')
    return p.stdout

def size(path):
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_blocks * 512
        return sum(size(p) for p in path.iterdir()) if path.is_dir() else 0
    except OSError:
        return 0

def processes():
    result = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            result.append((p, (p / 'comm').read_text().strip()))
        except OSError:
            pass
    return result

def safe(path):
    # Never traverse a symlink in an ancestor, even for a configured cache.
    return path.is_absolute() and not any(p.is_symlink() for p in [path, *path.parents])

def plan(trash):
    now = time.time()
    procs = processes()
    names = {name for _, name in procs}
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(HOME / '.cache')))
    data = Path(os.environ.get('XDG_DATA_HOME', str(HOME / '.local/share')))
    rows = []
    for label in LABELS:
        paths, note = [], ''
        if label == 'Pacman':
            if Path('/var/lib/pacman/db.lck').exists():
                note = 'pacman занят'
            else:
                try:
                    out = command(['paccache', '-d', '-k', '2', '-vv', '-z'])
                    paths = [Path(os.fsdecode(x)) for x in out.split(b'\n', 1)[-1].split(b'\0') if x.startswith(b'/') and b'\n' not in x]
                except Exception as e:
                    note = str(e)
        elif label in ['npm', 'pip', 'uv', 'yay', 'Go']:
            roots = {'npm': [HOME / '.npm/_cacache', HOME / '.npm/_logs'], 'pip': [cache / 'pip'], 'uv': [cache / 'uv'], 'yay': [cache / 'yay'], 'Go': [cache / 'go-build']}
            busy = {'npm': {'npm', 'node'}, 'pip': {'pip', 'pip3'}, 'uv': {'uv'}, 'yay': {'yay', 'makepkg', 'pacman'}, 'Go': {'go', 'compile', 'link'}}
            if names & busy[label]:
                note = 'инструмент занят'
            else:
                for root in roots[label]:
                    if safe(root) and root.is_dir():
                        paths.extend(root.iterdir())
        elif label == 'Миниатюры':
            root = cache / 'thumbnails'
            if safe(root) and root.is_dir():
                paths = list(root.iterdir())
        elif label == 'Корзина':
            if trash:
                for root in [data / 'Trash/files', data / 'Trash/info']:
                    if safe(root) and root.is_dir():
                        paths.extend(root.iterdir())
            else:
                note = 'отключено'
        elif label == 'Временные файлы':
            # Only old ordinary files; leave sockets, directories and PRoot alone.
            opened = set()
            for proc, _ in procs:
                try:
                    for fd in (proc / 'fd').iterdir():
                        try:
                            opened.add(os.readlink(fd))
                        except OSError:
                            pass
                except OSError:
                    pass
            for root in [Path('/tmp'), Path('/var/tmp')]:
                for p in root.glob('*'):
                    try:
                        if not p.name.startswith('proot') and p.is_file() and not p.is_symlink() and now - max(p.stat().st_mtime, p.stat().st_atime, p.stat().st_ctime) > 7 * 86400 and str(p) not in opened:
                            paths.append(p)
                    except OSError:
                        pass
        elif label == 'PRoot':
            for root in [Path('/tmp'), Path('/var/tmp')]:
                for p in root.glob('proot-*'):
                    m = re.fullmatch(r'proot-(\d+)-[A-Za-z0-9]+', p.name)
                    try:
                        # An existing PID is protected even if it has been reused.
                        if m and not Path('/proc', m[1]).exists() and now - p.stat().st_mtime > 86400:
                            paths.append(p)
                    except OSError:
                        pass
            if 'proot' in names:
                paths = []
                note = 'есть активная PRoot-сессия'
        elif label == 'Журналы':
            note = 'архивы старше 14 дней; оценка'
            for root in [Path('/var/log/journal'), Path('/run/log/journal')]:
                for p in root.glob('*/*@*.journal'):
                    try:
                        if now - p.stat().st_mtime > 14 * 86400:
                            paths.append(p)
                    except OSError:
                        pass
        paths = [p for p in paths if safe(p)]
        rows.append({'name': label, 'bytes': sum(size(p) for p in paths), 'note': note, 'paths': paths})
    return rows

def work(mode, trash):
    with (BASE / 'lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        old = read()
        state = {**old, 'busy': True, 'progress': 0, 'message': 'Сканирование…', 'errors': []}
        save(state)
        try:
            rows = plan(trash)
            total = sum(r['bytes'] for r in rows)
            state.update(rows=[{k: v for k, v in r.items() if k != 'paths'} for r in rows], total=total, checked=time.time())
            freed = 0
            if mode == 'clean':
                for i, row in enumerate(rows):
                    state.update(message='Очистка: ' + row['name'], progress=round(i / len(rows) * 100))
                    save(state)
                    try:
                        if row['name'] == 'Журналы':
                            if row['paths']:
                                before = sum(size(p) for p in row['paths'])
                                command(['journalctl', '--vacuum-time=14d'])
                                freed += max(0, before - sum(size(p) for p in row['paths']))
                        else:
                            for p in row['paths']:
                                if not safe(p) or not p.exists():
                                    continue
                                if row['name'] == 'Pacman' and Path('/var/lib/pacman/db.lck').exists():
                                    raise RuntimeError('pacman занят')
                                before = size(p)
                                if p.is_dir():
                                    shutil.rmtree(p)
                                else:
                                    p.unlink()
                                freed += max(0, before - size(p))
                    except Exception as e:
                        state['errors'].append(row['name'] + ': ' + str(e))
                state.update(freed=freed, cleaned=time.time())
                rows = plan(trash)
                state.update(total=sum(r['bytes'] for r in rows), rows=[{k: v for k, v in r.items() if k != 'paths'} for r in rows])
            state.update(message=('Очистка завершена' if mode == 'clean' else 'Оценка готова') + (' · есть ошибки' if state['errors'] else ''), progress=100)
        except Exception as e:
            state.update(message='Ошибка', errors=[str(e)])
        finally:
            state['busy'] = False
            save(state)

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'status'
    trash = len(sys.argv) > 2 and sys.argv[2] == 'yes'
    if mode == 'status':
        data = read()
        if data.get('busy'):
            with (BASE / 'lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    data.update(busy=False, message='Предыдущая задача прервана')
                    save(data)
                except BlockingIOError:
                    pass
        print(json.dumps(data, ensure_ascii=False))
    elif mode in ['scan', 'clean']:
        subprocess.Popen([sys.executable, __file__, '_'+mode, 'yes' if trash else 'no'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    elif mode in ['_scan', '_clean']:
        work(mode[1:], trash)
