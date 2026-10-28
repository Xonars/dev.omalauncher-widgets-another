# One-time onboarding project; never copy a user's projects or signing material.
starter_app() {
  local marker=$DATA/.starter-v1 slug=hello-world d=$APPS/hello-world LOG=$SLOG
  [ ! -e "$marker" ] || return 0
  # A prior partial attempt may be retried, but never adopt or overwrite another project.
  if [ -L "$d" ]; then
    touch "$marker"; return 0
  elif [ -d "$d" ]; then
    jq -e '.starter == true' "$d/.apkmaker.json" >/dev/null 2>&1 || { touch "$marker"; return 0; }
  else
    local entry
    for entry in "$APPS"/* "$APPS"/.[!.]* "$APPS"/..?*; do
      [ ! -e "$entry" ] || { touch "$marker"; return 0; }
    done
    local stage
    stage=$(mktemp -d "$CACHE/.starter.XXXX") || return 1
    (
      trap 'rm -rf "$stage"' EXIT
      local APPS=$stage
      list_apps() { :; }
      scaffold "$slug" &&
      cp "$DATA/bin/HelloWorld.kt" "$APPS/$slug/app/src/main/java/com/apkmaker/hello_world/MainActivity.kt" &&
      printf '<resources><string name="app_name">Hello World</string></resources>\n' > "$APPS/$slug/app/src/main/res/values/strings.xml" &&
      meta "$slug" '.starter=true | .label="Hello World"' &&
      save "$slug" 'Add Hello World starter' &&
      mv -T "$APPS/$slug" "$d"
    ) || return 1
  fi
  do_build "$slug" || { meta "$slug" '.status="failed" | .outcomes.build="failed"'; return 1; }
  meta "$slug" '.status="ready"' || return 1
  touch "$marker"
}
