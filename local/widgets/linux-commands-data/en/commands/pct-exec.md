# TAGLINE

launches a command inside a specified Proxmox LXC container

# TLDR

**Execute** command in container

```pct exec 100 command```

Open **bash** shell

```pct exec 100 bash```

Pass **arguments**

```pct exec 100 -- command arguments```

# SYNOPSIS

**pct exec** _vmid_ [--] _command_ [_arguments_...]

# DESCRIPTION

**pct exec** launches a command inside a specified Proxmox LXC container. It provides direct command execution without needing to enter the container interactively.

# PARAMETERS

_VMID_
> The numeric ID of the LXC container (100–999999999).

_COMMAND_
> The command and any arguments to execute inside the container.

**--**
> Separator that stops `pct` from interpreting subsequent flags, so they are passed through to the command.

# CAVEATS

The container must be running to execute commands. The command runs as **root** inside the container, regardless of the host user invoking `pct exec`. There is no TTY allocation by default — for interactive shells use **pct enter** instead. The command's exit status is returned to the caller, but pre-execution failures (container not running, etc.) yield Proxmox-specific error codes.

# HISTORY

**pct exec** is part of the **Proxmox VE** virtualization platform for managing LXC containers.

# SEE ALSO

[pct](/man/pct)(1), [pct-enter](/man/pct-enter)(1)
