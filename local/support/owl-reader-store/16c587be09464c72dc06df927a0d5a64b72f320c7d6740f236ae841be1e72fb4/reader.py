#!/usr/bin/env python3
"""Local EPUB/TXT reader and OPDS 1/2 client for reader.owl.

No EPUB content is executed and ZIP members are never extracted to disk.
Reading positions use text offsets, so changing typography preserves the place.
"""
import bisect
import fcntl
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import sys
import time
import warnings
from urllib.parse import unquote, urljoin, urlparse
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path.home() / '.local/state/owl-reader-store'
CACHE = Path.home() / '.cache/owl-reader-store'
STATE = ROOT / 'state.json'
FONT = '/usr/share/fonts/TTF/DejaVuSerif.ttf'
MAX_BOOK = 40 * 1024 * 1024
BOOK_EXTENSIONS = ('.epub', '.txt', '.mobi')
ATOM = '{http://www.w3.org/2005/Atom}'
SESSION = None
DEFAULT_CATALOGS = [
    dict(name='Wolne Lektury', url='https://wolnelektury.pl/opds/',
         description='Polish literature and classics.'),
    dict(name='Project Gutenberg', url='https://www.gutenberg.org/ebooks.opds/',
         description='Public-domain books in many languages.'),
    dict(name='The Anarchist Library', url='https://theanarchistlibrary.org/opds',
         description='English-language anarchist writing, social theory and history.'),
    dict(name='textos.info', url='https://www.textos.info/opds',
         description='Spanish literature, short stories and contemporary writing.'),
    dict(name='Ebooks libres et gratuits', url='https://www.ebooksgratuits.com/opds/',
         description='French-language novels, stories and essays.'),
]


def atomic(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def defaults():
    folder = Path.home() / 'Books'
    folder.mkdir(exist_ok=True)
    return dict(folder=str(folder), font=20, spacing=1.55, margin=24,
                theme='paper', width=400, height=800, inset=24,
                catalogs=[c.copy() for c in DEFAULT_CATALOGS],
                books=[], current=None, positions={}, statuses={}, page=0, total=0, lines=[],
                feed=None, trail=[], message='', revision=0)


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def xml_text(root, name, fallback=''):
    return next((''.join(e.itertext()).strip() for e in root.iter()
                 if local_name(e.tag) == name), fallback)


def book_id(path):
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]


def read_member(z, name):
    info = z.getinfo(name)
    if info.file_size > 20 * 1024 * 1024:
        raise ValueError('An EPUB section is too large (20 MB limit).')
    return z.read(info)


def epub_package(z):
    if sum(i.file_size for i in z.infolist()) > 100 * 1024 * 1024:
        raise ValueError('The uncompressed EPUB exceeds 100 MB.')
    container = ET.fromstring(read_member(z, 'META-INF/container.xml'))
    opf = next(e.attrib['full-path'] for e in container.iter()
               if local_name(e.tag) == 'rootfile')
    return opf, ET.fromstring(read_member(z, opf))


def metadata(path):
    title, author = path.stem, ''
    if path.suffix.lower() == '.epub':
        with zipfile.ZipFile(path) as z:
            _, package = epub_package(z)
            title = xml_text(package, 'title', title)
            author = xml_text(package, 'creator')
    elif path.suffix.lower() == '.mobi':
        from mobi_support import mobi_info
        info = mobi_info(path)
        title, author = info['title'], info['author']
    return dict(id=book_id(path), path=str(path), title=title, author=author,
                format=path.suffix[1:].upper())


def scan(s):
    folder = Path(s['folder'])
    if not folder.is_dir():
        raise ValueError('The books folder is not accessible. Choose another folder in Settings.')
    index_path = CACHE / 'metadata-v1.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    updated = {}
    books, skipped = [], 0
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in BOOK_EXTENSIONS:
            try:
                stat = path.stat()
                signature = [stat.st_size, stat.st_mtime_ns]
                entry = index.get(str(path))
                book = entry['book'] if entry and entry['signature'] == signature else metadata(path)
                books.append(book)
                updated[str(path)] = dict(signature=signature, book=book)
            except Exception:
                skipped += 1
    s['books'] = sorted(books, key=lambda b: b['title'].casefold())
    if updated != index:
        atomic(index_path, updated)
    s['message'] = f'Skipped {skipped} unreadable book(s).' if skipped else ''


def plain_html(raw):
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)
    soup = BeautifulSoup(raw, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'svg', 'noscript']):
        tag.decompose()
    for tag in soup.find_all('br'):
        tag.replace_with('\n')
    for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote', 'section', 'pre']):
        tag.insert_before('\n\n')
        tag.insert_after('\n\n')
    return '\n\n'.join(re.sub(r'\s+', ' ', p).strip()
                         for p in re.split(r'\n\s*\n', soup.get_text()) if p.strip())


def text_key(book):
    path = Path(book['path'])
    st = path.stat()
    return hashlib.sha256(f'{path}:{st.st_size}:{st.st_mtime_ns}:v2'.encode()).hexdigest()


def epub_text(path):
    with zipfile.ZipFile(path) as z:
        opf, package = epub_package(z)
        manifest = {e.attrib['id']: e.attrib for e in package.iter()
                    if local_name(e.tag) == 'item'}
        parts = []
        for ref in package.iter():
            if local_name(ref.tag) != 'itemref' or ref.get('linear') == 'no':
                continue
            item = manifest.get(ref.get('idref'), {})
            href = unquote(item.get('href', '').split('#')[0])
            if href and item.get('media-type') in ('application/xhtml+xml', 'text/html'):
                member = posixpath.normpath(posixpath.join(posixpath.dirname(opf), href))
                parts.append(plain_html(read_member(z, member)))
        return '\n\n'.join(p for p in parts if p)


def book_text(book):
    path = Path(book['path'])
    key = text_key(book)
    cached = CACHE / f'{key}.json'
    if cached.exists():
        return json.loads(cached.read_text())['text'], key
    if path.stat().st_size > MAX_BOOK:
        raise ValueError('This book exceeds the 40 MB limit.')
    if path.suffix.lower() == '.txt':
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = raw.decode('cp1250')
            except UnicodeDecodeError:
                text = raw.decode('cp1252', errors='replace')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = '\n\n'.join(re.sub(r'\s+', ' ', p).strip()
                             for p in re.split(r'\n\s*\n', text) if p.strip())
    elif path.suffix.lower() == '.mobi':
        from mobi_support import unpack_mobi
        with unpack_mobi(path, CACHE) as output:
            epubs = sorted(output.rglob('*.epub'))
            if epubs:
                text = epub_text(epubs[0])
            elif (output / 'mobi7' / 'book.html').is_file():
                text = plain_html((output / 'mobi7' / 'book.html').read_bytes())
            else:
                raise ValueError('No readable text found in this MOBI book. Image-only books are not supported.')
    else:
        text = epub_text(path)
    if not text.strip():
        raise ValueError('No readable text found. Image-only and DRM-protected books are not supported.')
    atomic(cached, {'text': text})
    return text, key


def page_cache(s):
    key = text_key(s['current'])
    width = max(80, min(s['width'], 760) - 2 * s['margin'] - 4)
    height = max(40, s['height'] - 44 - 56 - s['inset'] - 20)
    line_height = s['font'] * s['spacing']
    count = max(1, math.floor(height / line_height))
    layout = f'{key}:{width}:{count}:{s["font"]}:{s["spacing"]}:v3'
    cache = CACHE / ('pages-' + hashlib.sha256(layout.encode()).hexdigest() + '.json')
    return cache, width, count


def paginate(s):
    cache, width, count = page_cache(s)
    if cache.exists():
        return json.loads(cache.read_text())
    text, _ = book_text(s['current'])
    from PIL import ImageFont
    font = ImageFont.truetype(FONT, s['font'] * 4)
    @lru_cache(maxsize=16384)
    def measure(text):
        return font.getlength(text) / 4
    rows, offsets = [], []
    line, start = '', 0
    # Tokens carry original offsets: no text is lost at page boundaries.
    for token in re.finditer(r'\n\n|[^\s]+', text):
        word = token.group()
        if word == '\n\n':
            if line:
                rows.append(line); offsets.append(start); line = ''
            if rows and rows[-1] != '':
                rows.append(''); offsets.append(token.start())
            continue
        candidate = f'{line} {word}' if line else word
        if measure(candidate) <= width:
            if not line:
                start = token.start()
            line = candidate
            continue
        if line:
            rows.append(line); offsets.append(start); line = ''
        if measure(word) <= width:
            line, start = word, token.start()
            continue
        # Split exceptionally long words/URLs, preserving their character offsets.
        for n, char in enumerate(word):
            prefix = ' ' if n == 0 and line else ''
            if line and measure(line + prefix + char) > width:
                rows.append(line); offsets.append(start); line = ''; prefix = ''
            if not line:
                start = token.start() + n
            line += prefix + char
    if line:
        rows.append(line); offsets.append(start)
    pages = [{'lines': rows[i:i + count], 'offset': offsets[i]}
             for i in range(0, len(rows), count)]
    atomic(cache, pages)
    return pages


def book_status(s, book):
    current = s.get('current') or {}
    return s.get('statuses', {}).get(book['id'],
        'reading' if current.get('id') == book['id'] or s['positions'].get(book['id'], 0) > 0 else 'new')


def record_progress(s, index, total):
    status = book_status(s, s['current'])
    s.setdefault('statuses', {})[s['current']['id']] = (
        'done' if index == total - 1 or status == 'done' else 'reading')


def publish_page(s, pages, index, navigate=True):
    start = max(0, index - 24)
    s.update(lines=pages[index]['lines'], page=index, total=len(pages),
             windowStart=start, pageWindow=pages[start:start + 80])
    s['positions'][s['current']['id']] = pages[index]['offset']
    if navigate:
        s['navigation'] = time.time_ns()


def checkpoint(s, page, layout):
    """Save a UI cursor without reading the book or resetting the UI cursor.

    A layout token prevents delayed saves from a previous book or typography
    from moving the current book. Existing page caches remain compatible.
    """
    if not s['current'] or not layout or layout != s.get('layoutKey'):
        return
    cache = CACHE / s['pageCache']
    pages = json.loads(cache.read_text())
    index = max(0, min(len(pages) - 1, int(page)))
    if index != s['page']:
        record_progress(s, index, len(pages))
    publish_page(s, pages, index, navigate=False)


def render(s, delta=0, jump=None):
    if not s['current']:
        s.update(lines=[], page=0, total=0, pageWindow=[], windowStart=0,
                 layoutKey='', navigation=time.time_ns())
        return
    pages = paginate(s)
    offset = s['positions'].get(s['current']['id'], 0)
    index = max(0, bisect.bisect_right([p['offset'] for p in pages], offset) - 1)
    index = max(0, min(len(pages) - 1, (jump if jump is not None else index + delta)))
    if delta or jump is not None:
        record_progress(s, index, len(pages))
    cache, _, _ = page_cache(s)
    # Include a navigation generation: a late save must not undo a subsequent
    # jump or reopening of the same book with identical typography.
    s.update(pageCache=cache.name, layoutKey=f'{cache.stem}:{time.time_ns()}')
    publish_page(s, pages, index)


def safe_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Enter an HTTP or HTTPS URL without embedded credentials.')
    return url


def fetch(url, limit=4 * 1024 * 1024):
    global SESSION
    if SESSION is None:
        import requests
        SESSION = requests.Session()
        SESSION.headers['User-Agent'] = 'OwlReader/1.0 (personal OPDS reader)'
    with SESSION.get(safe_url(url), timeout=(8, 22), stream=True) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for part in response.iter_content(65536):
            size += len(part)
            if size > limit:
                raise ValueError('The server response exceeds the size limit.')
            chunks.append(part)
        return b''.join(chunks), response.url


def resolved(base, href):
    url = urljoin(base, href)
    # Both default providers have legacy HTTP links, but support HTTPS.
    if urlparse(url).hostname in ('wolnelektury.pl', 'static.wolnelektury.pl', 'www.gutenberg.org', 'm.gutenberg.org', 'gutenberg.org'):
        url = re.sub(r'^http:', 'https:', url)
    return safe_url(url)


def link_choice(links, base):
    # Prefer EPUB when several formats are offered; use MOBI before plain text.
    for mime, fmt in [('application/epub+zip', 'epub'),
                      ('application/x-mobipocket-ebook', 'mobi'), ('text/plain', 'txt')]:
        for link in links:
            rel = link.get('rel', '')
            rels = rel if isinstance(rel, list) else [rel]
            typ = link.get('type', '').split(';')[0].strip().lower()
            if any('acquisition' in r for r in rels) and typ == mime:
                return dict(url=resolved(base, link.get('href', '')), kind='download', format=fmt)
    for link in links:
        typ = link.get('type', '')
        if 'atom+xml' in typ or 'opds+json' in typ:
            return dict(url=resolved(base, link.get('href', '')), kind='browse', format='')
    return None


def load_feed(url):
    cached = CACHE / ('feed-' + hashlib.sha256(url.encode()).hexdigest() + '.json')
    if cached.exists() and time.time() - cached.stat().st_mtime < 300:
        return json.loads(cached.read_text())
    raw, base = fetch(url)
    entries, search, next_url = [], '', ''
    if raw.lstrip().startswith(b'{'):
        feed = json.loads(raw)
        title = feed.get('metadata', {}).get('title', 'Catalog')
        links = feed.get('links', [])
        for group in [feed] + feed.get('groups', []):
            for entry in group.get('navigation', []) + group.get('publications', []):
                meta = entry.get('metadata', {})
                choice = link_choice(entry.get('links', []), base)
                if choice:
                    authors = meta.get('author', [])
                    if not isinstance(authors, list):
                        authors = [authors]
                    author = ', '.join(a if isinstance(a, str) else a.get('name', '') for a in authors)
                    entries.append(dict(title=meta.get('title', entry.get('title', 'Untitled')),
                                        author=author, **choice))
    else:
        feed = ET.fromstring(raw)
        title = feed.findtext(ATOM + 'title') or 'Catalog'
        links = [e.attrib for e in feed.findall(ATOM + 'link')]
        for entry in feed.findall(ATOM + 'entry'):
            choice = link_choice([e.attrib for e in entry.findall(ATOM + 'link')], base)
            if choice:
                title_text = entry.findtext(ATOM + 'title') or 'Untitled'
                # Navigation labels are UI; book titles remain in their original language.
                if choice['kind'] == 'browse':
                    title_text = {'Autorzy': 'Authors', 'Tytuły': 'Titles', 'Rodzaje': 'Literary forms',
                                  'Gatunki': 'Genres', 'Epoki': 'Periods', 'Motywy': 'Themes',
                                  'Moje półki': 'My shelves (sign-in required)',
                                  'Wszystkie książki': 'All books', 'Nowości': 'New books'}.get(title_text, title_text)
                entries.append(dict(title=title_text,
                                    author=entry.findtext(ATOM + 'author/' + ATOM + 'name') or '', **choice))
    for link in links:
        rel = link.get('rel', '')
        if rel == 'next':
            next_url = resolved(base, link['href'])
        if rel == 'search':
            href = resolved(base, link['href'])
            if 'opensearchdescription' in link.get('type', ''):
                try:
                    description, description_url = fetch(href)
                    for el in ET.fromstring(description).iter():
                        if local_name(el.tag) == 'Url' and ('atom+xml' in el.get('type', '') or 'opds+json' in el.get('type', '')):
                            search = resolved(description_url, el.get('template', ''))
                            break
                except Exception:
                    pass
            else:
                search = href
    result = dict(title=title, url=base, entries=entries[:500], next=next_url, search=search)
    atomic(cached, result)
    return result


def browse(s, url, push=True):
    feed = load_feed(url)
    if push and s['feed']:
        s['trail'].append(s['feed']['url'])
    s['feed'] = feed


def dispatch(s, args):
    action = args[0]
    s['message'] = ''
    if action in ('init', 'snapshot'):
        scan(s)
        render(s)
    elif action == 'layout':
        width, height, inset = (int(float(v)) for v in args[1:4])
        # Keyboard must not repaginate the book underneath settings.
        if inset < 120 and width > 100 and height > 150:
            if len(args) >= 6:
                checkpoint(s, args[4], args[5])
            if (width, height, inset) != (s['width'], s['height'], s['inset']) or 'pageWindow' not in s:
                s.update(width=width, height=height, inset=inset)
                render(s)
    elif action == 'scan':
        scan(s)
    elif action == 'folder':
        path = Path(args[1].strip()).expanduser()
        if not path.is_absolute():
            raise ValueError('Use an absolute folder path, or start it with ~/.')
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
            raise ValueError('This folder must be readable and writable.')
        s['folder'] = str(path.resolve())
        scan(s)
    elif action == 'open':
        if len(args) >= 4:
            checkpoint(s, args[2], args[3])
        book = next((b for b in s['books'] if b['id'] == args[1]), None)
        if not book:
            raise ValueError('Book not found. Refresh the library.')
        # Prepare the candidate before replacing the current book.
        candidate = s | {'current': book}
        render(candidate)
        s.update(candidate)
        if book_status(s, book) != 'done':
            s.setdefault('statuses', {})[book['id']] = 'reading'
    elif action == 'begin-reading':
        # Entering the reading view after a download does not go through open.
        # Ignore delayed events belonging to a previously selected book.
        if s['current'] and s['current']['id'] == args[1] and book_status(s, s['current']) != 'done':
            s.setdefault('statuses', {})[args[1]] = 'reading'
    elif action == 'status':
        book = next((b for b in s['books'] if b['id'] == args[1]), None)
        if not book:
            raise ValueError('Book not found. Refresh the library.')
        if args[2] not in ('new', 'reading', 'done'):
            raise ValueError('Choose New, Reading, or Done.')
        s.setdefault('statuses', {})[book['id']] = args[2]
    elif action == 'delete':
        book = next((b for b in s['books'] if b['id'] == args[1]), None)
        if not book:
            raise ValueError('Book not found. Refresh the library.')
        path = Path(book['path'])
        # Only unlink the selected library entry, never a resolved symlink
        # target, a directory, or a file outside the current books folder.
        if path.parent.resolve() != Path(s['folder']).resolve() or path.suffix.lower() not in BOOK_EXTENSIONS:
            raise ValueError('Only books in the selected books folder can be deleted.')
        path.unlink()
        s['positions'].pop(book['id'], None)
        s.setdefault('statuses', {}).pop(book['id'], None)
        if s['current'] and s['current']['id'] == book['id']:
            s['current'] = None
            render(s)
        scan(s)
        s['message'] = 'Book deleted from this device.'
    elif action == 'turn':
        render(s, delta=int(args[1]))
    elif action == 'jump':
        render(s, jump=int(args[1]) - 1)
    elif action == 'checkpoint':
        checkpoint(s, args[1], args[2])
    elif action == 'setting':
        if len(args) >= 5:
            checkpoint(s, args[3], args[4])
        key, val = args[1:3]
        if key == 'theme' and val in ('paper', 'sepia', 'night'):
            s[key] = val
        elif key == 'font':
            s[key] = max(14, min(32, int(float(val))))
        elif key == 'spacing':
            s[key] = max(1.2, min(2.0, float(val)))
        elif key == 'margin':
            s[key] = max(12, min(48, int(float(val))))
        else:
            raise ValueError('Unknown setting.')
        if key != 'theme':
            render(s)
    elif action == 'catalog-add':
        name, url = args[1].strip(), args[2].strip()
        if not name:
            raise ValueError('Enter a catalog name.')
        safe_url(url)
        if any(c['url'] == url for c in s['catalogs']):
            raise ValueError('This catalog has already been added.')
        catalog = dict(name=name, url=url)
        if len(args) > 3:
            catalog['description'] = args[3].strip()
        s['catalogs'].append(catalog)
    elif action == 'catalog-remove':
        s['catalogs'] = [c for c in s['catalogs'] if c['url'] != args[1]]
    elif action == 'catalog':
        feed = load_feed(args[1])
        s.update(feed=feed, trail=[])
    elif action == 'browse':
        browse(s, args[1])
    elif action == 'feed-back':
        if s['trail']:
            feed = load_feed(s['trail'][-1])
            s['trail'].pop()
            s['feed'] = feed
        else:
            s['feed'] = None
    elif action == 'search':
        template = (s['feed'] or {}).get('search', '')
        if not template:
            raise ValueError('This catalog does not advertise a search endpoint.')
        from urllib.parse import quote
        url = re.sub(r'\{searchTerms\??\}', quote(args[1], safe=''), template)
        url = re.sub(r'\{[^}]+\??\}', '', url)
        browse(s, url)
    elif action == 'download':
        url, title, fmt = args[1:4]
        if '.' + fmt not in BOOK_EXTENSIONS:
            raise ValueError('Only EPUB, MOBI and TXT downloads are supported.')
        data, _ = fetch(url, MAX_BOOK)
        name = re.sub(r'[^\w .()-]', '_', title).strip(' .')[:120] or 'Book'
        folder = Path(s['folder'])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{name}.{fmt}'
        n = 2
        while path.exists():
            path = folder / f'{name} ({n}).{fmt}'
            n += 1
        # Validate a temporary file before making it visible in the library.
        temp = folder / ('.download-' + str(os.getpid()) + '.' + fmt)
        try:
            temp.write_bytes(data)
            meta = metadata(temp)
            text, _ = book_text(meta)
            temp.replace(path)
            # Reuse validation's extracted text after the temporary download
            # gets its permanent name, rather than unpacking MOBI twice.
            atomic(CACHE / f'{text_key({"path": str(path)})}.json', {'text': text})
        finally:
            temp.unlink(missing_ok=True)
        scan(s)
        s['current'] = metadata(path)
        s.setdefault('statuses', {})[s['current']['id']] = 'new'
        render(s)
        s['message'] = 'Downloaded. Open Reading to start.'
    elif action == 'dismiss':
        pass
    else:
        raise ValueError('Unknown reader action.')


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:] == ['snapshot'] and STATE.exists():
        print(STATE.read_text())
        return
    with (ROOT / 'reader.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = json.loads(STATE.read_text()) if STATE.exists() else defaults()
        try:
            dispatch(s, sys.argv[1:] or ['init'])
            result = {'ok': True}
        except Exception as error:
            if type(error).__module__.startswith(('requests.', 'urllib3.')):
                message = 'Cannot reach this server. Check the URL and connection, then try again.'
            elif isinstance(error, (ET.ParseError, zipfile.BadZipFile)):
                message = 'This is not a valid OPDS feed or EPUB book.'
            else:
                message = str(error) or type(error).__name__
            s['message'] = message
            result = {'ok': False, 'error': message}
        s['revision'] = time.time_ns()
        result['revision'] = s['revision']
        atomic(STATE, s)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
