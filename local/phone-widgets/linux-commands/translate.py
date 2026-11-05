"""Fetch and cache Russian Linux Command Library pages, preserving code."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = 'https://raw.githubusercontent.com/SimonSchubert/LinuxCommandLibrary/master/assets/'
CACHE = Path.home() / '.cache/omalauncher/linux-commands-ru-v2'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'LinuxCommands-Russian/1.0'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode('utf-8')


def translate(markdown):
    protected = []

    def protect(match):
        token = f'ZXQ{len(protected):05d}QXZ'
        protected.append(match.group())
        return token

    # Preserve section identifiers used by the OWL parser, fenced and inline code,
    # links (including command names), URLs, and option/shortcut labels in bold.
    names = set(re.findall(r'\]\(/man/([^/)]+)\)', markdown))
    names.update(['Bash', 'ZSH', 'Fish', 'bash', 'zsh', 'fish', 'cat', 'less', 'reset', 'history', 'rwx'])
    command_names = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    pattern = (r'^# SYNOPSIS\n[\s\S]*?(?=\n# |\Z)|```[\s\S]*?```|`[^`\n]+`|'
               r'\[[^\]\n]*\]\([^\n)]*\)|https?://[^\s)]+|'
               r'^# [A-Z][A-Z ]*$|\*\*[\w./+\-]+\*\*|_[A-Za-z][\w-]*_|'
               r'(?<!\w)--?[a-zA-Z][\w-]*|(?<!\w)(?:' + command_names + r')(?!\w)|'
               r'(?<=\| )(?:r|w|x)(?= \|)')
    masked = re.sub(pattern, protect, markdown, flags=re.M)
    chunks = []
    chunk = ''
    for line in masked.splitlines(keepends=True):
        # Split very long prose as well, never through a protected token.
        pieces = re.findall(r'.{1,1800}(?:\s+|$)|\S+', line) if len(line) > 2000 else [line]
        for piece in pieces:
            if len(chunk) + len(piece) > 2400:
                chunks.append(chunk)
                chunk = ''
            chunk += piece
    if chunk:
        chunks.append(chunk)
    translated = []
    for chunk in chunks:
        query = urllib.parse.urlencode({'client': 'gtx', 'sl': 'en', 'tl': 'ru', 'dt': 't', 'q': chunk})
        error = None
        for attempt in range(3):
            try:
                data = json.loads(fetch('https://translate.google.ru/translate_a/single?' + query))
                result = ''.join(segment[0] or '' for segment in data[0])
                expected = re.findall(r'ZXQ\d{5}QXZ', chunk)
                actual = re.findall(r'ZXQ\d{5}QXZ', result)
                if sorted(expected) != sorted(actual):
                    raise ValueError('Сервис перевода изменил защищённые фрагменты')
                translated.append(result)
                break
            except Exception as exc:
                error = exc
                if attempt == 2:
                    raise error
                time.sleep(attempt + 1)
    result = '\n'.join(translated)
    for i, original in enumerate(protected):
        result = result.replace(f'ZXQ{i:05d}QXZ', original)
    return result


def main(page):
    if not re.fullmatch(r'tips\.md|(?:commands|basics)/[\w.+-]+\.md', page):
        raise ValueError('Недопустимый адрес статьи')
    if page == 'tips.md':
        bundled = Path(__file__).with_name('tips-ru.md')
        if bundled.exists():
            return bundled.read_text()
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / (hashlib.sha256(page.encode()).hexdigest() + '.json')
    saved = None
    try:
        saved = json.loads(target.read_text())
    except (OSError, ValueError):
        pass
    if saved and time.time() - saved['time'] < 86400:
        return saved['text']
    try:
        original = fetch(BASE + urllib.parse.quote(page, safe='/'))
        digest = hashlib.sha256(original.encode()).hexdigest()
        text = saved['text'] if saved and saved['digest'] == digest else translate(original)
        temp = target.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps({'time': time.time(), 'digest': digest, 'text': text}, ensure_ascii=False))
        temp.replace(target)
        return text
    except Exception:
        if saved:
            return saved['text']
        raise


if __name__ == '__main__':
    try:
        print(main(sys.argv[1]))
    except Exception as exc:
        print('Не удалось загрузить русский перевод: ' + str(exc), file=sys.stderr)
        sys.exit(1)
