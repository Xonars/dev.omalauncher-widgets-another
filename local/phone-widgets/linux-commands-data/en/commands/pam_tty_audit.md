# TAGLINE

logs TTY keystrokes

# TLDR

**Enable TTY auditing**

```session required pam_tty_audit.so enable=*```

**Audit specific users**

```session required pam_tty_audit.so enable=admin,root```

**Disable for users**

```session required pam_tty_audit.so disable=service_account```

# SYNOPSIS

**pam_tty_audit.so** [_options_]

# PARAMETERS

**enable=**_PATTERN_
> Enable TTY auditing for users matching the comma-separated pattern (use `*` for all users).

**disable=**_PATTERN_
> Disable TTY auditing for the matching users; processed alongside `enable=` so order matters.

**open_only**
> Set the audit flag only for the session opening, not for the whole login session.

**log_passwd**
> Also log keystrokes entered while the TTY is in non-echo (password) mode. Disabled by default for privacy.

**debug**
> Log additional information for debugging via `syslog(3)`.

# DESCRIPTION

**pam_tty_audit** is a PAM session module that toggles the per-process TTY input auditing flag (`task->signal->audit_tty`) at session open and restores it on close. When enabled, every keystroke read from a controlling TTY by the affected processes is recorded by the kernel and forwarded to **auditd** as `TTY` records.

It is commonly placed in `/etc/pam.d/system-auth` (or distribution-specific equivalent) as a `session` rule and used to satisfy compliance requirements (PCI-DSS, STIG) that mandate logging of administrative shell activity.

# CAVEATS

Requires the kernel `CONFIG_AUDIT_TTY` feature and a running **auditd**. Logging keystrokes raises serious privacy concerns and may capture passwords in non-echo mode if `log_passwd` is set. Audit records are written to `/var/log/audit/audit.log`; review with **aureport --tty** or **ausearch -m TTY**.

# HISTORY

pam_tty_audit provides **keystroke auditing** for compliance requirements.

# SEE ALSO

[pam](/man/pam)(8), [auditd](/man/auditd)(8), [aureport](/man/aureport)(8)

