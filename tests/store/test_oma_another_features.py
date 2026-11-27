import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "local/phone-widgets/oma-another-features"
APP = ROOT / "local/phone-widgets/84-oma-another-features-app.owl"


class FeaturesTest(unittest.TestCase):
    def test_catalog_and_icons(self):
        features = json.loads((LOCAL / "catalog.json").read_text())["features"]
        self.assertEqual(21, len(features))
        self.assertEqual(len(features), len({f["id"] for f in features}))
        source = APP.read_text()
        self.assertIn("screenWidth", source)
        self.assertIn("align: center", source)
        for f in features:
            self.assertIn('name == "' + f["id"] + '"', source)
            self.assertTrue(f["shortTitle"])
            self.assertEqual(f["details"], " ".join(f["benefits"]))
            self.assertEqual(f["howTo"], " ".join(f["steps"]))
            for shot in f["screenshots"]:
                self.assertTrue((LOCAL / "screenshots" / Path(shot["src"]).name).is_file())

    def test_store_catalogs_match(self):
        catalog = json.loads((LOCAL / "catalog.json").read_text())
        manifest = json.loads((ROOT / "store-collection.json").read_text())
        entries = [r for r in manifest if r["source"] in ("84-oma-another-features-app.owl", "85-oma-another-features.owl")]
        self.assertEqual(2, len(entries))
        for entry in entries:
            with zipfile.ZipFile(ROOT / entry["resources"]) as z:
                packed = json.loads(z.read("widgets/oma-another-features/catalog.json"))
            self.assertEqual([f["id"] for f in catalog["features"]], [f["id"] for f in packed["features"]])
            self.assertEqual(len(catalog["features"]), len(packed["features"]))
