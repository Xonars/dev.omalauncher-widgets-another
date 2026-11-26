"""Exercise the exact embedded helper shipped in the theme widget."""
from pathlib import Path
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]


def helper(path):
    return (ROOT / path).read_text().split('let workspaceHelper = """', 1)[1].split('"""', 1)[0].strip()


class WorkspaceThemeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home = root / 'home'
        (self.home / 'workspaces').mkdir(parents=True)
        self.style = root / 'style.toml'
        self.style.write_text('theme = "vault"\nbackground = "global.webp"\n')
        self.base = root / 'themes'
        for name in ('vault', 'tokyo-night', 'gruvbox'):
            (self.base / name / 'backgrounds').mkdir(parents=True)
            (self.base / name / 'backgrounds' / 'wall.webp').touch()
        self.layout = 'version = 1\ncolumns = 4\nmembership = "explicit"\n[[page]]\ntiles = [{ widget = "themes.owl", x = 0, y = 0, w = 4, h = 2 }]\n'
        self.first = self.home / 'layout.toml'
        self.second = self.home / 'workspaces/5.toml'
        self.first.write_text(self.layout)
        self.second.write_text(self.layout + '\n[appearance]\ntheme = "tokyo-night"\nbackground = ""\nwidgets.gaps-in = 9\n')
        source = helper('widgets/xonars/themes/widget.owl')
        self.assertEqual(source, helper('local/phone-widgets/83-themes.owl'))
        self.env = {'__name__': 'workspace_theme_test'}
        exec(compile(source, 'workspaceHelper', 'exec'), self.env)
        self.active = 0
        self.env.update(home=self.home, style=self.style, bases=[self.base], active=lambda: self.active)

    def test_inheritance_and_workspace_switch(self):
        self.assertEqual(self.env['status'](), dict(workspace=0, theme='vault', background='global.webp'))
        self.active = 5
        self.assertEqual(self.env['status'](), dict(workspace=5, theme='tokyo-night', background=None))

    def test_edit_only_selected_workspace(self):
        other, global_style = self.second.read_bytes(), self.style.read_bytes()
        self.env['edit'](0, 'gruvbox', 'wall.webp')
        expected = tomllib.loads(self.layout)
        expected['appearance'] = {'theme': 'gruvbox', 'background': 'wall.webp'}
        self.assertEqual(tomllib.loads(self.first.read_text()), expected)
        self.assertEqual(self.second.read_bytes(), other)
        self.assertEqual(self.style.read_bytes(), global_style)
        self.active = 5
        before = tomllib.loads(self.second.read_text())
        self.env['edit'](5, 'vault')
        before['appearance'].update(theme='vault', background='')
        self.assertEqual(tomllib.loads(self.second.read_text()), before)
        self.assertEqual(self.env['status']()['background'], None)

    def test_stale_target_and_invalid_theme_do_not_write(self):
        original = self.first.read_bytes()
        self.active = 5
        with self.assertRaises(ValueError):
            self.env['edit'](0, 'vault')
        self.active = 0
        with self.assertRaises(ValueError):
            self.env['edit'](0, '../vault')
        self.assertEqual(self.first.read_bytes(), original)

    def test_concurrent_edit_aborts(self):
        original = self.first.read_bytes()
        replies = iter((0, 5))
        self.env['active'] = lambda: next(replies)
        with self.assertRaises(ValueError):
            self.env['edit'](0, 'gruvbox')
        self.assertEqual(self.first.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
