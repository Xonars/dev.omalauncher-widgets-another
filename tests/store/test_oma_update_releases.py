"""Offline regression checks for the embedded OMA Update release helper."""
import hashlib
import json
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
OWL = ROOT / "apps/xonars/oma-update/app.owl"
SOURCE = ROOT / "local/phone-widgets/76-oma-update-app.owl"

def helper(path):
    return path.read_text().split('let releaseHelper = """\n', 1)[1].split('"""', 1)[0]

ns = {"__name__": "release_test"}
exec(compile(helper(OWL), str(OWL), "exec"), ns)

class Releases(unittest.TestCase):
    def asset(self, **kw):
        return dict(id=42, name="OMA-Another-70.apk", state="uploaded", size=123,
                    digest="sha256:" + "a"*64, **{}) | kw

    def release(self, *assets, **kw):
        return dict(tag_name="v70", assets=list(assets), published_at="2026-11-26", **kw)

    def test_source_matches_store(self):
        self.assertEqual(helper(OWL), helper(SOURCE))

    def test_selection(self):
        chosen = ns["select_release"](self.release(self.asset(), self.asset(name="OMA-Another-ci.apk")))
        self.assertEqual(chosen["id"], 42)
        self.assertEqual(chosen["sha256"], "a"*64)
        self.assertIsNone(ns["select_release"](self.release(self.asset(name="other.apk"))))
        self.assertEqual(ns["select_release"](self.release(self.asset(name="app-foss-debug.apk")))["id"], 42)

    def test_invalid_metadata(self):
        for release in (self.release(self.asset(digest=None)), self.release(self.asset(size=0)),
                        self.release(self.asset(), self.asset(id=43)), self.release(self.asset(), prerelease=True)):
            with self.assertRaises(RuntimeError):
                ns["select_release"](release)

    def test_no_release_vs_no_access(self):
        error = ns["HttpFailure"]
        with patch.dict(ns, api=lambda *a: (_ for _ in ()).throw(error(404)) if a[0] else {}):
            self.assertIsNone(ns["latest"]("token"))
        with patch.dict(ns, api=lambda *a: (_ for _ in ()).throw(error(404))):
            with self.assertRaisesRegex(RuntimeError, "Нет доступа"):
                ns["latest"]("token")

    def test_package_and_signature(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "a.apk"
            path.write_bytes(b"test")
            asset = dict(size=4, sha256=hashlib.sha256(b"test").hexdigest())
            for pkg, cert, ok in ((ns["APP"], ns["CERT"], True), ("wrong", ns["CERT"], False),
                                  (ns["APP"], "0"*64, False)):
                def output(args, **kw):
                    return ("package: name='%s' versionCode='70'" % pkg if args[0].endswith("aapt2")
                            else "Signer #1 certificate SHA-256 digest: " + cert)
                with patch.dict(ns, tools=lambda: pathlib.Path(folder)), patch("subprocess.check_output", side_effect=output):
                    if ok:
                        self.assertEqual(ns["verify"](path, asset), 70)
                    else:
                        with self.assertRaises(RuntimeError):
                            ns["verify"](path, asset)
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                ns["verify"](path, dict(asset, sha256="0"*64))

    def test_redirect_does_not_forward_credentials(self):
        import io
        import urllib.error
        from unittest.mock import Mock
        redirect = urllib.error.HTTPError(
            ns["API"] + "/releases/assets/42", 302, "Found",
            {"Location": "https://release-assets.githubusercontent.com/download?sig=example"}, io.BytesIO())
        opener = Mock()
        opener.open.side_effect = [redirect, io.BytesIO(b"apk")]
        with patch("urllib.request.build_opener", return_value=opener):
            with ns["open_url"](ns["API"] + "/releases/assets/42", "test-token", True) as response:
                self.assertEqual(response.read(), b"apk")
        first, second = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(first.get_header("Authorization"), "Bearer test-token")
        self.assertIsNone(second.get_header("Authorization"))

    def test_install_rejects_same_version_and_downgrade(self):
        import tempfile
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            cache = pathlib.Path(folder)
            for installed in (70, 71):
                selected = self.release(self.asset())
                state = {"phase": "ready", "selected": ns["select_release"](selected)}
                saved = Mock()
                with patch.dict(ns, CACHE=cache, read=lambda: state, save=saved,
                                verify=lambda *a: 70, installed=lambda: installed), patch("subprocess.run") as run:
                    ns["worker"]("install")
                    run.assert_not_called()
                    self.assertEqual(saved.call_args.kwargs["phase"], "current")

if __name__ == "__main__":
    unittest.main()
