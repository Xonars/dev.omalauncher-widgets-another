# TAGLINE

Command-line client for Atlassian Jira

# TLDR

**Initialize configuration**

```jira init```

**List recent issues**

```jira issue list```

**Filter issues** by JQL

```jira issue list --jql "[project = PROJ AND status = Open]"```

**Create an issue** interactively

```jira issue create```

**View an issue**

```jira issue view [PROJ-123]```

**Move an issue** to a status

```jira issue move [PROJ-123] "[In Progress]"```

**Assign an issue** to a user

```jira issue assign [PROJ-123] [username]```

**Add a comment**

```jira issue comment add [PROJ-123] "[comment body]"```

**Open issue in browser**

```jira open [PROJ-123]```

# SYNOPSIS

**jira** _command_ [_subcommand_] [_options_]

# COMMANDS

**init**
> Initialize the configuration file with server URL, login, and default project.

**issue**
> Issue management: create, view, list, edit, assign, move, comment, link, watch, etc.

**project**
> List and inspect projects.

**sprint**
> Manage sprints (Jira Cloud / Software).

**epic**
> Manage epics and their child issues.

**board**
> List boards in a project.

**me**
> Show the currently authenticated user.

**open**
> Open an issue in the default web browser.

**completion**
> Generate shell completion scripts.

# PARAMETERS

**-p**, **--project** _key_
> Override the default project key for the current invocation.

**--config** _file_
> Path to a config file other than the default.

**--debug**
> Enable verbose debug logging.

**--help**
> Display help information.

# DESCRIPTION

**jira** (jira-cli) is an open-source command-line client for Atlassian Jira Cloud and Data Center. It provides interactive TUI flows for the common workflow operations (create, transition, comment) and JQL-driven listings suitable for piping into shell scripts.

Authentication is handled via API tokens stored in **~/.config/.jira/.config.yml**. The tool supports multiple Jira instances, custom fields, and templates for issue creation.

# CONFIGURATION

**~/.config/.jira/.config.yml**
> Stores server URL, default project, user/email, and API token.

**JIRA_API_TOKEN**
> Environment variable that overrides the stored API token.

# CAVEATS

Requires a Jira account and API token (Atlassian Cloud) or personal access token (Data Center). This is the third-party **jira-cli** tool by **ankitpokhrel**, not an official Atlassian product. Some features (e.g. sprint operations) require Jira Software, not just Jira Core/Work Management.

# HISTORY

**jira-cli** was created by **Ankit Pokhrel** to provide a fast, scriptable interface to Jira from the terminal. The project is written in Go.

# SEE ALSO

[gh](/man/gh)(1), [glab](/man/glab)(1), [git](/man/git)(1)
