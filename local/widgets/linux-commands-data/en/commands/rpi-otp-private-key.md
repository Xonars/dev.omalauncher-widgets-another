# TAGLINE

Read or write a private key in Raspberry Pi OTP memory

# TLDR

**Read the OTP private key**

```sudo rpi-otp-private-key```

**Write a private key** from a binary file (irreversible!)

```sudo rpi-otp-private-key -w [keyfile.bin]```

**Specify which row** of OTP memory to read or write

```sudo rpi-otp-private-key -y [56]```

# SYNOPSIS

**rpi-otp-private-key** [**-w** _file_] [**-y** _row_] [**-c**]

# PARAMETERS

**-w** _file_
> Write the contents of _file_ (must be 32 bytes / 256 bits) to OTP memory. Permanent.

**-y** _row_
> Override the default OTP row used to store the key.

**-c**
> Check whether the OTP key has been programmed without printing it.

# DESCRIPTION

**rpi-otp-private-key** reads or writes the customer-controlled 256-bit private key stored in the One-Time Programmable (OTP) memory of a Raspberry Pi's SoC. The key is used to sign or decrypt material as part of the Raspberry Pi secure boot chain (sometimes called "Customer OTP").

When invoked with no flags, it prints the currently programmed key as a 64-character hex string (or all zeros if it has not been programmed). With **-w**, it burns the supplied 32-byte file into OTP — this is **permanent and cannot be undone**, including after factory reset.

# CAVEATS

OTP programming is **irreversible**: once burned, the bits cannot be cleared. A bad write can permanently brick secure-boot deployments. The displayed private key should be treated as sensitive and never shared. Requires running as root because it accesses the OTP via the VideoCore mailbox interface (vcgencmd).

# HISTORY

Part of the **rpi-eeprom** package shipped with Raspberry Pi OS, providing tools for managing EEPROM and OTP on Raspberry Pi 4 and later. Used by Raspberry Pi's secure-boot infrastructure introduced with the Raspberry Pi 4 boot ROM updates.

# SEE ALSO

[rpi-eeprom-update](/man/rpi-eeprom-update)(1), [vcgencmd](/man/vcgencmd)(1)
