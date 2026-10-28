# Android app project (built by apk-maker)

You are building an Android app on an aarch64 Arch Linux system that runs on the phone itself.
The finished APK is installed on this same phone.

## Build

- In managed jobs (`APKMAKER_MANAGED_AGENT=1`), finish the requested code edits and return. Do not run Gradle
  or launch another coding agent: apk-maker builds after you exit and returns compiler errors for repair.
  This keeps build progress visible and avoids overlapping agent and build work on a phone.
- In interactive work, build with `./gradlew --console=plain -q assembleRelease` and finish only when it succeeds.
- The toolchain is fixed: JDK 17, Gradle 8.11.1, AGP 8.7.3, Kotlin 2.0.21, compileSdk/targetSdk 36 (Android 16, which Google Play requires),
  build-tools 35.0.0 (the SDK path is in local.properties). Do not change these versions, the Gradle wrapper,
  `gradle.properties` (here or in ~/.gradle), or `android.aapt2FromMavenOverride` (aapt2 is a custom aarch64 build).
- RAM is limited (~2 GB free). Don't start extra Gradle daemons, emulators or parallel builds.
- Don't run `adb` yourself. To see the app running on this phone (install, open, screenshot, tap, catch
  crashes), use `apk-maker peek`: the see-it-run skill explains it. Check every build with it when it works.
- The release build is signed with the debug key on purpose; apk-maker signs Play bundles itself and sets
  `versionCode`/`versionName`. Keep `isMinifyEnabled = false`.
- Android 16 draws apps edge to edge and ignores orientation locks on large screens: handle insets, and
  make layouts work in landscape too.
- Files in `play/` (store listing, privacy policy, graphics) are for Google Play: leave them unless asked.
- Don't run git (no commits, branches or pushes): apk-maker commits your work and keeps each change on its own
  branch for the user to accept or discard.

## Skills

Tested guides with working code are in `.claude/skills/<name>/SKILL.md` (Claude Code loads them by
itself; other agents: read the ones that fit before writing code). Each has an `example/` folder with code
that builds with this project's libraries: copy it, change the package to the app's, and adapt it.

| Skill | Read it when the app needs |
| --- | --- |
| screens | several pages, tabs, settings, a back button |
| data | to save lists or settings (Room, DataStore) |
| design | to look finished: theme, dynamic colour, empty states, landscape (every app) |
| reminders | notifications, timers, daily reminders (WorkManager) |
| network | data from the internet (Ktor, JSON, images) |
| games | a game loop, drawing, touch (Canvas) |
| camera | the camera (CameraX) |
| media | sound or video (Media3) |
| widget | a home-screen widget (Glance) |
| see-it-run | to check the app on this phone after a build (every app) |
| play-ready | before publishing to Google Play |

Only the skills present in `.claude/skills/` are switched on.

## Code

- Kotlin + Jetpack Compose + Material 3, single `:app` module. Keep `applicationId` and `namespace` as they are.
- Libraries: use the aliases in `gradle/libs.versions.toml` (`implementation(libs.androidx.room.runtime)`).
  They are tested together with this toolchain; a version you pick yourself often needs a newer Kotlin or
  AGP and breaks the build. Anything not listed must come from google() or mavenCentral() and fit the
  versions above.
- Prefer no network and no runtime permissions unless the app needs them; when it does, declare them in
  the manifest and request them at runtime.
- Persist user data locally (SharedPreferences, DataStore or Room) when the app has any.
- Follow the system dark/light theme; use dynamic color on Android 12+.
- Make it look finished: real app name in `strings.xml`, sensible empty states, edge-to-edge insets handled.
- Replace the placeholder launcher icon foreground (`res/drawable/ic_fg.xml`, a 108dp vector, keep
  content inside the central 66dp) and background color (`res/values/colors.xml`) with ones that fit the app.
- Keep the code in a few clear files; no tests needed.
- The project may be published on GitHub, even publicly: never put API keys, passwords, tokens or personal
  details (names, emails, phone numbers, addresses, paths on this phone) in the code or its files. If the app
  needs a key, let the user enter it in the app's settings and keep it in its local storage.

## Acceptance and data safety

- Maintain `acceptance.json` with `{"checks":[{"id":"short-id","title":"Concrete behavior to verify","status":"pending","note":""}]}`.
  Cover the user's actual features. Never put private requests or credentials in it.
- Use `apk-maker peek` for observable runtime checks. Mark pass only for behavior actually observed;
  use skip with an explanation when the phone is unavailable. A successful build proves compilation only.
- Always check startup, navigation/back behavior, dark/light appearance, insets, landscape, large text,
  accessible labels and usable touch targets. For saved data: create, restart, and check persistence.
  For network apps: loading, offline and errors. For permissions: denial and later approval.
  For reminders/media/camera: scheduling or lifecycle behavior as applicable.
- Preserve existing user data. Prefer additive, backward-compatible database migrations; do not use
  destructive migration fallbacks. Discard restores source and the previous APK, not the app's data.
- Do not modify the Gradle wrapper, dependency catalog or protected toolchain files. Request missing
  dependencies through a small, explicit project change rather than upgrading the fixed toolchain.
