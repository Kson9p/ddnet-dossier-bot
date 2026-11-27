# DDNet dossier bot and existing feedback bot

This repository contains **two separate Telegram bot programs**:

- The existing feedback bot stays at the repository root and keeps its original
  entry point, configuration names, database and support workflow.
- The new dossier bot is isolated in [`dossier_bot`](dossier_bot/README.md). It
  has its own entry point, `DOSSIER_*` settings and SQLite database.

## BotHosting with one startup file

Upload the repository to the service and keep `STARTUP_FILE=main.py`. Keep its
existing `BOT_TOKEN`, `OWNER_ID`, and `DATABASE_PATH` values. Add these secret
variables in the same service:

- `DOSSIER_BOT_TOKEN` for the **second** bot account.
- `DOSSIER_OWNER_ID` for the owner's numeric Telegram user ID.
- `DOSSIER_LINK_SECRET` for the signed handoff between the two bots (use the
  same random value of at least 32 characters in both services).
- `DOSSIER_BOT_USERNAME=ddnet_sliv_bot` so the existing bot can link back to it.

`DOSSIER_DATABASE_PATH` is optional and defaults to
`dossier_bot/data/dossiers.db`. Keep both database files on persistent storage.

At startup, the existing bot starts polling first. After Telegram returns its
first successful response to polling, even if there are no new messages,
`main.py` starts the dossier bot in the same Python process. Look for a `[Досье]` log
with the new bot's username and `принимает обновления` before trying `/start`.
Send `/start` to the new bot from the owner's account and from a regular
account to check both menus. Both bots share the Python and aiogram runtime to reduce memory use. Stopping the service stops both bots.

If `DOSSIER_BOT_TOKEN` is absent, this service runs the existing bot alone.
If the dossier task exits, the console shows the error and the existing bot
continues running. Correct the second bot's settings and restart the service.

The Mini App source is in [`web_app`](web_app/README.md). The existing bot
continues to start first; after its first successful polling response, the web
server waits 10 seconds and then serves the Mini App from the same Python
process on the hosting panel's `SERVER_PORT` (or `PORT`). No extra bot process
or package is needed. Make sure the host exposes that port through a public
HTTPS address before setting it as the Telegram Mini App URL. The site currently
uses sample player data; real voting and its weekly change limit still need a
server-side API and database implementation.

## Independent services or terminals

### 1. Start the existing bot

From this repository root, use its existing `.env` and run the following
without any `DOSSIER_BOT_TOKEN` in this service's environment or its copy of
`dossier_bot/.env`:

```powershell
python main.py
```

Check that logs report long polling started. In Telegram, send `/start` to the
existing bot from a regular account and confirm it responds; send `/menu` from
the configured owner account. Keep this process running after it is stable.

### 2. Prepare and start the dossier bot

Create the second bot account with BotFather. In the second service, set its
token and the numeric owner ID in the environment. For local startup you can
use a copy of `dossier_bot/.env.example` at `dossier_bot/.env`:

```dotenv
DOSSIER_BOT_TOKEN=<second bot token>
DOSSIER_OWNER_ID=<numeric Telegram ID>
DOSSIER_DATABASE_PATH=data/dossiers.db
DOSSIER_ABOUT_TEXT=Short configurable description
```

Install its dependencies and start from the repository root in another terminal:

```powershell
python -m venv .venv-dossier
.\.venv-dossier\Scripts\Activate.ps1
pip install -r dossier_bot\requirements.txt
python -m dossier_bot.main
```

For a second service that takes a startup file, set `STARTUP_FILE=dossier_bot/main.py`.
Check the log for the separate dossier bot polling process, then send `/start`
to the new bot. Verify its three menu actions and send a small test dossier to
confirm the moderation card reaches the owner. This is a separate local process;
it does not load the old bot's `BOT_TOKEN`, `OWNER_ID`, or database.

The new bot uses `dossier_bot/data/dossiers.db` by default. Keep that path on
persistent storage on hosting. Do not place the new token in the root `.env`.

To require the existing channel and bot before submitting a dossier, add the
dossier bot as an administrator of `@ddnet_podslushka` (membership checks need
channel admin rights). Set the same `DOSSIER_LINK_SECRET` in both bot services.
The dossier bot checks channel membership itself. To prove that the user started
the existing `@ddnet_podslushka_bot`, that bot sends a short signed return link;
no bot token is shared between services. The channel and source bot usernames
can be changed with `DOSSIER_CHANNEL_USERNAME` and
`DOSSIER_SOURCE_BOT_USERNAME` in the dossier service.

## New dossier bot behavior

- Main menu has exactly **Добавить досье**, **Написать в техподдержку**, and
  **О боте**.
- A user can submit only a dossier about themself: gender/category, exact DDNet
  nickname, description up to 600 characters, and up to 10 optional photos or
  videos. The draft can be reviewed, edited with back/cancel actions, and must
  be confirmed before submission.
- The user confirms that the information and media are about them and that they
  agree to submit them. A moderator reviews every dossier; approval does not
  publish it. The user can withdraw/delete their dossier.
- Dossiers and support arrive in the same owner chat, separately labeled.
  Support replies can be sent through the bot.
- No public catalog, expanded dossier, clan or family details, or Gemini flow.

### DDNet data

The bot calls DDStats' documented `/profile/json?player=<nickname>` endpoint
with a request timeout and URL-encoded nickname. It validates the returned
`name` and `points`, and displays only DDNet ranking points. A missing player,
network error, timeout, or unexpected response shows the unavailable state.
The routes and source are documented in the [DDStats FAQ](https://ddstats.tw/faq).

The exact `@ddnetapp` command mapping remains `/race <nickname>`,
`/kog <nickname>`, and `/ego <nickname>`. KOG's official organization lists a
production API host, but a documented player-stat schema was not found, so KOG
stays unavailable. No documented public Eternal Gores stats API was found.
The bot does not message a private Telegram bot or use a personal session.

## Privacy and configuration

Both processes need separate Telegram tokens and independent polling. Their
databases are separate. The dossier bot reads only `DOSSIER_BOT_TOKEN`,
`DOSSIER_OWNER_ID`, `DOSSIER_DATABASE_PATH`, and `DOSSIER_ABOUT_TEXT` from its
own `.env` or the process environment. Never commit either `.env` file.
