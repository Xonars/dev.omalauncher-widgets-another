# TAGLINE

Query and set Raspberry Pi GPIO pin states

# TLDR

**Show all GPIO pin states**

```raspi-gpio get```

**Get the state of a specific pin**

```raspi-gpio get [17]```

**Configure a pin as output**

```sudo raspi-gpio set [17] op```

**Drive a pin high**

```sudo raspi-gpio set [17] dh```

**Drive a pin low**

```sudo raspi-gpio set [17] dl```

**Set as input with pull-up**

```sudo raspi-gpio set [18] ip pu```

**List alternate functions** for a pin

```raspi-gpio funcs [17]```

**Dump raw register values**

```sudo raspi-gpio raw```

# SYNOPSIS

**raspi-gpio** _command_ [_pin_] [_options_]

# COMMANDS

**get** [_pin_|_pin1,pin2,..._]
> Show pin states. Without a pin number, shows all GPIOs (0-53).

**set** _pin_ _options..._
> Configure pin direction, drive level, pull, or alternate function.

**funcs** [_pin_]
> Print the BCM-defined alternate functions for the given pin (or all pins).

**raw**
> Print the raw GPIO register values.

# OPTIONS FOR SET

**ip** / **op**
> Set as input / output.

**a0** ... **a5**
> Select alternate function 0-5.

**dl** / **dh**
> Drive low / drive high (only meaningful when **op** is set).

**pu** / **pd** / **pn**
> Pull up / pull down / no pull.

# DESCRIPTION

**raspi-gpio** is a low-level tool for inspecting and manipulating GPIO pins on Raspberry Pi boards. It writes directly to the BCM GPIO controller registers via /dev/gpiomem (or /dev/mem when run as root), bypassing higher-level libraries like libgpiod.

The tool is mainly intended for debugging hardware setups, verifying that DT overlays applied the expected pin functions, and one-off scripting. For production use, the kernel **gpiod** interface (via **libgpiod**'s **gpioget**/**gpioset**) is recommended because it integrates with the kernel's GPIO subsystem and respects kernel-claimed lines.

# CAVEATS

Raspberry Pi specific. **set** and **raw** require root because they write to the hardware. Writing the wrong direction or drive level on a pin connected to external hardware can damage the SoC. The numbering used is BCM (Broadcom) — not the physical board pin numbers.

# HISTORY

**raspi-gpio** is included with **Raspberry Pi OS** as a small utility maintained by the Raspberry Pi Foundation. It complements higher-level libraries like **wiringPi** (deprecated) and the kernel **gpiod** interface.

# SEE ALSO

[gpio](/man/gpio)(1), [vcgencmd](/man/vcgencmd)(1)
