# OWL for Quickshell

A second runtime for OWL, the widget language of this store: the same
`widget.owl` files the Android launcher draws, drawn by
[Quickshell](https://quickshell.org) on Linux. Omarchy Mobile's widget board
is built on it.

```sh
quickshell -p runtimes/quickshell                              # every face and widget in this repo
OWL_WIDGETS=~/my-widgets quickshell -p runtimes/quickshell     # a folder of your own
```

## How it works

| File | Does |
| --- | --- |
| `Owl.js` | the language: lexer, parser, compiler, builtins, and the live instance that turns a widget into a plain render tree. No QML in it, so it also runs under node |
| `OwlWidget.qml` | one widget file, live: compiles it, runs its sources, keeps its state, runs its actions, writes `.errors/<file>.txt` |
| `OwlSource.qml` | one `source`: cmd, stream, http, file, clock, android.* |
| `OwlNode.qml`, `OwlLayout.js` | the nodes, laid out by the launcher's rules |
| `OwlCanvas.qml` | `Canvas` drawing calls, replayed onto a QML Canvas each frame |
| `OwlTerminal.qml` | `Terminal { }` |
| `OwlHost.qml` | what a widget needs from the shell around it, with defaults |
| `owl-source` | android.device, android.system (with the Arch facts as `linux`), android.volume, android.modes and android.network, read from Linux |
| `shell.qml` | a board of widgets in a window: the example, and `quickshell -p`'s entry |

Quickshell draws everything; `Owl.js` decides what. Each widget is compiled
once, its sources update values, and only a render tree of plain objects
reaches QML, so a source that changes a number redraws that number. Sources
run only while the widget is shown (`active`). An animated widget draws on a
clock at the host's `frameRate`, and the clock runs only while something on
screen reads `time` -- the tree, or a Canvas's drawing -- so a player's bars
cost nothing while nothing plays. A Canvas whose drawing doesn't read `time`
is not painted again by the clock.

## Embedding it

Copy this folder into your shell (Quickshell imports QML only from inside its
config folder) and give each widget a host:

```qml
OwlHost {
  id: owlHost
  monoFamily: "JetBrainsMono Nerd Font"
  function act(widget, name, args) {
    if (name === "launcher") return myLauncher.open(args[0])
    defaultAct(widget, name, args)
  }
}

OwlWidget { id: w; path: "/path/to/widget.owl"; host: owlHost; palette: myPalette; active: shown }
OwlNode { anchors.fill: w; widget: w; node: w.tree ? w.tree.children[0] : null }
```

`palette` is `Owl.themeFromToml(<an Omarchy colors.toml>)`: OWL's theme names
(`accent`, `red`, `color4`, `lighter_background`...) to colors. `shell.qml`
is a complete example, and Omarchy Mobile's board
(`shell/plugins/mobile/surfaces/widget-board/`) a larger one, with the
launcher's long-press editing.

`OwlHost` is where a shell differs: fonts, the scale (`dp`), where persisted
state lives, how `terminal()`/`app()`/`url()`/`launcher()` start things, what
`android.media` reads (MPRIS by default), how many frames a second an
animated widget draws (`frameRate`, 30), and a hook for an on-screen keyboard.

## How faithful it is

The language half is a port of the reference implementation, the `owl`
module in `tools/owl.jar`, and is held to it by `test/run.sh`: the jar's
compiler and evaluator and `Owl.js` walk the same widgets with the same data
and must print the same bytes -- every store widget and face, with and without
data, and a few hundred expressions chosen to break a port -- and `owl check`
and `Owl.js` must accept and reject the same files with the same messages,
those and the one-rule files in `test/cases/`. CI runs it on every change to
this folder or to the jar.

The renderer follows the launcher's (`widgets/render/Render.kt` in
omarchy-proot): Compose's Row and Column measure order and weights, its
monospace text with Android's line spacing, its default sizes, a 69 dp cell.

Where it differs, because Android is not here:

- **Shader** draws its `fallback`: Qt compiles shaders ahead of time, and AGSL
  is Android's. The language already allows for phones that cannot run one.
- **Terminal** is a terminal of its own -- a pseudo-terminal, its output as
  text, a line to type into -- not an embedded foot window, which only a
  compositor can do. Full-screen programs open in a real terminal.
- **android.notifications**, **android.apps** and **android.recent** are empty
  lists, **android.agents** has none installed and **android.drawer** no apps;
  **androidApp()**, **notification()**, **open()**, **ask()**, **appAction()**
  and **workApps()** report that there is no Android or launcher drawer, and
  `shortcuts(...)` gives an empty list. A shell that has its own can override
  `act()`.
- **Apps, panels and key bars** (`app "…" { }`, `panel "…" { }`,
  `keybar "…" { }`) are refused: there is no app drawer to open an app from, no
  home screen or prompt bar to swipe a panel out of, and no soft keyboard for
  the extra keys to sit over. `query` and `screenTop` are therefore unknown here
  too, and `pressKey()`, `typeText()` and `latch()` report that there's no
  on-screen keyboard; `android.modifiers` holds none.
- **Secrets** (`state token = null secret`) are kept in
  `<stateDir>/<file>.secrets.json`, a file only the user can read, beside the
  `persist` values: a desktop has no keystore to encrypt them with, as the
  launcher does. Like the launcher, it keeps each only while the widget sends it
  to the same servers.
- **settings()** reports that there are no Android settings panels;
  **dnd()** switches mako's do-not-disturb mode, as Omarchy does, and
  `android.modes` reads the radios from rfkill, the dark theme from GNOME's
  setting and the brightness from brightnessctl. **torch()** does nothing, and
  **volume()** has only the media stream. **android.sim** is a tablet's: no
  mobile service. **android.network** counts every interface but loopback.
- **android.power** reads nothing, every field null, and **android.speech**
  is a desktop's without a recognizer: `available` false, so `speech("start")`
  reports that there is none. **pickImages()** reports that there are no phone
  photos to pick.
- **ws(...)** sources don't connect: they stay null, `send(...)` goes nowhere
  and `on … each` never runs. `pin:` is taken and not checked: a request goes
  out with the system's certificates, which a server with one of its own fails.
- **strings** and `lang()` take the language of Qt's locale, as the launcher
  takes the phone's.
- **onPull** never runs: a desktop list is scrolled, not pulled.
- `gapsIn`, `gapsOut` and `borderWidth` are the OwlHost's, Omarchy's Hyprland
  gaps and borders by default, and `tileOpacity` 1 and `tileFrost` 0.
- **lazy** Columns and Grids scroll, but build every row: the launcher's lazy
  lists save work this runtime doesn't need to. `reverse` still lists them from
  the bottom and starts at the end.
- **Faces** take the board's whole width and a window's height. There is no
  status bar to hide and no navigation bar, so `statusBar` changes nothing and
  `screenInset` is 0.
- **frost** draws only the node's `background`: there is no launcher wallpaper
  behind the widgets to blur, as in the launcher's own windows.
- **Popup** is a menu over the window, not a window of its own.
- **Time zones** by name are read from `/usr/share/zoneinfo` (QML's JavaScript
  has no Intl), and day and month names in another language from `Qt.locale`.
- **letterSpacing** in Canvas `text(...)` is left out: Context2D has none.
- **sound()** plays through `mpv`, and images and sounds from the web are
  fetched each time instead of kept for a day.
- **`e` in `fmtTime`** counts from Monday: the jar declares it and leaves
  its meaning to the launcher, which is not published.
