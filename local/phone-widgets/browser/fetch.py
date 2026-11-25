#!/usr/bin/env python3
"""Fetch a public HTML page and expose bounded native OWL reader blocks."""
import json
import re
import sys
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup, NavigableString


def fetch(raw):
    raw = raw.strip()
    if raw == 'browser:home':
        return dict(url=raw, title='Веб в цветах вашей темы', blocks=[
            dict(id=0, kind='h1', text='Browser', spans=[]),
            dict(id=1, kind='p', text='Экспериментальный браузер на Owl. Введите адрес сайта сверху и нажмите Enter.', spans=[]),
            dict(id=2, kind='h2', text='Страница становится частью темы', spans=[]),
            dict(id=3, kind='p', text='Текст, заголовки, фон и ссылки используют цвета лаунчера и меняются вместе с темой.', spans=[]),
            dict(id=4, kind='p', text='Это режим чтения HTML: без JavaScript, форм, изображений и исходной вёрстки. Для перехода нажмите «Ссылки». Полную версию страницы можно открыть кнопкой ↗.', spans=[]),
        ], links=[dict(text='Example · простая тестовая страница', url='https://example.com/'), dict(text='Википедия', url='https://ru.wikipedia.org/wiki/Заглавная_страница'), dict(text='Arch Linux', url='https://archlinux.org/')], error='')
    if '://' not in raw:
        raw = 'https://' + raw
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Введите адрес http:// или https:// без логина и пароля.')
    # Encode Unicode paths and international hostnames while retaining URL separators.
    host = parts.hostname.encode('idna').decode()
    if ':' in host:
        host = '[' + host + ']'
    if parts.port:
        host += ':' + str(parts.port)
    address = urllib.parse.urlunsplit((parts.scheme, host, urllib.parse.quote(parts.path, safe='/%:@!$&\'()*+,;=-._~'), urllib.parse.quote(parts.query, safe='=&%/:?@!$\'()*+,;~-._'), ''))
    req = urllib.request.Request(address, headers={'User-Agent': 'Mozilla/5.0 (compatible; OwlBrowser/1.0)', 'Accept': 'text/html, text/plain;q=0.9', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=15) as response:
        final = response.url
        mime = response.headers.get_content_type()
        if mime not in ('text/html', 'application/xhtml+xml', 'text/plain'):
            raise ValueError('Этот формат не поддерживается: ' + mime)
        data = response.read(2000001)
        if len(data) > 2000000:
            raise ValueError('Страница больше 2 МБ. Откройте её во внешнем браузере.')
        charset = response.headers.get_content_charset()
    if mime == 'text/plain':
        text = data.decode(charset or 'utf-8', errors='replace')
        return dict(url=final, title=parts.hostname, blocks=[dict(id=i, kind='p', text=t[:5000], spans=[]) for i, t in enumerate(text.split('\n\n')[:180]) if t.strip()], links=[], error='')
    soup = BeautifulSoup(data, 'html.parser', from_encoding=charset)
    title = soup.title.get_text(' ', strip=True) if soup.title else parts.hostname
    base = soup.find('base', href=True)
    base_url = urllib.parse.urljoin(final, base['href']) if base else final
    for el in soup.select('script, style, noscript, template, svg, iframe, head, [hidden], [aria-hidden="true"]'):
        el.decompose()
    root = soup.find('article') or soup.find('main') or soup.body or soup
    links, seen = [], set()
    for a in root.find_all('a', href=True):
        target = urllib.parse.urljoin(base_url, a['href'])
        label = a.get_text(' ', strip=True)
        if label and urllib.parse.urlsplit(target).scheme in ('http', 'https') and target not in seen:
            seen.add(target)
            links.append(dict(text=label[:180], url=target))
            if len(links) >= 200:
                break
    tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'pre', 'blockquote', 'td', 'dt', 'dd']
    blocks = []
    for el in root.find_all(tags):
        if el.find(tags):
            continue
        text = el.get_text(' ', strip=True)
        if not text:
            continue
        spans = []
        for node in el.descendants:
            if isinstance(node, NavigableString):
                s = re.sub(r'\s+', ' ', str(node))
                if s.strip():
                    spans.append(dict(text=s, link=node.find_parent('a') is not None))
        blocks.append(dict(id=len(blocks), kind=el.name, text=text[:6000], spans=spans[:100] if len(text) < 6000 else []))
        if len(blocks) >= 180:
            break
    if not blocks:
        text = root.get_text(' ', strip=True)
        blocks = [dict(id=0, kind='p', text=text[:20000] or 'Сайт не отдал текст. Возможно, ему нужен JavaScript.', spans=[])]
    return dict(url=final, title=title, blocks=blocks, links=links, error='', truncated=len(blocks) >= 180)


if __name__ == '__main__':
    raw = sys.argv[1] if len(sys.argv) > 1 else 'browser:home'
    try:
        result = fetch(raw)
    except Exception as exc:
        result = dict(url=raw, title='Не удалось открыть страницу', blocks=[], links=[], error=str(exc))
    result['request'] = raw
    result['revision'] = sys.argv[2] if len(sys.argv) > 2 else '0'
    print(json.dumps(result, ensure_ascii=False))
