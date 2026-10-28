# TAGLINE

CLI for the Kanwas collaborative thinking space

# TLDR

**Initialize** a new Kanwas workspace in the current directory

```kanwas init```

**Pull markdown** from a Kanwas board into the local repo

```kanwas pull```

**Push local changes** back to the workspace

```kanwas push```

**Authenticate** via browser-based OAuth on first use

```kanwas init```

# SYNOPSIS

**kanwas** _command_ [_options_]

# DESCRIPTION

**kanwas** is the command-line client for **Kanwas**, an open-source thinking space that combines a canvas, AI agents, real-time collaboration, and a sandbox. The CLI lets users sync content between a Kanwas workspace and a local Git repository so the resulting markdown can be handed to AI coding agents (Claude Code, Codex, etc.) or version-controlled alongside source.

Authentication uses browser-based OAuth, so credentials are not stored as long-lived tokens on the local machine.

# COMMANDS

**init**
> Initialize a new local workspace, linking it to a remote Kanwas board and triggering OAuth.

**pull**
> Download the markdown representation of the workspace into the current repository.

**push**
> Upload local markdown changes back to the linked Kanwas board.

# CAVEATS

The CLI is part of an actively evolving platform; the set of commands and their flags may change between releases. OAuth requires a browser on the same machine that runs **kanwas**, so headless servers may need a different login flow.

# HISTORY

**Kanwas** is developed by the **kanwas-ai** organization as an open-source platform for collaborative thinking that pairs human users with AI agents on a shared canvas. The CLI exists to integrate canvas content into existing developer workflows.

# SEE ALSO

[git](/man/git)(1), [claude](/man/claude)(1)
