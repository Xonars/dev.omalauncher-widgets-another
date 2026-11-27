#!/usr/bin/env python3
"""Import the generated card archive and rebuild ONLY Ghost Letters' store bundle.

Run from the visual-overhaul branch. Standard library only; no network.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "local/phone-widgets/ghost-letters"
SOURCE = ROOT / "local/phone-widgets/ghost-letters.owl"
APP = ROOT / "apps/xonars/ghost-letters/app.owl"
COLLECTION = ROOT / "store-collection.json"
PREFIX = "widgets/ghost-letters/"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    deck = json.loads((ENGINE / "deck.json").read_text())
    expected = {c["id"]: c["name"] for c in deck}
    with zipfile.ZipFile(args.archive) as z:
        manifest = json.loads(z.read("manifest.json"))
        cards = manifest["cards"]
        require(len(cards) == len(expected) == 131, "Incomplete deck")
        require({c["id"]:c["name"] for c in cards} == expected, "Deck IDs/names differ")
        require(len(set(z.namelist())) == len(z.namelist()), "Duplicate ZIP members")
        assets = {}
        for card in cards:
            name = f'assets/cards/{card["id"]:03d}.webp'
            require(card["file"] == name, "Invalid card path")
            info = z.getinfo(name)
            require(info.file_size <= 1024 * 1024, "Oversized card")
            data = z.read(info)
            require(digest(data) == card["sha256"], "Card checksum mismatch: " + name)
            require(data[:4] == b"RIFF" and data[8:12] == b"WEBP", "Invalid WebP")
            assets[name] = data
        require(len({digest(x) for x in assets.values()}) == 131, "Duplicate images")
        manifest_bytes = z.read("manifest.json")
    source_text = SOURCE.read_text()
    app_text = APP.read_text()
    require("state illustrated = true" in source_text and "entry.artwork" in app_text,
            "Switch to ghost-letters-visual-overhaul first")
    engine_text = (ENGINE / "game.py").read_text()
    old = '    return dict(value=card_id, label=card["name"], glyph=card["glyph"], **fields)'
    new = ('    artwork = HERE / "assets" / "cards" / f"{card_id:03d}.webp"\n'
           '    return dict(value=card_id, label=card["name"], glyph=card["glyph"],\n'
           '                artwork=str(artwork) if artwork.is_file() else None, **fields)')
    if old in engine_text:
        engine_text = engine_text.replace(old, new, 1)
    require(new in engine_text, "Unexpected card_view implementation")
    compile(engine_text, "game.py", "exec")
    collection = json.loads(COLLECTION.read_text())
    row = next(x for x in collection if x["source"] == "ghost-letters.owl")
    previous = ROOT / row["resources"]
    old_sha = previous.stem
    require(digest(previous.read_bytes()) == old_sha, "Previous package checksum mismatch")
    with zipfile.ZipFile(previous) as z:
        members = {name:z.read(name) for name in z.namelist() if not name.endswith("/")}
    members[PREFIX + "game.py"] = engine_text.encode()
    for name, data in assets.items():
        members[PREFIX + name] = data
    members[PREFIX + "assets/manifest.json"] = manifest_bytes
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name,data in sorted(members.items()):
            info = zipfile.ZipInfo(name, (2026,11,27,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    payload = buffer.getvalue()
    sha = digest(payload)
    require(old_sha in app_text, "Store bootstrap digest not found")
    app_text = app_text.replace(old_sha, sha)
    source_text = source_text.replace('version: "2.3.0"', 'version: "2.4.0"', 1)
    app_text = app_text.replace('version: "2.3.1"', 'version: "2.4.1"', 1)
    require('version: "2.4.0"' in source_text and 'version: "2.4.1"' in app_text, "Version mismatch")
    row["resources"] = f"resources/{sha}.zip"
    # All validation precedes writes; no arbitrary extraction paths or other store entries.
    for name,data in assets.items():
        target = ENGINE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (ENGINE / "assets/manifest.json").write_bytes(manifest_bytes)
    (ENGINE / "game.py").write_text(engine_text)
    SOURCE.write_text(source_text)
    APP.write_text(app_text)
    (ROOT / row["resources"]).write_bytes(payload)
    COLLECTION.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n")
    print(f"Imported {len(assets)} cards; package {row['resources']}")
    print("Run store tests and commit only Ghost Letters changes.")

if __name__ == "__main__":
    main()
