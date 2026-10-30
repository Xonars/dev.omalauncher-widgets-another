# omarchy-widgets-another by Xonars

OWL apps и widgets Xonars: `apps/xonars/` и `widgets/xonars/`.
`faces/xonars/` предназначен для собственных faces; сейчас их нет.
Оригинальный каталог доступен отдельно как **omarchy-widgets by Simon Schubert**.
Каталоги не смешиваются.

Авторство подтверждено владельцем: APK Share, Cassette, Справочник разработчика, Pinterest wallswap и Тихая читалка написаны Xonars с нуля. Шахматы и APK Maker — приложения Xonars на основе сторонних виджетов; ссылки на оригиналы и атрибуция сохранены в их README. Локальные исходники и зависимости: [local/README.md](local/README.md).

Инструменты, runtime и документация основаны на SimonSchubert/omarchy-widgets; лицензии сохранены.

Синхронизация upstream: `a981ae7f` (30 октября 2026). Quickshell runtime и
правила каталога поддерживают OWL 15–17; `tools/owl.jar` совпадает с upstream
для OMA Launcher 0.16.0. Каталог Xonars и локальные исходники сохранены отдельно.
Upstream-тест `runtimes/quickshell/test/run.sh` требует оригинальные widgets/faces
Simon: для полного conformance используйте временную копию с этими каталогами
из того же upstream, не добавляя их в публикуемый каталог Xonars.
На ARM64 Java 25 / Node проверка 30 октября дала 296 успешных сравнений;
`random-walk` расходится в последних знаках чисел (~1e-9). Проверки принятия
и отклонения всех OWL-файлов совпали. Все OWL Xonars прошли `owl.jar review`.

# omarchy widgets

The widget store for [Omalauncher](https://github.com/SimonSchubert/omalauncher), the Android launcher that
runs Arch Linux and draws home-screen widgets written in OWL, a small declarative widget language.
It also holds OWL faces, whole home pages, and OWL apps: full-screen views that open from the app drawer
instead of sitting on a page.

Everything in `widgets/`, `faces/` and `apps/` has been reviewed. When a pull request is merged, CI builds
`index.json` (widgets), `faces.json` (faces) and `apps.json` (apps) and publishes the store to GitHub Pages, where the
launcher's **store** reads them. Before installing, it shows you every command a widget or app runs
and every package it installs, and it checks the download against the reviewed file's SHA-256.

## Submitting a widget

The easy way: long-press your widget on the phone and tap **publish**. Your coding agent forks
this repo with the GitHub CLI and opens the pull request for you.

By hand:

1. Fork this repo and add your widget at `widgets/<your GitHub username, lowercase>/<name>/widget.owl`.
   Names use lowercase letters, digits and dashes.
2. Give it `meta` and declare its packages:

   ```owl
   widget "disk" {
     meta { description: "Free space on the root disk"; version: "1.0"; license: "MIT"; category: "system" }
     size: 3x2
     requires { pacman: ["dua-cli"] }
     ...
   }
   ```

3. Optionally add `preview.png`, a screenshot of the tile (under 300 KB). For the store to show
   the tile in the user's own Omarchy theme, add `previews/<theme>.webp` too, one per theme (under
   100 KB each, named like `tokyo-night.webp`); the launcher's debug build makes them with
   `scripts/store-previews.sh`. This goes for faces and apps as much as widgets: anything that uses
   theme colors (`accent`, `foreground` and the rest) gets `previews/`, not only `preview.png`.
4. Check it locally: `java -jar tools/owl.jar review . widgets/<you>/<name>/widget.owl`
5. Open a pull request. The **review** check runs the same rules and writes a summary of what the
   widget runs and installs; a maintainer reviews it and merges.

The widget language is documented in [docs/LANGUAGE.md](docs/LANGUAGE.md).

## Submitting an app

An app is an OWL file that starts with `app "name" { }` instead of `widget`: the nodes at its top
are the whole full-screen view, and it has no tile, so no `size`. It goes at
`apps/<your GitHub username, lowercase>/<name>/app.owl`, follows the same steps and rules as a
widget, needs `meta { owl: 8 }`, and should have an `icon`: an SVG in the file, drawn in
`currentColor` so it takes the user's theme accent, or a PNG embedded as an `asset`. The launcher
shows it standalone on the theme's background; see the Apps section of the launcher's widget
README for the style the store's apps share. A game or a view with a header of its own can leave
the window's title row out with `title: ""`; launchers before that show an empty title row instead:

```owl
app "notes" {
  meta { owl: 8; description: "Quick notes that stay on the phone"; version: "1.0"; license: "MIT"; category: "productivity" }
  title: "notes"
  icon: """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M11 5h18l9 9v29H11z"/>
    <path d="M29 5v9h9M17 24h15M17 32h10"/>
  </svg>"""
  state notes = [] persist
  Column {
    Input { placeholder: "write a note…"; clear: true; onSubmit: notes = [value] + notes }
    for n in notes { Text { text: n } }
  }
}
```

Check it with `java -jar tools/owl.jar review . apps/<you>/<name>/app.owl`. Its previews are
pictures of the whole view at a phone's size, which `scripts/store-previews.sh` makes too. An app that
uses theme colors gets `previews/<theme>.webp` like a widget, not only `preview.png`. A widget
and an app can't share a name. Launchers from before apps (0.7.2 and older) only read `index.json`, so they never see one.

## Submitting a face

A face is a whole home page, as a watch face is a watch's whole screen: an OWL file that starts with
`face "name" { }`. Its nodes fill the screen, with no tile and no `size`, and it sits left of page 1
where a stock launcher has its feed. It goes at `faces/<your GitHub username, lowercase>/<name>/face.owl`,
follows the same steps and rules as a widget and needs `meta { owl: 10 }`. `statusBar: false` hides
the status bar; see the Faces section of the launcher's widget README:

```owl
face "quiet" {
  meta { owl: 10; description: "The time, large, and nothing else"; version: "1.0"; license: "MIT"; category: "time" }
  source now = clock every 1m
  Column {
    align: center
    Text { text: fmtTime(now, "HH:mm"); fontSize: 96; fontWeight: 200 }
  }
}
```

Check it with `java -jar tools/owl.jar review . faces/<you>/<name>/face.owl`. Its previews are
pictures of the whole page at a phone's size, which `scripts/store-previews.sh` makes too. A face that
uses theme colors gets `previews/<theme>.webp` like a widget, not only `preview.png`. Launchers from before faces (0.8.1 and older) only read
`index.json` and `apps.json`, so they never see one.

A face can have several pages, installed side by side: its others go beside `face.owl` as
`page-2.owl`, `page-3.owl`, ..., numbered without gaps, and land right of page 1 in that order. Each
is a face of its own (`face "name" { }`), but only `face.owl`'s meta describes the face: a page needs
no description, version or license, just the `owl` level it uses. Every page is reviewed, the face's
commands and packages are those of all its pages, and it needs owl 14 or the highest level a page uses.
Adding, changing or removing a page needs `face.owl`'s version to go up. A page's pictures go in
`screens/<page>/<theme>.webp`, which `scripts/store-previews.sh` draws in the same run as page 1.
Check them all with `java -jar tools/owl.jar review . faces/<you>/<name>/*.owl`.

## Rules

- One folder per widget, and only `widget.owl`, `preview.png`, `README.md` and `previews/<theme>.webp` in it
  (`face.owl` for a face, with its `page-2.owl`, ... and `screens/<page>/<theme>.webp` if it has several pages;
  `app.owl` for an app).
- You can only add or change widgets, faces and apps under your own username.
- `meta` needs a `description` (10-200 characters), a `version` and a `license`. Add a `category`
  (`news`, `dev`, `productivity`, `time`, `world`, `sport`, `finance`, `media`, `games`, `pets`, `fun`, `home` or `system`) so it shows under that tab in the store; without one it goes under "other".
- Every package the commands need goes in `requires`. CI checks that the packages exist in Arch
  and warns about programs whose package isn't declared.
- `meta { owl: N }` is the language level the widget needs (none is level 1). It has to be one
  that [owl.txt](owl.txt) lists as supported; a level marked deprecated there is only allowed for
  widgets that aren't changed. A launcher older than a widget's level can't install or update it,
  so raise `owl` only when the widget uses something that needs it.
- Updates raise the version. If an update changes the commands or packages, the app asks users to
  approve it again.
- Values go into commands as `${sh(value)}`, outside any quotes, or as numbers (`${int(n)}`):
  anything else could run whatever a server or a file sends. CI rejects it.
- No hidden or surprising behavior. Commands that pipe downloads into a shell or run
  downloaded files, delete recursively, ask for root, decode base64 or use `eval` are flagged, and need a good reason and
  a clear description.
- No personal data: tokens, personal paths or a hard-coded location.

## What the review looks at

Widgets run shell commands inside the phone's Arch system, not with Android permissions. They
can still read and change files there, and use the network. Reviewers read every command; the
CI summary lists them all, with anything risky flagged.

## Layout

```
widgets/<author>/<name>/widget.owl    the widget
widgets/<author>/<name>/preview.png   optional screenshot
widgets/<author>/<name>/previews/     optional screenshots per Omarchy theme (<theme>.webp)
faces/<author>/<name>/face.owl        a face, with preview.png and previews/ like a widget's
faces/<author>/<name>/page-2.owl      a face's second page, if it has more; its pictures in screens/2/
apps/<author>/<name>/app.owl          an app, with preview.png and previews/ like a widget's
order.txt                             the order of the store
docs/LANGUAGE.md                      the widget language
w/index.html                          where a shared widget's link lands: shows it, opens the launcher
owl.txt                               the owl levels the store takes, and the launcher that runs each
tools/owl.jar                         the checker CI runs (built from the latest launcher release's owl module)
runtimes/quickshell/                  OWL for Quickshell on Linux: the same widgets, drawn
                                      by Quickshell (Omarchy Mobile's widget board uses it)
```
