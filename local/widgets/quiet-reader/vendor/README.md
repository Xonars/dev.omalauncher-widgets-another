# Bundled MOBI extractor

KindleUnpack by Charles M. Hannum, P. Durrant, K. Hendricks, S. Siebert,
fandrieu, DiapDealer, nickredding, tkeo and other upstream contributors.

- Source: https://github.com/kevinhendricks/KindleUnpack
- Pinned commit: `bf0ca6ece4e73494625e7950be3e259b6260774c`
- Archive SHA-256: `7df30c8e2096e31812fba99f3862e56c9b55008f71e422bef9f7eea51ddb0b6e`
- Included: unmodified `lib/`, upstream `README.md`, and `COPYING.txt`.
- License: GPL-3.0; see `KindleUnpack/COPYING.txt` and file-level notices.

The reader invokes this standalone program through `unpack_mobi.py` in a
separate Python process. It needs only Python's standard library, including
the upstream-bundled image header detector; no Calibre, pip, GUI packages,
network connection, or DRM-removal tools are needed at runtime.
