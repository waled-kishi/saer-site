#!/bin/sh
# Deploy step for saer1.rifd-dt.com, run by an hPanel cron job every few minutes:
#   sh ~/domains/saer1.rifd-dt.com/public_html/_deploy/tools/sync.sh
# hPanel's Git integration keeps public_html/_deploy in sync with the GitHub repo.
# This script copies the theme and our plugins from there into Grav's user/ folder,
# installs pinned third-party plugins, and clears Grav's cache. It only does work
# when the deployed content changed, so running it every few minutes is cheap.

SITE="$HOME/domains/saer1.rifd-dt.com/public_html"
SRC="$SITE/_deploy"
STATE="$HOME/.saer"
LOG="$STATE/sync.log"
mkdir -p "$STATE"

[ -d "$SRC/theme" ] || exit 0

# Fingerprint of everything we deploy; skip when unchanged.
FP=$(cd "$SRC" && find theme plugins tools -type f 2>/dev/null | sort | xargs cat 2>/dev/null | md5sum | cut -d' ' -f1)
[ "$FP" = "$(cat "$STATE/last_fp" 2>/dev/null)" ] && exit 0

exec >> "$LOG" 2>&1
echo "=== $(date -u '+%Y-%m-%d %H:%M:%S') deploy $FP"

# Replace a directory atomically-ish: copy to .new, then swap.
swap_in() { # $1 = source dir, $2 = target dir
  rm -rf "$2.new" "$2.old"
  cp -a "$1" "$2.new" || { echo "copy failed: $1"; return 1; }
  [ -d "$2" ] && mv "$2" "$2.old"
  mv "$2.new" "$2" && rm -rf "$2.old"
  echo "deployed $(basename "$2")"
}

ok=1
swap_in "$SRC/theme" "$SITE/user/themes/saer" || ok=0

# Our own plugins live in plugins/<name>.
if [ -d "$SRC/plugins" ]; then
  for p in "$SRC"/plugins/*/; do
    [ -d "$p" ] || continue
    n=$(basename "$p")
    swap_in "$p" "$SITE/user/plugins/$n" || ok=0
  done
fi

# Third-party plugins, pinned in tools/plugins.txt.
TMP="$STATE/tmp"
grep -v '^\s*#' "$SRC/tools/plugins.txt" 2>/dev/null | while read -r name ver url; do
  [ -n "$name" ] || continue
  marker="$SITE/user/plugins/$name/.saer-version"
  [ "$(cat "$marker" 2>/dev/null)" = "$ver" ] && continue
  rm -rf "$TMP" && mkdir -p "$TMP"
  if curl -fsSL -o "$TMP/p.zip" "$url" && unzip -q "$TMP/p.zip" -d "$TMP/x"; then
    top=$(find "$TMP/x" -mindepth 1 -maxdepth 1 -type d | head -1)
    echo "$ver" > "$top/.saer-version"
    swap_in "$top" "$SITE/user/plugins/$name"
  else
    echo "plugin $name $ver: download/unzip failed"
  fi
  rm -rf "$TMP"
done

# One-time cleanup of the install log left by tools/install-grav.sh.
rm -f "$SITE/log.txt"

# Clear Grav's cache so new templates/blueprints are picked up.
( cd "$SITE" && php bin/grav clearcache >/dev/null 2>&1 ) && echo "cache cleared"

[ "$ok" = 1 ] && echo "$FP" > "$STATE/last_fp"
echo "done"
