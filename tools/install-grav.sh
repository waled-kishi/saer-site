#!/bin/sh
# One-time Grav 2 install for saer1.rifd-dt.com (run by an hPanel cron job).
# Safe to run every minute: exits immediately once .grav_ok exists.
SITE="$HOME/domains/saer1.rifd-dt.com"
V=2.2.14
cd "$SITE" || exit 1
[ -f .grav_ok ] && exit 0
LOG="$SITE/public_html/log.txt"
{
  echo "start: $(date)"
  echo "pwd: $(pwd)"
  ls -la
  curl -fsSLo g.zip "https://github.com/getgrav/grav/releases/download/$V/grav-admin-v$V.zip" \
    && echo "download ok: $(wc -c < g.zip) bytes" \
    && rm -rf grav-admin \
    && unzip -qo g.zip \
    && echo "unzip ok" \
    && cp -a grav-admin/. public_html/ \
    && echo "copy ok" \
    && rm -rf grav-admin g.zip public_html/default.php \
    && touch .grav_ok \
    && echo "DONE"
  echo "end: $(date)"
} > "$LOG" 2>&1
