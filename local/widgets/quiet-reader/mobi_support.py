"""Bounded MOBI metadata reads and an isolated, bundled KindleUnpack worker."""
from contextlib import contextmanager
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def mobi_info(path):
    path = Path(path)
    size = path.stat().st_size
    with path.open('rb') as source:
        header = source.read(78)
        if len(header) != 78 or header[60:68] != b'BOOKMOBI':
            raise ValueError('This is not a valid MOBI book.')
        count = struct.unpack_from('>H', header, 76)[0]
        if not count or 78 + count * 8 > size:
            raise ValueError('The MOBI record table is incomplete.')
        table = source.read(count * 8)
        offsets = [struct.unpack_from('>I', table, i * 8)[0] for i in range(count)] + [size]
        if offsets[0] < 78 + count * 8 or any(a > b or b > size for a, b in zip(offsets, offsets[1:])):
            raise ValueError('The MOBI record table is invalid.')
        length = offsets[1] - offsets[0]
        if length < 96 or length > 1024 * 1024:
            raise ValueError('The MOBI header is invalid or too large.')
        source.seek(offsets[0])
        record = source.read(length)
    if record[16:20] != b'MOBI':
        raise ValueError('The MOBI header is missing.')
    header_length = struct.unpack_from('>I', record, 20)[0]
    if header_length < 80 or 16 + header_length > len(record):
        raise ValueError('The MOBI header is truncated.')
    encoding = struct.unpack_from('>I', record, 28)[0]
    codec = 'utf-8' if encoding == 65001 else f'cp{encoding}'
    def decode(value):
        try:
            return value.decode(codec, errors='replace').strip('\x00 \r\n')
        except LookupError:
            return value.decode('cp1252', errors='replace').strip('\x00 \r\n')
    offset, length = struct.unpack_from('>II', record, 84)
    title = decode(record[offset:offset + length]) if offset + length <= len(record) else ''
    title = title or decode(header[:32]) or path.stem
    authors = []
    exth = 16 + header_length
    if record[exth:exth + 4] == b'EXTH' and exth + 12 <= len(record):
        exth_length, entries = struct.unpack_from('>II', record, exth + 4)
        end = exth + exth_length
        if exth_length < 12 or end > len(record) or entries > (exth_length - 12) // 8:
            raise ValueError('The MOBI metadata is damaged.')
        cursor = exth + 12
        for _ in range(entries):
            if cursor + 8 > end:
                raise ValueError('The MOBI metadata is truncated.')
            kind, length = struct.unpack_from('>II', record, cursor)
            if length < 8 or cursor + length > end:
                raise ValueError('The MOBI metadata is invalid.')
            value = decode(record[cursor + 8:cursor + length])
            if kind == 100 and value:
                authors.append(value)
            elif kind == 503 and value:
                title = value
            cursor += length
    return dict(title=title, author=', '.join(authors),
                encrypted=struct.unpack_from('>H', record, 12)[0] != 0)


@contextmanager
def unpack_mobi(path, cache):
    if mobi_info(path)['encrypted']:
        raise ValueError('DRM-protected MOBI books are not supported. Use a DRM-free copy.')
    with tempfile.TemporaryDirectory(prefix='mobi-', dir=cache) as folder:
        output = Path(folder) / 'book'
        worker = Path(__file__).with_name('unpack_mobi.py')
        with (Path(folder) / 'extract.log').open('wb') as log:
            try:
                result = subprocess.run(
                    [sys.executable, '-I', str(worker), str(Path(path).resolve()), str(output)],
                    cwd=folder, stdout=log, stderr=log, timeout=45,
                )
            except subprocess.TimeoutExpired:
                raise ValueError('This MOBI book took too long to unpack.') from None
        if result.returncode:
            raise ValueError('Cannot open this MOBI book. It may be damaged or use an unsupported Kindle format.')
        files = list(output.rglob('*'))
        if len(files) > 10000 or sum(p.stat().st_size for p in files if p.is_file()) > 100 * 1024 * 1024:
            raise ValueError('The unpacked MOBI book exceeds the size limit.')
        yield output
