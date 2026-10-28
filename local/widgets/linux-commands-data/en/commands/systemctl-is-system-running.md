# TAGLINE

Check overall system operational state

# TLDR

Check **system state**

```systemctl is-system-running```

**Quiet** mode (exit code only)

```systemctl is-system-running -q```

**Wait** for boot completion

```systemctl is-system-running --wait```

# SYNOPSIS

**systemctl is-system-running** [_OPTIONS_]

# PARAMETERS

**-q, --quiet**
> Suppress output, return only exit code

**--wait**
> Wait until boot process is completed before returning

# DESCRIPTION

**systemctl is-system-running** checks the overall operational state of the system. It reports whether the system has finished booting and whether all units are functioning properly.

Possible states: initializing, starting, running, degraded, maintenance, stopping, offline, unknown. "Running" indicates successful boot with all units healthy.

# SYSTEM STATES

**initializing** — Early boot, before basic.target reached.

**starting** — Late boot, before all services have finished.

**running** — System fully operational, all units healthy.

**degraded** — System is running but at least one unit has failed.

**maintenance** — Rescue/emergency mode.

**stopping** — Shutdown in progress.

**offline** — System not booted under systemd (e.g., chroot).

**unknown** — State could not be determined.

# EXIT STATUS

Returns **0** only when the system reports `running`. Any other state returns non-zero, so `systemctl is-system-running -q` is a convenient health-check primitive in scripts.

# CAVEATS

The `--wait` option is useful in scripts that need to wait for complete system startup before proceeding. "Degraded" state indicates at least one unit failed.

# HISTORY

The **is-system-running** subcommand provides a high-level health check for the entire system, enabling automated monitoring and boot-completion detection.

# SEE ALSO

[systemctl-status](/man/systemctl-status)(1), [systemctl](/man/systemctl)(1)
