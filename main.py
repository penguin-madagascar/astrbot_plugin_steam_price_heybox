import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

from .name_correction import (
    CORRECTION_SYSTEM_PROMPT,
    NameCorrection,
    NameCorrectionRequest,
    build_correction_prompt,
    parse_correction_response,
)
from .steam_price import PriceLookupError, SteamPriceService

PLUGIN_NAME = "astrbot_plugin_steam_price_heybox"
PLUGIN_VERSION = "1.2.2"
PLUGIN_REPOSITORY = "https://github.com/penguin-madagascar/astrbot_plugin_steam_price_heybox"
PLUGIN_DESCRIPTION = (
    "无需 API Key，查询 Steam 游戏当前价、历史最低价、促销记录、小黑盒跨区价格与游戏资料。"
)


class AstrBotGameNameCorrector:
    def __init__(self, context: Context, provider_id: str) -> None:
        self.context = context
        self.provider_id = provider_id

    async def __call__(self, request: NameCorrectionRequest) -> NameCorrection | None:
        try:
            response = await self.context.llm_generate(
                chat_provider_id=self.provider_id,
                prompt=build_correction_prompt(request),
                system_prompt=CORRECTION_SYSTEM_PROMPT,
            )
        except Exception as exc:
            logger.warning(f"Steam game name correction failed: {exc}")
            return None
        correction = parse_correction_response(response.completion_text or "")
        if correction is None:
            logger.warning("Steam game name correction returned invalid JSON.")
        return correction


@register(
    PLUGIN_NAME,
    "penguin-madagascar",
    PLUGIN_DESCRIPTION,
    PLUGIN_VERSION,
    PLUGIN_REPOSITORY,
)
class SteamPriceHeyboxPlugin(Star):
    def __init__(
        self,
        context: Context,
        config: AstrBotConfig | dict | None = None,
    ) -> None:
        super().__init__(context)
        self.config = config or {}
        timeout = float(self.config.get("timeout_seconds", 15))
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        provider_id = str(self.config.get("llm_provider_id", "")).strip()
        name_corrector = AstrBotGameNameCorrector(context, provider_id) if provider_id else None
        self.service = SteamPriceService.from_config(
            self.config,
            self.http_client,
            name_corrector=name_corrector,
        )

    async def terminate(self) -> None:
        await self.http_client.aclose()
        logger.info("Steam price Heybox plugin stopped.")

    @filter.command(
        "steamprice",
        alias={"xhhprice", "heyboxprice", "steam查价", "小黑盒查价"},
        desc="查询 Steam 当前价、史低、促销历史、跨区价格和游戏资料。",
    )
    async def steam_price_command(
        self,
        event: AstrMessageEvent,
        query: GreedyStr,
    ):
        try:
            messages = await self.service.execute(query.strip())
        except PriceLookupError as exc:
            yield event.plain_result(str(exc))
            return
        except Exception as exc:
            logger.exception("Steam price lookup failed")
            yield event.plain_result(f"Steam 价格查询失败：{exc}")
            return

        for message in messages:
            yield event.plain_result(message)
