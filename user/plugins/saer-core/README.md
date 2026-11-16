# saer-core

Site plugin for saer1.rifd-dt.com.

- **Downloads**: the theme's `book_files()` links every chosen file to `/dl/{id}`. The id is stable per
  (page route, filename) in the `files` table. `/dl/{id}` shows the form (per book `download_form`:
  off / optional / required, default from this plugin's config), records the download and streams the
  file. After the form, a cookie (`saer_dl`, 30 days) skips the form for later downloads, and each later
  download is still linked to the same answers. Direct access to PDF/EPUB/ZIP under user/pages is blocked
  in .htaccess so every download is counted.
- **Statistics**: page views recorded on shutdown (GET, 200, not bots or prefetch). No IP or user agent
  is stored; a visitor is an HMAC of (day, IP, UA) with a server secret, so uniques are per day.
  Country from DB-IP Lite (data/dbip-country-lite.mmdb, refreshed monthly by .github/workflows/geo-db.yml,
  CC BY 4.0 — "IP Geolocation by DB-IP") or a CDN country header when present.
- **Admin2**: sidebar item "الإحصائيات" (component page `admin-next/pages/saer-core.js`), dashboard widget
  (`admin-next/widgets/saer-core.js`), API under `/api/v1/saer-core/*` (needs `api.system.read`).
- Data: `user/data/saer-core/saer.sqlite` (+ `secret`). Not in the repository.

Bundled: MaxMind DB Reader (lib/MaxMind, Apache-2.0).
