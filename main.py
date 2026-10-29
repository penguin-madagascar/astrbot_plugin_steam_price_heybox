import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Plain
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
PLUGIN_VERSION = "1.3.0"
PLUGIN_REPOSITORY = "https://github.com/penguin-madagascar/astrbot_plugin_steam_price_heybox"
PLUGIN_DESCRIPTION = (
    "无需 API Key，查询 Steam 游戏当前价、历史最低价、促销记录、小黑盒跨区价格与游戏资料。"
)
TOOL_OUTPUT_MODES = ("model", "direct", "both")
BOTH_NOTE = (
    "（以上内容已经直接发送给用户，请勿重复价格、链接或明细；如需回应，请结合用户问题继续分析。）"
)
STEAM_TIMEOUT_HINT = (
    "查询超时：Steam 商店接口连接被挂起（当前网络下会偶发）。"
    "如果知道 appid，可以直接用 appid 重试；appid 查询不需要先搜索商店。"
)


def describe_error(exc: Exception) -> str:
    """返回异常的可读描述，httpx 部分异常的 str() 是空串。"""
    return str(exc).strip() or type(exc).__name__


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
        output_mode = str(self.config.get("llm_tool_output_mode", "model")).strip().lower()
        self.llm_tool_output_mode = output_mode if output_mode in TOOL_OUTPUT_MODES else "model"
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
        except httpx.TimeoutException:
            yield event.plain_result(STEAM_TIMEOUT_HINT)
            return
        except Exception as exc:
            logger.exception("Steam price lookup failed")
            yield event.plain_result(f"Steam 价格查询失败：{describe_error(exc)}")
            return

        for message in messages:
            yield event.plain_result(message)

    @filter.llm_tool(name="steam_price_query")
    async def steam_price_query_tool(
        self,
        event: AstrMessageEvent,
        game: str = "",
        mode: str = "summary",
        country: str = "",
    ) -> str | None:
        """查询 Steam 游戏价格，返回当前价、史低、促销记录、区价或游戏资料。

        mode 取值：summary（默认，当前价与史低）、history（促销历史）、
        regions（小黑盒全球区价）、info（基础资料）、detailed_info（扩展资料）。

        Args:
            game(string): 游戏名称、Steam appid（例如 1245620）或 Steam 商店链接
            mode(string): summary、history、regions、info、detailed_info 之一
            country(string): 可选地区，如 CN、US、香港；仅 summary 与 history 生效
        """
        try:
            text = await self.service.query(game, mode=mode, country=country)
        except PriceLookupError as exc:
            return f"查询失败：{exc}"
        except httpx.TimeoutException:
            return STEAM_TIMEOUT_HINT
        except Exception as exc:
            logger.exception("Steam price LLM tool failed")
            return f"Steam 价格查询失败：{describe_error(exc)}"

        if self.llm_tool_output_mode in {"direct", "both"}:
            try:
                await event.send(MessageChain(chain=[Plain(text)]))
            except Exception as exc:
                logger.exception("Steam price direct send failed")
                return f"{text}\n\n（直接发送失败，请由你转述给用户：{exc}）"
            if self.llm_tool_output_mode == "direct":
                return None
            return f"{text}\n\n{BOTH_NOTE}"
        return text
