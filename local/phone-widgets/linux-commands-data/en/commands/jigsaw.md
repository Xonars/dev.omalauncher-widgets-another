# TAGLINE

XScreenSaver hack that animates a jigsaw puzzle solving itself

# TLDR

**Run as the screensaver** on the root window

```jigsaw -root```

**Run in a window** for testing

```jigsaw -window```

**Set the animation speed**

```jigsaw -root -speed [1.0]```

**Set the puzzle complexity**

```jigsaw -root -complexity [1.0]```

# SYNOPSIS

**jigsaw** [**-root** | **-window**] [_options_]

# PARAMETERS

**-root**
> Draw on the root window (used by xscreensaver itself).

**-window**
> Draw in a new top-level window.

**-window-id** _id_
> Draw in an existing window with the given X11 ID.

**-speed** _float_
> Animation speed multiplier.

**-complexity** _float_
> Puzzle complexity (controls number of pieces).

**-delay** _usecs_
> Delay between frames, in microseconds.

**-fps**
> Display the frames-per-second counter.

# DESCRIPTION

**jigsaw** is one of the OpenGL hacks shipped with **xscreensaver** (and **xscreensaver-gl**). It loads an image, slices it into jigsaw puzzle pieces, scatters them in 3D space, and then animates them flying back together to reform the picture before scrambling again.

The image source is controlled by xscreensaver's standard image-grabbing settings, so the screensaver can use a random image from disk, a webcam frame, or a screenshot of the desktop.

# CAVEATS

Requires OpenGL and a working X11 display. Older systems without 3D acceleration will see degraded performance. Image source is configured globally for xscreensaver via **xscreensaver-settings**, not per-hack.

# SEE ALSO

[xscreensaver](/man/xscreensaver)(1), [xscreensaver-settings](/man/xscreensaver-settings)(1)
