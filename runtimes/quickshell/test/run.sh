#!/bin/bash
# Holds the Quickshell runtime to the language's reference implementation.
#
# OwlOracle.java drives tools/owl.jar's own compiler and evaluator with a
# fixed host and prints every evaluated property and drawing call as JSON;
# walk.js does the same walk with Owl.js. They must print the same JSON, numbers
# alike to 1e-9:
#
#   edge.owl                expressions and nodes chosen to break a port
#   <widget>.fixture.json   store widgets with the data their sources gave once
#   every store widget      with no source data at all, and every face
#
# and `owl check` and Owl.js must accept and reject the same files: those, and
# cases/*.owl, small files that each pass or fail one rule.
#
# Needs java (17+), javac and node. The expected output is never stored:
# it comes from the jar in this repo, so a new owl.jar is checked as it lands.

set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../../.." && pwd)
jar=$repo/tools/owl.jar
# Captured data belongs to the pinned oracle tree, not a newer catalogue overlay.
fixture_widgets=${OWL_FIXTURE_WIDGETS:-"$repo/widgets"}
owl=$here/../Owl.js
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The fixtures' times are formatted in Berlin, and java's locale starts the
# week on Sunday, as walk.js does.
export TZ=Europe/Berlin
java_opts=(-Duser.timezone=Europe/Berlin -Duser.language=en -Duser.country=US)

javac -cp "$jar" -d "$out" "$here/OwlOracle.java"

# The same JSON, except that numbers may differ in their last bits: sin, cos and
# pow round differently in the JVM and in V8, so a curve can land a few ulps apart.
same() {
  cmp -s "$1" "$2" && return
  node -e '
    const fs = require("fs")
    const [a, b] = process.argv.slice(1).map(f => JSON.parse(fs.readFileSync(f, "utf8")))
    const close = (x, y) => Math.abs(x - y) <= 1e-9 * Math.max(1, Math.abs(x), Math.abs(y))
    // Strings too, since points and paths arrive as text: the same words, the numbers close.
    const parts = s => s.split(/(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/)
    const eq = (x, y) => {
      if (typeof x === "number" && typeof y === "number") return close(x, y)
      if (typeof x === "string" && typeof y === "string") {
        if (x === y) return true
        const p = parts(x), q = parts(y)
        return p.length === q.length && p.every((s, i) => i % 2 ? close(+s, +q[i]) : s === q[i])
      }
      if (Array.isArray(x) && Array.isArray(y)) return x.length === y.length && x.every((v, i) => eq(v, y[i]))
      if (x && y && typeof x === "object" && typeof y === "object") {
        const k = Object.keys(x)
        return k.length === Object.keys(y).length && k.every(n => n in y && eq(x[n], y[n]))
      }
      return x === y
    }
    process.exit(eq(a, b) ? 0 : 1)' "$1" "$2"
}

# Store widgets above Owl.js's level are left out until it's ported: Quickshell
# shows them as needing an update, as an older launcher does.
js_level=$(sed -n 's/^var LEVEL = \([0-9]*\).*/\1/p' "$owl")
level() { awk 'match($0, /(^|[^A-Za-z0-9_])owl:[ \t]*[0-9]+/) { s = substr($0, RSTART, RLENGTH); sub(/.*:[ \t]*/, "", s); print s; found = 1; exit } END { if (!found) print 1 }' "$1"; }
widgets=()
for w in "$repo"/widgets/*/*/widget.owl "$repo"/faces/*/*/face.owl; do
  lv=$(level "$w")
  if [ "$lv" -le "$js_level" ]; then
    widgets+=("$w")
  else
    echo "skip - $(basename "$(dirname "$w")") needs owl $lv, Owl.js runs up to $js_level"
  fi
done

failed=0
check() {
  local name=$1 src=$2 fixture=$3
  if ! java "${java_opts[@]}" -cp "$jar:$out" OwlOracle "$src" "$fixture" >"$out/java.json" 2>"$out/java.err"; then
    echo "not ok - $name (reference evaluator: $src)"
    cat "$out/java.err" >&2
    failed=1
    return
  fi
  if ! node "$here/walk.js" "$owl" "$src" "$fixture" >"$out/js.json" 2>"$out/js.err"; then
    echo "not ok - $name (Owl.js evaluator: $src)"
    cat "$out/js.err" >&2
    failed=1
    return
  fi
  if same "$out/java.json" "$out/js.json"; then
    echo "ok - $name"
  else
    echo "not ok - $name"
    diff <(tr ',' '\n' <"$out/java.json") <(tr ',' '\n' <"$out/js.json") | head -10 || true
    failed=1
  fi
}

check "edge cases" "$here/edge.owl" "$here/edge.fixture.json"
for f in "$here"/*.fixture.json; do
  name=$(basename "$f" .fixture.json)
  case $name in edge | base) continue ;; esac
  check "$name with data" "$fixture_widgets/simonschubert/$name/widget.owl" "$f"
done
for w in "${widgets[@]}"; do
  check "$(basename "$(dirname "$w")") without data" "$w" "$here/base.fixture.json"
done

# Accepted and rejected alike, with the same message at the same place.
mine=$(node -e '
  const fs = require("fs"), Module = require("module")
  const m = new Module(process.argv[1]); m.filename = process.argv[1]
  m._compile(fs.readFileSync(process.argv[1], "utf8").replace(/^\.pragma library/, "//"), process.argv[1])
  for (const f of process.argv.slice(2)) {
    const src = fs.readFileSync(f, "utf8")
    try { m.exports.compile(src); console.log("OK  " + f) }
    catch (e) { console.log("ERR " + f + ":" + m.exports.formatError(src, e).split("\n")[0]) }
  }' "$owl" "${widgets[@]}" "$here/edge.owl" "$here"/cases/*.owl | sort)
theirs=$(java "${java_opts[@]}" -cp "$jar" dev.omalauncher.widgets.cli.MainKt check "${widgets[@]}" "$here/edge.owl" "$here"/cases/*.owl 2>&1 |
  grep -E '^(ok|ERR)' | sed -E 's/^ok  ([^ ]+).*/OK  \1/' | sort) || true # it exits 1 for the cases meant to fail
if [ "$mine" = "$theirs" ]; then
  echo "ok - owl check and Owl.js agree on every widget, face and case"
else
  echo "not ok - owl check and Owl.js disagree"
  diff <(echo "$theirs") <(echo "$mine") | head -10
  failed=1
fi

exit $failed
