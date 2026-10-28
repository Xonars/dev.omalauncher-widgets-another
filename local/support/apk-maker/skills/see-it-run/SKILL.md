---
name: see-it-run
description: See the app actually running on this phone - install the latest build, open it, take a screenshot, list what's on screen, tap buttons, type text, and catch crashes - with the apk-maker peek command. Use after every successful build to check the app works and looks right, and whenever something might crash or look wrong.
---

# Seeing the app run

A build that passes can still crash on launch or look wrong. `apk-maker peek` installs your latest
build on this phone, opens it, and shows you the result. Run it from the project folder.

## Commands

| Command | Does |
|---|---|
| `apk-maker peek` | install the latest build (`app/build/outputs/apk/release/`), open the app, then look |
| `apk-maker peek look` | look again without reinstalling |
| `apk-maker peek tap "Add"` | tap the element showing that text (or with that description), then look |
| `apk-maker peek tap 3` | tap element number 3 from the last list, then look |
| `apk-maker peek type "milk"` | type into the focused field, then look |
| `apk-maker peek swipe up` | swipe up, down, left or right, then look |
| `apk-maker peek back` | press back, then look |
| `apk-maker peek log` | the app's recent log lines and any crash |

Every look writes:

- `.peek/screen.png`: a screenshot, 540 px wide. Read it as an image to see the layout and colours.
- `.peek/screen.txt`: the elements on screen, numbered, with their text, kind and position.
- `.peek/crash.txt`: the crash, if the app crashed (also printed). Fix it before anything else.

## How to use it

1. Build (`./gradlew --console=plain -q assembleRelease`), then `apk-maker peek`.
2. Read `.peek/screen.png`: does it look finished? Check the design skill's list.
3. Walk through the main feature with `tap` and `type`, looking at each step.
4. A crash prints `CRASH:` with the exception: fix it, rebuild, peek again.

## Rules

- If it prints `can't see the app`, the phone isn't set up for installing: skip seeing it and continue.
  Don't try to set it up yourself, and don't run `adb` directly.
- Peek shows the whole screen. Look only at the app; ignore and never write down anything from other
  apps or the status bar.
- `.peek/` stays out of git (it's ignored).
