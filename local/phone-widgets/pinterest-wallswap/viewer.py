#!/usr/bin/env python3
"""Local image queue, filled by a detached worker. Never changes wallpapers."""
import contextlib
import fcntl
import hashlib
import io
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import pinterest
import downloads

STATE = pinterest.ROOT / 'viewer.json'

@contextlib.contextmanager
def locked():
    with (pinterest.ROOT / 'viewer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = pinterest.read(STATE)
        data.setdefault('history', [])
        data.setdefault('index', -1)
        data.setdefault('queue', [])
        yield data
        pinterest.save(STATE, data)

def select(data, item):
    data['history'] = (data['history'][:data['index'] + 1] + [item])[-40:]
    data['index'] = len(data['history']) - 1
    data['error'] = ''
    data['pending'] = False

def info(data):
    index = data['index']
    current = dict(data['history'][index]) if 0 <= index < len(data['history']) else {}
    current.update(hasPrevious=(data.get('localIndex', 0) > 0 if data.get('mode') == 'local' else index > 0), error=data.get('error', ''), ready=len(data['queue']), loading=data.get('pending', False))
    return current

def start_worker():
    lock = (pinterest.ROOT / 'prefetch.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', str(lock.fileno())],
                     pass_fds=(lock.fileno(),), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    lock.close()

def download(row):
    url, title, credit, page, width, height = row
    image = pinterest.ROOT / ('view-' + hashlib.sha256(url.encode()).hexdigest()[:24] + '.' + url.rsplit('.', 1)[-1])
    if not image.is_file():
        with tempfile.TemporaryDirectory(dir=pinterest.ROOT) as directory:
            temp = Path(directory) / 'image'
            subprocess.run(['curl', '--fail', '--silent', '--show-error', '--proto', '=https', '--max-time', '45',
                            '--max-filesize', '80000000', '-o', str(temp), url], check=True)
            temp.replace(image)
    return dict(image=str(image), url=url, title=title, credit=credit, page=page, size=f'{width}×{height}')

def worker():
    # The inherited descriptor holds the worker lock until this process exits.
    for attempt in range(10):
        with locked() as data:
            cfg = data.get('cfg', {})
            signature = data.get('signature')
            if data.get('mode') == 'local' or len(data['queue']) >= 4: return
            if data.get('retryAt', 0) > time.time(): return
            seen = {item.get('url', item.get('image')) for item in data['history'] + data['queue']}
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output): pinterest.candidates(cfg)
            rows = [line.split('\t') for line in output.getvalue().splitlines()]
            random.shuffle(rows)
            choices = [row for row in rows if len(row) == 6 and row[0] not in seen]
            if not choices: continue
            for row in choices[:4]:
                item = download(row)
                with locked() as data:
                    if data.get('signature') != signature or data.get('mode') == 'local': return
                    item['signature'] = signature
                    if data.get('pending'): select(data, item)
                    else: data['queue'].append(item)
                    data['error'] = ''
                    if data.get('mode') == 'local' or len(data['queue']) >= 4: return
        except Exception as error:
            with locked() as data:
                if data.get('signature') != signature or data.get('mode') == 'local': return
                data['error'] = str(error)
    with locked() as data:
        if data.get('signature') == signature and data.get('mode') != 'local':
            data['pending'] = False
            data['retryAt'] = time.time() + 30
            if not data['queue']: data['error'] = data.get('error') or 'Нет новых изображений. Попробуйте другие доски.'

def main():
    action = sys.argv[1]
    if action == 'worker':
        worker()
        return
    cfg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    if len(cfg.get('boards', [])) != 1:
        print(json.dumps({'error': 'Откройте одну доску'}))
        return
    signature = json.dumps(cfg, sort_keys=True)
    local, job = downloads.local_items(cfg['boards'][0])
    if local or job.get('status') == 'completed':
        with locked() as data:
            position = data.get('localIndex', 0) if data.get('signature') == signature and data.get('mode') == 'local' else 0
            if action == 'next': position += 1
            elif action == 'prev': position -= 1
            position = max(0, min(position, len(local) - 1))
            item = dict(local[position], signature=signature) if local else None
            data.update(signature=signature, cfg=cfg, mode='local', localIndex=position,
                        localCount=len(local), localDirectory=job.get('directory', ''),
                        history=[item] if item else [], index=0 if item else -1,
                        queue=[], pending=False, error='' if local else 'Нет сохранённых изображений')
            result = info(data)
        print(json.dumps(result, ensure_ascii=False))
        return
    with locked() as data:
        if data.get('signature') != signature or data.get('mode') == 'local':
            data.update(signature=signature, cfg=cfg, mode='online', history=[], index=-1, queue=[], pending=False, error='', retryAt=0)
        if action == 'open':
            if data['index'] < 0:
                data.update(pending=True, error='', retryAt=0)
        elif action == 'next':
            following = data['index'] + 1
            if following < len(data['history']) and data['history'][following].get('signature') == signature:
                data['index'] = following
                data['error'] = ''
            elif data['queue']:
                select(data, data['queue'].pop(0))
            else:
                data.update(pending=True, error='', retryAt=0)
        elif action == 'prev' and data['index'] > 0:
            data['index'] -= 1
            data.update(error='', pending=False)
        result = info(data)
        needs_worker = len(data['queue']) < 4
    if needs_worker: start_worker()
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
