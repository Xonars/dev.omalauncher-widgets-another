# The tweaks widget's backend: dump, set, unset, snapshot, restore, reset, disable, enable, add-example.
import json, os, re, shutil, subprocess, sys, time, tomllib
from pathlib import Path

HOME = Path.home()
ROOT = HOME / ".config/omalauncher"
STYLE = ROOT / "style/style.toml"
DEFAULTS = ROOT / "style/defaults.toml"
WIDGETS = ROOT / "widgets"
REMOVED = WIDGETS / ".removed"
EXAMPLES = WIDGETS / "examples"
THEME_DIRS = [HOME / ".local/share/omarchy/themes", HOME / ".config/omarchy/themes"]  # later wins
PROTECTED = {"drawer.owl"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

# Ranges for numbers; defaults.toml only says them in prose.
RANGES = {
    "home.columns": (3, 10, 1),
    "widgets.gaps-in": (0, 24, 1),
    "widgets.gaps-out": (0, 24, 1),
    "widgets.border-width": (0, 8, 1),
    "screens.gaps-out": (0, 24, 1),
    "screens.border-width": (0, 8, 1),
    "corners.scale": (0, 1, 0.25),
    "status-bar.opacity": (0, 1, 0.05),
    "status-bar.border-width": (0, 8, 1),
    "navigation-bar.opacity": (0, 1, 0.05),
    "navigation-bar.border-width": (0, 8, 1),
    "terminal.text": (8, 20, 1),
}
COLOR_KEYS = {"widgets.border", "widgets.border-focused", "status-bar.background", "status-bar.border",
              "navigation-bar.background", "navigation-bar.border"}


def parse_defaults():
    # Settings in defaults.toml's order, each with the comment above it as its description.
    out, section, comment = [], "", []
    for line in DEFAULTS.read_text().splitlines():
        s = line.strip()
        if m := re.fullmatch(r"\[([\w-]+)\]", s):
            section, comment = m[1], []
        elif m := re.fullmatch(r"#\s*([\w-]+)\s*=\s*(.*)", s):  # documented but unset: theme, background
            out.append((section, m[1], None, " ".join(comment)))
            comment = []
        elif s.startswith("#"):
            comment.append(s.lstrip("# "))
        elif m := re.fullmatch(r"([\w-]+)\s*=\s*(.+)", s):
            if not section and m[1] == "version":
                comment = []
                continue
            out.append((section, m[1], tomllib.loads(f"v = {m[2]}")["v"], " ".join(comment)))
            comment = []
        else:
            comment = []
    return out


def read_style():
    try:
        return tomllib.loads(STYLE.read_text())
    except Exception:
        return {}


def themes():
    found = {}
    for base in THEME_DIRS:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            colors = {}
            try:
                colors = tomllib.loads((d / "colors.toml").read_text())
            except Exception:
                pass
            preview = next((str(p) for p in sorted(d.glob("preview.*")) if p.suffix in IMAGE_EXT), None)
            found[d.name] = {
                "name": d.name, "user": base == THEME_DIRS[-1], "preview": preview,
                "mode": colors.get("mode", "dark"),
                "swatch": [colors.get(k) for k in ("background", "foreground", "accent", "red", "green", "yellow", "blue", "magenta") if colors.get(k)],
                "colors": colors,
            }
    return sorted(found.values(), key=lambda t: t["name"])


def backgrounds(theme):
    out = []
    for base in THEME_DIRS:
        d = base / theme / "backgrounds"
        if d.is_dir():
            out += [p for p in sorted(d.iterdir()) if p.suffix.lower() in IMAGE_EXT]
    d = HOME / ".config/omarchy/backgrounds" / theme
    if d.is_dir():
        out += [p for p in sorted(d.iterdir()) if p.suffix.lower() in IMAGE_EXT]
    return [{"name": p.name, "path": str(p), "preview": str(p) if p.stat().st_size <= 8 * 1024 * 1024 else None} for p in out]


def mono_fonts():
    try:
        r = subprocess.run(["fc-list", ":spacing=100", "family"], capture_output=True, text=True, timeout=10)
        fams = {l.split(",")[0].strip() for l in r.stdout.splitlines() if l.strip()}
        return sorted(f for f in fams if f and "Symbols" not in f)
    except Exception:
        return []


def owl_kind(path):
    try:
        with open(path, errors="replace") as f:
            for line in f:
                if m := re.match(r'\s*(widget|face|app|panel)\s+"([^"]*)"', line):
                    return m[1], m[2]
                if line.strip() and not line.strip().startswith("//"):
                    break
    except Exception:
        pass
    return "?", path.stem


def owl_files(folder, errors=False):
    out = []
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob("*.owl")):
        if p.name.startswith("."):
            continue
        kind, name = owl_kind(p)
        mine = "omalauncher-tweaks-tool" in p.read_text(errors="replace")
        item = {"file": p.name, "kind": kind, "name": name, "size": p.stat().st_size,
                "protected": p.name in PROTECTED or mine}
        if errors:
            e = WIDGETS / ".errors" / f"{p.name}.txt"
            text = e.read_text(errors="replace").strip() if e.is_file() else ""
            item["errors"] = text[:600]
        out.append(item)
    return out


def dump():
    style = read_style()
    theme_list = themes()
    cur_theme = style.get("theme")
    cur = next((t for t in theme_list if t["name"] == cur_theme), None)
    fonts = mono_fonts()
    panels = [f["file"] for f in owl_files(WIDGETS) if f["kind"] == "panel"]
    palette = ["theme"]
    if cur:
        for k in ("accent", "foreground", "muted", "background", "red", "orange", "yellow", "green", "cyan", "blue", "magenta"):
            v = cur["colors"].get(k)
            if isinstance(v, str) and v not in palette:
                palette.append(v)

    settings = []
    for section, key, default, desc in parse_defaults():
        path = f"{section}.{key}" if section else key
        table = style.get(section, {}) if section else style
        is_set = isinstance(table, dict) and key in table
        value = table.get(key) if is_set else default
        kind = "bool" if isinstance(default, bool) else "number" if isinstance(default, (int, float)) else "text"
        s = {"section": section or "general", "key": key, "path": path, "desc": desc, "default": default,
             "value": value, "set": is_set, "type": kind}
        if path in RANGES:
            s["min"], s["max"], s["step"] = RANGES[path]
        if path == "theme":
            s["type"] = "theme"
        elif path == "background":
            s["type"] = "background"
        elif path == "font":
            s["choices"] = ["system"] + fonts
        elif path == "terminal.font":
            s["choices"] = fonts
        elif path == "gestures.swipe-up":
            s["choices"] = panels + ["none"]
        elif path == "gestures.swipe-down":
            s["choices"] = ["none"] + panels
        elif path in COLOR_KEYS:
            s["type"] = "color"
            s["choices"] = palette + ([value] if value not in palette else [])
        settings.append(s)

    backups = []
    for p in sorted(STYLE.parent.glob("style.toml.*"), key=lambda p: -p.stat().st_mtime):
        backups.append({"file": p.name, "time": int(p.stat().st_mtime)})

    errors = STYLE.parent / "errors.txt"
    layout_err = ROOT / "home/errors.txt"
    removed = owl_files(REMOVED)
    active = owl_files(WIDGETS, errors=True)
    have = {f["file"] for f in active}
    examples = owl_files(EXAMPLES)
    for e in examples:
        e["added"] = e["file"] in have

    print(json.dumps({
        "settings": settings,
        "themes": [{k: t[k] for k in ("name", "user", "preview", "mode", "swatch")} for t in theme_list],
        "theme": cur_theme,
        "backgrounds": backgrounds(cur_theme) if cur_theme else [],
        "files": active, "removed": removed, "examples": examples,
        "backups": backups,
        "styleErrors": errors.read_text(errors="replace").strip() if errors.is_file() else "",
        "layoutErrors": layout_err.read_text(errors="replace").strip() if layout_err.is_file() else "",
        "agent": (ROOT / "agent").read_text().strip() if (ROOT / "agent").is_file() else None,
    }))


def toml_value(path, raw):
    default = next((d for s, k, d, _ in parse_defaults() if (f"{s}.{k}" if s else k) == path), None)
    if isinstance(default, bool):
        return "true" if raw.lower() in ("true", "1", "yes", "on") else "false"
    if isinstance(default, (int, float)):
        n = float(raw)
        return str(int(n)) if isinstance(default, int) and not isinstance(default, bool) and n == int(n) else repr(round(n, 4))
    return json.dumps(raw)


def write_style(lines):
    text = "\n".join(lines).rstrip("\n") + "\n"
    tmp = STYLE.with_suffix(".toml.tmp")
    tmp.write_text(text)
    os.replace(tmp, STYLE)


def section_bounds(lines, section):
    # (start, end) line indexes of a section's body; top level when section is ''.
    headers = [i for i, l in enumerate(lines) if re.match(r"\s*\[[^\]]+\]\s*$", l)]
    if not section:
        return 0, headers[0] if headers else len(lines)
    for n, i in enumerate(headers):
        if re.match(rf"\s*\[{re.escape(section)}\]\s*$", lines[i]):
            return i + 1, headers[n + 1] if n + 1 < len(headers) else len(lines)
    return None


def set_key(path, raw, remove=False):
    section, _, key = path.rpartition(".")
    lines = STYLE.read_text().splitlines() if STYLE.exists() else ["version = 1"]
    bounds = section_bounds(lines, section)
    if bounds:
        a, b = bounds
        for i in range(a, b):
            if re.match(rf"\s*{re.escape(key)}\s*=", lines[i]):
                if remove:
                    del lines[i]
                else:
                    lines[i] = f"{key} = {toml_value(path, raw)}"
                return write_style(lines)
    if remove:
        return
    entry = f"{key} = {toml_value(path, raw)}"
    if bounds:
        a, b = bounds
        at = b
        while at > a and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, entry)
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", f"[{section}]", entry]
    write_style(lines)


def snapshot(tag="snap"):
    if STYLE.exists():
        shutil.copy2(STYLE, STYLE.parent / f"style.toml.{tag}-{time.strftime('%Y%m%d-%H%M%S')}")


def safe_name(name):
    if not re.fullmatch(r"[\w.+ -]+\.owl", name) or name.startswith("."):
        sys.exit(f"bad file name: {name}")
    return name


def main():
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("dump", [])
    if cmd == "dump":
        dump()
    elif cmd == "set" and len(args) == 2:
        set_key(args[0], args[1])
    elif cmd == "unset" and len(args) == 1:
        set_key(args[0], "", remove=True)
    elif cmd == "snapshot":
        snapshot()
    elif cmd == "restore" and len(args) == 1:
        src = STYLE.parent / args[0]
        if not re.fullmatch(r"style\.toml\.[\w.-]+", args[0]) or not src.is_file():
            sys.exit("no such backup")
        snapshot("before-restore")
        shutil.copy2(src, STYLE)
    elif cmd == "reset":
        snapshot("before-reset")
        write_style(["# The launcher's style. Settings left out have their default; defaults.toml lists them all.",
                     "", "version = 1"])
    elif cmd == "disable" and len(args) == 1:
        name = safe_name(args[0])
        if name in PROTECTED or "omalauncher-tweaks-tool" in (WIDGETS / name).read_text(errors="replace"):
            sys.exit(f"{name} stays")
        REMOVED.mkdir(exist_ok=True)
        dest = REMOVED / name
        if dest.exists():
            dest.rename(REMOVED / f"{name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
        (WIDGETS / name).rename(dest)
    elif cmd == "enable" and len(args) == 1:
        name = safe_name(args[0])
        if (WIDGETS / name).exists():
            sys.exit(f"{name} is already there")
        (REMOVED / name).rename(WIDGETS / name)
    elif cmd == "add-example" and len(args) == 1:
        name = safe_name(args[0])
        if (WIDGETS / name).exists():
            sys.exit(f"{name} is already there")
        shutil.copy2(EXAMPLES / name, WIDGETS / name)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
