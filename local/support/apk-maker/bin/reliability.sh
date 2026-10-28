# Shared locking, identities and immutable build receipts. Sourced by apk-maker.
json_edit() (
  local f=$1 tmp; shift
  mkdir -p "$(dirname "$f")"
  local lock; lock=$(printf '%s' "$(realpath -m "$f")" | sha256sum | cut -d' ' -f1)
  mkdir -p "$CACHE/state-locks"
  exec 7> "$CACHE/state-locks/$lock"; flock -w 30 7 || return 1
  tmp=$(mktemp "$(dirname "$f")/.json.XXXX") || return 1
  trap 'rm -f "$tmp"' EXIT
  { cat "$f" 2>/dev/null || echo '{}'; } | jq -c "$@" > "$tmp" && mv "$tmp" "$f"
)
process_id() { [ -r "/proc/$1/stat" ] && sed 's/.*) //' "/proc/$1/stat" | awk '{print $20}'; }
worker_alive() {
  local p id
  p=$(jq -r '.pid // 0' "$JOB" 2>/dev/null); id=$(jq -r '.process // empty' "$JOB" 2>/dev/null)
  [[ $p =~ ^[0-9]+$ ]] && [ "$p" -gt 1 ] && [ -n "$id" ] && [ "$(process_id "$p")" = "$id" ]
}
mutation_lock() {
  [ "${MUTATION_LOCKED:-}" = 1 ] && return 0
  exec 6> "$CACHE/work.lock"; flock -n 6 || { echo "another job or update is running" >&2; exit 1; }
  MUTATION_LOCKED=1
}
vault_lock() { exec 5> "$DATA/vault.lock"; flock -w 15 5 || { echo "publishing keys are in use" >&2; exit 1; }; }
adb() {
  local action=${1:-}
  case $action in
    devices|connect|pair|mdns|start-server|kill-server|version) timeout 15s "$(type -P adb)" "$@" ;;
    *)
      if [ -z "${ADB_SERIAL:-}" ]; then
        local devices; devices=$(timeout 10s "$(type -P adb)" devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1}')
        [ "$(wc -w <<< "$devices")" = 1 ] || { echo "select one device: apk-maker set device <serial>" >&2; return 1; }
        ADB_SERIAL=$devices
      fi
      timeout 90s "$(type -P adb)" -s "$ADB_SERIAL" "$@" ;;
  esac
}
git() { timeout 120s "$(type -P git)" "$@"; }
gh() { timeout 120s "$(type -P gh)" "$@"; }
isolated() { "$DATA/bin/isolate" "$@"; }
source_id() (
  local d=$APPS/$1
  cd "$d" || exit 1
  find . -type f ! -path './.git/*' ! -path './.gradle/*' ! -path './.kotlin/*' \
    ! -path '*/build/*' ! -path './.claude/*' ! -path './.peek/*' ! -path './play/*' \
    ! -name '.apkmaker.json*' ! -name 'local.properties' ! -name 'CLAUDE.md' \
    ! -name '*.apk' ! -name '*.aab' -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | cut -d' ' -f1
)
artifact_record() {
  local slug=$1 kind=$2 file=$3 certificate=${4:-} hash src commit
  [ -n "$certificate" ] || certificate=$(jq -r --arg k "$kind" '.artifacts[$k].certificate // empty' "$APPS/$slug/.apkmaker.json")
  hash=$(sha256sum "$file" | cut -d' ' -f1) || return 1
  src=$(source_id "$slug") || return 1
  commit=$(git -C "$APPS/$slug" rev-parse HEAD 2>/dev/null || true)
  meta "$slug" '.artifacts[$kind]={sha256:$hash, source:$source, commit:$commit, certificate:$cert, job:$job, at:$t}' \
    --arg kind "$kind" --arg hash "$hash" --arg source "$src" --arg commit "$commit" --arg cert "$certificate" \
    --arg job "${JOB_ID:-manual}" --argjson t "$(now)"
}
artifact_ok() {
  local slug=$1 kind=$2 file=$3 hash
  [ -s "$file" ] || return 1
  hash=$(sha256sum "$file" | cut -d' ' -f1) || return 1
  jq -e --arg k "$kind" --arg h "$hash" --arg s "$(source_id "$slug")" \
    '.artifacts[$k].sha256 == $h and .artifacts[$k].source == $s' "$APPS/$slug/.apkmaker.json" >/dev/null
}
certificate_id() { openssl x509 -inform DER -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f'; }
key_certificate() {
  KS_PASS=$(cat "$KEYS/$1.pass") keytool -exportcert -alias upload -keystore "$KEYS/$1.p12" -storepass:env KS_PASS 2>/dev/null | certificate_id
}
bundle_certificate() {
  unzip -p "$1" 'META-INF/*.RSA' 2>/dev/null | openssl pkcs7 -inform DER -print_certs 2>/dev/null \
    | openssl x509 -outform DER 2>/dev/null | certificate_id
}
protected_id() {
  local dir=$1
  (cd "$dir" && sha256sum gradlew gradle/wrapper/* gradle.properties gradle/libs.versions.toml 2>/dev/null)
}
validate_project() {
  local slug=$1 pkg=${2:-} dir=$APPS/$1
  [ -n "$pkg" ] || pkg=$(jq -r .pkg "$dir/.apkmaker.json")
  grep -qE "applicationId *= *\"$pkg\"" "$dir/app/build.gradle.kts" && \
    grep -qE "namespace *= *\"$pkg\"" "$dir/app/build.gradle.kts" && \
    grep -qE 'isMinifyEnabled *= *false' "$dir/app/build.gradle.kts" || {
      echo 'package identity or protected build configuration changed' >> "$LOG"; return 1;
    }
}
agent_budget() {
  local used=${AGENT_RUNS:-0} max=$(( (FIX_ROUNDS + 1) * 2 + 2 ))
  [ "$used" -lt "$max" ] && [ "$(now)" -lt "${JOB_DEADLINE:-$(( $(now) + 1 ))}" ] || return 1
  AGENT_RUNS=$((used + 1))
}
rotate_vault() (
  local old=$VP new t f generation link
  new_pass || return 1; new=$VP
  t=$(mktemp -d "$CACHE/.unlocked.$$.XXXX") || return 1
  generation=$DATA/vault.generations/$(now)-$$-$RANDOM
  mkdir -p "$generation"
  trap 'rm -rf "$t"; recover_vault' EXIT
  trap 'exit 130' INT TERM HUP
  local active=$VAULT
  while IFS= read -r -d '' f; do
    local name=${f#"$active"/}; name=${name%.enc}
    VP=$old VAULT=$active
    vault_dec "$name" "$t/plain" || return 1
    VP=$new VAULT=$generation
    vault_put "$t/plain" "$name" || { VAULT=$active; return 1; }
    rm -f "$t/plain"
  done < <(find -L "$active" -type f -name '*.enc' -print0)
  VAULT=$generation VP=$new
  vault_check || { VAULT=$active; return 1; }
  VAULT=$active
  link=$DATA/.vault.link.$$
  ln -s "$generation" "$link" || return 1
  if [ -d "$VAULT" ] && [ ! -L "$VAULT" ]; then
    [ ! -e "$DATA/vault.previous" ] || { echo 'vault.previous already exists; recovery needed' >&2; return 1; }
    : > "$DATA/.vault-activating"
    mv "$VAULT" "$DATA/vault.previous" || return 1
  fi
  mv -Tf "$link" "$VAULT" || return 1
  rm -f "$DATA/.vault-activating"
  rm -rf "$t"
  trap - EXIT INT TERM HUP
  echo 'passphrase changed; complete previous encrypted vault retained for recovery'
)
recover_vault() {
  if [ -f "$DATA/.vault-activating" ] && [ ! -e "$DATA/vault" ] && [ ! -L "$DATA/vault" ] && [ -d "$DATA/vault.previous" ]; then
    mv "$DATA/vault.previous" "$DATA/vault"
    rm -f "$DATA/.vault-activating"
  fi
}
release_preflight() {
  local slug=$1 dir=$APPS/$1 f=$APPS/$1/play/listing.json
  listing_ok "$slug" || { echo 'complete the store listing first' >&2; return 1; }
  jq -e '(.shortDescription | length)>0 and (.fullDescription | length)>0' "$f" >/dev/null || return 1
  [ -s "$dir/play/privacy-policy.md" ] && [ -s "$dir/play/icon.png" ] && [ -s "$dir/play/feature.png" ] || {
    echo 'privacy policy or store graphics are missing' >&2; return 1;
  }
  artifact_ok "$slug" aab "$CACHE/apks/$slug.aab" || { echo 'bundle is outdated: prepare again' >&2; return 1; }
  local cert; cert=$(bundle_certificate "$CACHE/apks/$slug.aab")
  [ -n "$cert" ] && [ "$cert" = "$(jq -r '.artifacts.aab.certificate' "$dir/.apkmaker.json")" ] || return 1
  local count; count=$(find "$dir/play/shots" -maxdepth 1 -name '*.png' -type f 2>/dev/null | wc -l)
  [ "$count" -ge 2 ] && [ "$(jq -r '.play.graphicsSource // empty' "$dir/.apkmaker.json")" = "$(source_id "$slug")" ] || { echo 'capture at least two screenshots of the current build before review' >&2; return 1; }
  local review; review=$(release_review_id "$slug")
  jq -e --arg h "$review" '.play.reviewed == $h' "$dir/.apkmaker.json" >/dev/null || {
    echo 'review the release: apk-maker play preview <app>, then apk-maker play approve <app> <fingerprint>' >&2; return 1;
  }
}
release_review_id() {
  local slug=$1
  { source_id "$slug"; sha256sum "$CACHE/apks/$slug.aab"; find "$APPS/$slug/play" -type f -print0 | sort -z | xargs -0 -r sha256sum; } | sha256sum | cut -d' ' -f1
}
release_preview() {
  local slug=$1 h; h=$(release_review_id "$slug") || return 1
  jq --arg fingerprint "$h" '{app:.label,package:.pkg,version:.play.vn,code:.play.vc,bundle:.artifacts.aab,graphics:.play.graphics,listing:.play.title,notes:.play.notes,reviewFingerprint:$fingerprint,tracks:.play.tracks}' "$APPS/$slug/.apkmaker.json"
  echo "Review play/listing.json, play/privacy-policy.md, play/shots and release notes, then:"
  echo "apk-maker play approve $slug $h"
}
