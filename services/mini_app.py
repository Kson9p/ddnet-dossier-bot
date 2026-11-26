"""Serve the static Telegram Mini App on the hosting panel's public port."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web

log = logging.getLogger(__name__)
WEB_APP_DIR = Path(__file__).resolve().parent.parent / "web_app"


async def serve_mini_app_after_polling(
    polling_ready: asyncio.Event | None = None,
    *,
    delay_seconds: int = 10,
) -> None:
    """Start serving 10 seconds after Telegram polling is known to be ready."""
    if polling_ready is not None:
        await polling_ready.wait()
    log.info("Mini App запустится через %s сек.", delay_seconds)
    await asyncio.sleep(delay_seconds)

    raw_port = os.getenv("SERVER_PORT", "").strip() or os.getenv("PORT", "").strip()
    try:
        port = int(raw_port)
        if not 1 <= port <= 65_535:
            raise ValueError
    except ValueError:
        log.error("Mini App не запущен: хостинг не передал корректный SERVER_PORT.")
        return

    if not (WEB_APP_DIR / "index.html").is_file():
        log.error("Mini App не запущен: web_app/index.html не найден.")
        return

    app = web.Application()

    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_APP_DIR / "index.html")

    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    # Keep developer notes and local tools out of the public route.
    app.router.add_static("/css/", WEB_APP_DIR / "css", show_index=False)
    app.router.add_static("/js/", WEB_APP_DIR / "js", show_index=False)
    app.router.add_static("/assets/", WEB_APP_DIR / "assets", show_index=False)

    runner = web.AppRunner(app, access_log=None)
    try:
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()
    except (OSError, ValueError) as exc:
        log.error(
            "Mini App не запущен (%s); бот продолжает работать.",
            type(exc).__name__,
        )
        await runner.cleanup()
        return

    log.info("Mini App запущен на порту %s.", port)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
