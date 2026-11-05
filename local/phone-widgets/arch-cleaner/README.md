# Arch · очистка

Home-screen tile: `../85-arch-cleaner.owl`. Helper: `cleaner.py`.

The tile opens a detailed screen. «Оценить» scans without deleting;
«Очистить…» opens confirmation. Automation is off by default. Choosing daily
or weekly schedules the first cleanup one interval later using a persistent
OWL `at` trigger; a missed deadline runs when the launcher resumes. Linux must
be available. Trash cleanup is separately disabled by default.

Rules:

- Pacman: `paccache` selects obsolete archives and signatures, retaining the
  latest two versions of each package. An active pacman lock blocks deletion.
- npm: `~/.npm/_cacache` and `_logs`; pip, uv and yay: their XDG cache folders.
- Go: XDG `go-build` only; downloaded modules and projects are preserved.
- Known running package/build tools cause their cache category to be skipped.
- Temporary files: ordinary top-level files in `/tmp` and `/var/tmp`, with
  access, modification and change times older than seven days. Open files,
  sockets, directories and PRoot files are excluded.
- Thumbnails: XDG `thumbnails`; trash: XDG `Trash/files` and `Trash/info`.
- Journals: `journalctl --vacuum-time=14d`; estimate uses archived journal files
  older than 14 days. Active journals and ordinary text logs are preserved.
- PRoot: only `proot-PID-SUFFIX` entries older than a day with no existing PID;
  skipped entirely if any visible process is named `proot`.
- Symlinks and paths with symlink ancestors are excluded. A file lock prevents
  concurrent scans/cleanups. Errors and partial results appear in the screen.

Sizes use allocated file blocks. Reported freed space is the reduction in
candidate sizes; actual filesystem free space may differ because of open files,
compression, hard links or concurrent activity. Live cache use can race a scan;
run manual cleanup after stopping builds and package managers.

Status is atomically written to `~/.cache/arch-cleaner/status.json` and watched
by the widget. Background jobs continue while Linux runs. A status poll detects
interrupted jobs. Progress represents completed categories rather than bytes.

Verification: `python arch-cleaner/test_cleaner.py` uses disposable fixtures to
check two-version retention, cache deletion and symlink protection.
