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

ROOT = Path.home() / '.local/state/owl-quiet-reader'
CACHE = Path.home() / '.cache/owl-quiet-reader'
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
                text = raw.decode('cp1251')
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


