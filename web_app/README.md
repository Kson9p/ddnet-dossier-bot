# DDNet dossier Mini App

The Mini App is served by the dossier bot from the same process and reads the
same SQLite database. It lists only dossiers whose moderation status is
`approved`.

## How publishing works

1. A user submits a dossier to the bot.
2. The dossier is stored in `DOSSIER_DATABASE_PATH` and sent to the owner for
   review.
3. Choosing **Одобрить** changes its status to `approved`.
4. The website API then includes it in `/api/players`; its details are available
   at `/api/players/{id}`.

The browser never receives the Telegram bot token or Telegram user ID. Approved
photos and videos are proxied by the server at `/api/players/{id}/media/{index}`.
Rejecting or deleting a dossier removes it from public API results immediately.

## Hosting

Run `dossier_bot/main.py` as the host startup file. Keep the configured
`DOSSIER_DATABASE_PATH` persistent between restarts. The bot starts the web app
on `SERVER_PORT` (or `PORT`) ten seconds after Telegram polling starts. The
front end uses the same-origin API at `/api` and needs no separate web server.

The site contains no sample player cards. If there are no approved dossiers,
the catalog displays its empty state.
