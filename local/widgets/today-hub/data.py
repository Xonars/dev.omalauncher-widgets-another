import json, sys, re, os
from pathlib import Path
base = Path.home() / 'notes'
base.mkdir(exist_ok=True)
todo = base / 'todo.md'
note = base / 'today.md'
action = sys.argv[1]
if action == 'done':
    rows = todo.read_text().splitlines(keepends=True) if todo.exists() else []
    idx = int(sys.argv[2])
    # Match the text too: a stale tile must never complete a different task.
    if 0 <= idx < len(rows):
        m = re.match(r'^\s*[-*] \[ \] (.*?)(?:\n)?$', rows[idx])
        if m and m.group(1) == sys.argv[3]:
            rows[idx] = rows[idx].replace('[ ]', '[x]', 1)
            tmp = todo.with_suffix('.tmp')
            tmp.write_text(''.join(rows)); os.replace(tmp, todo)
elif action == 'add':
    text = ' '.join(sys.argv[2].split())
    if text:
        with todo.open('a') as f: f.write('\n- [ ] ' + text + '\n')
elif action == 'note':
    tmp = note.with_suffix('.tmp')
    tmp.write_text(sys.argv[2].strip() + '\n'); os.replace(tmp, note)
elif action == 'read':
    items = []
    for i, line in enumerate(todo.read_text().splitlines() if todo.exists() else []):
        m = re.match(r'^\s*[-*] \[ \] (.*)$', line)
        if m: items.append({'line': i, 'text': m.group(1)})
    print(json.dumps({'items': items, 'note': note.read_text().strip() if note.exists() else ''}, ensure_ascii=False))
