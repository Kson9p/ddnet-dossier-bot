"""Serve the static Telegram Mini App on the hosting panel's public port."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl

import aiohttp
from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from dossier_bot.store import DossierStore

log = logging.getLogger(__name__)
WEB_APP_DIR = Path(__file__).resolve().parent.parent / "web_app"


def _telegram_owner(init_data: str, bot_token: str, owner_id: int) -> bool:
    """Validate Telegram Mini App initData and match its user to the owner."""
    if not init_data or len(init_data) > 8192:
        return False
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return False
        received_hash = fields.pop("hash")
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = user.get("id") if isinstance(user, dict) else None
        now = int(time.time())
        if now - auth_date > 86_400 or auth_date > now + 60 or type(user_id) is not int:
            return False
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_hash, expected_hash) and user_id == owner_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


async def serve_mini_app_after_polling(
    polling_ready: asyncio.Event | None = None,
    *,
    delay_seconds: int = 10,
    store: DossierStore | None = None,
    bot: Bot | None = None,
    owner_id: int | None = None,
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

    async def admin_session(request: web.Request) -> web.Response:
        is_admin = bool(
            bot is not None
            and owner_id is not None
            and _telegram_owner(
                request.headers.get("X-Telegram-Init-Data", ""), bot.token, owner_id
            )
        )
        return web.json_response({"isAdmin": is_admin}, headers={"Cache-Control": "no-store"})

    async def delete_player(request: web.Request) -> web.Response:
        if store is None or bot is None or owner_id is None:
            raise web.HTTPServiceUnavailable()
        if not _telegram_owner(
            request.headers.get("X-Telegram-Init-Data", ""), bot.token, owner_id
        ):
            raise web.HTTPForbidden()
        try:
            dossier_id = int(request.match_info["player_id"])
        except ValueError:
            raise web.HTTPNotFound() from None
        row = await store.get(dossier_id)
        if row is None or not await store.delete(dossier_id):
            raise web.HTTPNotFound()
        try:
            message_ids = json.loads(row.get("admin_messages_json", "[]"))
        except (TypeError, json.JSONDecodeError):
            message_ids = []
        if isinstance(message_ids, list):
            for message_id in message_ids:
                try:
                    await bot.delete_message(owner_id, int(message_id))
                except (TelegramAPIError, TypeError, ValueError):
                    # The dossier is already removed from the database and public API.
                    pass
        return web.json_response({"deleted": True}, headers={"Cache-Control": "no-store"})

    async def public_record(row: dict, *, summary: bool = False) -> dict:
        try:
            media = json.loads(row.get("media_json", "[]"))
        except (TypeError, json.JSONDecodeError):
            media = []
        if not isinstance(media, list):
            media = []
        media = [item for item in media if isinstance(item, dict) and item.get("type") in {"photo", "video"} and isinstance(item.get("file_id"), str)]
        media_urls = [
            {"type": "image" if item["type"] == "photo" else "video",
             "src": f"/api/players/{row['id']}/media/{index}",
             "poster": (f"/api/players/{row['id']}/media/{index}" if item["type"] == "photo" else "/assets/profile-cover.svg"), "caption": ""}
            for index, item in enumerate(media)
        ]
        photo = next((entry for entry in media_urls if entry["type"] == "image"), None)
        placeholder = "/assets/profile-cover.svg"
        try:
            stats_text = row.get("stats_text", "")
            points_match = re.search(r"DDRaceNetwork:\s*(\d+)\s+очков", stats_text, re.IGNORECASE)
            hours_match = re.search(r"DDNet:\s*([\d.,]+)\s*ч\.", stats_text, re.IGNORECASE)
            points = int(points_match.group(1)) if points_match else None
            hours = int(float(hours_match.group(1).replace(",", "."))) if hours_match else None
        except (TypeError, ValueError):
            points = hours = None
        record = {
            "id": str(row["id"]), "nick": row["nickname"], "initials": row["nickname"][:2].upper(),
            "tagline": "", "description": row["description"], "approved": True,
            "online": False, "currentServer": "", "currentMap": "", "region": "",
            "badges": [], "stats": {"points": points, "globalRank": None, "teamRank": None,
                "hours": hours, "mapsFinished": None, "bestRank": None, "favoriteMap": "",
                "joinedYear": None, "lastSeenHoursAgo": None},
            "avatar": photo["src"] if photo else placeholder,
            "cover": photo["src"] if photo else placeholder,
            "gallery": media_urls,
        }
        if summary:
            record.pop("description")
            record.pop("gallery")
            record["stats"] = {key: record["stats"][key] for key in ("points", "globalRank", "mapsFinished", "hours")}
            record["lastSeenHoursAgo"] = None
        return record

    async def list_players(request: web.Request) -> web.Response:
        if store is None:
            return web.json_response({"items": [], "total": 0, "page": 1, "pageSize": 6, "hasMore": False})
        query = request.query.get("query", "")[:80]
        sort = request.query.get("sort", "default")
        try:
            page = max(1, min(100_000, int(request.query.get("page", "1"))))
            page_size = max(1, min(50, int(request.query.get("pageSize", "6"))))
        except ValueError:
            return web.json_response({"error": "invalid_pagination"}, status=400)
        rows, total = await store.list_approved(query=query, sort=sort, page=page, page_size=page_size)
        items = [await public_record(row, summary=True) for row in rows]
        return web.json_response({"items": items, "total": total, "page": page, "pageSize": page_size, "hasMore": page * page_size < total}, headers={"Cache-Control": "no-store"})

    async def get_player(request: web.Request) -> web.Response:
        if store is None:
            raise web.HTTPNotFound()
        try:
            dossier_id = int(request.match_info["player_id"])
        except ValueError:
            raise web.HTTPNotFound() from None
        row = await store.get(dossier_id)
        if row is None or row.get("status") != "approved":
            raise web.HTTPNotFound()
        return web.json_response(await public_record(row), headers={"Cache-Control": "no-store"})

    async def get_player_media(request: web.Request) -> web.StreamResponse:
        if store is None or bot is None:
            raise web.HTTPNotFound()
        try:
            dossier_id, index = int(request.match_info["player_id"]), int(request.match_info["media_index"])
        except ValueError:
            raise web.HTTPNotFound() from None
        row = await store.get(dossier_id)
        if row is None or row.get("status") != "approved":
            raise web.HTTPNotFound()
        try:
            items = json.loads(row.get("media_json", "[]"))
            item = items[index]
            if item.get("type") not in {"photo", "video"} or not isinstance(item.get("file_id"), str):
                raise IndexError
            telegram_file = await bot.get_file(item["file_id"])
        except (TypeError, ValueError, IndexError, KeyError, json.JSONDecodeError):
            raise web.HTTPNotFound() from None
        if not telegram_file.file_path:
            raise web.HTTPNotFound()
        url = f"https://api.telegram.org/file/bot{bot.token}/{telegram_file.file_path}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
            async with session.get(url) as upstream:
                if upstream.status != 200:
                    raise web.HTTPBadGateway()
                content_type = "video/mp4" if item["type"] == "video" else upstream.headers.get("Content-Type", "image/jpeg")
                response = web.StreamResponse(status=200, headers={"Content-Type": content_type, "Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})
                if upstream.content_length is not None:
                    response.content_length = upstream.content_length
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await response.write(chunk)
                await response.write_eof()
                return response

    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_APP_DIR / "index.html", headers={"Cache-Control": "no-store"})

    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/api/players", list_players)
    app.router.add_get("/api/players/{player_id}/media/{media_index}", get_player_media)
    app.router.add_get("/api/players/{player_id}", get_player)
    app.router.add_get("/api/admin/session", admin_session)
    app.router.add_delete("/api/players/{player_id}", delete_player)
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
