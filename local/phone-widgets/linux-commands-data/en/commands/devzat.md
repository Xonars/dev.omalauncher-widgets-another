# TAGLINE

SSH-based chat server you join with your existing SSH client

# TLDR

**Connect** to the public Devzat server

```ssh [devzat.hackclub.com]```

**Pick a display name** by passing it as the SSH username

```ssh [nickname]@[devzat.hackclub.com]```

**Connect over port 443** (useful behind restrictive firewalls)

```ssh [devzat.hackclub.com] -p 443```

**Run your own Devzat server** (binary built from source)

```devzat```

**Run a server on a custom port**

```devzat --port [4242]```

# SYNOPSIS

**ssh** [_user_@]_devzat-host_ [**-p** _port_]

**devzat** [**--port** _N_] [**--admin** _key_] [_options_]   _(server-side)_

# DESCRIPTION

**Devzat** is a custom SSH server that drops connecting clients into a real-time chat room instead of giving them a shell. Because the protocol is plain SSH, **there is no client to install** — every device with an SSH client (Linux, macOS, Windows, even mobile SSH apps) can join.

The display name shown in chat is the username supplied during the SSH handshake (**user@host**); change it by reconnecting with a different name or by using the in-room **/nick** command. Servers identify users by their SSH public key, so the same key consistently maps to the same identity across reconnects.

The **devzat** binary referenced on the command line is the **server**; end users almost never run it. Self-hosters use it to expose their own chat instance.

# IN-ROOM COMMANDS

**/users**
> List users currently in the room.

**/dm** _user_ _message_ (or **/msg**)
> Send a private message to another user.

**/nick** _name_
> Change your display name.

**/rooms**
> List available chat rooms.

**/join** _room_
> Switch to another room (creates it if missing).

**/help**
> Show all available slash commands.

**/exit**
> Leave the chat (Ctrl+C also works).

# CAVEATS

The **devzat** package on most package managers installs the **server**, not a client. To chat, just use **ssh** — the previous "client CLI" usage documented in some places never existed. Server operators see all messages in plaintext (the SSH transport is encrypted hop-to-server only); do not share secrets in chat.

# HISTORY

**Devzat** was created by **Arjun Salyan / Ishan Goel (quackduck)** to let developers chat over the SSH infrastructure they already trust. The flagship public instance runs at **devzat.hackclub.com**, sponsored by Hack Club.

# SEE ALSO

[ssh](/man/ssh)(1), [weechat](/man/weechat)(1), [irssi](/man/irssi)(1)
