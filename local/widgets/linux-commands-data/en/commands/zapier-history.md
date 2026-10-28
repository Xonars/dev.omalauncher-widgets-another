# TAGLINE

View Zapier integration deployment history

# TLDR

**Show version history** for the current integration

```zapier history```

**Show in JSON format**

```zapier history --format=json```

**Limit number of entries**

```zapier history --limit=[20]```

# SYNOPSIS

**zapier** **history** [_options_]

# PARAMETERS

**--format** _FORMAT_
> Output format: **plain**, **json**, **raw**, **row**, or **table** (default: table).

**--limit** _N_
> Maximum number of history entries to display.

**--debug**
> Show debug logs alongside output.

# DESCRIPTION

**zapier history** displays the deployment and migration history for a Zapier CLI integration. Each row shows the action performed (push, migrate, promote, deprecate), the version affected, the user who performed it, and the timestamp.

The command is useful for auditing rollouts, finding the version a migration moved users to, and spotting when a version was promoted to production.

# CAVEATS

Run inside a Zapier integration project directory, after authenticating with **zapier login**. History only covers the integration linked to the current directory.

# SEE ALSO

[zapier](/man/zapier)(1), [zapier-versions](/man/zapier-versions)(1)
