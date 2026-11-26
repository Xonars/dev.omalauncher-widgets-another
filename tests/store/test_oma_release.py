from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
def helper(path):
    return path.read_text().split('let inspector = """\n',1)[1].split('"""',1)[0]
ns = {"__name__": "test"}
exec(compile(helper(ROOT/"apps/xonars/oma-release/app.owl"), "release", "exec"), ns)

class ReleaseInspector(unittest.TestCase):
    def test_source(self):
        self.assertEqual(helper(ROOT/"apps/xonars/oma-release/app.owl"), helper(ROOT/"local/phone-widgets/oma-release.owl"))
    def test_version(self):
        self.assertEqual(ns["source_version"]('versionCode = 71\nversionName = "1.11.0"'), ("1.11.0",71))
        with self.assertRaises(RuntimeError):
            ns["source_version"]('versionCode = 71\nversionCode = 72\nversionName = "1.11.0"')
    def test_history(self):
        self.assertEqual(ns["published_build"]([dict(tagName="v1.11.0-build70",isDraft=False,isPrerelease=False),dict(tagName="v1.11.0-build71",isDraft=True,isPrerelease=False)]),70)
        with self.assertRaises(RuntimeError):
            ns["published_build"]([dict(tagName="other",isDraft=False,isPrerelease=False)])
    def test_current(self):
        import base64
        def api(path):
            if path == "/branches/main":
                return dict(commit=dict(sha="a"*40))
            if path.startswith("/contents/"):
                return dict(content=base64.b64encode(b'versionCode = 70\nversionName = "1.11.0"'))
            self.fail("Already published must not request artifacts")
        with patch.dict(ns,api=api,gh=lambda *a:[dict(tagName="v1.11.0-build70",isDraft=False,isPrerelease=False)]):
            self.assertEqual(ns["inspect"]()["phase"],"current")
