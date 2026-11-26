from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp


@dataclass(frozen=True, slots=True)
class StatsResult:
    available: bool
    text: str


class DdnetStatsProvider:
    profile_url = "https://ddstats.tw/profile/json"
    playtime_url = "https://ddnet.org/players/"
    ego_profile_url = "https://eternal-gores.com/profile/{nickname}.json"
    live_servers_url = "https://master1.ddnet.org/ddnet/15/servers.json"
    request_timeout_seconds = 8
    live_cache_seconds = 60
    live_response_max_bytes = 16 * 1024 * 1024

    def __init__(self) -> None:
        self._ego_servers: list[tuple[str, str, frozenset[str]]] = []
        self._ego_servers_expires_at = 0.0
        self._ego_servers_lock = asyncio.Lock()

    @staticmethod
    def commands(nickname: str) -> tuple[str, str, str]:
        return (f"/race {nickname}", f"/kog {nickname}", f"/ego {nickname}")

    async def _get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        params: dict[str, str] | None = None,
        max_bytes: int = 65_536,
    ) -> object | None:
        try:
            async with session.get(url, params=params) as response:
                if response.status != 200 or response.content_type != "application/json":
                    return None
                body = await response.content.read(max_bytes + 1)
                if len(body) > max_bytes:
                    return None
                return json.loads(body)
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    async def _get_ego_servers(
        self, session: aiohttp.ClientSession
    ) -> list[tuple[str, str, frozenset[str]]] | None:
        now = time.monotonic()
        if now < self._ego_servers_expires_at:
            return self._ego_servers

        async with self._ego_servers_lock:
            now = time.monotonic()
            if now < self._ego_servers_expires_at:
                return self._ego_servers
            payload = await self._get_json(
                session, self.live_servers_url, max_bytes=self.live_response_max_bytes
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("servers"), list):
                return None

            servers: list[tuple[str, str, frozenset[str]]] = []
            for entry in payload["servers"]:
                if not isinstance(entry, dict):
                    continue
                info = entry.get("info")
                if not isinstance(info, dict):
                    continue
                server_name = info.get("name")
                if not isinstance(server_name, str) or "eternal-gores.com" not in server_name.casefold():
                    continue
                map_info = info.get("map")
                map_name = map_info.get("name") if isinstance(map_info, dict) else None
                clients = info.get("clients")
                if not isinstance(clients, list):
                    clients = []
                players = frozenset(
                    client["name"].strip().casefold()
                    for client in clients
                    if isinstance(client, dict)
                    and client.get("is_player") is True
                    and isinstance(client.get("name"), str)
                    and client["name"].strip()
                )
                servers.append((server_name, map_name if isinstance(map_name, str) else "", players))

            self._ego_servers = servers
            self._ego_servers_expires_at = time.monotonic() + self.live_cache_seconds
            return self._ego_servers

    async def _ego_live_status(self, session: aiohttp.ClientSession, nickname: str) -> str:
        servers = await self._get_ego_servers(session)
        if servers is None:
            return "Eternal Gores: текущий статус серверов недоступен."
        matches = [
            (server_name, map_name)
            for server_name, map_name, players in servers
            if nickname.casefold() in players
        ]
        if not matches:
            return "Eternal Gores: сейчас не найден среди игроков на серверах EGO."
        locations = [
            f"{server_name} — карта {map_name}" if map_name else server_name
            for server_name, map_name in matches[:3]
        ]
        suffix = " (совпадение по нику)" if len(matches) > 1 else ""
        return f"Eternal Gores: сейчас играет: {'; '.join(locations)}.{suffix}"

    async def fetch(self, nickname: str) -> StatsResult:
        nickname = nickname.strip()
        if not nickname:
            return StatsResult(False, "Статистика недоступна: ник не указан.")

        unavailable_points = "DDRaceNetwork: очки сейчас недоступны."
        unavailable_hours = "DDNet: часы за последние 365 дней недоступны."
        unavailable_ego = "Eternal Gores: профиль не найден или статистика недоступна."
        points_text = unavailable_points
        hours_text = unavailable_hours
        ego_text = unavailable_ego
        points_available = hours_available = ego_available = False
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "DDNetDossierBot/1.0 (+public profile lookup)"},
        ) as session:
            profile = await self._get_json(session, self.profile_url, params={"player": nickname})
            if isinstance(profile, dict):
                name, points = profile.get("name"), profile.get("points")
                if (isinstance(name, str) and name.casefold() == nickname.casefold()
                        and type(points) is int and points >= 0):
                    points_text = f"DDRaceNetwork: {points} очков рейтинга по данным DDStats."
                    points_available = True

            playtime = await self._get_json(
                session, self.playtime_url, params={"json2": nickname}
            )
            if isinstance(playtime, dict):
                name = playtime.get("player")
                hours = playtime.get("hours_played_past_365_days")
                if (isinstance(name, str) and name.casefold() == nickname.casefold()
                        and type(hours) in (int, float) and hours >= 0):
                    hours_text = f"DDNet: {hours:g} ч. за последние 365 дней."
                    hours_available = True

            encoded_nickname = quote(nickname, safe="")
            ego_url = self.ego_profile_url.format(nickname=encoded_nickname)
            ego_profile = await self._get_json(session, ego_url, max_bytes=262_144)
            if isinstance(ego_profile, dict):
                returned_name = ego_profile.get("player")
                if isinstance(returned_name, str) and returned_name.casefold() == nickname.casefold():
                    ego_points = ego_profile.get("points")
                    ego_points = ego_points if isinstance(ego_points, dict) else {}
                    parts: list[str] = []
                    score, rank = ego_points.get("points"), ego_points.get("rank")
                    if type(score) is int and score >= 0:
                        parts.append(f"{score} очков")
                    if type(rank) is int and rank > 0:
                        parts.append(f"место #{rank}")

                    favorite_server = ego_profile.get("favorite_server")
                    if isinstance(favorite_server, dict):
                        server_name = favorite_server.get("name")
                        if isinstance(server_name, str) and server_name.strip():
                            parts.append(f"любимый сервер: {server_name.strip()}")

                    finishes = ego_profile.get("last_finishes")
                    if isinstance(finishes, list) and finishes and isinstance(finishes[0], dict):
                        last_map = finishes[0].get("map_name")
                        if isinstance(last_map, str) and last_map.strip():
                            parts.append(f"последнее прохождение: {last_map.strip()}")

                    ego_text = (
                        "Eternal Gores: " + "; ".join(parts) + "."
                        if parts
                        else "Eternal Gores: профиль найден, публичная статистика пока отсутствует."
                    )
                    ego_available = True

            ego_live_text = await self._ego_live_status(session, nickname)
            if "недоступен" not in ego_live_text:
                ego_available = True
            ego_text = f"{ego_text}\n{ego_live_text}"

        return StatsResult(
            points_available or hours_available or ego_available,
            f"{points_text}\n{hours_text}\n{ego_text}",
        )
