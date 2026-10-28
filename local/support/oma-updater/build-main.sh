#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export JAVA_HOME=/usr/lib/jvm/java-25-openjdk
export ANDROID_HOME=/root/android-sdk
exec /root/build-downloads/gradle-9.8.0/bin/gradle :app:assembleDebug --no-daemon --max-workers=2 -Dorg.gradle.jvmargs="-Xmx1536m -Dfile.encoding=UTF-8" -Pandroid.aapt2FromMavenOverride=/root/android-sdk/build-tools/37.0.0/aapt2 "$@"
