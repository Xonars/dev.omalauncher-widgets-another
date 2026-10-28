"""Integration checks; run with server stopped (uses port 8765)."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

BACKEND = Path(__file__).with_name('backend.py')

def command(*args):
    return json.loads(subprocess.check_output([sys.executable, str(BACKEND), *args]))

def fetch(path, expected=200):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765' + path, timeout=3) as r:
            assert r.status == expected
            return r.read()
    except urllib.error.HTTPError as e:
        assert e.code == expected, (path, e.code, expected)

assert command('status')['status'] != 'Running', 'Stop the server before tests'
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp, 'apks')
    root.mkdir()
    nested = root / 'nested'
    nested.mkdir()
    (nested / 'hello space.apk').write_bytes(b'APK test payload')
    (root / 'secret.txt').write_text('not downloadable')
    outside = Path(temp, 'outside.apk')
    outside.write_text('outside')
    (root / 'link.apk').symlink_to(outside)
    (root / 'escape').symlink_to(Path(temp), target_is_directory=True)
    try:
        listing = command('list', '--directory', str(root))
        assert listing['count'] == 1, listing
        start = command('start', '--directory', str(root))
        assert start['status'] == 'Running', start
        again = command('start', '--directory', str(root))
        assert start['pid'] == again['pid']
        assert b'hello%20space.apk' in fetch('/')
        assert fetch('/apk/nested/hello%20space.apk') == b'APK test payload'
        for path in ['/secret.txt', '/apk/secret.txt', '/apk/../outside.apk', '/apk/%2e%2e/outside.apk', '/apk/link.apk', '/apk/escape/outside.apk', '/apk/%2Fetc/passwd.apk']:
            fetch(path, 404)
        # Swap a formerly valid file for a symlink after it was listed.
        (nested / 'hello space.apk').unlink()
        (nested / 'hello space.apk').symlink_to(outside)
        fetch('/apk/nested/hello%20space.apk', 404)
        assert command('stop')['status'] == 'Stopped'
        assert command('stop')['status'] == 'Stopped'
        assert command('start', '--directory', str(root))['status'] == 'Running'
        command('stop')
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(('127.0.0.1', 8765))
            occupied.listen()
            failure = command('start', '--directory', str(root))
            assert failure['status'] == 'Error', failure
        assert command('start', '--directory', str(root))['status'] == 'Running'
        assert command('start', '--directory', '/nonexistent-apk-share-test')['status'] == 'Error'
    finally:
        command('stop')
print('PASS: recursive listing, downloads, traversal/symlink rejection, duplicate start, stop/restart, occupied port, invalid directory')
