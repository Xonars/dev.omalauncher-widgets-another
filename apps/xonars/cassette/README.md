# Cassette

Yandex Music client for OWL with English/Russian UI and Android media controls.
Declares OWL 15 and requires a launcher build with `mediaSession` from
[omalauncher PR #227](https://github.com/SimonSchubert/omalauncher/pull/227).
The API level is pending maintainer agreement; other OWL 15 builds may lack this API.

## Install locally

From the repository root, in the launcher's Linux environment:

```sh
mkdir -p ~/.config/omalauncher/widgets/cassette
cp apps/xonars/cassette/app.owl ~/.config/omalauncher/widgets/cassette.owl
cp local/widgets/cassette/player.py ~/.config/omalauncher/widgets/cassette/
owl-check ~/.config/omalauncher/widgets/cassette.owl
```

Install the `python`, `mpv` and `ffmpeg` packages if needed. The app appears as
**Cassette** in the launcher drawer. The current source uses `/root` paths.

See [the companion README](../../../local/widgets/cassette/README.md) for sign-in,
features, limitations and device verification. The matching local snapshot is
[`local/widgets/cassette.owl`](../../../local/widgets/cassette.owl).

Preserves original metadata and attribution; not submitted for public store review.
