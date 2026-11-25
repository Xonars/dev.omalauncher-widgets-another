"""Shared phone/desktop favorites, with one-time import of legacy state."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path.home() / '.local/state/omalauncher-themes'
ROOT.mkdir(parents=True, exist_ok=True)
with (ROOT / 'favorites.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    path = ROOT / 'favorites.json'
    data = json.loads(path.read_text()) if path.exists() else {'names': [], 'imports': []}
    action, value = sys.argv[1:3]
    if action == 'import':
        names = json.loads(value)
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError('Expected theme names')
        key = hashlib.sha256(json.dumps(sorted(set(names))).encode()).hexdigest()
        if key not in data['imports']:
            data['names'] = list(dict.fromkeys(data['names'] + names))
            data['imports'].append(key)
    elif action == 'toggle':
        if value in data['names']:
            data['names'].remove(value)
        else:
            data['names'].append(value)
    else:
        raise ValueError('Unknown action')
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, path)
