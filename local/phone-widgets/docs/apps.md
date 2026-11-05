# Apps

Part of the widget docs: README.md, one folder up, comes first, and paths here are from the widgets folder.

A file can also be an app instead of a widget: a screen of its own, listed in the app drawer.
The nodes at the top are the whole view, with the room and limits of a `screen { }`, and it takes
the same declarations as a widget (sources, state, lets, components, triggers, `requires`, `meta`).
There's no tile, so no `size`, `minSize`, `page`, `order`, `padding`, `background`, `onTap` or
`screen { }`; the properties are `title`, `icon`, `back` (with its `onBack`), `edge` and `statusBar`, and `close()` closes it. Apps need owl 8 and
run only while open, unless an explicit `mediaSession({background: true, ...})` lease keeps their non-Android sources and triggers active (owl 19, Another; see docs/handlers.md).

```owl
app "notes" {
  meta { owl: 8 }
  title: "notes"                // the window's title; the drawer shows the name
  icon: """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
    <rect width="256" height="256" rx="56" fill="#24283B"/>
    <rect x="70" y="58" width="128" height="164" rx="14" fill="#16161E" fill-opacity="0.5"/>
    <rect x="64" y="50" width="128" height="164" rx="14" fill="#F4E3A1"/>
    <path d="M64 64a14 14 0 0 1 14-14h100a14 14 0 0 1 14 14v18H64z" fill="#E0AF68"/>
    <path d="M86 112h84M86 140h84M86 168h52" stroke="#B8A36A" stroke-width="10" stroke-linecap="round"/>
    <g transform="rotate(45 178 168)">
      <rect x="164" y="88" width="28" height="104" rx="4" fill="#7AA2F7"/>
      <rect x="164" y="88" width="10" height="104" fill="#A9C1FF"/>
      <rect x="164" y="76" width="28" height="18" rx="4" fill="#F7768E"/>
      <path d="M164 192h28l-14 26z" fill="#F0D2B0"/>
      <path d="M173 209h10l-5 9z" fill="#1A1B26"/>
    </g>
  </svg>"""
  state text = "" persist
  Column {
    gap: 8
    padding: [12, 0]           // the view runs to the screen's edges; this is the usual margin
    Input { text: text; placeholder: "write…"; focus: true; onSubmit: text = value }
    Text { text: text }
  }
}
```

**Edges.** An app fills the screen below its title, from edge to edge: there's no window border
and no margin, so the app decides where its content sits. For text, lists and forms, give the top
node `padding: [12, 0]`, which lines them up with the title. Leave it off (or pad only the parts
inside) for what should run to the edges, like a photo, a map, a canvas or a bar along the bottom.

**Under the navigation bar.** An app ends above Android's navigation bar (the gesture handle or the
three buttons). With `edge: true` it runs on under it, like a list that scrolls behind the bar:
`screenHeight` then reaches the screen's bottom, and `screenInset` is how much of it the bar covers,
in dp (0 without `edge`, and while the keyboard is up; only apps and pages have it, since a widget's screen ends above the bar). Taps there go to Android, so keep buttons
and the last row of a list above it: end a scrolling list with `Spacer { height: screenInset }`, and
pad a view with buttons along its bottom by `screenInset`. `edge` is `true` or `false`, not an expression.

```owl
app "photos" {
  meta { owl: 8 }
  edge: true
  Column {
    scroll: true
    padding: [12, 0]
    for p in range(40) { Text { text: "photo ${p}" } }
    Spacer { height: screenInset }   // the last row scrolls up clear of the bar
  }
}
```

**Going back.** An app with views inside it (a list, then one item) says when Back goes up a
level with `back`, and how with `onBack`. While `back` is true, the window shows a chevron before
the title, and the chevron, the title and Android's Back run `onBack`; otherwise Back leaves the app.
`title` is an expression too, so it can name the view that's open:

```owl
app "recipes" {
  meta { owl: 8 }
  state open = ""
  title: open == "" ? "recipes" : open
  back: open != ""
  onBack: open = ""
  Column {
    if open == "" {
      for r in ["soup", "bread"] { Text { text: r; onTap: open = r } }
    } else {
      Text { text: "how to make ${open}" }
    }
  }
}
```

**Its own title.** `title: ""` leaves the window's title row out, and the view starts at the top, under the
status bar: for a game or a view with a header of its own. Recent apps still shows the name. While `back` holds
there's no chevron to tap then, so put a way back in the view, or leave it to Android's Back, which still runs `onBack`.
`statusBar: false` (owl 11) hides the status bar too, as on a face, and the view takes its room: a swipe down from
the top brings it back for a moment. It can be any expression (`statusBar: !playing`). The view then runs up to the
screen's top edge, around the camera on a phone with a cutout: `screenTop` (owl 12) is how much of the top the
cutout covers, in dp (0 without one, and while the status bar shows). Draw the background there and start the content
below it, `padding: [0, screenTop, 0, 0]`, the way `screenInset` keeps buttons clear of the navigation bar.

An app is listed in the app drawer (under apps, and in search) by its name. Tapping it opens
it in its own window, with its own card in recent apps and its `title` (or name). Like any Android app,
Back leaves it and swiping its card away in recent apps closes it; `close()` closes it too.
Long-press it in the drawer to add it to home, like any app.

**Icon.** `icon` is the app's icon in the drawer, on home and in recent apps. It's fixed in the
file rather than an expression, since it's drawn before the app runs, and it's one of two things:

- an SVG in a string, `icon: """<svg ...>...</svg>"""` (under 16 KB). `currentColor` in it becomes
  the Omarchy theme's accent, so the icon follows theme changes; other colors stay as written.
- an image, `asset logo = base64"..."` and `icon: logo`: a PNG (or WebP) shown as it is, scaled to
  fit a square. For a logo or artwork that has its own colors.

Without one, the drawer shows the name's initials. Give every app one, and make it look like an
app icon from a good phone, not a symbol from an icon font. The launcher draws no plate or frame of
its own, so the icon brings its tile. That's how the store's apps look, so they sit together in
the drawer:

- A rounded tile filling the canvas: `viewBox="0 0 256 256"` with
  `<rect width="256" height="256" rx="56" fill="…"/>` first. A dark tile (`#1A1B26`, `#24283B`) or a
  deep color that fits the subject (night blue for a lantern, sea blue for fishing).
- One subject, big: it fills about two thirds of the tile, in flat fills of 4 to 8 colors that go
  together, with a lighter side for light and a darker one, or a soft shadow under it, for depth. A
  notepad and pencil for notes, a gold fish on a line for fishing, a knight for a dungeon game.
  Games can fill the whole tile with a small scene (the tile clipped with a `clipPath`) instead.
- Filled shapes rather than outlines. Thin strokes vanish at 40 dp, so keep any line at least 8
  units wide on the 256 canvas. Pixel art (`shape-rendering="crispEdges"`, a grid of `<rect>`s)
  suits retro games.
- No text, and no other app's or brand's logo. Write the colors out; `currentColor` (the theme's
  accent) only for a part that should change with the theme.
- With monochrome icons on, the launcher draws the icon's bright parts in one color, so the subject
  should be brighter than its tile.

owl-check doesn't draw the icon, so render it and look at it before you're done:
`rsvg-convert -w 192 icon.svg > icon.png` and `-w 48` (from `librsvg`). At 48 px it should still
read as its subject at a glance; if it's a muddle there, make it simpler and bigger.

A widget and an app are separate files and don't share state; a widget that needs a bigger view
of itself has its own `screen { }`.

## Hardware keys — OMA Another extension

This fork adds `onKeyDown`, `onKeyUp` and `captureKeys` to **apps only**. These are
OMA Another extensions at the existing `meta { owl: 17 }` level, not an upstream
OWL version increase. A launcher without this extension rejects these names.
They need neither Linux nor an accessibility permission. Events are delivered
only to the foreground, focused app window, including on an external display.

```owl
app "Keyboard example" {
  meta { owl: 17 }
  state testing = false
  state held = []
  state result = "Press a key"
  captureKeys: testing
  onKeyDown: {
    held = value.pressed
    if value.ctrl && value.key == "K" && value.repeat == 0 {
      result = "Ctrl+K"
    } else {
      result = value.combo
    }
  }
  onKeyUp: held = value.pressed
  Column {
    Text { text: result }
    Text { text: join(held, " + ") }
    Button { text: testing ? "Stop capture" : "Capture keys"; onTap: testing = !testing }
    Button { text: "Close"; onTap: close() }
  }
}
```

Without `captureKeys`, handlers observe input and normal text fields, arrows,
Tab and Esc continue working. While `captureKeys` is true, key events are consumed
before normal navigation, text fields and Esc-as-Back. Provide a touch button to
stop capture or close the app. A press, its repeats and its release keep the same
consumption decision even if `captureKeys` changes while held. To implement an
app shortcut, check `value.key`, the modifier flags and `value.repeat == 0` in
`onKeyDown`, and run the desired OWL action there. Capture is local to the app;
it never invokes Delete/Insert actions on the home screen underneath it.

Both handlers receive a `value` object:

- `key`: physical key name independent of typed layout; letters `A`…`Z`, digits,
  punctuation, `ESC`, `BKSP`, `DEL`, `INS`, `ENTER`, `SPACE`, `TAB`, `UP`, `DOWN`,
  `LEFT`, `RIGHT`, `HOME`, `END`, `PGUP`, `PGDN`, `F1`…`F12`, `CAPS`.
- Modifiers retain their side: `CTRL_LEFT`, `CTRL_RIGHT`, `ALT_LEFT`, `ALT_RIGHT`,
  `SHIFT_LEFT`, `SHIFT_RIGHT`, `SUPER_LEFT`, `SUPER_RIGHT`. Other Android key
  names omit `KEYCODE_` (for example `NUMPAD_ENTER`).
- `pressed`: currently held physical key names, after this event, without repeats.
  Independent keyboards are tracked by device and key code.
- `ctrl`, `alt`, `shift`, `super`: modifier flags; `modifiers`: names in canonical
  order SUPER, CTRL, ALT, SHIFT; `combo`: these names plus the key joined by ` + `.
- `down`, `repeat`, `cancelled`: phase, Android repeat count (0 for the first
  down), and cancellation. Focus loss/pause emits cancelled `onKeyUp` events for
  all held keys. Do not trigger shortcut actions on cancelled releases.
- `keyCode`, `scanCode`, `deviceId`, `device`: Android codes and keyboard identity.
- `text`: printable Unicode from Android's active layout, or an empty string;
  `capsLock`, `numLock`: lock flags; `time`: Android event uptime in seconds.

Back, Home, Recents, power and volume remain system keys. The soft keyboard is
excluded. Android may reserve Super combinations or other system shortcuts before
an Activity receives them; this API cannot observe or override those. It reports
input received by the app, not whether a home-screen shortcut performed its action.
The bundled `examples/key-bindings.owl` provides a complete visual tester.
