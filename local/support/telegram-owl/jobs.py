"""One explicit user action per job; no automatic retries of outgoing messages."""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import client

ROOT = client.ROOT
STATUS = ROOT / 'transfer.json'
LOCK = ROOT / 'transfer.lock'


def save(record):
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False))
    temporary.replace(STATUS)


def read():
    try:
        return json.loads(STATUS.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def active(record):
    if record.get('status') not in ('queued', 'running'):
        return False
    try:
        os.kill(record['pid'], 0)
        return record['id'].encode() in Path(f"/proc/{record['pid']}/cmdline").read_bytes()
    except (ProcessLookupError, KeyError, FileNotFoundError):
        return False


def status():
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = read()
        if record.get('status') in ('queued', 'running') and not active(record):
            record.update(status='error', result=dict(ok=False, error=
                          'Операция прервана. Проверьте чат перед повторной отправкой.'))
            save(record)
        return record


def start(args):
    if not args or args[0] not in ('pick', 'send', 'send-file', 'download'):
        raise ValueError('Неизвестная операция')
    kind = args[0]
    count = {'pick': 1, 'send': 3, 'send-file': 4, 'download': 2}[kind]
    if len(args[1:]) != count:
        raise ValueError('Недостаточно параметров операции')
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if active(read()):
            raise ValueError('Дождитесь завершения текущей операции')
        record = dict(id=uuid.uuid4().hex, kind=kind, args=args[1:],
                      chat=int(args[1]), status='queued', progress=0)
        # The child waits on LOCK until its ID and PID have been saved.
        worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', record['id']],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        record['pid'] = worker.pid
        save(record)
    return dict(ok=True, job=record['id'])


async def pick_file():
    directory = ROOT / 'outbox' / uuid.uuid4().hex
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec('omalauncher', 'pick', str(directory),
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), 130)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    if process.returncode:
        if process.returncode == 1 and b'nothing picked' in err:
            return dict(ok=True, cancelled=True)
        raise ValueError(err.decode(errors='replace').strip() or 'Не удалось выбрать файл')
    paths = out.decode().strip().splitlines()
    if not paths:
        return dict(ok=True, cancelled=True)
    path = Path(paths[0]).resolve(strict=True)
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError('Не удалось прочитать выбранный файл')
    if path.stat().st_size > client.MAX_FILE_SIZE:
        path.unlink()
        raise ValueError('Пока поддерживаются файлы до 100 МБ')
    return dict(ok=True, path=str(path), name=path.name, size=path.stat().st_size)


async def run(record):
    if record['kind'] == 'pick':
        return await pick_file()
    # The picker must never hold the Telegram session lock.
    with (ROOT / 'lock').open('a') as lock:
        deadline = time.monotonic() + 55
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError('Telegram занят. Закройте другое окно входа и повторите операцию.')
                await asyncio.sleep(0.2)
        return await asyncio.wait_for(client.execute(record['kind'], record['args']), 600)


def worker(job_id):
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = read()
        if record.get('id') != job_id:
            return
        record['status'] = 'running'
        save(record)
    last_write = [0.0]

    def progress(current, total):
        if time.monotonic() - last_write[0] < 0.5 and current != total:
            return
        last_write[0] = time.monotonic()
        record.update(progress=int(current * 100 / total) if total else 0,
                      bytes=current, total=total)
        save(record)

    client.transfer_progress = progress
    try:
        result = asyncio.run(run(record))
        if result.get('authorized') is False:
            raise ValueError('Сессия завершена. Войдите в Telegram снова.')
        record.update(status='done', result=result, progress=100)
        if record['kind'] == 'send-file':
            # Remove only the private copy produced by our own picker.
            path = Path(record['args'][3]).resolve()
            outbox = (ROOT / 'outbox').resolve()
            if path.is_relative_to(outbox):
                try:
                    path.unlink(missing_ok=True)
                    path.parent.rmdir()
                except OSError:
                    pass
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        if type(exc).__name__ == 'FloodWaitError':
            message = f'Telegram просит подождать {exc.seconds} сек.'
        elif isinstance(exc, TimeoutError):
            message = 'Время операции истекло. Проверьте чат перед повторной отправкой.'
        elif record['kind'] in ('send', 'send-file') and not isinstance(exc, ValueError):
            message += ' Проверьте чат перед повторной отправкой.'
        record.update(status='error', result=dict(ok=False, error=message))
    save(record)


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == 'worker':
    worker(sys.argv[2])
