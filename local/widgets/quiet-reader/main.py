"""Minimal reader; Reader's EPUB/MOBI extractors retain their original licenses."""
import json
import sys
from pathlib import Path

CACHE = Path.home() / '.cache/owl-quiet-reader'
EXTENSIONS = ('.epub', '.mobi', '.txt')


def main():
    mode = sys.argv[1]
    path = Path(sys.argv[2]).expanduser().resolve()
    if mode == 'list':
        entries = sorted((p for p in path.iterdir() if not p.name.startswith('.')),
                         key=lambda p: (not p.is_dir(), p.name.casefold()))
        print(json.dumps(dict(path=str(path), parent=str(path.parent), entries=[
            dict(path=str(p), name=p.name, directory=p.is_dir()) for p in entries
            if p.is_dir() or p.suffix.lower() in EXTENSIONS][:1000]), ensure_ascii=False))
        return
    import reader
    CACHE.mkdir(parents=True, exist_ok=True)
    text, key = reader.book_text(dict(path=str(path)))
    # Native lazy rows: transfer text once, never spawn commands while scrolling.
    # At most 900 rows, below OWL's 1000-item limit, with no text omitted.
    target = max(900, (len(text) + 899) // 900)
    blocks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target)
        if end < len(text):
            boundary = text.find('\n\n', end, min(len(text), end + 240))
            if boundary < 0:
                boundary = text.find(' ', end, min(len(text), end + 160))
            if boundary >= 0:
                end = boundary + 1
        blocks.append(dict(id=len(blocks), text=text[start:end]))
        start = end
    print(json.dumps(dict(title=path.stem, key=key, blocks=blocks), ensure_ascii=False))



if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False))
