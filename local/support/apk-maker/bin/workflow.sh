# Job lifecycle and outcomes. All mutations enter through work.lock.
job() {
  json_edit "$JOB" --arg p "$1" --arg m "${2:-}" --argjson t "$(now)" \
    '.phase=$p | .msg=$m | .updated=$t | .at=(if $p | IN("agent","checking","building","fixing","art","installing","uploading") then $p else .at end)' || return 1
  publish_job
  echo "== [$1] ${2:-}" >> "$LOG"
}
jobset() { json_edit "$JOB" "$@" && publish_job; }
meta() {
  local f="$APPS/$1/.apkmaker.json"; shift
  json_edit "$f" "$@" || return 1
  list_apps
}
pstate() { json_edit "$PSTATE" "$@"; }
ghs() { json_edit "$GHSTATE" "$@"; }
job_running() { job_active && worker_alive; }
can_start() {
  [ -z "$1" ] || command -v "$1" >/dev/null 2>&1 || { echo "$1 is not installed" >&2; exit 1; }
  mutation_lock
  [ "$(jq -r '.phase // empty' "$CACHE/job.json" 2>/dev/null)" != locked ] || {
    echo 'finish or cancel the job waiting for unlock first' >&2; exit 1;
  }
}
start() {
  local kind=$1 slug=$2 agent=$3 prompt=$4
  can_start "$agent"
  JOB_ID="$(now)-$$-$RANDOM"; export JOB_ID
  local run=$CACHE/jobs/$JOB_ID
  mkdir -p "$run"
  jq -nc --arg id "$JOB_ID" --arg s "$slug" --arg a "$agent" --arg p "$prompt" --arg k "$kind" --argjson t "$(now)" \
    '{id:$id,kind:$k,slug:$s,agent:$a,prompt:(if $k=="app" then $p else null end),arg:(if $k=="app" then null else $p end),phase:"queued",msg:"",started:$t,updated:$t,pid:0}' > "$run/job.json"
  cp "$run/job.json" "$CACHE/job.json"
  : > "$run/log.txt"; : > "$run/build-err.txt"
  ln -sfn "$run/log.txt" "$CACHE/log.txt"; ln -sfn "$run/build-err.txt" "$CACHE/build-err.txt"
  setsid -f bash -c 'exec timeout --kill-after=15s 2h "$0" "_$1" "$2" "$3" "$4"' "$0" "$kind" "$slug" "$agent" "$prompt" \
    >> "$run/log.txt" 2>&1 < /dev/null 8>&-
  [ -t 1 ] && echo "$slug"
  true
}
worker_run() {
  local fn=$1; shift
  [ -n "${JOB_ID:-}" ] || { echo 'missing job identity' >&2; return 1; }
  JOB=$CACHE/jobs/$JOB_ID/job.json LOG=$CACHE/jobs/$JOB_ID/log.txt
  JOB_DEADLINE=$(( $(now) + 7200 )); AGENT_RUNS=0
  jobset '.pid=$p | .process=$id | .pgid=$group' --argjson p $$ --arg id "$(process_id $$)" --argjson group "$(ps -o pgid= -p $$ | tr -d ' ')"
  trap 'job failed "worker interrupted; see retained job log"; exit 130' INT TERM HUP
  local rc=0
  "$fn" "$@" || rc=$?
  if [ "$rc" -ne 0 ] && job_active; then job failed "job failed: see retained log"; fi
  list_apps
  return "$rc"
}
build_only() {
  job building 'building APK'
  do_build "$1" || { meta "$1" '.status="failed" | .outcomes.build="failed"'; job failed 'build failed: see log'; return 1; }
  job ready 'built; install to try it'
}
do_install() {
  local slug=$1 injob=${2:-} pkg o launch
  pkg=$(jq -r .pkg "$APPS/$slug/.apkmaker.json")
  [ -s "$CACHE/apks/$slug.apk" ] || return 1
  artifact_ok "$slug" apk "$CACHE/apks/$slug.apk" || {
    meta "$slug" '.outcomes.install="stale"'; echo 'APK does not match source; rebuild first' >> "$LOG"; return 1;
  }
  meta "$slug" '.outcomes.runtime="unverified"'
  if adb_reconnect; then
    [ -z "$injob" ] || job installing 'installing APK'
    o=$(adb install -r "$CACHE/apks/$slug.apk" 2>&1); echo "$o" >> "$LOG"
    if [[ $o == *Success* ]]; then
      local devicehash localhash path
      path=$(adb shell pm path "$pkg" 2>/dev/null | sed -n 's/^package://p' | head -1 | tr -d '\r')
      localhash=$(sha256sum "$CACHE/apks/$slug.apk" | cut -d' ' -f1)
      devicehash=$(adb shell sha256sum "$path" 2>/dev/null | awk '{print $1}')
      [ "$devicehash" = "$localhash" ] || {
        meta "$slug" '.outcomes.install="unverified" | .status="ready"'; return 4;
      }
      meta "$slug" '.status="installed" | .installed=$t | .outcomes.install="verified" | .installedArtifact=.artifacts.apk' --argjson t "$(now)"
      adb logcat -c -b crash >/dev/null 2>&1 || return 4
      adb shell am force-stop "$pkg" >/dev/null 2>&1 || return 4
      launch=$(adb shell monkey -p "$pkg" -c android.intent.category.LAUNCHER 1 2>&1)
      if [[ $launch != *"Events injected: 1"* ]]; then
        echo "$launch" >> "$LOG"; meta "$slug" '.outcomes.runtime="launch-failed"'; return 4
      fi
      return 0
    fi
    if [[ $o == *UPDATE_INCOMPATIBLE* || $o == *"signatures do not match"* ]]; then
      meta "$slug" '.status="ready" | .outcomes.install="signature-conflict"'; return 3
    fi
  fi
  serve || return 1
  meta "$slug" '.status="ready" | .outcomes.install="download-offered"'
  return 2
}
crash_check() {
  local pkg=$1 logs pid
  sleep "${APKMAKER_STARTUP_DELAY:-4}"
  logs=$(adb logcat -d -b crash 2>/dev/null) || return 4
  local crash; crash=$(grep -F -A 30 "Process: $pkg," <<< "$logs" | head -40)
  [ -z "$crash" ] || { printf '%s\n' "$crash"; return 3; }
  pid=$(adb shell pidof "$pkg" 2>/dev/null | tr -d '\r') || return 4
  [ -n "$pid" ] || return 4
  return 0
}
crash_fix() {
  local slug=$1 agent=$2 round=0 pkg crash rc
  pkg=$(jq -r .pkg "$APPS/$slug/.apkmaker.json")
  while :; do
    job installing 'checking startup'
    crash=$(crash_check "$pkg"); rc=$?
    case $rc in
      0) meta "$slug" '.outcomes.runtime="startup-verified"'; return 0 ;;
      3) meta "$slug" '.outcomes.runtime="crashed"' ;;
      *) meta "$slug" '.outcomes.runtime="unavailable"'; return 4 ;;
    esac
    printf '== startup crash:\n%s\n' "$crash" >> "$LOG"
    round=$((round + 1))
    [ "$round" -le "$FIX_ROUNDS" ] && [ -n "$agent" ] || { job failed 'app crashes on startup'; return 1; }
    job fixing "$agent fixing startup ($round/$FIX_ROUNDS)"
    run_agent "$agent" "$APPS/$slug" "Fix this startup crash, read AGENTS.md and verify with apk-maker peek:\n$crash"
    rc=$?; [ "$rc" -eq 0 ] || { job failed "agent failed ($rc): see log"; return 1; }
    build_fixing "$slug" "$agent" do_build 'gradle build' || return 1
    save "$slug" "$agent: fix startup crash" || return 1
    do_install "$slug" job; rc=$?
    [ "$rc" -eq 0 ] || return "$rc"
  done
}
sync_final() {
  local slug=$1 dir=$APPS/$1 rc=0
  if pending "$slug"; then
    if [ -z "$(app_account "$slug")" ]; then meta "$slug" '.outcomes.github="local-only"'; return 0; fi
    if app_gh "$slug"; then open_pr "$slug" >> "$LOG" 2>&1 || rc=1; else rc=1; fi
  elif [ -n "$(app_account "$slug")" ]; then
    if app_gh "$slug"; then push_app "$slug" "$(git -C "$dir" branch --show-current)" >> "$LOG" 2>&1 || rc=1
    else rc=1; fi
  elif gh_on && jq -e '.auto != false and .account != null' "$GHSTATE" >/dev/null 2>&1; then
    github_publish "$slug" private >> "$LOG" 2>&1 || rc=1
  else meta "$slug" '.outcomes.github="local-only"'; return 0; fi
  if [ "$rc" -eq 0 ]; then
    meta "$slug" '.outcomes.github="synced" | .github.syncedCommit=$c' --arg c "$(git -C "$dir" rev-parse HEAD)"
  else meta "$slug" '.outcomes.github="pending"'; fi
  return "$rc"
}
work() {
  local slug=$1 agent=$2 prompt=$3 dir=$APPS/$1 rc irc=1 syncnote='' try=''
  install_skills "$dir"
  meta "$slug" '.agent=$a | .history += [{t:$t,agent:$a,prompt:$p}] | .status="building" | .updated=$t | .outcomes={build:"running",install:"unverified",runtime:"unverified",github:"pending"} | if .pending then .pending.built=false else . end' \
    --arg a "$agent" --arg p "$prompt" --argjson t "$(now)"
  job agent "$agent is writing the app"
  run_agent "$agent" "$dir" "$prompt"; rc=$?
  if [ "$rc" -ne 0 ]; then
    meta "$slug" '.status="failed"'; job failed "agent failed ($rc): see log"; return 1
  fi
  validate_project "$slug" || { job failed 'protected project configuration changed'; return 1; }
  build_fixing "$slug" "$agent" do_build 'gradle build' || { meta "$slug" '.status="failed" | .outcomes.build="failed"'; return 1; }
  note_skills "$slug"
  record_checks "$slug"
  save "$slug" "$agent: implement app update" || { job failed 'could not commit build'; return 1; }
  artifact_record "$slug" apk "$CACHE/apks/$slug.apk" || return 1
  do_install "$slug" job; irc=$?
  if [ "$irc" -eq 0 ]; then crash_fix "$slug" "$agent"; irc=$?; fi
  record_checks "$slug"
  sync_final "$slug" || syncnote='; GitHub sync pending (see log)'
  if pending "$slug"; then
    [ "$irc" -ne 1 ] && meta "$slug" '.pending.built=true'
    try='; try it, then accept or discard'
  fi
  case $irc in
    0) job done "installed; startup verified$try$syncnote" ;;
    2) job ready "built; download and install$try$syncnote" ;;
    3) job ready "built; installed copy has a different signature$syncnote" ;;
    4) job ready "installation or startup verification unavailable; retry install$syncnote" ;;
    *) meta "$slug" '.status="failed"'; job failed "runtime check or installation failed$syncnote"; return 1 ;;
  esac
}
do_build() {
  local slug=$1
  validate_project "$slug" || return 1
  do_build_impl "$slug" || return $?
  local apk=$CACHE/apks/$slug.apk pkg version
  pkg=$("$ANDROID_HOME/build-tools/35.0.0/aapt2" dump badging "$apk" 2>/dev/null | head -1)
  local expected; expected=$(jq -r .pkg "$APPS/$slug/.apkmaker.json")
  [[ $pkg == *"name='$expected'"* ]] || { echo 'built APK package differs from project identity' >> "$LOG"; return 1; }
  local cert; cert=$("$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --print-certs "$apk" 2>/dev/null | sed -n 's/^Signer #1 certificate SHA-256 digest: //p')
  [[ $cert =~ ^[0-9a-fA-F]{64}$ ]] || { echo 'APK signature could not be verified' >> "$LOG"; return 1; }
  artifact_record "$slug" apk "$apk" "$cert" || return 1
  meta "$slug" '.outcomes.build="succeeded" | .outcomes.install="unverified" | .outcomes.runtime="unverified" | del(.downloaded)'
}
run_agent() {
  local agent=$1 dir=$2 prompt=$3 before after rc
  agent_budget || { echo 'total repair/time budget exhausted' >> "$LOG"; return 125; }
  local isolation=compatible
  "$DATA/bin/sandbox-check" && isolation=isolated
  meta "${dir##*/}" '.history[-1].isolation=$s' --arg s "$isolation"
  local available="" tool
  for tool in bash perl python3 python ruby javac cc; do type -P "$tool" >/dev/null && available="$available $tool"; done
  prompt="Managed APK Maker job: implement the requested edits, then return. Do not run Gradle or start other coding agents; the backend builds afterwards and sends compiler errors back when needed. Available scripting tools:$available. Do not assume missing tools exist. This managed-job instruction overrides build-before-return instructions in older requests.

$prompt"
  before=$(protected_id "$dir")
  run_agent_impl "$agent" "$dir" "$prompt"; rc=$?
  after=$(protected_id "$dir")
  [ "$before" = "$after" ] || { echo 'agent changed protected toolchain files; review required' >> "$LOG"; return 1; }
  case $rc in
    124|137) echo 'agent timed out or was terminated; retry with a smaller request' >> "$LOG" ;;
    0) ;;
    *) echo "agent failed with exit $rc; see its output above" >> "$LOG" ;;
  esac
  return "$rc"
}
do_bundle() {
  local slug=$1 dir=$APPS/$1 aab expected actual
  validate_project "$slug" || return 1
  do_bundle_check "$slug" || return $?
  aab=$(ls -t "$dir"/app/build/outputs/bundle/release/*.aab 2>/dev/null | head -1)
  [ -n "$aab" ] || return 1
  local tmp; tmp=$(mktemp "$CACHE/.bundle.XXXX.aab") || return 1
  rm -f "$tmp"
  java -Xmx96m "$DATA/bin/Bundle.java" "$aab" "$tmp" || { rm -f "$tmp"; return 1; }
  KS_PASS=$(cat "$KEYS/$slug.pass") timeout 90s jarsigner -keystore "$KEYS/$slug.p12" -storepass:env KS_PASS -keypass:env KS_PASS \
    -sigalg SHA256withRSA -digestalg SHA-256 "$tmp" upload >> "$LOG" 2>&1 || { rm -f "$tmp"; return 1; }
  timeout 90s jarsigner -verify "$tmp" >> "$LOG" 2>&1 || { rm -f "$tmp"; return 1; }
  expected=$(key_certificate "$slug"); actual=$(bundle_certificate "$tmp")
  [ -n "$expected" ] && [ "$expected" = "$actual" ] || { rm -f "$tmp"; echo 'bundle signing certificate mismatch' >> "$LOG"; return 1; }
  mv "$tmp" "$CACHE/apks/$slug.aab"
  pmeta "$slug" '.aab=$a | .vc=$c | .vn=$n | .built=$t' --arg a "$CACHE/apks/$slug.aab" --argjson c "$PLAY_VC" --arg n "$PLAY_VN" --argjson t "$(now)"
  artifact_record "$slug" aab "$CACHE/apks/$slug.aab" "$actual"
}
list_apps() (
  exec 7> "$CACHE/apps-index.lock"; flock -w 30 7 || exit 1
  list_apps_impl
)
adb_device() {
  local devices
  devices=$(timeout 10s "$(type -P adb)" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1}')
  if [ -n "${ADB_SERIAL:-}" ]; then grep -Fx -- "$ADB_SERIAL" <<< "$devices"
  elif [ "$(wc -w <<< "$devices")" = 1 ]; then echo "$devices"; fi
}
attach_job() {
  JOB_ID=$(jq -r '.id // empty' "$CACHE/job.json")
  if [ -n "$JOB_ID" ] && [ -f "$CACHE/jobs/$JOB_ID/job.json" ]; then
    JOB=$CACHE/jobs/$JOB_ID/job.json LOG=$CACHE/jobs/$JOB_ID/log.txt
  fi
}
health() {
  recover_stale_job
  worker_alive && echo alive || echo dead
  local p id
  p=$(jq -r '.pid // 0' "$SETUP" 2>/dev/null); id=$(jq -r '.process // empty' "$SETUP" 2>/dev/null)
  if [ -n "$id" ] && [ "$(process_id "${p:-0}")" = "$id" ]; then echo alive; else echo dead; fi
}
review_release() {
  local slug=$1 fingerprint answer
  release_preview "$slug" || return 1
  fingerprint=$(release_review_id "$slug") || return 1
  [ -t 0 ] || { echo 'review needs a terminal' >&2; return 1; }
  echo 'Listing:'; jq '{title,shortDescription,fullDescription,releaseNotes}' "$APPS/$slug/play/listing.json"
  echo 'Privacy policy:'; cat "$APPS/$slug/play/privacy-policy.md"
  echo 'Inspect screenshots in play/shots; generated privacy claims must match the app.'
  IFS= read -rp 'Approve this exact release? Type approve: ' answer
  [ "$answer" = approve ] || return 1
  [ "$fingerprint" = "$(release_review_id "$slug")" ] || { echo 'release changed during review' >&2; return 1; }
  pmeta "$slug" '.reviewed=$h' --arg h "$fingerprint"
}
backup_password() {
  if [ -t 0 ]; then
    local again
    IFS= read -rsp 'Backup passphrase (at least 10 characters): ' BACKUP_PASS; echo
    if [ "${1:-}" = new ]; then
      IFS= read -rsp 'Again: ' again; echo
      [ "$BACKUP_PASS" = "$again" ] || return 1
    fi
  else IFS= read -r BACKUP_PASS || return 1; fi
  [ "${#BACKUP_PASS}" -ge 10 ]
}
project_backup() (
  local slug=$1 output=$2 t
  need_app "$slug"
  [ ! -e "$output" ] || { echo 'backup output already exists' >&2; return 1; }
  if locked_mode; then ask_pass && open_secrets "$slug" || return 1; fi
  t=$(mktemp -d "$CACHE/.unlocked.$$.XXXX") || return 1
  trap 'rm -rf "$t"; close_secrets' EXIT
  trap 'exit 130' INT TERM HUP
  backup_password new || return 1
  mkdir -p "$t/keys" "$t/artifacts"
  for ext in p12 pass; do [ ! -f "$KEYS/$slug.$ext" ] || cp "$KEYS/$slug.$ext" "$t/keys/"; done
  for ext in apk aab; do [ ! -f "$CACHE/apks/$slug.$ext" ] || cp "$CACHE/apks/$slug.$ext" "$t/artifacts/"; done
  java -Xmx96m "$DATA/bin/Backup.java" create "$t/project.zip" project "$APPS/$slug" keys "$t/keys" artifacts "$t/artifacts" || return 1
  openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass fd:3 -in "$t/project.zip" -out "$t/backup.enc" 3< <(printf '%s\n' "$BACKUP_PASS") || return 1
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass fd:3 -in "$t/backup.enc" -out "$t/verified.zip" 3< <(printf '%s\n' "$BACKUP_PASS") || return 1
  cmp -s "$t/project.zip" "$t/verified.zip" || return 1
  java -Xmx96m "$DATA/bin/Backup.java" extract "$t/verified.zip" "$t/check" || return 1
  cp -n "$t/backup.enc" "$output" || return 1
  echo "Backup: $output"
  echo 'Verified encrypted project, metadata, artifacts and upload-key backup saved. App user data is separate.'
)
project_restore() (
  local slug=$1 input=$2 t pkg
  [[ $slug =~ ^[a-z0-9][a-z0-9-]*$ ]] && [ ! -e "$APPS/$slug" ] || { echo 'choose an unused app slug' >&2; return 1; }
  key_known "$slug" && { echo 'this slug has a retained upload key; choose another slug' >&2; return 1; }
  t=$(mktemp -d "$CACHE/.unlocked.$$.XXXX") || return 1
  trap 'rm -rf "$t"; close_secrets' EXIT
  trap 'exit 130' INT TERM HUP
  backup_password || return 1
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass fd:3 -in "$input" -out "$t/project.zip" 3< <(printf '%s\n' "$BACKUP_PASS") || return 1
  java -Xmx96m "$DATA/bin/Backup.java" extract "$t/project.zip" "$t/unpacked" || return 1
  local old; old=$(jq -er '.slug | select(test("^[a-z0-9][a-z0-9-]*$"))' "$t/unpacked/project/.apkmaker.json") || return 1
  pkg=$(jq -er '.pkg | select(test("^[a-zA-Z][a-zA-Z0-9_.]+$"))' "$t/unpacked/project/.apkmaker.json") || return 1
  if [ -f "$t/unpacked/keys/$old.p12" ]; then
    KS_PASS=$(cat "$t/unpacked/keys/$old.pass") keytool -list -keystore "$t/unpacked/keys/$old.p12" -storepass:env KS_PASS -alias upload >/dev/null 2>&1 || return 1
    if locked_mode; then
      ask_pass || return 1
      vault_put "$t/unpacked/keys/$old.p12" "keys/$slug.p12" && vault_put "$t/unpacked/keys/$old.pass" "keys/$slug.pass" || return 1
    else
      mkdir -p "$KEYS"
      cp "$t/unpacked/keys/$old.p12" "$KEYS/$slug.p12"; cp "$t/unpacked/keys/$old.pass" "$KEYS/$slug.pass"
    fi
  fi
  mv "$t/unpacked/project" "$APPS/$slug" || return 1
  cp "$DATA/template/local.properties" "$DATA/template/gradle.properties" "$APPS/$slug/"
  meta "$slug" '.slug=$s | .status="ready" | del(.installed,.installedArtifact,.downloaded,.pending,.play.reviewed) | .outcomes.install="unverified" | .outcomes.runtime="unverified"' --arg s "$slug"
  ln -sfn AGENTS.md "$APPS/$slug/CLAUDE.md"
  [ ! -f "$APPS/$slug/gradlew" ] || chmod +x "$APPS/$slug/gradlew"
  for ext in apk aab; do
    if [ -f "$t/unpacked/artifacts/$old.$ext" ]; then
      cp "$t/unpacked/artifacts/$old.$ext" "$CACHE/apks/$slug.$ext"
      meta "$slug" 'if $e=="apk" then .apk=$f else .play.aab=$f end' --arg e "$ext" --arg f "$CACHE/apks/$slug.$ext"
    fi
  done
  echo "Restored $slug. Rebuild to verify this device's configuration before installation or publishing."
)
record_checks() {
  local slug=$1 file=$APPS/$1/acceptance.json
  if [ -f "$file" ] && jq -e '.checks | type=="array"' "$file" >/dev/null 2>&1; then
    meta "$slug" '.checks=$checks | .checksSource=$source' --argjson checks "$(jq -c .checks "$file")" --arg source "$(source_id "$slug")"
  else
    meta "$slug" '.checks=[{id:"features",title:"Verify requested features",status:"pending"}] | .checksSource=$source' --arg source "$(source_id "$slug")"
  fi
}
checks_cmd() {
  local slug=$1 id=${2:-} status=${3:-}
  if [ -n "$id" ]; then
    [[ $status =~ ^(pass|fail|skip|pending)$ ]] || return 1
    meta "$slug" '.checks |= map(if .id==$id then .status=$s | .note=$n | .at=$t else . end)' \
      --arg id "$id" --arg s "$status" --arg n "${4:-}" --argjson t "$(now)"
  fi
  jq '{checks,checksSource,outcomes}' "$APPS/$slug/.apkmaker.json"
}
publish_job() {
  [ "$JOB" != "$CACHE/job.json" ] || return 0
  local tmp; tmp=$(mktemp "$CACHE/.current-job.XXXX") || return 1
  cp "$JOB" "$tmp" && mv "$tmp" "$CACHE/job.json"
}
recover_stale_job() (
  exec 6> "$CACHE/work.lock"; flock -n 6 || return 0
  job_active || return 0
  worker_alive && return 0
  local updated pid identity id slug
  updated=$(jq -r '.updated // 0' "$JOB"); pid=$(jq -r '.pid // 0' "$JOB"); identity=$(jq -r '.process // empty' "$JOB")
  [ "$(( $(now) - updated ))" -gt 30 ] || return 0
  if [ -z "$identity" ] && [[ $pid =~ ^[0-9]+$ ]] && [ "$pid" -gt 1 ] && kill -0 "$pid" 2>/dev/null; then return 0; fi
  id=$(jq -r '.id // empty' "$JOB")
  if [ -z "$id" ]; then
    id=legacy-$(jq -r '.started // 0' "$JOB")
    mkdir -p "$CACHE/jobs/$id"
    cp "$JOB" "$CACHE/jobs/$id/job.json"
    [ ! -f "$LOG" ] || cp "$LOG" "$CACHE/jobs/$id/log.txt"
    JOB=$CACHE/jobs/$id/job.json LOG=$CACHE/jobs/$id/log.txt
    jobset '.id=$id' --arg id "$id"
  else attach_job; fi
  slug=$(jq -r '.slug // empty' "$JOB")
  job failed 'previous worker stopped; retry to continue from the saved project'
  if [ -n "$slug" ] && [ -f "$APPS/$slug/.apkmaker.json" ]; then
    meta "$slug" '.status=(if .apk then "ready" else "failed" end) | .outcomes.build="interrupted"'
  fi
)
