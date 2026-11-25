import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('continue_build', Path(__file__).with_name('continue_build.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ContinueBuildTest(unittest.TestCase):
    def test_published_clean_main_and_completed_upstream_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, text=True, stderr=subprocess.PIPE).strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.com')
            (repo / 'file').write_text('base')
            git('add', 'file'); git('commit', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            git('update-ref', 'refs/remotes/origin/main', base)
            git('update-ref', 'refs/remotes/upstream/main', base)
            original = c.git
            def local(*args):
                return '' if args[0] == 'fetch' else original(*args)
            with patch.object(c, 'REPO', repo), patch.object(c, 'git', side_effect=local):
                c.validate(True)
                (repo / 'file').write_text('uncommitted')
                with self.assertRaisesRegex(RuntimeError, 'несохранённые'):
                    c.validate()
                git('add', 'file'); git('commit', '-m', 'fix')
                with self.assertRaisesRegex(RuntimeError, 'отличается от GitHub'):
                    c.validate()
                git('update-ref', 'refs/remotes/origin/main', 'HEAD')
                c.validate()
                merge_head = Path(git('rev-parse', '--git-path', 'MERGE_HEAD'))
                if not merge_head.is_absolute(): merge_head = repo / merge_head
                merge_head.write_text(base + '\n')
                with self.assertRaisesRegex(RuntimeError, 'ещё не завершена'):
                    c.validate()
                merge_head.unlink()
                git('checkout', '-b', 'upstream-test', base)
                (repo / 'other').write_text('Simon')
                git('add', 'other'); git('commit', '-m', 'upstream')
                git('update-ref', 'refs/remotes/upstream/main', 'HEAD')
                git('checkout', 'main')
                with self.assertRaisesRegex(RuntimeError, 'Не все коммиты'):
                    c.validate(True)
                c.validate(False)
                git('merge', '--no-ff', 'upstream-test', '-m', 'merge upstream')
                git('update-ref', 'refs/remotes/origin/main', 'HEAD')
                c.validate(True)

    def test_validation_failure_never_starts_worker(self):
        with patch.object(c, 'validate', side_effect=RuntimeError('not ready')), patch.object(c.subprocess, 'run') as run:
            self.assertEqual(c.main(), 1)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
