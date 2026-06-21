from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_steam_price_heybox.models import (  # noqa: E402
    RegionPrice,
    SteamGameDetails,
    SteamPrice,
)
from astrbot_plugin_steam_price_heybox.price_analysis import (  # noqa: E402
    parse_price_history,
)
from astrbot_plugin_steam_price_heybox.steam_price import (  # noqa: E402
    PriceLookupError,
    SteamPriceService,
    choose_steam_candidate,
    extract_appid,
    format_current_price,
    parse_command,
    steam_lookup_game_query,
)


class FakeSteamClient:
    def __init__(self, details: SteamGameDetails | Exception | None = None) -> None:
        self.details_result = details or game_details()
        self.search_calls = []
        self.detail_calls = []

    async def search(self, query: str, country: str, language: str):
        self.search_calls.append((query, country, language))
        return [{"appid": 123, "name": "Test Game"}]

    async def details(self, appid: int, country: str, language: str):
        self.detail_calls.append((appid, country, language))
        if isinstance(self.details_result, Exception):
            raise self.details_result
        return self.details_result


class FakeHeyboxClient:
    def __init__(self, history=None, regions=None) -> None:
        self.history = history if history is not None else history_payload()
        self.regions = regions if regions is not None else region_prices()
        self.history_calls = []
        self.global_calls = []

    async def price_history(self, appid: int, country: str, days: int):
        self.history_calls.append((appid, country, days))
        if isinstance(self.history, Exception):
            raise self.history
        return self.history

    async def global_prices(self, appid: int):
        self.global_calls.append(appid)
        if isinstance(self.regions, Exception):
            raise self.regions
        return self.regions


class SteamPriceServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self, steam=None, heybox=None) -> SteamPriceService:
        return SteamPriceService(
            steam_client=steam or FakeSteamClient(),
            heybox_client=heybox or FakeHeyboxClient(),
            today_provider=lambda: date(2026, 2, 10),
        )

    async def test_summary_contains_price_history_and_region_comparison(self) -> None:
        messages = await self.service().execute("appid=123 CN")

        self.assertEqual(len(messages), 1)
        self.assertIn("Steam 当前价格：¥60", messages[0])
        self.assertIn("历史最低：¥50", messages[0])
        self.assertIn("当前促销", messages[0])
        self.assertIn("最低价区服：乌克兰 / UA", messages[0])

    async def test_history_mode_lists_recent_sale_events(self) -> None:
        messages = await self.service().execute("history 123 国区")

        self.assertIn("2 次促销", messages[0])
        self.assertIn("最近 2 次促销", messages[0])
        self.assertIn("进行中", messages[0])

    async def test_regions_mode_sorts_prices_and_uses_china_baseline(self) -> None:
        messages = await self.service().execute("regions 123")

        self.assertLess(messages[0].index("乌克兰 / UA"), messages[0].index("中国 / CN"))
        self.assertIn("比国区省约", messages[0])

    async def test_info_and_detailed_info_are_layered(self) -> None:
        info = await self.service().execute("info 123")
        detailed = await self.service().execute("detailed_info 123")

        self.assertEqual(len(info), 1)
        self.assertNotIn("Steam 扩展资料", info[0])
        self.assertEqual(len(detailed), 2)
        self.assertIn("Steam 基本资料", detailed[0])
        self.assertIn("Steam 扩展资料", detailed[1])
        self.assertIn("Metacritic：88", detailed[1])

    async def test_appid_query_skips_search(self) -> None:
        steam = FakeSteamClient()
        await self.service(steam=steam).execute("123")

        self.assertEqual(steam.search_calls, [])

    async def test_summary_falls_back_to_history_when_steam_fails(self) -> None:
        steam = FakeSteamClient(RuntimeError("Steam unavailable"))
        messages = await self.service(steam=steam).execute("123")

        self.assertIn("小黑盒最新价格", messages[0])

    async def test_summary_fails_when_both_price_sources_fail(self) -> None:
        steam = FakeSteamClient(RuntimeError("Steam unavailable"))
        heybox = FakeHeyboxClient(history=RuntimeError("Heybox unavailable"))

        with self.assertRaisesRegex(PriceLookupError, "均暂时不可用"):
            await self.service(steam=steam, heybox=heybox).execute("123")

    async def test_empty_query_reports_usage(self) -> None:
        with self.assertRaisesRegex(PriceLookupError, "/steamprice detailed_info"):
            await self.service().execute("")


class CommandParserTests(unittest.TestCase):
    def test_modes_and_country(self) -> None:
        parsed = parse_command("detailed_info 艾尔登法环 美区")

        self.assertEqual(parsed.mode, "detailed_info")
        self.assertEqual(parsed.country, "US")
        self.assertEqual(parsed.target, "艾尔登法环 美区")

    def test_extract_appid(self) -> None:
        self.assertEqual(extract_appid("https://store.steampowered.com/app/730/"), 730)
        self.assertEqual(extract_appid("steam_appid=1245620"), 1245620)
        self.assertEqual(extract_appid("appid 570"), 570)

    def test_query_cleanup(self) -> None:
        self.assertEqual(
            steam_lookup_game_query("帮我查 Steam 价格 艾尔登法环 国区"),
            "艾尔登法环",
        )
        self.assertEqual(steam_lookup_game_query("Stardew Valley CN"), "Stardew Valley")

    def test_candidate_selection_prefers_exact_match(self) -> None:
        selected = choose_steam_candidate(
            "Test Game",
            [
                {"appid": 1, "name": "Test Game Demo"},
                {"appid": 2, "name": "Test Game"},
            ],
        )

        self.assertEqual(selected["appid"], 2)

    def test_free_and_unreleased_price_labels(self) -> None:
        free_game = replace(game_details(), is_free=True, price=None)
        unreleased_game = replace(
            game_details(),
            coming_soon=True,
            release_date="即将推出",
            price=None,
        )
        empty_history = parse_price_history({})

        self.assertEqual(format_current_price(free_game, empty_history), "Steam 当前价格：免费")
        self.assertEqual(
            format_current_price(unreleased_game, empty_history),
            "Steam 当前价格：尚未发售",
        )


def game_details() -> SteamGameDetails:
    return SteamGameDetails(
        appid=123,
        name="Test Game",
        game_type="game",
        is_free=False,
        coming_soon=False,
        release_date="2026 年 1 月 1 日",
        price=SteamPrice(Decimal("60"), Decimal("100"), "CNY", 40),
        developers=("Developer",),
        publishers=("Publisher",),
        platforms=("windows", "linux"),
        genres=("角色扮演",),
        categories=("单人", "Steam 成就"),
        languages=("简体中文", "英语"),
        controller_support="full",
        achievement_count=42,
        dlc_count=2,
        metacritic_score=88,
        recommendation_count=12345,
        required_age="16",
        content_notes="暴力内容",
        website="https://example.com",
    )


def history_payload() -> dict:
    return {
        "prices": [
            history_point("2026-01-01", "100", 0),
            history_point("2026-01-10", "50", 50),
            history_point("2026-01-20", "100", 0),
            history_point("2026-02-01", "50", 50),
        ],
        "lowest_info": {"date": "2026-01-10", "price": "50", "discount": 50},
        "lowest_info_v2": {"currency": "CNY"},
    }


def history_point(recorded_on: str, price: str, discount: int) -> dict:
    return {
        "date": recorded_on,
        "price": price,
        "rmb_price": price,
        "currency": "CNY",
        "discount": discount,
    }


def region_prices() -> list[RegionPrice]:
    return [
        RegionPrice("CN", "中国", Decimal("60"), Decimal("100"), 40),
        RegionPrice("UA", "乌克兰", Decimal("40"), Decimal("80"), 50),
        RegionPrice("US", "美国", Decimal("70"), Decimal("70"), 0),
    ]


if __name__ == "__main__":
    unittest.main()
