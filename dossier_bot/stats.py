from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import aiohttp


@dataclass(frozen=True, slots=True)
class StatsResult:
    available: bool
    text: str


class DdnetStatsProvider:
    profile_url = "https://ddstats.tw/profile/json"
    request_timeout_seconds = 8

    @staticmethod
    def commands(nickname: str) -> tuple[str, str, str]:
        return (f"/race {nickname}", f"/kog {nickname}", f"/ego {nickname}")

    async def fetch(self, nickname: str) -> StatsResult:
        unavailable = (
            "DDraceNetwork: статистика сейчас недоступна.\n"
            "KOG: недоступно (нет подтверждённой схемы публичного API).\n"
            "Eternal Gores: недоступно (публичный API не найден)."
        )
        if not nickname.strip():
            return StatsResult(False, unavailable)

        try:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "DDNetDossierBot/1.0 (+public profile lookup)"},
            ) as session:
                async with session.get(self.profile_url, params={"player": nickname}) as response:
                    if response.status == 404:
                        return StatsResult(
                            False,
                            "DDraceNetwork: ник не найден в DDStats.\n"
                            "KOG: недоступно (нет подтверждённой схемы публичного API).\n"
                            "Eternal Gores: недоступно (публичный API не найден).",
                        )
                    if response.status != 200 or response.content_type != "application/json":
                        return StatsResult(False, unavailable)
                    body = await response.content.read(65_537)
                    if len(body) > 65_536:
                        return StatsResult(False, unavailable)
                    profile = json.loads(body)
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            return StatsResult(False, unavailable)

        if not isinstance(profile, dict):
            return StatsResult(False, unavailable)
        name, points = profile.get("name"), profile.get("points")
        if (not isinstance(name, str) or name.casefold() != nickname.casefold()
                or type(points) is not int or points < 0):
            return StatsResult(False, unavailable)
        return StatsResult(
            True,
            f"DDraceNetwork: {points} очков рейтинга по данным DDStats.\n"
            "KOG: недоступно (нет подтверждённой схемы публичного API).\n"
            "Eternal Gores: недоступно (публичный API не найден).",
        )
