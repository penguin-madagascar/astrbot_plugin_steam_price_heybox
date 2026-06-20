from __future__ import annotations

import unittest

from xiaoheihe_price import (
    XiaoheihePriceService,
    choose_steam_candidate,
    countries_from_text,
    extract_appid,
    steam_lookup_game_query,
    xiaoheihe_format_price_summary,
)


class XiaoheihePriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_formats_history_and_global_prices(self) -> None:
        async def fake_get_json(url, params=None, headers=None):
            if "storesearch" in url:
                return {"items": [{"id": 123, "name": "Test Game"}]}
            if "history" in url:
                return {
                    "status": "ok",
                    "result": {
                        "prices": [
                            {"date": 1700000000, "price": "20", "currency": "UAH", "rmb_price": "4", "discount": 50}
                        ],
                        "lowest_info": {"date": 1700000000, "price": "20", "discount": 50},
                        "lowest_info_v2": {"currency": "UAH", "count": 1},
                    },
                }
            if "global_prices" in url:
                return {
                    "result": {
                        "prices": [
                            {"cc": "cn", "name": "China", "current": "58", "initial": "98", "discount": 40},
                            {"cc": "ua", "name": "Ukraine", "current": "4", "initial": "8", "discount": 50},
                        ]
                    }
                }
            if "mobile" in url:
                return {
                    "result": {
                        "price": {
                            "current": "58",
                            "initial": "98",
                            "lowest_price": "40",
                            "discount": 40,
                        },
                        "heybox_price": {
                            "cost_coin": 5000,
                            "original_coin": 8000,
                        },
                    }
                }
            raise AssertionError(url)

        service = XiaoheihePriceService(http_get_json=fake_get_json)

        result = await service.lookup_text("Test Game 国区")

        self.assertIn("Test Game / appid=123", result)
        self.assertIn("China / CN", result)
        self.assertIn("历史最低", result)
        self.assertIn("小黑盒各区当前价", result)
        self.assertIn("小黑盒商城价 ¥5", result)

    async def test_appid_query_skips_steam_search(self) -> None:
        calls = []

        async def fake_get_json(url, params=None, headers=None):
            calls.append(url)
            if "history" in url:
                return {"status": "ok", "result": {"prices": []}}
            if "global_prices" in url:
                return {"result": {"prices": []}}
            if "mobile" in url:
                return {"result": {}}
            raise AssertionError(url)

        service = XiaoheihePriceService(http_get_json=fake_get_json)

        result = await service.lookup_text("appid=730")

        self.assertIn("appid=730", result)
        self.assertFalse(any("storesearch" in url for url in calls))


class XiaoheihePriceParserTests(unittest.TestCase):
    def test_extract_appid(self) -> None:
        self.assertEqual(extract_appid("https://store.steampowered.com/app/730/"), 730)
        self.assertEqual(extract_appid("steam_appid=1245620"), 1245620)
        self.assertEqual(extract_appid("appid 570"), 570)

    def test_query_cleanup_and_country_parse(self) -> None:
        self.assertEqual(steam_lookup_game_query("帮我查小黑盒价格 艾尔登法环 国区"), "艾尔登法环")
        self.assertEqual(countries_from_text("国区 美区 UA"), ["CN", "US", "UA"])

    def test_candidate_selection_prefers_exact_match(self) -> None:
        selected = choose_steam_candidate(
            "Test Game",
            [
                {"appid": 1, "name": "Test Game Demo"},
                {"appid": 2, "name": "Test Game"},
            ],
        )

        self.assertEqual(selected["appid"], 2)

    def test_mobile_detail_summary(self) -> None:
        lines = xiaoheihe_format_price_summary(
            {
                "price": {"current": "10", "initial": "20", "lowest_price": "5", "is_lowest": True},
                "heybox_price": {
                    "cost_coin": 7000,
                    "coupon_info": {"final_price": "6", "coupon_desc": "券"},
                },
            }
        )

        self.assertEqual(len(lines), 2)
        self.assertIn("当前 ¥10", lines[0])
        self.assertIn("券后 ¥6", lines[1])


if __name__ == "__main__":
    unittest.main()
