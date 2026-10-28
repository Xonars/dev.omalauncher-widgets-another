"""Exercise deletion against disposable data, never the user's caches."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cleaner', Path(__file__).with_name('cleaner.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

class CleanerTest(unittest.TestCase):
    def test_cache_cleaning_and_symlink_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            home = root / 'home'
            cache = home / '.cache'
            target = cache / 'pip/http-v2'
            target.mkdir(parents=True)
            (target / 'entry').write_bytes(b'x' * 8192)
            outside = root / 'precious'
            outside.mkdir()
            (outside / 'keep').write_text('keep')
            (cache / 'uv').symlink_to(outside, target_is_directory=True)
            base = root / 'state'
            base.mkdir()
            with patch.object(c, 'HOME', home), patch.dict(c.os.environ, {'XDG_CACHE_HOME': str(cache), 'XDG_DATA_HOME': str(home / '.local/share')}), patch.object(c, 'processes', return_value=[]), patch.object(c, 'BASE', base), patch.object(c, 'STATUS', base / 'status.json'):
                rows = c.plan(False)
                pip = next(row for row in rows if row['name'] == 'pip')
                uv = next(row for row in rows if row['name'] == 'uv')
                self.assertGreater(pip['bytes'], 0)
                self.assertEqual(uv['paths'], [])
                self.assertFalse(c.safe(cache / 'uv/keep'))
                with patch.object(c, 'plan', return_value=[pip]):
                    c.work('clean', False)
                self.assertFalse(target.exists())
                self.assertTrue((outside / 'keep').exists())
                self.assertFalse(c.read()['busy'])
                self.assertGreater(c.read()['freed'], 0)

    def test_pacman_keeps_two_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for version in range(1, 5):
                (root / f'fixture-{version}-1-any.pkg.tar.zst').write_bytes(b'x')
            out = subprocess.check_output(['paccache', '-d', '-k', '2', '-vv', '-z', '-c', folder])
            paths = [Path(c.os.fsdecode(x)) for x in out.split(b'\n', 1)[-1].split(b'\0') if x.startswith(b'/') and b'\n' not in x]
            self.assertEqual({p.name for p in paths}, {'fixture-1-1-any.pkg.tar.zst', 'fixture-2-1-any.pkg.tar.zst'})

if __name__ == '__main__':
    unittest.main()
