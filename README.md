# saer-site

Theme and custom plugin for the Sheikh Mohammed Saer Al-Shabaan website (Grav 2).

- `theme/` → deployed to `user/themes/saer`
- `plugin/` → deployed to `user/plugins/saer-core`

Content (`user/pages`) is not stored here.
No passwords, keys, or tokens in this repository.

## Layout
- `theme/` — Grav theme `saer` (templates, CSS, local fonts, admin blueprints)
- `content-seed/` — sample pages used to seed and test the site
- `tools/sync.sh` — deploy step run by cron on the server
- `tools/plugins.txt` — pinned third-party plugins installed by `sync.sh`
