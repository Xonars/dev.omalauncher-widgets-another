# TAGLINE

Sandbox launcher for AI coding agents with computer-use

# TLDR

**Run the default agent** in a sandbox

```cuabot```

**Launch a specific agent** (claude, codex, aider, openclaw, gemini, vibe)

```cuabot [agent]```

**Run any command** inside the sandbox

```cuabot [command]```

**Start a named isolated** session

```cuabot -n [session_name] [agent]```

**Take a screenshot** of the sandbox

```cuabot --screenshot [path/to/output.png]```

**Click at** specific coordinates

```cuabot --click [x] [y]```

**Run a bash command** inside the sandbox

```cuabot --bash "[command]"```

**Start the** background daemon

```cuabot --serve [port]```

**Check daemon** status

```cuabot --status```

# SYNOPSIS

**cuabot** [_options_] [_agent_ | _command_]

# DESCRIPTION

**cuabot** is a TUI launcher that runs any CLI coding agent (Claude Code, Codex, Aider, OpenClaw, etc.) or GUI application inside an isolated sandbox with computer-use capabilities. Each agent gets its own window streamed to the host desktop, with clipboard sharing and audio, while remaining isolated from the host system.

The sandbox exposes a computer-use API so agents can take screenshots, click, type, scroll, and run shell commands inside the container. Multiple isolated sessions can run concurrently using **-n**, each with its own container and port.

# COMMANDS

**cuabot** _agent_
> Launch the named agent (e.g. _claude_, _codex_, _aider_, _openclaw_, _gemini_, _vibe_) in a sandbox.

**cuabot** _command_
> Execute an arbitrary command inside the sandbox.

**--serve** [_port_]
> Start the **cuabotd** daemon on the optional port.

**--stop**
> Stop the running daemon.

**--status**
> Print daemon status.

# COMPUTER-USE OPTIONS

**--screenshot** [_path_]
> Capture a screenshot of the sandbox display.

**--click** _x_ _y_ [_button_]
> Click at the given coordinates with the optional button.

**--doubleclick** _x_ _y_
> Double-click at the given coordinates.

**--move** _x_ _y_
> Move the mouse to the coordinates.

**--mousedown** / **--mouseup** _x_ _y_
> Press or release a mouse button.

**--drag** _x1_ _y1_ _x2_ _y2_
> Drag from one coordinate to another.

**--scroll** _x_ _y_ _dx_ _dy_
> Scroll at the given position by the given delta.

**--type** _text_
> Type the given string.

**--key** _key_
> Press and release a single key.

**--keydown** _key_ / **--keyup** _key_
> Press or release a key without releasing/pressing it.

**--bash** _command_
> Run a bash command inside the sandbox.

# OPTIONS

**-n**, **--name** _name_
> Use a named isolated session (separate container and port).

**--help**
> Show usage information.

# CAVEATS

The sandbox is intended for AI agents that may execute arbitrary commands. While containerization isolates agents from the host, sharing the clipboard, microphone, or sensitive credentials into a sandbox can leak data. Treat the sandbox boundary as defense-in-depth, not a substitute for code review of agent actions.

# HISTORY

**cuabot** is developed by **trycua** as part of the **Cua** project, an open-source platform for **Computer-Use Agents**. The tool aims to provide a uniform sandbox layer that any coding agent can plug into, decoupling the agent from the host environment.

# SEE ALSO

[claude](/man/claude)(1), [aider](/man/aider)(1), [docker](/man/docker)(1), [chromium](/man/chromium)(1)
