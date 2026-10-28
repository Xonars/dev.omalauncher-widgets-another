
#!/bin/bash
# pinterest-wallswap for omalauncher: swap the launcher's wallpaper for a fresh image from the web.
# A port of omarchy-pinterest-wallswap (https://github.com/petrzpav/omarchy-pinterest-wallswap).
#
#   pinterest-wallswap next [CFG]            fetch a new image now and set it
#   pinterest-wallswap prev [CFG]            go back to the previous image
#   pinterest-wallswap tick [CFG]            like next, but only when the interval has elapsed
#   pinterest-wallswap pause|resume|toggle   stop or restart automatic swapping
#   pinterest-wallswap info [CFG]            the current image and the schedule as JSON
#   pinterest-wallswap keep                  copy the current image into the theme's backgrounds
#
# CFG is one JSON argument (all keys optional):
#   {"sources": ["apod","bing","wikimedia","wallhaven","local"], "interval": 1440,
#    "query": "", "screen": [1080, 2400], "theme": "tokyo-night", "localDir": "~/Pictures/Wallpapers",
#    "wifiOnly": true}
# With wifiOnly, automatic swaps wait for Wi-Fi; next always swaps.
#
# The wallpaper is set the way the launcher's Style menu sets it: the image goes into
# ~/.config/omarchy/backgrounds/<theme>/ as pinterest-wallswap-*.jpg, cropped to the screen, and
# style.toml's background names it.

set -o pipefail

declare -A SOURCE_NAMES=(
  [pinterest]="Pinterest · xonars"
  [apod]="NASA Astronomy Picture of the Day"
  [bing]="Bing image of the day"
  [wikimedia]="Wikimedia Commons picture of the day"
  [wallhaven]="Wallhaven top wallpapers"
  [local]="Local folder"
)

CACHE_DIR=${XDG_CACHE_HOME:-$HOME/.cache}/pinterest-wallswap
STATE_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/pinterest-wallswap
STYLE=$HOME/.config/omalauncher/style/style.toml
BG_ROOT=$HOME/.config/omarchy/backgrounds
UA="pinterest-wallswap/1.0 (omalauncher wallpaper widget)"
ATTEMPTS=3
KEEP=40
RETRY=600 # after a failed swap, or without Wi-Fi, try again in 10 minutes

log() { echo "pinterest-wallswap: $*" >&2; }
die() { log "$*"; printf '%s\n' "$*" | write_state error 2>/dev/null; exit 1; }

# Every file this script writes lands in a fresh mktemp file (O_EXCL, never an existing
# path or symlink) that is then renamed over the target.
atomic_write() { # path  (content on stdin)
  local tmp
  tmp=$(mktemp -- "$(dirname -- "$1")/.$(basename -- "$1").XXXXXX") || return 1
  if cat > "$tmp" && mv -f -- "$tmp" "$1"; then return 0; fi
  rm -f -- "$tmp"
  return 1
}
write_state() { atomic_write "$STATE_DIR/$1"; }
append_state() { { cat -- "$STATE_DIR/$1" 2>/dev/null; printf '%s\n' "$2"; } | write_state "$1"; }

private_dir() {
  [[ -L $1 ]] && { log "refusing a symlinked directory: $1"; exit 1; }
  mkdir -p -m 700 -- "$1" || exit 1
  [[ -d $1 && -O $1 ]] || { log "not a directory owned by you: $1"; exit 1; }
  chmod 700 -- "$1"
}

# HTTPS only, no redirects, a ceiling on bytes and time.
CURL_POLICY=(--fail --silent --show-error --proto =https --max-redirs 0 -A "$UA")
http() { curl "${CURL_POLICY[@]}" --max-time 30 --max-filesize 2000000 "$@"; }

# Each source may only hand back images, and link to pages, on its own hosts.
allowed_image() {
  case $1 in
    pinterest) [[ $2 =~ ^https://i\.pinimg\.com/[^[:space:]]+\.(jpg|jpeg|png|webp)$ ]] ;;
    apod) [[ $2 =~ ^https://assets\.science\.nasa\.gov/content/dam/science/cds/apod/[^[:space:]]+$ ]] ;;
    bing) [[ $2 =~ ^https://www\.bing\.com/th\?id=[^[:space:]]+$ ]] ;;
    wikimedia) [[ $2 =~ ^https://upload\.wikimedia\.org/wikipedia/commons/[^[:space:]]+$ ]] ;;
    wallhaven) [[ $2 =~ ^https://w\.wallhaven\.cc/full/[^[:space:]]+$ ]] ;;
    local) [[ $2 == file://* ]] && inside_local_dir "${2#file://}" ;;
    *) return 1 ;;
  esac
}
allowed_page() {
  case $1 in
    pinterest) [[ $2 =~ ^https://www\.pinterest\.com/pin/[A-Za-z0-9_-]+/$ ]] ;;
    apod) [[ $2 =~ ^https://science\.nasa\.gov/image-article/apod-[^[:space:]]*$ ]] ;;
    bing) [[ $2 =~ ^https://www\.bing\.com/[^[:space:]]*$ ]] ;;
    wikimedia) [[ $2 =~ ^https://commons\.wikimedia\.org/[^[:space:]]*$ ]] ;;
    wallhaven) [[ $2 =~ ^https://wallhaven\.cc/w/[a-z0-9]+$ ]] ;;
    *) return 1 ;;
  esac
}
inside_local_dir() {
  local dir path
  dir=$(realpath -e -- "$LOCAL_DIR" 2>/dev/null) || return 1
  path=$(realpath -e -- "$1" 2>/dev/null) || return 1
  [[ $path == "$dir"/* && -f $path ]]
}

# Decode only the formats we asked for, whatever the file claims to be.
image_coder() {
  case $(file -b --mime-type -- "$1" 2>/dev/null) in
    image/jpeg) echo jpeg ;;
    image/png) echo png ;;
    image/webp) echo webp ;;
    *) return 1 ;;
  esac
}

# --------------------------------------------------------------- sources
# Each prints candidates, one per line, tab separated:
#   image-url  title  credit  page-url  [width  height]

src_pinterest() {
  python "$HOME/.config/omalauncher/widgets/pinterest-wallswap/pinterest.py" pins "$cfg" 2> "$STATE_DIR/source-error"
}

src_apod() {
  local page=$(( RANDOM % 1100 + 1 ))
  http "https://science.nasa.gov/wp-json/wp/v2/image-article?search=APOD&per_page=10&page=$page&_embed=wp:featuredmedia&_fields=link,title,_links,_embedded" | jq -r '
    .[] | (.title.rendered
      | gsub("&#(?<n>[0-9]+);"; ([.n | tonumber] | implode))
      | gsub("&amp;"; "&") | gsub("&quot;"; "\"") | gsub("[\t\n]"; " ")) as $t
    | select($t | startswith("APOD:"))
    | (._embedded["wp:featuredmedia"][0] // empty) as $m
    | select($m.source_url // "" | contains("/cds/apod/"))
    | [$m.source_url, ($t | sub("^APOD:\\s*[0-9]{4} [A-Za-z]+ [0-9]{1,2}\\s*[–-]\\s*"; "")), "NASA APOD",
       .link, $m.media_details.width, $m.media_details.height] | @tsv'
}

src_bing() {
  # Bing serves every image of the day in a phone's portrait size too.
  local idx=$(( RANDOM % 2 * 8 )) size=UHD w=3840 h=2160
  (( SCREEN_H > SCREEN_W )) && size=1080x1920 w=1080 h=1920
  http "https://www.bing.com/HPImageArchive.aspx?format=js&idx=$idx&n=8&mkt=en-US" | jq -r --arg s "$size" --arg w "$w" --arg h "$h" '
    .images[]
    | (.copyright | capture("^(?<t>.*?)\\s*\\((?<c>©.*)\\)$") // {t: .copyright, c: "Bing"}) as $m
    | ["https://www.bing.com\(.urlbase)_\($s).jpg", $m.t, ("Bing · " + $m.c), .copyrightlink, $w, $h] | @tsv'
}

src_wikimedia() {
  local day
  day=$(date -d "-$(( RANDOM % 1095 )) days" +%Y/%m/%d)
  http "https://api.wikimedia.org/feed/v1/wikipedia/en/featured/$day" | jq -r '
    .image | select(. != null)
    | (.image.source | sub("\\?.*$"; "")) as $src
    | ($src | capture("/commons/(?<p>[0-9a-f]/[0-9a-f]{2})/(?<f>[^/]+)$")) as $m
    | (if .image.width > 3840 and ($m.f | test("\\.(jpe?g|png)$"; "i"))
       then "https://upload.wikimedia.org/wikipedia/commons/thumb/\($m.p)/\($m.f)/3840px-\($m.f)"
       else $src end) as $url
    | (if .image.width > 3840 then [3840, (.image.height * 3840 / .image.width | floor)] else [.image.width, .image.height] end) as $wh
    | [$url, ((.description.text // (.title | sub("^File:"; "") | sub("\\.[A-Za-z]+$"; ""))) | gsub("[\t\n]"; " ") | .[0:160]),
       ("Wikimedia Commons" + (if .artist.text then " · " + (.artist.text | gsub("[\t\n]"; " ") | split(". ")[0] | .[0:60]) else "" end)),
       .file_page, $wh[0], $wh[1]] | @tsv'
}

src_wallhaven() {
  local page=$(( RANDOM % 5 + 1 )) q ratio=landscape atleast=1920x1080
  (( SCREEN_H > SCREEN_W )) && ratio=portrait atleast=1080x1920
  q=$(jq -rn --arg q "$QUERY" '$q | @uri')
  http "https://wallhaven.cc/api/v1/search?sorting=toplist&topRange=1y&categories=100&purity=100&atleast=$atleast&ratios=$ratio&page=$page&q=$q" | jq -r '
    .data[] | (.resolution | split("x")) as $r
    | [.path, ("Wallhaven " + .id), "Wallhaven", .url, $r[0], $r[1]] | @tsv'
}

src_local() {
  [[ -d $LOCAL_DIR ]] || { log "local folder not found: $LOCAL_DIR"; return 1; }
  find -L "$LOCAL_DIR" -maxdepth 2 -type f \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) -print0 |
    while IFS= read -r -d '' f; do
      printf 'file://%s\t%s\t%s\t\n' "$f" "$(basename "${f%.*}")" "Local folder"
    done
}

# --------------------------------------------------------------- helpers

# Android keeps a default route per network it's connected to; a Wi-Fi one means Wi-Fi.
# When the routes can't be read, don't hold swaps back.
on_wifi() {
  local routes
  routes=$(ip -o route show table all 2>/dev/null) || return 0
  [[ -n $routes ]] || return 0
  grep -qE '^default .*dev (wlan|wifi)' <<< "$routes"
}

seen() { grep -qxF -- "$1" "$STATE_DIR/seen" 2>/dev/null; }

# Big enough to cover the screen without blowing it up more than 1.5 times.
acceptable() { # width height
  local w=$1 h=$2
  [[ $w =~ ^[0-9]+$ && $h =~ ^[0-9]+$ && $w -gt 0 && $h -gt 0 ]] || return 0 # unknown: decide after download
  (( w >= 320 && h >= 320 ))
}

# The theme's directory name. style.toml names it only when it isn't the default, and the
# launcher gives the theme's title ("Tokyo Night"), so that is turned into its directory.
theme_name() {
  local t
  t=$(sed -n 's/^theme[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$STYLE" 2>/dev/null | head -1)
  if [[ -z $t ]]; then
    t=${THEME,,}; t=${t//[^a-z0-9._-]/-}
    [[ -n $t && ( -d $HOME/.config/omarchy/themes/$t || -d $HOME/.local/share/omarchy/themes/$t ) ]] || t=tokyo-night
  fi
  [[ $t =~ ^[A-Za-z0-9._-]+$ && $t != . && $t != .. ]] || return 1
  echo "$t"
}

# Point style.toml's top-level background at a file name, written in place so the
# launcher's watch on the file sees it.
set_style_background() { # name
  local new
  new=$(awk -v bg="$1" '
    BEGIN { done = 0; top = 1 }
    /^\[/ { if (top && !done) { print "background = \"" bg "\""; done = 1 } top = 0 }
    top && /^background[[:space:]]*=/ { if (!done) print "background = \"" bg "\""; done = 1; next }
    { print }
    END { if (!done) print "background = \"" bg "\"" }' "$STYLE" 2>/dev/null) || return 1
  [[ -f $STYLE ]] || new="version = 1"$'\n'"background = \"$1\""
  mkdir -p -- "$(dirname -- "$STYLE")"
  printf '%s\n' "$new" > "$STYLE"
}

# Crop the image to the screen into the theme's backgrounds, show it, and remove the
# pinterest-wallswap images shown before it.
set_background() { # source-file id  -> prints the installed path
  local theme dir name coder
  theme=$(theme_name) || { log "unexpected theme name"; return 1; }
  dir=$BG_ROOT/$theme
  mkdir -p -- "$dir"
  name="pinterest-wallswap-$2.jpg"
  coder=$(image_coder "$1") || return 1
  magick "$coder:$1[0]" -auto-orient -resize "${SCREEN_W}x${SCREEN_H}^" -gravity center \
    -extent "${SCREEN_W}x${SCREEN_H}" -strip -quality 90 "jpeg:$dir/.$name.tmp" 2>/dev/null &&
    mv -f -- "$dir/.$name.tmp" "$dir/$name" || { rm -f -- "$dir/.$name.tmp"; return 1; }
  set_style_background "$name" || return 1
  # The one shown before stays until the next swap, so a view still showing it never loses it.
  ls -1t -- "$BG_ROOT"/*/pinterest-wallswap-*.jpg 2>/dev/null | grep -vxF -- "$dir/$name" | tail -n +2 |
    while read -r old; do rm -f -- "$old"; done
  echo "$dir/$name"
}

prune_cache() {
  ls -1t "$CACHE_DIR"/*.json 2>/dev/null | tail -n +$(( KEEP + 1 )) | while read -r meta; do
    local img
    img=$(jq -r '.file' "$meta" 2>/dev/null)
    [[ $img == "$(jq -r '.file' "$STATE_DIR/current.json" 2>/dev/null)" ]] && continue
    [[ $img == "$CACHE_DIR"/* ]] && rm -f -- "$img"
    rm -f -- "$meta"
  done
  [[ -f $STATE_DIR/history ]] && while read -r m; do [[ -f $m ]] && echo "$m"; done < "$STATE_DIR/history" | tail -n "$KEEP" | write_state history
  [[ -f $STATE_DIR/seen ]] && tail -n 2000 "$STATE_DIR/seen" | write_state seen
}

try_candidate() { # source url title credit page w h
  local source=$1 url=$2 title=$3 credit=$4 page=$5 w=$6 h=$7
  [[ -n $url ]] || return 1
  allowed_image "$source" "$url" || { log "$source: ignoring image outside its hosts: ${url:0:120}"; return 1; }
  allowed_page "$source" "$page" || page=""
  seen "$url" && return 1
  acceptable "$w" "$h" || { append_state seen "$url"; return 1; }

  local id ext file tmp dims coder
  id=$(printf '%s' "$url" | sha1sum | cut -c1-12)
  ext=${url##*.}; ext=${ext%%\?*}; ext=${ext,,}
  [[ $ext =~ ^(jpg|jpeg|png|webp)$ ]] || ext=jpg
  file="$CACHE_DIR/$source-$id.$ext"

  if [[ $url == file://* ]]; then
    file=$(realpath -e -- "${url#file://}") || return 1
  elif [[ -L $file || ! -s $file ]]; then
    tmp=$(mktemp -- "$CACHE_DIR/.download.XXXXXX") || return 1
    log "downloading $url"
    if ! curl "${CURL_POLICY[@]}" --max-time 120 --max-filesize 80000000 -o "$tmp" -- "$url"; then
      rm -f -- "$tmp"; return 1
    fi
    mv -f -- "$tmp" "$file"
  fi

  coder=$(image_coder "$file") || coder=""
  [[ -n $coder ]] && dims=$(magick identify -format '%w %h' "$coder:${file}[0]" 2>/dev/null)
  if [[ -z $dims ]] || ! acceptable $dims; then
    log "rejected $url (${dims:-not an image})"
    append_state seen "$url"
    [[ $url == file://* ]] || rm -f -- "$file"
    return 1
  fi

  append_state seen "$url"
  if [[ $source == wallhaven && $page =~ /w/([a-z0-9]+)$ ]]; then
    local tags
    tags=$(http "https://wallhaven.cc/api/v1/w/${BASH_REMATCH[1]}" 2>/dev/null |
      jq -r '[.data.tags[].name] | .[0:4] | join(", ") | select(. != "")' 2>/dev/null)
    [[ -n $tags ]] && title=${tags^}
  fi
  local meta="$CACHE_DIR/$source-$id.json"
  jq -n --arg file "$file" --arg id "$source-$id" --arg url "$url" --arg title "$title" --arg credit "$credit" \
    --arg page "$page" --arg source "$source" --arg sourceName "${SOURCE_NAMES[$source]}" \
    --arg size "${dims/ /x}" --arg at "$(date -Iseconds)" \
    '{file:$file, id:$id, url:$url, title:$title, credit:$credit, page:$page, source:$source, sourceName:$sourceName, size:$size, fetchedAt:$at}' |
    atomic_write "$meta" || return 1
  # The image is fine but can't be set: drop it, and don't download more that would fail too.
  apply "$meta" && return 0
  [[ $url == file://* ]] || rm -f -- "$file"
  rm -f -- "$meta"
  return 2
}

apply() { # meta.json [--no-history]
  local file id bg
  file=$(jq -r '.file' "$1"); id=$(jq -r '.id' "$1")
  [[ -f $file && $id =~ ^[a-z]+-[0-9a-f]+$ ]] || return 1
  bg=$(set_background "$file" "$id") || return 1
  jq --arg bg "$bg" '. + {bg: $bg}' "$1" | write_state current.json
  [[ $2 == --no-history ]] || append_state history "$1"
  date +%s | write_state last
  rm -f -- "$STATE_DIR/error" "$STATE_DIR/failed" "$STATE_DIR/nowifi"
  log "set $(jq -r '"\(.title) — \(.credit)"' "$1")"
}

fallback_cached() {
  local current meta
  current=$(jq -r '.file' "$STATE_DIR/current.json" 2>/dev/null)
  meta=$(ls -1 "$CACHE_DIR"/*.json 2>/dev/null | shuf | while read -r m; do
    [[ $(jq -r '.file' "$m") != "$current" && -f $(jq -r '.file' "$m") ]] && { echo "$m"; break; }
  done)
  [[ -n $meta ]] || return 1
  log "no new image available, reusing a cached one"
  apply "$meta"
}

cmd_next() {
  (( ${#SOURCES[@]} )) || die "no sources switched on"
  theme_name >/dev/null || die "unexpected theme name"
  local attempt source line rc
  for (( attempt = 0; attempt < ATTEMPTS; attempt++ )); do
    source=${SOURCES[RANDOM % ${#SOURCES[@]}]}
    declare -F "src_$source" >/dev/null || { log "unknown source: $source"; continue; }
    while IFS=$'\t' read -r url title credit page w h; do
      try_candidate "$source" "$url" "$title" "$credit" "$page" "$w" "$h"; rc=$?
      (( rc == 0 )) && { prune_cache; return 0; }
      (( rc == 2 )) && { date +%s | write_state failed; die "couldn't set the background"; }
    done < <("src_$source" 2>/dev/null | shuf)
    log "$source: nothing new, trying another source"
  done
  fallback_cached && return 0
  date +%s | write_state failed
  die "$(cat "$STATE_DIR/source-error" 2>/dev/null || true) Не удалось получить новое изображение из выбранных досок"
}

cmd_prev() {
  local -a history
  mapfile -t history < "$STATE_DIR/history" 2>/dev/null
  (( ${#history[@]} >= 2 )) || die "no previous background"
  printf '%s\n' "${history[@]:0:${#history[@]}-1}" | write_state history
  apply "${history[-2]}" --no-history || die "couldn't go back"
}

cmd_pause() { : | write_state paused; }
cmd_resume() { rm -f -- "$STATE_DIR/paused"; date +%s | write_state last; }
cmd_toggle() { if [[ -f $STATE_DIR/paused ]]; then cmd_resume; else cmd_pause; fi; }

cmd_tick() {
  (( INTERVAL > 0 )) || return 0
  [[ -f $STATE_DIR/paused ]] && return 0
  local last failed nowifi now
  last=$(cat "$STATE_DIR/last" 2>/dev/null || echo 0)
  failed=$(cat "$STATE_DIR/failed" 2>/dev/null || echo 0)
  nowifi=$(cat "$STATE_DIR/nowifi" 2>/dev/null || echo 0)
  now=$(date +%s)
  (( now - last >= INTERVAL * 60 && now - failed >= RETRY && now - nowifi >= RETRY )) || return 0
  if [[ $WIFI_ONLY == true ]] && ! on_wifi; then
    log "not on Wi-Fi, waiting"
    echo "$now" | write_state nowifi
    return 0
  fi
  cmd_next
}

# When the next automatic swap is due, as Unix seconds (0: none).
next_at() {
  (( INTERVAL > 0 )) && [[ ! -f $STATE_DIR/paused ]] || { echo 0; return; }
  local last failed nowifi at
  last=$(cat "$STATE_DIR/last" 2>/dev/null || echo 0)
  failed=$(cat "$STATE_DIR/failed" 2>/dev/null || echo 0)
  nowifi=$(cat "$STATE_DIR/nowifi" 2>/dev/null || echo 0)
  (( last > 0 )) || last=$(( $(date +%s) - INTERVAL * 60 ))
  at=$(( last + INTERVAL * 60 ))
  (( failed + RETRY > at )) && at=$(( failed + RETRY ))
  (( nowifi + RETRY > at )) && at=$(( nowifi + RETRY ))
  echo "$at"
}

cmd_info() {
  local cur='{}' current
  [[ -f $STATE_DIR/current.json ]] && cur=$(cat "$STATE_DIR/current.json")
  # The image may have gone, with a theme change or by hand: then there's none to show.
  current=$(jq -r '.bg // empty' <<< "$cur" 2>/dev/null)
  [[ -n $current && -f $current ]] || cur=$(jq -c 'del(.bg)' <<< "$cur" 2>/dev/null || echo '{}')
  jq -c --argjson next "$(next_at)" \
    --argjson paused "$([[ -f $STATE_DIR/paused ]] && echo true || echo false)" \
    --argjson waitingWifi "$([[ $WIFI_ONLY == true && -f $STATE_DIR/nowifi ]] && echo true || echo false)" \
    --argjson history "$(wc -l 2>/dev/null < "$STATE_DIR/history" || echo 0)" \
    --arg error "$(cat "$STATE_DIR/error" 2>/dev/null)" \
    --arg style "$(sed -n 's/^background[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$STYLE" 2>/dev/null | head -1)" \
    '. + {nextAt: $next, paused: $paused, waitingWifi: $waitingWifi, hasPrevious: ($history >= 2), error: $error,
      shown: (.bg != null and ((.bg | split("/") | last) as $b | $style == $b or ("pinterest-wallswap-" + $style) == $b))}' <<< "$cur"
}

cmd_keep() {
  local bg dest
  bg=$(jq -r '.bg // empty' "$STATE_DIR/current.json" 2>/dev/null)
  [[ -f $bg ]] || die "nothing to keep yet"
  dest="$(dirname -- "$bg")/$(basename -- "$bg" | sed 's/^pinterest-wallswap-//')"
  [[ -e $dest || -L $dest ]] || atomic_write "$dest" < "$bg" || die "couldn't save $dest"
  set_style_background "$(basename -- "$dest")"
  echo "$dest"
}

# --------------------------------------------------------------- main

cmd=${1:-help}
cfg=${2:-'{}'}
jq -e 'type == "object"' >/dev/null 2>&1 <<< "$cfg" || cfg='{}'
SOURCES=(pinterest)
INTERVAL=$(jq -r '.interval // 1440' <<< "$cfg")
QUERY=$(jq -r '.query // ""' <<< "$cfg")
WIFI_ONLY=$(jq -r 'if .wifiOnly == false then false else true end' <<< "$cfg")
THEME=$(jq -r '.theme // ""' <<< "$cfg")
LOCAL_DIR=$(jq -r '.localDir // "~/Pictures/Wallpapers"' <<< "$cfg"); LOCAL_DIR=${LOCAL_DIR/#\~/$HOME}
read -r SCREEN_W SCREEN_H < <(jq -r '(.screen // [1080, 2400]) | map(tostring) | join(" ")' <<< "$cfg")
[[ $INTERVAL =~ ^[0-9]+$ ]] || INTERVAL=1440
[[ $SCREEN_W =~ ^[0-9]+$ && $SCREEN_W -ge 200 && $SCREEN_W -le 8000 ]] || SCREEN_W=1080
[[ $SCREEN_H =~ ^[0-9]+$ && $SCREEN_H -ge 200 && $SCREEN_H -le 8000 ]] || SCREEN_H=2400

for tool in curl jq file magick; do command -v $tool >/dev/null || { log "$tool is required"; exit 1; }; done
private_dir "$CACHE_DIR"
private_dir "$STATE_DIR"

case $cmd in
  next|prev|tick)
    # One swap at a time: lock the private state directory itself.
    exec 9< "$STATE_DIR"
    flock -n 9 || { log "another swap is running"; exit 0; }
    "cmd_$cmd" ;;
  info|keep|pause|resume|toggle) "cmd_$cmd" ;;
  *) sed -n '2,17p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; [[ $cmd == help ]] ;;
esac
