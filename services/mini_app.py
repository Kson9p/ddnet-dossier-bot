"""Serve the static Telegram Mini App on the hosting panel's public port."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiohttp import web

from dossier_bot.store import DossierStore
from services.dossier_verification import verify_proof

log = logging.getLogger(__name__)
WEB_APP_DIR = Path(__file__).resolve().parent.parent / "web_app"


def _telegram_user_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram Mini App initData and return its signed user data."""
    if not init_data or len(init_data) > 8192:
        return None
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return None
        received_hash = fields.pop("hash")
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = user.get("id") if isinstance(user, dict) else None
        now = int(time.time())
        if now - auth_date > 86_400 or auth_date > now + 60 or type(user_id) is not int:
            return None
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return user if hmac.compare_digest(received_hash, expected) else None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _telegram_user_id(init_data: str, bot_token: str) -> int | None:
    user = _telegram_user_data(init_data, bot_token)
    user_id = user.get("id") if user else None
    return user_id if type(user_id) is int else None


def _telegram_owner(init_data: str, bot_token: str, owner_id: int) -> bool:
    return _telegram_user_id(init_data, bot_token) == owner_id


def _vote_key(bot_token: str, user_id: int) -> str:
    return hmac.new(
        bot_token.encode(), f"dossier-voter:{user_id}".encode(), hashlib.sha256
    ).hexdigest()


async def serve_mini_app_after_polling(
    polling_ready: asyncio.Event | None = None,
    *,
    delay_seconds: int = 10,
    store: DossierStore | None = None,
    bot: Bot | None = None,
    owner_id: int | None = None,
    link_secret: str = "",
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

    async def source_bot_verification(request: web.Request) -> web.Response:
        if store is None or not link_secret:
            raise web.HTTPServiceUnavailable()
        if request.content_length is not None and request.content_length > 1024:
            return web.json_response({"error": "payload_too_large"}, status=413)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError, aiohttp.ClientError):
            return web.json_response({"error": "invalid_json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "invalid_payload"}, status=400)
        user_id = payload.get("user_id")
        proof = payload.get("proof")
        if type(user_id) is not int or user_id <= 0 or not isinstance(proof, str):
            return web.json_response({"error": "invalid_payload"}, status=400)
        verified = verify_proof(link_secret, proof, user_id)
        if verified is None:
            return web.json_response({"error": "invalid_proof"}, status=403)
        if not await store.accept_source_bot_proof(user_id, *verified):
            return web.json_response({"error": "challenge_expired"}, status=409)
        if bot is not None:
            try:
                await bot.send_message(
                    user_id,
                    "✅ Бот «Подслушка» подтверждён. Теперь вернись в это сообщение и нажми «Проверить подписку».",
                )
            except TelegramAPIError as exc:
                log.warning("Verification notice not delivered (%s).", type(exc).__name__)
        return web.json_response({"verified": True}, headers={"Cache-Control": "no-store"})

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

    async def cast_vote(request: web.Request) -> web.Response:
        if store is None or bot is None:
            raise web.HTTPServiceUnavailable()
        user_id = _telegram_user_id(
            request.headers.get("X-Telegram-Init-Data", ""), bot.token
        )
        if user_id is None:
            return web.json_response({"error": "telegram_auth_required"}, status=401)
        try:
            dossier_id = int(request.match_info["player_id"])
        except ValueError:
            raise web.HTTPNotFound() from None
        row = await store.get(dossier_id)
        if row is None or row.get("status") != "approved":
            raise web.HTTPNotFound()
        if request.content_length is not None and request.content_length > 256:
            return web.json_response({"error": "payload_too_large"}, status=413)
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError, aiohttp.ClientError):
            return web.json_response({"error": "invalid_json"}, status=400)
        score = payload.get("score") if isinstance(payload, dict) else None
        if type(score) is not int or not 1 <= score <= 7:
            return web.json_response({"error": "invalid_score"}, status=400)
        voter_key = _vote_key(bot.token, user_id)
        user_data = _telegram_user_data(
            request.headers.get("X-Telegram-Init-Data", ""), bot.token
        ) or {}
        display_name = " ".join(
            part.strip() for part in (user_data.get("first_name"), user_data.get("last_name"))
            if isinstance(part, str) and part.strip()
        )[:120] or "Пользователь Telegram"
        username = user_data.get("username")
        if not isinstance(username, str):
            username = None
        else:
            username = username.removeprefix("@").strip()[:64] or None
        if username is None:
            try:
                chat = await bot.get_chat(user_id)
                chat_username = getattr(chat, "username", None)
                username = chat_username.strip()[:64] or None if isinstance(chat_username, str) else None
            except TelegramAPIError:
                # initData remains the trusted identity; the public username is optional.
                pass
        outcome = await store.cast_vote(
            dossier_id, voter_key, score, telegram_user_id=user_id,
            username=username, display_name=display_name,
        )
        rating = await store.get_vote_summary(dossier_id, voter_key)
        return web.json_response(
            {"outcome": outcome, "rating": rating},
            headers={"Cache-Control": "no-store"},
        )

    async def admin_player_votes(request: web.Request) -> web.Response:
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
        if row is None or row.get("status") != "approved":
            raise web.HTTPNotFound()
        scores = await store.get_vote_breakdown(dossier_id)
        return web.json_response({"scores": scores}, headers={"Cache-Control": "no-store"})

    async def public_record(
        row: dict, *, summary: bool = False, voter_key: str | None = None
    ) -> dict:
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
            "id": str(row["id"]), "nick": row["nickname"], "gender": row.get("gender", ""), "initials": row["nickname"][:2].upper(),
            "tagline": "", "description": row["description"], "approved": True,
            "online": False, "currentServer": "", "currentMap": "", "region": "",
            "badges": [], "stats": {"points": points, "globalRank": None, "teamRank": None,
                "hours": hours, "mapsFinished": None, "bestRank": None, "favoriteMap": "",
                "joinedYear": None, "lastSeenHoursAgo": None},
            "cover": photo["src"] if photo else placeholder,
            "gallery": media_urls,
        }
        if summary:
            record.pop("description")
            record.pop("gallery")
            record["stats"] = {key: record["stats"][key] for key in ("points", "globalRank", "mapsFinished", "hours")}
            record["lastSeenHoursAgo"] = None
            if store is not None:
                record["rating"] = await store.get_vote_summary(int(row["id"]))
        else:
            record.pop("gender", None)
            if store is not None:
                record["rating"] = await store.get_vote_summary(
                    int(row["id"]), voter_key
                )
        return record

    async def list_players(request: web.Request) -> web.Response:
        if store is None:
            return web.json_response({"items": [], "total": 0, "page": 1, "pageSize": 6, "hasMore": False})
        query = request.query.get("query", "")[:80]
        gender = request.query.get("gender", "")
        if gender not in {"boy", "girl"}:
            gender = ""
        sort = request.query.get("sort", "default")
        try:
            page = max(1, min(100_000, int(request.query.get("page", "1"))))
            page_size = max(1, min(50, int(request.query.get("pageSize", "6"))))
        except ValueError:
            return web.json_response({"error": "invalid_pagination"}, status=400)
        rows, total = await store.list_approved(query=query, gender=gender, sort=sort, page=page, page_size=page_size)
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
        user_id = _telegram_user_id(
            request.headers.get("X-Telegram-Init-Data", ""), bot.token if bot else ""
        )
        voter_key = _vote_key(bot.token, user_id) if bot is not None and user_id is not None else None
        return web.json_response(
            await public_record(row, voter_key=voter_key),
            headers={"Cache-Control": "no-store"},
        )

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
    app.router.add_post("/api/players/{player_id}/vote", cast_vote)
    app.router.add_get("/api/admin/players/{player_id}/votes", admin_player_votes)
    app.router.add_get("/api/admin/session", admin_session)
    app.router.add_post("/api/verification/source-bot", source_bot_verification)
    app.router.add_delete("/api/players/{player_id}", delete_player)
    # Keep developer notes and local tools out of the public route.
    # Revalidate static files after deployments; Telegram WebViews may otherwise
    # keep an old stylesheet while the HTML has already updated.
    @web.middleware
    async def revalidate_static(request: web.Request, handler):
        response = await handler(request)
        if request.path.startswith(("/css/", "/js/", "/assets/")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    app.middlewares.append(revalidate_static)
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
