# saer-site

Full Grav 2 site for the Sheikh Mohammed Saer Al-Shabaan website, deployed to Hostinger
by hPanel's "Deployment from GitHub" (the repo root becomes `public_html`).

- Grav core + Admin2 + plugins are committed as released (currently Grav 2.2.29). Upgrade by
  committing a newer release (GPM updates inside Admin2 fail on this host).
- `user/themes/saer/` — the site theme.
- `.saer/` — content seed and API seeding script (blocked from the web in `.htaccess`).
- Server-only data (pages, accounts, config, user/data, cache, logs…) is listed in `.gitignore`;
  the deployment preserves those paths, so publishing never touches content.

No passwords, keys or tokens in this repository.
