#!/usr/bin/env python3
"""Rebuild only the existing Ghost Letters resource bundle (stdlib only)."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"local/phone-widgets/ghost-letters"
APP=ROOT/"apps/xonars/ghost-letters/app.owl"
COLLECTION=ROOT/"store-collection.json"

def main():
    collection=json.loads(COLLECTION.read_text())
    row=next(x for x in collection if x["source"]=="ghost-letters.owl")
    old=ROOT/row["resources"]
    app=APP.read_text()
    if hashlib.sha256(old.read_bytes()).hexdigest()!=old.stem or old.stem not in app:
        raise ValueError("Previous package/digest mismatch")
    files={f"widgets/ghost-letters/{p.relative_to(SOURCE).as_posix()}":p.read_bytes()
           for p in SOURCE.rglob("*") if p.is_file()
           and not any(part.startswith(".") or part=="__pycache__" for part in p.relative_to(SOURCE).parts)}
    compile(files["widgets/ghost-letters/game.py"],"game.py","exec")
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,11,27,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    payload=out.getvalue()
    sha=hashlib.sha256(payload).hexdigest()
    row["resources"]=f"resources/{sha}.zip"
    (ROOT/row["resources"]).write_bytes(payload)
    APP.write_text(app.replace(old.stem,sha))
    COLLECTION.write_text(json.dumps(collection,ensure_ascii=False,indent=2)+"\n")
    print(row["resources"])

if __name__=="__main__":
    main()
