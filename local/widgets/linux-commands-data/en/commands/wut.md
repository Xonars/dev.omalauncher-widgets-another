# TAGLINE

CLI that explains your last terminal command output using an LLM

# TLDR

**Explain the output of the last command**

```wut```

# SYNOPSIS

**wut**

# DESCRIPTION

**wut** is a terminal assistant that uses a large language model (LLM) to explain whatever was most recently printed to your terminal. It can decipher stack traces, error codes, unfamiliar log lines, and unexpected command output, returning a plain-language explanation and often a suggested next step.

The tool reads the visible scrollback of the current pane via the host terminal multiplexer, so it must be invoked from inside a **tmux** or **screen** session. It sends the captured text to a configured LLM provider (e.g. OpenAI or Anthropic) using credentials stored as environment variables.

# CONFIGURATION

**OPENAI_API_KEY**
> API key used when wut is configured to call OpenAI models.

**ANTHROPIC_API_KEY**
> API key used when wut is configured to call Anthropic models.

# CAVEATS

Must be run inside a **tmux** or **screen** session — wut needs the multiplexer to capture pane contents. Each invocation sends terminal output to a third-party LLM, so avoid running it on output that contains secrets, tokens, or PII. Network access and a valid API key are required.

# HISTORY

**wut** was created by **Jonathan Shobrook** (shobrook) and is written in Python. It targets the same problem space as **thefuck** but explains errors instead of trying to auto-correct them.

# SEE ALSO

[tldr](/man/tldr)(1), [tmux](/man/tmux)(1), [screen](/man/screen)(1)
