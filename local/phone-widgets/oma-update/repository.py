#!/usr/bin/env python3
"""Read-only repository dashboard. Fetch updates refs, never checks out or merges."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path('/root/dev.omalauncher-another')
CACHE = Path('/root/.cache/oma-updater')
CACHE.mkdir(parents=True, exist_ok=True)
SYNC = CACHE / 'repository-sync.json'

def git(*args):
    p = subprocess.run(['git', '--no-pager', *args], cwd=REPO, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[-1200:] or 'Ошибка Git')
    return p.stdout.strip()

def sync_state():
    try:
        return json.loads(SYNC.read_text())
    except (OSError, ValueError):
        return {}

def fetch():
    with (CACHE / 'repository-fetch.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        state = sync_state()
        errors = []
        for remote in ('origin', 'upstream'):
            try:
                p = subprocess.run(['git', 'fetch', '--no-tags', remote], cwd=REPO,
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=120, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
                if p.returncode:
                    raise RuntimeError(p.stderr.strip()[-900:])
                state[remote] = int(time.time())
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                errors.append(f'{remote}: {exc}')
        state.update(error='\n'.join(errors), attempted=int(time.time()))
        tmp = SYNC.with_suffix('.tmp')
        tmp.write_text(json.dumps(state))
        tmp.replace(SYNC)

def commits(revision):
    rows = git('log', '-n', '30', '--format=%h%x09%cs%x09%s', revision)
    return [dict(zip(('hash', 'date', 'subject'), row.split('\t', 2))) for row in rows.splitlines()]

def counts(base, ref):
    behind, ahead = map(int, git('rev-list', '--left-right', '--count', f'{base}...{ref}').split())
    return dict(ahead=ahead, behind=behind)

def dashboard(ref):
    branches = git('for-each-ref', '--format=%(refname:short)%09%(objectname:short)%09%(committerdate:short)%09%(symref)%09%(subject)', 'refs/heads', 'refs/remotes/origin', 'refs/remotes/upstream').splitlines()
    refs = []
    for row in branches:
        name, sha, date, symref, subject = row.split('\t', 4)
        if not symref:
            refs.append((name, sha, date, subject))
    allowed = {row[0] for row in refs}
    if ref not in allowed:
        raise RuntimeError('Ветка не найдена. Выберите существующую ветку.')
    base = 'upstream/main'
    result = dict(ref=ref, sync=sync_state(), head=git('branch', '--show-current'),
                  dirty=git('status', '--porcelain'), hash=git('rev-parse', '--short', ref),
                  upstream=git('rev-parse', '--short', base), fork=git('rev-parse', '--short', 'origin/main'),
                  fork_url='https://github.com/Xonars/dev.omalauncher-another', branches=[])
    result.update(counts(base, ref))
    result['published'] = counts('origin/main', 'HEAD')
    for name, sha, date, subject in refs[:60]:
        row = dict(name=name, hash=sha, date=date, subject=subject)
        try:
            row.update(counts(base, name))
        except RuntimeError:
            row.update(ahead=None, behind=None)
        result['branches'].append(row)
    result['own'] = commits(f'{base}..{ref}')
    result['incoming'] = commits(f'{ref}..{base}')
    result['recent'] = commits(ref)
    result['summary'] = git('diff', '--shortstat', base, ref)
    result['files'] = []
    for row in git('diff', '--numstat', base, ref).splitlines()[:60]:
        added, removed, path = row.split('\t', 2)
        result['files'].append(dict(path=path, added=added, removed=removed))
    result['patches'] = sum(row.startswith('+') for row in git('cherry', base, ref).splitlines())
    result['error'] = ''
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ref', default='origin/main')
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    try:
        if args.fetch:
            fetch()
            print(json.dumps(sync_state(), ensure_ascii=False))
        else:
            print(json.dumps(dashboard(args.ref), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps(dict(error=str(exc), sync=sync_state()), ensure_ascii=False))

if __name__ == '__main__':
    main()
