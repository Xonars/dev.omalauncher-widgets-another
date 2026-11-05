import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('repository', Path(__file__).with_name('repository.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class RepositoryTest(unittest.TestCase):
    def test_divergence_branches_dirty_and_invalid_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, text=True, stderr=subprocess.PIPE).strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.com')
            (repo / 'file').write_text('base')
            git('add', '.'); git('commit', '-m', 'base')
            git('branch', 'base')
            (repo / 'file').write_text('fork')
            git('commit', '-am', 'fork feature')
            git('update-ref', 'refs/remotes/origin/main', 'HEAD')
            git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
            git('checkout', 'base')
            (repo / 'other').write_text('upstream')
            git('add', '.'); git('commit', '-m', 'Simon feature')
            git('update-ref', 'refs/remotes/upstream/main', 'HEAD')
            git('checkout', 'main')
            (repo / 'file').write_text('dirty')
            with patch.object(r, 'REPO', repo):
                data = r.dashboard('origin/main')
                self.assertEqual((data['ahead'], data['behind']), (1, 1))
                self.assertEqual(data['own'][0]['subject'], 'fork feature')
                self.assertEqual(data['incoming'][0]['subject'], 'Simon feature')
                self.assertTrue(data['dirty'])
                self.assertNotIn('origin', [b['name'] for b in data['branches']])
                with self.assertRaises(RuntimeError):
                    r.dashboard('--all')
                self.assertEqual(git('branch', '--show-current'), 'main')
                self.assertEqual((repo / 'file').read_text(), 'dirty')

    def test_fetch_failure_retains_last_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            state = cache / 'sync.json'
            state.write_text('{"origin": 123, "upstream": 456}')
            with patch.multiple(r, CACHE=cache, SYNC=state), patch.object(r.subprocess, 'run', side_effect=subprocess.TimeoutExpired('git', 120)):
                r.fetch()
                result = r.sync_state()
                self.assertEqual(result['origin'], 123)
                self.assertEqual(result['upstream'], 456)
                self.assertIn('upstream', result['error'])

if __name__ == '__main__':
    unittest.main()
