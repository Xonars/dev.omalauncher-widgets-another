#!/usr/bin/bash
set -e
support="$HOME/.config/omalauncher/widgets/matrix-terminal"
tic -x "$support/transparent.terminfo"
export TERM=owl-matrix-transparent
exec cmatrix -b -u 5 -C green
