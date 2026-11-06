"""Local theme catalog and atomic edits of the launcher's two appearance keys."""
import json
import os
from pathlib import Path
import re
import sys
import tomllib
import time
from tempfile import NamedTemporaryFile

HOME = Path.home()
STYLE = HOME / '.config/omalauncher/style/style.toml'
BASES = [HOME / '.local/share/omarchy/themes', HOME / '.config/omarchy/themes']
EXT = {'.png', '.jpg', '.jpeg', '.webp'}
CACHE = HOME / '.cache/omalauncher/theme-catalog'


def thumbnail(path):
    """Small, decoded previews; original wallpaper paths remain selection keys."""
    import hashlib
    from PIL import Image, ImageOps

    try:
        path = Path(path)
        stat = path.stat()
        key = hashlib.sha256(f'{path}:{stat.st_mtime_ns}:{stat.st_size}:v1'.encode()).hexdigest()
        target = CACHE / (key + '.jpg')
        if not target.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            with Image.open(path) as source:
                source.thumbnail((640, 400))
                image = ImageOps.exif_transpose(source).convert('RGB')
                with NamedTemporaryFile(dir=CACHE, suffix='.jpg', delete=False) as temp:
                    temporary = Path(temp.name)
                try:
                    image.save(temporary, 'JPEG', quality=82)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        return str(target)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def catalog():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as thumbnails:
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
            wall_items = sorted(walls.items())
            previews = thumbnails.map(thumbnail, (p for _, p in wall_items))
            pictures = [{'name': n, 'path': str(p), 'preview': preview, 'theme': name}
                        for (n, p), preview in zip(wall_items, previews)]
            preview = next((thumb for p in sorted(folder.glob('preview.*')) if p.suffix.lower() in EXT and (thumb := thumbnail(p))), None)
            preview = preview or next((w['preview'] for w in pictures if w['preview']), None)
            swatch = [colors.get(k, colors.get(f'color{i}')) for k, i in [('background', 0), ('foreground', 7), ('accent', 4), ('red', 1), ('green', 2), ('yellow', 3), ('blue', 4), ('magenta', 5)]]
            result.append({'name': name, 'preview': preview, 'swatch': [c for c in swatch if isinstance(c, str)], 'walls': pictures})
        return result


def set_appearance(theme, background=None):
    # Applying a theme must not scan or decode the entire image catalog.
    if not theme or Path(theme).name != theme or theme in {'.', '..'}:
        raise ValueError('Недопустимое имя темы')
    if not any((base / theme).is_dir() for base in BASES):
        raise ValueError('Тема больше не доступна')
    if background is not None:
        roots = [base / theme / 'backgrounds' for base in BASES]
        roots.append(HOME / '.config/omarchy/backgrounds' / theme)
        if (not background or Path(background).name != background
                or Path(background).suffix.lower() not in EXT
                or not any((root / background).is_file() for root in roots)):
            raise ValueError('Обои больше не доступны')
    text = STYLE.read_text() if STYLE.exists() else 'version = 1\n'
    existing = tomllib.loads(text)
    if existing.get('theme') == theme and (background is None or existing.get('background') == background):
        return
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines) if re.match(r'\s*\[', line)), len(lines))
    head = [line for line in lines[:end] if not re.match(r'\s*(theme|background)\s*=', line)]
    head.append('theme = ' + json.dumps(theme))
    if background is not None:
        head.append('background = ' + json.dumps(background))
    updated = '\n'.join(head + lines[end:]) + '\n'
    tomllib.loads(updated)
    with NamedTemporaryFile(mode='w', dir=STYLE.parent, prefix='.theme-', delete=False) as output:
        output.write(updated)
        temp = Path(output.name)
    try:
        os.replace(temp, STYLE)
    finally:
        temp.unlink(missing_ok=True)


def cached_catalog():
    # Appearance changes refresh sources too: reuse catalog data for five minutes.
    target = CACHE / 'catalog-v2.json'
    try:
        if time.time() - target.stat().st_mtime < 300:
            return json.loads(target.read_text())
    except (OSError, ValueError):
        pass
    themes = catalog()
    CACHE.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode='w', dir=CACHE, delete=False) as output:
        json.dump(themes, output, ensure_ascii=False)
        temp = Path(output.name)
    try:
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return themes


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'set':
        try:
            set_appearance(*sys.argv[2:])
            print('')
        except Exception as error:
            print(str(error))
        return
    if mode == 'list':
        print(json.dumps({'themes': cached_catalog()}, ensure_ascii=False))
        return
    style = tomllib.loads(STYLE.read_text()) if STYLE.exists() else {}
    if mode == 'status':
        print(json.dumps({'theme': style.get('theme'), 'background': style.get('background')}, ensure_ascii=False))
        return
    themes = cached_catalog()
    current = style.get('theme')
    active = next((t for t in themes if t['name'] == current), {})
    print(json.dumps({'theme': current, 'background': style.get('background') or next(iter(active.get('walls', [])), {}).get('name'), 'themes': themes}, ensure_ascii=False))


if __name__ == '__main__':
    main()
