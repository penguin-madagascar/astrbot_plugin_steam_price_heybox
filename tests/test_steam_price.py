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
from astrbot_plugin_steam_price_heybox.name_correction import (  # noqa: E402
    NameCorrection,
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
)


class FakeSteamClient:
    def __init__(
        self,
        details: SteamGameDetails | Exception | None = None,
        search_results: dict[str, list[dict]] | None = None,
    ) -> None:
        self.details_result = details or game_details()
        self.search_results = search_results
        self.search_calls = []
        self.detail_calls = []

    async def search(self, query: str, country: str, language: str):
        self.search_calls.append((query, country, language))
        if self.search_results is not None:
            return self.search_results.get(query, [])
        return [{"appid": 123, "name": query}]

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


class FakeNameCorrector:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, request):
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("Unexpected name correction call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class SteamPriceServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(
        self,
        steam=None,
        heybox=None,
        corrector=None,
        retry_count=3,
    ) -> SteamPriceService:
        return SteamPriceService(
            steam_client=steam or FakeSteamClient(),
            heybox_client=heybox or FakeHeyboxClient(),
            name_corrector=corrector,
            llm_name_retry_count=retry_count,
            today_provider=lambda: date(2026, 2, 10),
        )

    async def test_summary_contains_price_history_and_region_comparison(self) -> None:
        messages = await self.service().execute("-CN appid=123")

        self.assertEqual(len(messages), 1)
        self.assertIn("Steam 当前价格：¥60", messages[0])
        self.assertIn("历史最低：¥50", messages[0])
        self.assertIn("当前促销", messages[0])
        self.assertIn("最低价区服：乌克兰 / UA", messages[0])

    async def test_history_mode_lists_recent_sale_events(self) -> None:
        messages = await self.service().execute("history -中国 123")

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

    async def test_search_uses_explicit_country_and_preserves_full_name(self) -> None:
        steam = FakeSteamClient()
        await self.service(steam=steam).execute("-US ACE COMBAT™7: SKIES UNKNOWN")

        self.assertEqual(
            steam.search_calls,
            [("ACE COMBAT™7: SKIES UNKNOWN", "US", "schinese")],
        )

    async def test_search_preserves_hyphen_inside_game_name(self) -> None:
        steam = FakeSteamClient()
        await self.service(steam=steam).execute("Half-Life 2")

        self.assertEqual(
            steam.search_calls,
            [("Half-Life 2", "CN", "schinese")],
        )

    async def test_search_preserves_leading_hyphen_after_terminator(self) -> None:
        steam = FakeSteamClient()
        await self.service(steam=steam).execute("-- -US Game Name")

        self.assertEqual(
            steam.search_calls,
            [("-US Game Name", "CN", "schinese")],
        )

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

    async def test_llm_combines_name_and_unknown_country_correction(self) -> None:
        corrector = FakeNameCorrector([NameCorrection("ACE COMBAT™ 7: SKIES UNKNOWN", "SG")])
        steam = FakeSteamClient(
            search_results={
                "ACE COMBAT™ 7: SKIES UNKNOWN": [
                    {"appid": 502500, "name": "ACE COMBAT™ 7: SKIES UNKNOWN"}
                ]
            }
        )

        identity, country = await self.service(
            steam=steam,
            corrector=corrector,
        ).resolve_game("Ace Combat 7", "", "新加坡")

        self.assertEqual(identity.appid, 502500)
        self.assertEqual(country, "SG")
        self.assertEqual(corrector.calls[0].unresolved_country, "新加坡")
        self.assertEqual(
            steam.search_calls,
            [("ACE COMBAT™ 7: SKIES UNKNOWN", "SG", "schinese")],
        )

    async def test_llm_retries_until_a_confident_match(self) -> None:
        corrector = FakeNameCorrector(
            [
                NameCorrection("Wrong Name", "US"),
                NameCorrection("ACE COMBAT™ 7: SKIES UNKNOWN", "US"),
            ]
        )
        steam = FakeSteamClient(
            search_results={
                "ACE COMBAT™ 7: SKIES UNKNOWN": [
                    {"appid": 502500, "name": "ACE COMBAT™ 7: SKIES UNKNOWN"}
                ]
            }
        )

        identity, country = await self.service(
            steam=steam,
            corrector=corrector,
        ).resolve_game("Ace Combat", "US")

        self.assertEqual((identity.appid, country), (502500, "US"))
        self.assertEqual(len(corrector.calls), 2)
        self.assertEqual(corrector.calls[1].failed_names, ("Wrong Name",))

    async def test_llm_retry_count_controls_total_calls(self) -> None:
        for retry_count, expected_calls in ((-2, 1), (0, 1), (3, 4)):
            with self.subTest(retry_count=retry_count):
                corrector = FakeNameCorrector(
                    [NameCorrection(f"Wrong {index}", "CN") for index in range(expected_calls)]
                )
                service = self.service(
                    steam=FakeSteamClient(search_results={}),
                    corrector=corrector,
                    retry_count=retry_count,
                )

                with self.assertRaisesRegex(PriceLookupError, "没有搜索到游戏"):
                    await service.resolve_game("Original Name", "CN")

                self.assertEqual(len(corrector.calls), expected_calls)

    async def test_duplicate_llm_suggestions_are_searched_once(self) -> None:
        corrector = FakeNameCorrector([NameCorrection("Same Guess", "CN")] * 4)
        steam = FakeSteamClient(search_results={})

        with self.assertRaises(PriceLookupError):
            await self.service(steam=steam, corrector=corrector).resolve_game("Original Name", "CN")

        self.assertEqual(len(corrector.calls), 4)
        self.assertEqual(
            [call[0] for call in steam.search_calls].count("Same Guess"),
            1,
        )

    async def test_llm_failure_falls_back_to_original_name(self) -> None:
        corrector = FakeNameCorrector([RuntimeError("provider unavailable")])
        steam = FakeSteamClient()

        identity, country = await self.service(
            steam=steam,
            corrector=corrector,
            retry_count=0,
        ).resolve_game("Original Name", "CN")

        self.assertEqual((identity.appid, country), (123, "CN"))
        self.assertEqual(steam.search_calls[0][0], "Original Name")

    async def test_unknown_country_without_llm_reports_error(self) -> None:
        with self.assertRaisesRegex(PriceLookupError, "无法识别地区：-新加坡"):
            await self.service().resolve_game("Test Game", "", "新加坡")

    async def test_appid_skips_name_correction_for_known_country(self) -> None:
        corrector = FakeNameCorrector([])

        identity, country = await self.service(corrector=corrector).resolve_game("1245620", "CN")

        self.assertEqual((identity.appid, country), (1245620, "CN"))
        self.assertEqual(corrector.calls, [])

    async def test_appid_uses_llm_only_for_unknown_country(self) -> None:
        corrector = FakeNameCorrector([NameCorrection("", "SG")])

        identity, country = await self.service(corrector=corrector).resolve_game(
            "1245620", "", "新加坡"
        )

        self.assertEqual((identity.appid, country), (1245620, "SG"))
        self.assertEqual(len(corrector.calls), 1)


class CommandParserTests(unittest.TestCase):
    def test_hyphen_inside_game_name_is_not_a_country_prefix(self) -> None:
        parsed = parse_command("Half-Life 2")

        self.assertEqual(parsed.country, "CN")
        self.assertEqual(parsed.target, "Half-Life 2")

    def test_non_country_leading_hyphen_is_preserved(self) -> None:
        parsed = parse_command("-Half-Life 2")

        self.assertEqual(parsed.country, "CN")
        self.assertEqual(parsed.target, "-Half-Life 2")

    def test_terminator_disambiguates_country_shaped_game_name(self) -> None:
        parsed = parse_command("-- -US Game Name")

        self.assertEqual(parsed.country, "CN")
        self.assertEqual(parsed.target, "-US Game Name")

    def test_terminator_is_supported_after_country(self) -> None:
        parsed = parse_command("-US -- -Game Name")

        self.assertEqual(parsed.country, "US")
        self.assertEqual(parsed.target, "-Game Name")

    def test_terminator_is_supported_for_non_price_modes(self) -> None:
        for mode in ("regions", "info", "detailed_info"):
            with self.subTest(mode=mode):
                parsed = parse_command(f"{mode} -- -US Game Name")
                self.assertEqual(parsed.mode, mode)
                self.assertEqual(parsed.target, "-US Game Name")

    def test_summary_country_prefix_and_special_characters(self) -> None:
        parsed = parse_command("-us ACE COMBAT™7: SKIES UNKNOWN")

        self.assertEqual(parsed.mode, "summary")
        self.assertEqual(parsed.country, "US")
        self.assertEqual(parsed.target, "ACE COMBAT™7: SKIES UNKNOWN")

    def test_history_uses_formal_chinese_country(self) -> None:
        parsed = parse_command("history -俄罗斯 《艾尔登法环》")

        self.assertEqual(parsed.mode, "history")
        self.assertEqual(parsed.country, "RU")
        self.assertEqual(parsed.target, "《艾尔登法环》")

    def test_defaults_depend_on_mode(self) -> None:
        summary = parse_command("Test Game", "US", "JP")
        history = parse_command("history Test Game", "US", "JP")

        self.assertEqual(summary.country, "US")
        self.assertEqual(history.country, "JP")

    def test_any_two_letter_country_code_is_accepted(self) -> None:
        parsed = parse_command("-id Test Game")

        self.assertEqual(parsed.country, "ID")

    def test_unknown_chinese_country_is_retained_for_llm_resolution(self) -> None:
        parsed = parse_command("-新加坡 Test Game")

        self.assertEqual(parsed.country, "")
        self.assertEqual(parsed.country_token, "新加坡")

    def test_non_price_modes_reject_country_prefix(self) -> None:
        for command in (
            "regions -US Test Game",
            "info -US Test Game",
            "detailed_info -US Test Game",
        ):
            with (
                self.subTest(command=command),
                self.assertRaisesRegex(PriceLookupError, "不支持地区参数"),
            ):
                parse_command(command)

    def test_legacy_trailing_country_is_part_of_name(self) -> None:
        parsed = parse_command("history Test Game CN")

        self.assertEqual(parsed.country, "CN")
        self.assertEqual(parsed.target, "Test Game CN")

    def test_extract_appid(self) -> None:
        self.assertEqual(extract_appid("https://store.steampowered.com/app/730/"), 730)
        self.assertEqual(extract_appid("steam_appid=1245620"), 1245620)
        self.assertEqual(extract_appid("appid 570"), 570)

    def test_candidate_selection_prefers_exact_match(self) -> None:
        selected = choose_steam_candidate(
            "Test Game",
            [
                {"appid": 1, "name": "Test Game Demo"},
                {"appid": 2, "name": "Test Game"},
            ],
        )

        self.assertEqual(selected["appid"], 2)

    def test_candidate_selection_rejects_unrelated_first_result(self) -> None:
        selected = choose_steam_candidate(
            "ACE COMBAT 7",
            [{"appid": 1, "name": "Dandy Ace"}],
        )

        self.assertIsNone(selected)

    def test_candidate_selection_accepts_official_extended_title(self) -> None:
        selected = choose_steam_candidate(
            "Ace Combat 7",
            [
                {"appid": 502500, "name": "ACE COMBAT™ 7: SKIES UNKNOWN"},
                {"appid": 1, "name": "Dandy Ace"},
            ],
        )

        self.assertEqual(selected["appid"], 502500)

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
