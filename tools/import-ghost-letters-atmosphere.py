#!/usr/bin/env python3
"""Import eight atmospheric art files and rebuild only the Ghost Letters package."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "local/phone-widgets/ghost-letters"
APP = ROOT / "apps/xonars/ghost-letters/app.owl"
COLLECTION = ROOT / "store-collection.json"
PREFIX = "widgets/ghost-letters/"
KEYS = {"ghost", "detective", "killer", "accomplice", "witness", "expert", "back", "table"}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as z:
        manifest = json.loads(z.read("manifest.json"))
        records = manifest["assets"]
        require(manifest["schema"] == 1 and len(records) == 8 and {r["key"] for r in records} == KEYS, "Expected eight atmospheric assets")
        expected = {f"assets/atmosphere/{key}.webp" for key in KEYS} | {"manifest.json"}
        require(len(z.namelist()) == len(expected) and set(z.namelist()) == expected, "Unexpected ZIP members")
        assets = {}
        for record in records:
            name = f'assets/atmosphere/{record["key"]}.webp'
            require(record["file"] == name, "Invalid asset path")
            info = z.getinfo(name)
            require(0 < info.file_size <= 1024 * 1024, "Oversized or empty asset")
            data = z.read(info)
            require(digest(data) == record["sha256"], "Checksum mismatch: " + name)
            require(data[:4] == b"RIFF" and data[8:12] == b"WEBP", "Invalid WebP")
            assets[name] = data
        require(len({digest(data) for data in assets.values()}) == 8, "Duplicate artwork")
        assets["assets/atmosphere/manifest.json"] = z.read("manifest.json")
    app = APP.read_text()
    engine = (ENGINE / "game.py").read_bytes()
    require('version: "2.6.1"' in app and b"def atmosphere_view()" in engine, "Switch to ghost-letters-atmospheric-polish first")
    compile(engine, "game.py", "exec")
    collection = json.loads(COLLECTION.read_text())
    row = next(x for x in collection if x["source"] == "ghost-letters.owl")
    previous = ROOT / row["resources"]
    old_sha = previous.stem
    require(digest(previous.read_bytes()) == old_sha and old_sha in app, "Previous package or bootstrap mismatch")
    with zipfile.ZipFile(previous) as z:
        members = {name: z.read(name) for name in z.namelist() if not name.endswith("/")}
    members[PREFIX + "game.py"] = engine
    for name, data in assets.items():
        members[PREFIX + name] = data
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    payload = buffer.getvalue()
    sha = digest(payload)
    row["resources"] = f"resources/{sha}.zip"
    for name, data in assets.items():
        target = ENGINE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    APP.write_text(app.replace(old_sha, sha))
    (ROOT / row["resources"]).write_bytes(payload)
    COLLECTION.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n")
    print(f"Imported eight atmospheric assets; package {row['resources']}")

if __name__ == "__main__":
    main()
