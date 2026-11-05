# TAGLINE

network authentication protocol

# TLDR

**Get ticket**

```kinit [principal]```

**List tickets**

```klist```

**Destroy tickets**

```kdestroy```

**Change password**

```kpasswd```

**Forward ticket**

```kinit -f [principal]```

**Renew ticket**

```kinit -R```

# SYNOPSIS

Kerberos commands: **kinit**, **klist**, **kdestroy**, **kpasswd**

# PARAMETERS

**kinit** _PRINCIPAL_
> Get Kerberos ticket.

**klist**
> List cached tickets.

**kdestroy**
> Destroy tickets.

**kpasswd**
> Change Kerberos password.

**-f**
> Get forwardable ticket.

**-R**
> Renew existing ticket.

**-l** _LIFETIME_
> Ticket lifetime.

# DESCRIPTION

**Kerberos** is a network authentication protocol. Clients receive a time-limited Ticket-Granting Ticket (TGT) from a Key Distribution Center (KDC) after presenting credentials, then exchange the TGT for service tickets to access individual network services. All authentication exchanges are encrypted, and the user's password never traverses the network after the initial **kinit**.

The user-facing CLI is built around four small commands: **kinit** (request a TGT), **klist** (inspect the credential cache), **kdestroy** (clear cached tickets), and **kpasswd** (change the password held by the KDC). Service tickets are obtained transparently by Kerberos-aware applications (SSH, NFSv4, HTTP via SPNEGO, LDAP, SMB).

# CONFIGURATION

**/etc/krb5.conf**
> Client configuration: realms, KDC addresses, default principal, forwardable flag, encryption types.

**/etc/krb5.keytab** (or **$KRB5_KTNAME**)
> Service-side keytab containing long-term keys for daemon principals.

**$KRB5CCNAME**
> Path or backend for the credentials cache (e.g. **FILE:/tmp/krb5cc_$UID**, **KEYRING:persistent:$UID**, **KCM:**).

# CAVEATS

Clocks between client, KDC, and target service must agree to within a few minutes (default skew: 5 minutes). DNS forward and reverse records must match the principal name; broken reverse DNS is the most common cause of `KRB_AP_ERR_BAD_INTEGRITY` and `Server not found in Kerberos database` errors.

# HISTORY

Kerberos was developed at **MIT** as part of Project Athena in the late 1980s. **Kerberos v5** (RFC 4120) is the current standard; v4 is obsolete and removed from modern Linux distributions. The two interoperable implementations in widespread use are **MIT Kerberos** and **Heimdal**.

# SEE ALSO

[kinit](/man/kinit)(1), [smbclient](/man/smbclient)(1), [ldapsearch](/man/ldapsearch)(1)
