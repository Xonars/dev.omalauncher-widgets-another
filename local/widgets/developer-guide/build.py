#!/usr/bin/env python3
"""Rebuild the standalone offline OWL app and Markdown from articles.json."""
import json
from pathlib import Path
root = Path(__file__).resolve().parent
articles = json.loads((root/'articles.json').read_text())
assert len({a['id'] for a in articles}) == len(articles)
template = (root/'app.template').read_text()
# OWL interpolates ${...} even in ordinary strings. Escape literal $ in shell snippets.
data = json.dumps(articles, ensure_ascii=False, indent=2).replace('${', '\\${')
(root.parent/'81-developer-guide.owl').write_text(template.replace('ARTICLES_DATA', data))
md = ['# Справочник разработчика', 'Локальная база знаний · редакция 26.10.2026']
for a in articles:
    md += ['\n## '+a['title'], a['desc']]
    for b in a['blocks']:
        md += [b['text']]
        if b['code']: md += ['```bash\n'+b['code']+'\n```']
(root/'README.md').write_text('\n\n'.join(md)+'\n')
print(f'Собрано статей: {len(articles)}')
