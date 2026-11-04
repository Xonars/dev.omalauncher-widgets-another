#!/usr/bin/env bash
# Quickshell is still OWL 17. Compare it with its matching upstream oracle and
# fixtures in a temporary tree; keep the published Xonars catalogue owner-only.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
oracle_ref=a981ae7fd5560b16ff0264a167f38d3f28b777f0
workspace=$(mktemp -d "${TMPDIR:-/tmp}/another-quickshell.XXXXXXXX")
trap 'rm -rf -- "$workspace"' EXIT

git -C "$repo" cat-file -e "$oracle_ref^{commit}"
git -C "$repo" archive "$oracle_ref" tools/owl.jar widgets faces |
    tar -x -C "$workspace" --wildcards '*.owl' 'tools/owl.jar'
cp -a "$repo/runtimes" "$workspace/runtimes"
cp -a "$repo/widgets/." "$workspace/widgets/"
if [[ -d "$repo/faces" ]]; then cp -a "$repo/faces/." "$workspace/faces/"; fi

printf 'Quickshell OWL 17 oracle and fixtures: %s\n' "$oracle_ref"
"$workspace/runtimes/quickshell/test/run.sh"
