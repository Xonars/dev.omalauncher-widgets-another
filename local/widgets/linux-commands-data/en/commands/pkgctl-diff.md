# TAGLINE

Compare Arch package file differences

# TLDR

Compare package files in **tar content list** mode (default)

```pkgctl diff -l path/to/file```

Compare package files using **diffoscope**

```pkgctl diff -d path/to/file```

Compare package **.PKGINFO** files

```pkgctl diff -p path/to/file```

Compare package **.BUILDINFO** files

```pkgctl diff -b path/to/file```

# SYNOPSIS

**pkgctl diff** [_options_] _file|pkgname_

# PARAMETERS

**-l**, **--list**
> Compare using tar content list mode (default)

**-d**, **--diffoscope**
> Compare using diffoscope for detailed diff

**-p**, **--pkginfo**
> Compare .PKGINFO metadata files

**-b**, **--buildinfo**
> Compare .BUILDINFO files

# DESCRIPTION

**pkgctl diff** compares a locally built **.pkg.tar.zst** against the same package as currently published in the official Arch repositories (or against another local package file). It is the standard pre-release sanity check for Arch package maintainers, exposing accidental file moves, dropped binaries, soname bumps, or unintended **.PKGINFO**/**.BUILDINFO** drift.

Without flags it runs in **--list** mode, which compares the tar manifest. Use **--diffoscope** for byte-level differences (slow but exhaustive), **--pkginfo** for runtime metadata, or **--buildinfo** to verify reproducibility-relevant fields like compiler flags and installed build dependencies.

# CAVEATS

**--diffoscope** requires the **diffoscope** package and can be very slow on packages with large compiled artifacts. When passed a bare _pkgname_, **pkgctl diff** downloads the published package from the mirrors, so a working network and configured Pacman mirrorlist are required.

# HISTORY

Part of **pkgctl**, the Arch Linux package control tool for official repository maintainers.

# SEE ALSO

[pkgctl](/man/pkgctl)(1), [diffoscope](/man/diffoscope)(1)
