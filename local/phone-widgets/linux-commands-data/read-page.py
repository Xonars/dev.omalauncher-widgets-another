import json
import pathlib
import sys
root = pathlib.Path(__file__).resolve().parent
lang, name = sys.argv[1:3]
rel = pathlib.PurePosixPath(name)
valid = not rel.is_absolute() and '..' not in rel.parts and rel.suffix == '.md'
translated = valid and lang == 'ru' and (root / 'ru' / rel).is_file()
path = root / ('ru' if translated else 'en') / rel
ok = valid and path.is_file()
print(json.dumps(dict(path=name, lang=lang, translated=translated, ok=ok, out=path.read_text() if ok else '')))
