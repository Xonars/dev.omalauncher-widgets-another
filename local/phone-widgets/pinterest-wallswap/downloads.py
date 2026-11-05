#!/usr/bin/env python3
"""Persistent gallery-dl queue and local board library."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import pinterest

STATE_DIR = Path.home() / '.local/state/pinterest-wallswap'
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE = STATE_DIR / 'downloads.json'
GALLERY = Path.home() / '.local/share/pinterest-wallswap/venv/bin/gallery-dl'
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False)
    os.replace(stream.name, path)


@contextlib.contextmanager
def locked():
    with (STATE_DIR / 'downloads.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = pinterest.read(STATE)
        data.setdefault('jobs', {})
        yield data
        atomic(STATE, data)


def executable():
    return str(GALLERY) if GALLERY.is_file() else shutil.which('gallery-dl')


def destination(value):
    value = str(value).strip()
    if not value or not (value.startswith('/') or value == '~' or value.startswith('~/')):
        raise ValueError('Укажите абсолютный путь или путь с ~/')
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=path):
        pass
    return path


def validate_board(board):
    if not re.fullmatch(r'[0-9]+', str(board.get('id', ''))):
        raise ValueError('Неверный идентификатор доски')
    if not re.fullmatch(r'/[A-Za-z0-9_]+/[^/\s?#]+/', str(board.get('url', ''))):
        raise ValueError('Неверный адрес доски')
    return dict(board)


def update(board_id, **values):
    with locked() as data:
        data['jobs'][board_id].update(values, updated=time.time())


def start_worker():
    lock = (STATE_DIR / 'worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', str(lock.fileno())],
                     pass_fds=(lock.fileno(),), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    lock.close()


def enqueue(cfg, launch=True):
    board = validate_board(cfg['board'])
    binary = executable()
    if not binary:
        raise RuntimeError('gallery-dl не установлен')
    base = destination(cfg.get('saveDirectory', '~/Pictures'))
    # Keep punctuation and user input out of the directory structure.
    profile = board['url'].split('/')[1]
    slug = re.sub(r'[^A-Za-z0-9._-]', '_', board['url'].split('/')[2])[:80]
    directory = base / 'Pinterest' / profile / (slug + '-' + board['id'])
    directory.mkdir(parents=True, exist_ok=True)
    with locked() as data:
        old = data['jobs'].get(board['id'], {})
        if old.get('status') in ('queued', 'downloading'):
            return old
        job = dict(board=board, directory=str(directory), status='queued', saved=0,
                   expected=board.get('count', 0), error='', created=time.time(), updated=time.time(),
                   changeVersion=old.get('changeVersion', 0), dirty=old.get('dirty', False))
        manifest = pinterest.read(directory / '.pinterest-board.json')
        job['saved'] = sum(Path(i['image']).is_file() for i in manifest.get('items', []))
        data['jobs'][board['id']] = job
        data.pop('error', None)
    if launch:
        start_worker()
    return job


def enqueue_all(cfg):
    boards = [validate_board(board) for board in cfg.get('boards', [])]
    if not boards:
        raise ValueError('Нет досок для загрузки')
    try:
        for board in boards:
            enqueue(dict(board=board, saveDirectory=cfg.get('saveDirectory', '~/Pictures')), launch=False)
    finally:
        # Start the queue once, including any jobs added before a filesystem error.
        start_worker()


def mark_changed(board_id):
    with locked() as data:
        job = data['jobs'].get(str(board_id))
        if job:
            job.update(dirty=True, changeVersion=job.get('changeVersion', 0) + 1)


def observe_boards(boards):
    with locked() as data:
        for board in boards:
            job = data['jobs'].get(str(board['id']))
            if not job:
                continue
            modified = board.get('modifiedAt', 0)
            if modified > job.get('syncedAt', job.get('updated', 0)):
                job['dirty'] = True
                if modified > job.get('observedModifiedAt', 0):
                    job['changeVersion'] = job.get('changeVersion', 0) + 1
                    job['observedModifiedAt'] = modified
            if (board.get('count', 0) > job.get('syncedPinCount', job.get('expected', 0))
                    or ('syncedAt' not in job and board.get('count', 0) > job.get('saved', 0))):
                job['dirty'] = True
            job['onlineCount'] = board.get('count', 0)


def image_item(path, board):
    meta = pinterest.read(Path(str(path) + '.json'))
    pin_id = str(meta.get('id', ''))
    return dict(image=str(path), url=meta.get('images', {}).get('orig', {}).get('url', ''),
                title=meta.get('title') or meta.get('description') or board['name'],
                credit='Pinterest · ' + board['url'].split('/')[1] + ' / ' + board['name'],
                page='https://www.pinterest.com/pin/' + pin_id + '/' if re.fullmatch(r'[A-Za-z0-9_-]+', pin_id) else 'https://www.pinterest.com' + board['url'],
                size=str(meta.get('width', '?')) + '×' + str(meta.get('height', '?')))


def inventory(directory, board):
    return [image_item(p, board) for p in sorted(directory.iterdir())
            if p.suffix.lower() in EXTENSIONS and p.is_file() and p.stat().st_size > 0]


def run_job(board_id, job):
    directory = Path(job['directory'])
    board = job['board']
    log_path = STATE_DIR / ('gallery-' + board_id + '.log')
    sync_started = time.time()
    sync_version = job.get('changeVersion', 0)
    update(board_id, status='downloading', pid=os.getpid(), error='', phase='Получаю изображения Pinterest')
    args = [executable(), '--config-ignore', '--no-input', '--no-colors', '--quiet',
            '--retries', '2', '--http-timeout', '30', '-D', str(directory),
            '-f', '{id}_{num}.{extension}', '--write-metadata',
            '--Print', 'after:PW_FILE:{_path}', '--Print', 'skip:PW_FILE:{_path}',
            '-o', 'extractor.pinterest.videos=false',
            '--filter', "extension in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'avif')",
            'https://www.pinterest.com' + board['url']]
    runner = Path(__file__).with_name('gallery_runner.py')
    interpreter = GALLERY.with_name('python')
    if interpreter.is_file() and runner.is_file():
        args[:1] = [str(interpreter), str(runner)]
    cookies = STATE_DIR / 'pinterest-cookies.txt'
    if cookies.is_file():
        args[args.index('--config-ignore'):args.index('--config-ignore')] = ['--cookies', str(cookies)]
    items = inventory(directory, board)
    known = {i['image']: i for i in items}
    atomic(directory / '.pinterest-board.json', dict(board=board, items=items))
    try:
        with log_path.open('w') as log:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log,
                                       text=True, env=dict(os.environ, PYTHONUNBUFFERED='1'))
            for line in process.stdout:
                if not line.startswith('PW_FILE:'):
                    continue
                path = Path(line.strip()[8:])
                if path.parent != directory or path.suffix.lower() not in EXTENSIONS or not path.is_file():
                    continue
                known[str(path)] = image_item(path, board)
                atomic(directory / '.pinterest-board.json', dict(board=board, items=list(known.values())))
                update(board_id, saved=len(known), phase='Сохраняю изображения', current=path.name)
            code = process.wait()
        items = inventory(directory, board)
        atomic(directory / '.pinterest-board.json', dict(board=board, items=items))
        error = ''
        if code:
            error = log_path.read_text(errors='replace')[-1800:].strip() or 'gallery-dl завершился с кодом ' + str(code)
        with locked() as data:
            current = data['jobs'][board_id]
            changed_during_download = current.get('changeVersion', 0) != sync_version
            current.update(status='completed' if not code else 'error', saved=len(items),
                           total=len(items) if not code else None, error=error,
                           phase='Готово' if not code else 'Загрузка прервана', pid=None, updated=time.time())
            if not code:
                current.update(dirty=changed_during_download or len(items) < current.get('expected', 0), syncedAt=sync_started,
                               syncedPinCount=current.get('onlineCount', job.get('expected', 0)))

    except Exception as error:
        update(board_id, status='error', error=str(error), pid=None)


def worker():
    while True:
        with locked() as data:
            next_job = next(((key, job) for key, job in data['jobs'].items() if job['status'] == 'queued'), None)
            if next_job is None:
                return
            board_id, job = next_job
            # Claim under the state lock; the process lock serializes downloads.
            job.update(status='downloading', pid=os.getpid(), updated=time.time())
        run_job(board_id, job)


def snapshot():
    with locked() as data:
        for job in data['jobs'].values():
            if job['status'] == 'completed':
                manifest = pinterest.read(Path(job['directory']) / '.pinterest-board.json')
                actual = sum(Path(i['image']).is_file() for i in manifest.get('items', []))
                if actual != job.get('saved', 0):
                    job.update(status='error', saved=actual, error='Часть сохранённых файлов отсутствует. Нажмите «Повторить».')
            if job['status'] == 'downloading':
                try:
                    cmdline = Path('/proc/' + str(job.get('pid', 0)) + '/cmdline').read_bytes()
                    alive = b'downloads.py' in cmdline and b'worker' in cmdline
                except OSError:
                    alive = False
                if not alive:
                    job.update(status='error', error='Загрузка прервана. Нажмите «Повторить».', pid=None)
        result = dict(data)
        result['available'] = bool(executable())
    if any(j['status'] == 'queued' for j in result['jobs'].values()):
        start_worker()
    return result


def local_items(board_id):
    job = pinterest.read(STATE).get('jobs', {}).get(str(board_id), {})
    if not job.get('directory'):
        return [], job
    manifest = pinterest.read(Path(job['directory']) / '.pinterest-board.json')
    items = [i for i in manifest.get('items', []) if Path(i['image']).is_file()]
    return items, job


def main():
    action = sys.argv[1]
    if action == 'worker':
        worker()
        return
    cfg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    try:
        if action == 'start':
            enqueue(cfg)
        elif action == 'start-all':
            enqueue_all(cfg)
        elif action == 'validate':
            print(json.dumps({'ok': True, 'directory': str(destination(cfg['directory'])), 'requestId': time.time_ns()}))
            return
        print(json.dumps(snapshot(), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': str(error), 'requestId': time.time_ns()}, ensure_ascii=False))
        # Start errors are also visible in the Downloads window.
        if action in ('start', 'start-all'):
            with locked() as data:
                data['error'] = str(error)


if __name__ == '__main__':
    main()
