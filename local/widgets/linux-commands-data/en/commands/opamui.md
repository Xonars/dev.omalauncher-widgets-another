# TAGLINE

TUI for browsing and searching OCaml opam packages

# TLDR

**Browse opam packages** interactively

```opamui```

# SYNOPSIS

**opamui**

# DESCRIPTION

**opamui** is a terminal user interface for browsing and searching OCaml opam packages. It launches a full-screen TUI listing packages from the configured opam switch and lets you filter by name, see which packages are installed, and inspect package metadata such as version, synopsis, dependencies, and homepage.

It does **not** install or modify packages — it is purely a read-only browser that wraps **opam**'s package listing and inspection commands.

# KEY BINDINGS

**↑** / **↓**
> Move selection in the package list.

**/**
> Filter packages by substring.

**Enter**
> Open the metadata view for the selected package.

**q**
> Quit.

# CAVEATS

Requires **opam** to be installed and an opam switch to be initialized (**opam init**). The set of packages shown reflects the currently active switch; run **opam switch** to see another set.

# HISTORY

**opamui** was created by **Nicolas Lamirault** (nlamirault) and is written in OCaml. It targets developers who want to explore the opam ecosystem without leaving the terminal.

# SEE ALSO

[opam](/man/opam)(1)
