"""Local theme catalog and atomic edits of the launcher's two appearance keys."""
import json
import os
from pathlib import Path
import re
import sys
import tomllib

HOME = Path.home()
STYLE = HOME / '.config/omalauncher/style/style.toml'
BASES = [HOME / '.local/share/omarchy/themes', HOME / '.config/omarchy/themes']
EXT = {'.png', '.jpg', '.jpeg', '.webp'}


def catalog():
    found = {}
    for base in BASES:
        if base.is_dir():
            found.update({p.name: p for p in sorted(base.iterdir()) if p.is_dir()})
    result = []
    for name, folder in sorted(found.items()):
        try:
            colors = tomllib.loads((folder / 'colors.toml').read_text())
        except (OSError, ValueError):
            colors = {}
        walls = {}
        for root in [b / name / 'backgrounds' for b in BASES] + [HOME / '.config/omarchy/backgrounds' / name]:
            if root.is_dir():
                walls.update({p.name: p for p in sorted(root.iterdir()) if p.is_file() and p.suffix.lower() in EXT})
        pictures = [{'name': n, 'path': str(p), 'theme': name} for n, p in sorted(walls.items())]
        preview = next((str(p) for p in sorted(folder.glob('preview.*')) if p.suffix.lower() in EXT), None)
        swatch = [colors.get(k, colors.get(f'color{i}')) for k, i in [('background', 0), ('foreground', 7), ('accent', 4), ('red', 1), ('green', 2), ('yellow', 3), ('blue', 4), ('magenta', 5)]]
        result.append({'name': name, 'preview': preview or (pictures[0]['path'] if pictures else None), 'swatch': [c for c in swatch if isinstance(c, str)], 'walls': pictures})
    return result


def set_appearance(theme, background=None):
    themes = catalog()
    item = next((t for t in themes if t['name'] == theme), None)
    if item is None:
        raise ValueError('Тема больше не доступна')
    if background is not None and not any(w['name'] == background for w in item['walls']):
        raise ValueError('Обои больше не доступны')
    text = STYLE.read_text() if STYLE.exists() else 'version = 1\n'
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines) if re.match(r'\s*\[', line)), len(lines))
    head = [line for line in lines[:end] if not re.match(r'\s*(theme|background)\s*=', line)]
    head.append('theme = ' + json.dumps(theme))
    if background is not None:
        head.append('background = ' + json.dumps(background))
    updated = '\n'.join(head + lines[end:]) + '\n'
    tomllib.loads(updated)
    temp = STYLE.with_name('style.toml.theme-catalog.tmp')
    temp.write_text(updated)
    os.replace(temp, STYLE)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'set':
        try:
            set_appearance(*sys.argv[2:])
            print('')
        except Exception as error:
            print(str(error))
        return
    style = tomllib.loads(STYLE.read_text()) if STYLE.exists() else {}
    themes = catalog()
    current = style.get('theme')
    active = next((t for t in themes if t['name'] == current), {})
    print(json.dumps({'theme': current, 'background': style.get('background') or next(iter(active.get('walls', [])), {}).get('name'), 'themes': themes}, ensure_ascii=False))


if __name__ == '__main__':
    main()
