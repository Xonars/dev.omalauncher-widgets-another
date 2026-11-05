# TAGLINE

Official command-line interface for bunny.net

# TLDR

**Authenticate** the CLI with your bunny.net account

```bunny login```

**Deploy** the current project as a Magic Containers app

```bunny apps deploy```

**List** databases on your account

```bunny db list```

**Install** the CLI via the shell installer

```curl -fsSL https://cli.bunny.net/install.sh | sh```

**Install** the CLI globally via npm

```npm install -g @bunny.net/cli```

**Show** help and list available subcommands

```bunny --help```

# SYNOPSIS

**bunny** _command_ [_subcommand_] [_options_]

# PARAMETERS

**login**
> Authenticate the local CLI with a bunny.net account; tokens are stored locally for subsequent commands.

**apps deploy**
> Build and deploy the current project to **Magic Containers**. Automatically provisions infrastructure, scales globally, and routes traffic.

**db list**
> List databases (including bunny.net's edge database product) attached to the active account.

**--help**, **-h**
> Print help for the CLI or a specific subcommand.

**--version**
> Print version information.

# DESCRIPTION

**bunny** is the official command-line client for **bunny.net**, providing terminal access to the platform's developer toolkit: **Magic Containers**, edge databases, storage buckets, edge scripts, DNS zones, and CDN pull zones. It is implemented in **TypeScript** and distributed both as a standalone binary and as the npm package **@bunny.net/cli**.

The CLI's primary workflows include logging in, deploying applications to Magic Containers (which auto-provisions globally distributed runtimes), and managing supporting resources such as databases. It is part of bunny.net's broader move toward a unified developer experience, alongside the **@bunny.net/api** type-safe SDK and one-click templates.

# CAVEATS

The CLI is comparatively new and still evolving - subcommands and flags may change between releases. **bunny** is the binary name shipped by **BunnyWay/cli**; several unrelated community projects also call themselves "bunny CLI" (for example **own3d/bunny-cli**, **straticus1/bunny-cli**, and **simplesurance/bunny-cli**), each with its own command surface. Confirm which package is installed before troubleshooting.

# CONFIGURATION

After **bunny login**, credentials are persisted to the user's home directory (typically under **$XDG_CONFIG_HOME/bunny** or **~/.config/bunny**). API tokens used for non-interactive automation can be supplied via environment variables defined per subcommand.

# HISTORY

**bunny** is published by **bunny.net** in the **BunnyWay/cli** monorepo on GitHub. It was introduced in **2024** to expose the company's developer platform - in particular the **Magic Containers** product - through a single, scriptable CLI.

# SEE ALSO

[curl](/man/curl)(1), [docker](/man/docker)(1), [flyctl](/man/flyctl)(1), [wrangler](/man/wrangler)(1)
