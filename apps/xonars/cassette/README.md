# Cassette

An independent OWL client for Yandex Music, inspired by
[Rirusha/Cassette](https://github.com/Rirusha/Cassette). This is an original OWL/Python
implementation, not a GTK port. No GTK binaries or upstream artwork are bundled.

In OMA Another, requires **OWL 19** with `mediaSession`, plus Arch packages `python`, `mpv` and
`ffmpeg`. Ported from [Cassette PR #368](https://github.com/SimonSchubert/omarchy-widgets/pull/368)
and [MediaSession PR #227](https://github.com/SimonSchubert/omalauncher/pull/227).
The upstream submission remains separate; install `app.owl` as `cassette.owl`
in the launcher’s widgets directory. The backend is embedded; no companion file is required.

## Language and sign-in

English is the default. Select **English / Русский** on the sign-in page or in
Settings; the preference is saved. Switching language preserves the current tab,
account and queue. Artist names, track titles and server-provided errors remain
in the language supplied by Yandex.

Open Yandex sign-in, then paste an OAuth token or the redirect URL containing
`access_token`. The token is an OWL `secret`: the launcher encrypts it, and the
Python backend never receives it. The app uses the public OAuth client ID used by
the original Cassette project. Subscription and regional restrictions still apply.

## Features

- Search tracks, artists, albums and playlists; browse artist tracks and collections.
- Liked tracks (150 per page), like/unlike, personal playlists and My Wave batches.
- Queue, shuffle, repeat, a full-screen player, seeking and best available MP3.
- Download tracks to `~/Music/Cassette`; play MP3, M4A, OGG, OPUS, FLAC and WAV there.
- Publish track metadata, play/pause, stop and seek to Android media controls.

The entire backend is a readable constant inside `app.owl`, invoked with
`python -c` and OWL shell quoting. There is no external script download or install
step, and no dependency on files from the author's phone. The review warning
about executing a widget value refers to this fixed embedded source. All commands
and data arguments remain visible in the reviewed file.

Python uses only its standard library. Streaming/download redirects are restricted
to HTTPS Yandex domains. Local playback is restricted to files directly inside
`~/Music/Cassette`. State lives in `~/.cache/cassette-owl`; downloaded audio is
written to a temporary file before replacement. Tokens and signed playback URLs
are not included in status output or user-visible error logs.

The player status is polled once per second while the app is active, for progress
and queue advancement. The local library is refreshed every 30 seconds and after
actions; it is not rescanned every second.

## Limits

Queue advancement runs while the OWL app is active. The current track continues
after closing the screen, and published play/pause/stop/seek commands remain
available. Metadata updates are publisher-driven: this is not a background queue
service. Android next/previous controls are deliberately not advertised because
the queue belongs to the open OWL app. Album artwork is not published to Android
by this initial API.

Search uses the first API page. My Wave needs manual refresh; continuous feedback,
lyrics, playlist editing and full artist discographies are not implemented.
Downloaded files use their filename for title/artist and do not retain cover art.
The unofficial Yandex API may change.

## Validation

Tested on a physical Android phone running a debug build of omalauncher with OWL 16:

- Built APK installed through the APK Share localhost HTTP server.
- `owl-check`: compile and live full-screen rendering; English sign-in and signed-in
  Settings inspected for layout and translated navigation.
- A separate probe read `android.media` and observed the omalauncher session's
  title, artist, duration, position and playing state.
- `media("play")` and `media("pause")` traversed Android MediaController and
  MediaSession callbacks, then changed mpv's real pause property. Android playing
  state was read again and matched mpv. Commands also worked after the publishing
  probe's live polling ended.
- The user separately confirmed that play and pause work on the phone's lock
  screen. Next/previous are not shown because Cassette does not advertise them.
- After the final APK update, a silent-track regression check published position
  once and exercised Android play/pause without republishing metadata. Android's
  paused position advanced 9 → 15 → 19 seconds; mpv ended at 19.60 seconds, paused.
  `mediaSession(null)` also removed the session from a fresh Android media read.
- Python backend regression tests: six passed, covering signing, URL restrictions,
  local path confinement, metadata defaults, JSON state and explicit controls.
- Store review passes with the OWL 16 checker. Current released store tooling does
  not yet support OWL 16; this PR must remain a draft until that dependency lands.

Physical headset buttons, the output switcher, Android seek and
stop callbacks have not been manually exercised. Their wiring is implemented,
but these interactions are not claimed as device-tested.

License: MIT.

## Background playback (Another OWL 19)

Version 1.9 requires Another OWL 19. The explicit media-session background lease keeps queue transitions and authenticated download-info requests running when the view is hidden, without exporting the Yandex token to Linux. Android Next/Previous and the app buttons control the same queue through `owl-send`; Stop releases the background lease. Artwork and track metadata update in the Android notification and lock screen. Phone sensors remain subject to normal visibility. Playback survives closing the view, but not stopping Linux or the launcher process.
