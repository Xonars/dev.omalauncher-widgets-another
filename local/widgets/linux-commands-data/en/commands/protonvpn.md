# TAGLINE

Official Proton VPN command-line client

# TLDR

**Sign in** to Proton VPN

```protonvpn signin [username]```

**Sign out**

```protonvpn signout```

**Connect** to the fastest server

```protonvpn connect```

Connect to a **specific country**

```protonvpn connect --country [US]```

Connect to a **named server**

```protonvpn connect [US-NY-01]```

**Disconnect**

```protonvpn disconnect```

**Enable kill switch**

```protonvpn config set kill-switch on```

**List configurable options**

```protonvpn config list```

# SYNOPSIS

**protonvpn** [**signin**|**signout**|**connect**|**disconnect**|**info**|**status**]

# COMMANDS

**signin** [_username_]
> Authenticate with Proton VPN credentials.

**signout**
> Remove stored credentials.

**connect** [_server_]
> Establish a VPN connection. Without arguments, connects to the fastest available server. Accepts a server name or use **--country** / **--city**.

**disconnect**
> Terminate the active VPN connection.

**status**
> Show current connection status.

**info**
> Display account information.

**config list**
> List configurable options.

**config set** _option_ _value_
> Change a configuration option (e.g., **kill-switch on**, **netshield f1**, **vpn-accelerator on**).

# PARAMETERS

**--country** _CODE_
> Restrict **connect** to servers in a specific country.

**--city** _CITY_
> Restrict **connect** to servers in a specific city.

**--protocol** _PROTOCOL_
> Override the connection protocol (e.g., _wireguard_, _openvpn-tcp_, _openvpn-udp_).

**-h, --help**
> Display help information.

# DESCRIPTION

**protonvpn** is the official command-line client for Proton VPN service. It provides secure, encrypted VPN connections with features like kill switch, split tunneling, and server selection.

The CLI allows scripting VPN connections and provides all functionality of the graphical client for headless servers or terminal users.

# CAVEATS

Requires Proton VPN subscription. Some features require paid plans. Network manager integration varies by distribution. Root may be required for some operations.

# HISTORY

**protonvpn** CLI was developed by **Proton AG** to complement their graphical VPN clients. Proton VPN emphasizes privacy and is based in Switzerland with strong privacy laws.

# SEE ALSO

[openvpn](/man/openvpn)(8), [wg-quick](/man/wg-quick)(8), [nmcli](/man/nmcli)(1)
