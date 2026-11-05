# TAGLINE

List available Python interpreter versions on Debian

# TLDR

**List installed Python versions**

```pyversions -i```

**Show supported versions**

```pyversions -s```

**Show default version**

```pyversions -d```

**Show requested versions**

```pyversions -r```

# SYNOPSIS

**pyversions** [_options_]

# PARAMETERS

**-i**, **--installed**
> List installed Python versions.

**-s**, **--supported**
> List Python versions currently supported by the running Debian release.

**-d**, **--default**
> Print the default Python version (target of **/usr/bin/python**).

**-r**, **--requested** [_pkg_|_setup.py_|_debian/control_]
> Print the Python versions requested by a package source (defaults to the **debian/control** in the current directory).

**-v**, **--version**
> Combined with one of the above, also print the corresponding interpreter path.

# DESCRIPTION

**pyversions** is a Debian-specific helper that reports information about **Python 2** interpreter versions available on the system. It lists installed versions, the default version, the versions supported by the current Debian release, and the versions a source package requests via its **X-Python-Version** field in **debian/control**. It is used by Debian's Python packaging infrastructure (debhelper, dh_python2) to drive build-time decisions.

The Python 3 counterpart is **py3versions**, which is the tool you should use today; **pyversions** itself was retired together with Python 2 in **Debian 11 (bullseye)** and removed from later releases.

# CAVEATS

Debian/Ubuntu specific and Python-2 only. The package providing it (**python**) was dropped in Debian 11+ and Ubuntu 20.04+. On modern systems, use **py3versions** instead.

# HISTORY

**pyversions** shipped as part of Debian's **python-minimal** / **python** package and was the canonical way to query Python 2 versions in Debian packaging. After Python 2 reached end-of-life on **2020-01-01**, the tool was deprecated alongside the language and removed from current Debian/Ubuntu releases.

# SEE ALSO

[python](/man/python)(1), [py3versions](/man/py3versions)(1), [update-alternatives](/man/update-alternatives)(1)

