from __future__ import annotations

import logging

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter

from .xiaoheihe_price import PriceLookupError, XiaoheihePriceService


logger = logging.getLogger(__name__)
PLUGIN_NAME = "astrbot_plugin_xiaoheihe_price"
PLUGIN_VERSION = "1.0.0"
PLUGIN_REPOSITORY = "https://github.com/penguin-madagascar/astrbot_plugin_xiaoheihe_price"


@star.register(
    PLUGIN_NAME,
    "penguin-madagascar",
    "查询小黑盒 Steam 游戏价格、史低和跨区价格。",
    PLUGIN_VERSION,
    PLUGIN_REPOSITORY,
)
class XiaoheihePricePlugin(star.Star):
    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        self.config = config or {}
        self.service = XiaoheihePriceService.from_config(self.config)

    @filter.command(
        "steamprice",
        alias={"xhhprice", "heyboxprice"},
        ignore_prefix=True,
    )
    async def xiaoheihe_price_command(self, event: AstrMessageEvent, query: str = ""):
        query = query.strip()
        if not query:
            yield event.plain_result("Usage: /steamprice <game name|Steam appid|Steam URL> [CN/US/UA...]")
            return

        try:
            result = await self.service.lookup_text(query)
        except PriceLookupError as exc:
            yield event.plain_result(str(exc))
            return
        except Exception as exc:
            logger.exception("Xiaoheihe price lookup failed")
            yield event.plain_result(f"小黑盒价格查询失败：{exc}")
            return

        yield event.plain_result(result)
