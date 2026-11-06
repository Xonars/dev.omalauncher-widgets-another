#!/usr/bin/env python3
"""Fail publication if a declared entry is missing, skipped, or has corrupt resources."""
from pathlib import Path
import hashlib,json,re,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
entries=json.loads((ROOT/'store-collection.json').read_text())
expected={x['path'] for x in entries}|{'widgets/xonars/battery-time/widget.owl'}
actual={str(p.relative_to(ROOT)) for kind in ('apps','widgets','faces') for p in (ROOT/kind).glob('*/*/*.owl')}
assert expected==actual, f'Unexpected or missing store OWL: {expected ^ actual}'
for row in entries:
 p=ROOT/row['path']; assert p.with_name('README.md').is_file()
 assert 'Автор оригинала:' in p.with_name('README.md').read_text()
 if row['resources']:
  package=ROOT/row['resources']
  assert package.is_file() and package.name in p.read_text()
  assert package.stem in p.read_text()
for p in (ROOT/'resources').glob('*.zip'):
 assert hashlib.sha256(p.read_bytes()).hexdigest()==p.stem, f'Resource digest: {p}'
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  for name in z.namelist():
   assert name.startswith(('widgets/','support/')) and '..' not in Path(name).parts
   assert not name.endswith(('.pyc','.apk','.keystore','.secret'))
if '--catalogs' in sys.argv:
 published=set()
 for filename,kind in [('apps.json','apps'),('index.json','widgets'),('faces.json','faces')]:
  for e in json.loads((ROOT/filename).read_text())[kind]:
   p=ROOT/e['path']; assert hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256']
   assert e.get('preview') and (ROOT/e['preview']).is_file()
   assert (ROOT/e['preview']).stat().st_size<=300*1024
   published.add(e['path'])
 assert published==expected, f'Compiler skipped declared entries: {expected-published}'
print(f'Local collection verified: {len(expected)} store entries')
