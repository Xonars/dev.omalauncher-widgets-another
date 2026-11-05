# TAGLINE

shows the evolution history of a change

# TLDR

**Show evolution log**

```jj evolog```

**Evolog for specific revision(s)**

```jj evolog -r [revset]```

**Show with diff**

```jj evolog -p```

**Limit entries**

```jj evolog -n [10]```

**Flat list (no graph)**

```jj evolog --no-graph```

**Show oldest entries first**

```jj evolog --reversed```

# SYNOPSIS

**jj evolog** [_options_]

# PARAMETERS

**-r**, **--revisions** _REVSETS_
> Follow evolution of these revisions (default: _@_, the working-copy commit).

**-n**, **--limit** _LIMIT_
> Limit the number of revisions to show.

**--reversed**
> Show revisions in opposite order (older first).

**-G**, **--no-graph**
> Hide the ASCII graph and show a flat list of revisions.

**-T**, **--template** _TEMPLATE_
> Render output using a custom template expression.

**-p**, **--patch**
> Show a diff against the previous version of each change.

**-s**, **--summary**
> For each path, show only whether it was modified, added, or deleted.

**--stat**
> Show a histogram of the changes per file.

**--git**
> Format diffs in Git-compatible form.

**--name-only**
> Show only path names of changed files.

**--help**
> Display help information.

# DESCRIPTION

**jj evolog** shows the evolution history of a change. It displays how a change has been modified over time.

The command reveals rewriting, rebasing, and amendment history. It helps understand how changes evolved.

# CAVEATS

Subcommand of jj. Shows internal evolution. Unique to Jujutsu model.

# HISTORY

jj evolog is part of **Jujutsu**, leveraging its first-class support for change evolution tracking.

# SEE ALSO

[jj](/man/jj)(1), [jj-log](/man/jj-log)(1), [jj-show](/man/jj-show)(1)
