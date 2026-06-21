from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_steam_price_heybox.api_clients import (  # noqa: E402
    parse_region_prices,
    parse_steam_details,
)


class ApiClientParserTests(unittest.TestCase):
    def test_parses_steam_app_details(self) -> None:
        details = parse_steam_details(
            123,
            {
                "name": "Test Game",
                "type": "game",
                "is_free": False,
                "price_overview": {
                    "currency": "CNY",
                    "initial": 10000,
                    "final": 6000,
                    "discount_percent": 40,
                },
                "release_date": {"coming_soon": False, "date": "2026 年 1 月 1 日"},
                "developers": ["Developer"],
                "publishers": ["Publisher"],
                "platforms": {"windows": True, "mac": False, "linux": True},
                "genres": [{"description": "角色扮演"}],
                "categories": [{"description": "单人"}, {"description": "Steam 成就"}],
                "supported_languages": (
                    "英语<strong>*</strong>, 简体中文<br><strong>*</strong>音频"
                ),
                "controller_support": "full",
                "achievements": {"total": 42},
                "dlc": [1, 2],
                "metacritic": {"score": 88},
                "recommendations": {"total": 12345},
                "required_age": "16",
                "content_descriptors": {"notes": "暴力<br>成人内容"},
                "website": "https://example.com",
            },
        )

        self.assertEqual(details.price.current, Decimal("60"))
        self.assertEqual(details.price.discount, 40)
        self.assertEqual(details.platforms, ("windows", "linux"))
        self.assertEqual(details.languages, ("英语", "简体中文"))
        self.assertEqual(details.achievement_count, 42)
        self.assertEqual(details.dlc_count, 2)
        self.assertEqual(details.content_notes, "暴力, 成人内容")

    def test_parses_and_deduplicates_region_prices(self) -> None:
        regions = parse_region_prices(
            [
                {"cc": "cn", "name": "中国", "current": "60", "initial": "100", "discount": 40},
                {"cc": "us", "name": "美国", "current": "70", "initial": "70", "discount": 0},
                {"cc": "cn", "name": "重复", "current": "1"},
                {"cc": "", "current": "10"},
            ]
        )

        self.assertEqual([region.code for region in regions], ["CN", "US"])
        self.assertEqual(regions[0].current_rmb, Decimal("60"))


if __name__ == "__main__":
    unittest.main()
