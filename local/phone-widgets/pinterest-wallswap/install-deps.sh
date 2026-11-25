#!/usr/bin/env bash
set -euo pipefail
app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="$HOME/.local/share/pinterest-wallswap/venv"
python -m venv --system-site-packages "$venv_dir"
"$venv_dir/bin/python" -m pip install -r "$app_dir/requirements.txt"
