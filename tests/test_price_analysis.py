from __future__ import annotations

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_steam_price_heybox.price_analysis import (  # noqa: E402
    parse_history_date,
    parse_price_history,
)


class PriceAnalysisTests(unittest.TestCase):
    def test_builds_completed_and_active_sales(self) -> None:
        history = parse_price_history(
            {
                "prices": [
                    point("2026-01-01", "100", 0),
                    point("2026-01-02", "80", 20),
                    point("2026-01-05", "70", 30),
                    point("2026-01-08", "100", 0),
                    point("2026-02-01", "60", 40),
                    point("2026-02-03", "50", 50),
                ],
                "lowest_info": {"date": "2026-02-03", "price": "50", "discount": 50},
                "lowest_info_v2": {"currency": "CNY"},
            }
        )

        self.assertEqual(len(history.events), 2)
        self.assertEqual(history.events[0].ended_on, date(2026, 1, 8))
        self.assertEqual(history.events[0].maximum_discount, 30)
        self.assertEqual(history.events[0].lowest_price, Decimal("70"))
        self.assertIsNone(history.events[1].ended_on)
        self.assertEqual(history.events[1].maximum_discount, 50)
        self.assertEqual(history.active_sale, history.events[1])

    def test_counts_separate_lowest_price_periods(self) -> None:
        history = parse_price_history(
            {
                "prices": [
                    point("2026-01-01", "100", 0),
                    point("2026-01-02", "50", 50),
                    point("2026-01-03", "50", 50),
                    point("2026-01-04", "100", 0),
                    point("2026-02-01", "50", 50),
                ],
                "lowest_info": {"date": "2026-01-02", "price": "50", "discount": 50},
                "lowest_info_v2": {"currency": "CNY", "count": 999},
            }
        )

        self.assertEqual(history.lowest_occurrences, 2)

    def test_first_discount_point_starts_a_sale(self) -> None:
        history = parse_price_history(
            {
                "prices": [
                    point("2026-01-01", "50", 50),
                    point("2026-01-05", "100", 0),
                ]
            }
        )

        self.assertEqual(len(history.events), 1)
        self.assertEqual(history.events[0].started_on, date(2026, 1, 1))
        self.assertEqual(history.events[0].duration_days(date(2026, 2, 1)), 4)

    def test_falls_back_to_point_lowest(self) -> None:
        history = parse_price_history(
            {"prices": [point("2026-01-01", "100", 0), point("2026-01-02", "75", 25)]}
        )

        self.assertEqual(history.lowest_price, Decimal("75"))
        self.assertEqual(history.lowest_date, date(2026, 1, 2))
        self.assertEqual(history.lowest_occurrences, 1)

    def test_epoch_dates_are_parsed_in_utc(self) -> None:
        self.assertEqual(parse_history_date("1704067200"), date(2024, 1, 1))


def point(recorded_on: str, price: str, discount: int) -> dict:
    return {
        "date": recorded_on,
        "price": price,
        "rmb_price": price,
        "currency": "CNY",
        "discount": discount,
    }


if __name__ == "__main__":
    unittest.main()
