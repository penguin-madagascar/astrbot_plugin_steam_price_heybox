from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


logger = logging.getLogger(__name__)

STEAM_STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
XIAOHEIHE_WEB_BASE_URL = "https://www.xiaoheihe.cn"
XIAOHEIHE_GAME_SHARE_URL = "https://api.xiaoheihe.cn/game/get_game_detail_share/"
XIAOHEIHE_GLOBAL_PRICE_URL = "https://api.xiaoheihe.cn/game/get_game_global_prices/"
XIAOHEIHE_PRICE_HISTORY_URL = "https://api.xiaoheihe.cn/game/get_game_prices/history/v2"
XIAOHEIHE_MOBILE_DETAIL_URL = "https://api.xiaoheihe.cn/game/mobile/get_game_detail/"

COUNTRY_NAMES = {
    "CN": "China",
    "US": "United States",
    "HK": "Hong Kong",
    "TW": "Taiwan",
    "JP": "Japan",
    "KR": "Korea",
    "UA": "Ukraine",
    "TR": "Turkey",
    "AR": "Argentina",
    "BR": "Brazil",
    "RU": "Russia",
    "GB": "United Kingdom",
    "DE": "Germany",
}
COUNTRY_ALIASES = {
    "国区": "CN",
    "中国": "CN",
    "大陆": "CN",
    "美区": "US",
    "美国": "US",
    "港区": "HK",
    "香港": "HK",
    "台区": "TW",
    "台湾": "TW",
    "日区": "JP",
    "日本": "JP",
    "韩区": "KR",
    "韩国": "KR",
    "乌克兰区": "UA",
    "乌克兰": "UA",
    "ukraine": "UA",
    "ua": "UA",
    "土区": "TR",
    "土耳其": "TR",
    "阿区": "AR",
    "阿根廷": "AR",
    "巴西": "BR",
    "俄区": "RU",
    "俄罗斯": "RU",
    "英区": "GB",
    "英国": "GB",
    "德区": "DE",
    "德国": "DE",
}
XIAOHEIHE_REGION_ALIASES = {
    "CN": "cn",
    "US": "us",
    "HK": "hk",
    "TW": "tw",
    "JP": "jp",
    "KR": "kr",
    "UA": "ua",
    "TR": "tr",
    "AR": "ar",
    "BR": "br",
    "RU": "ru",
    "GB": "uk",
    "DE": "eu",
}
STATIC_QUERY_ALIASES = {
    "给他爱5": ["Grand Theft Auto V", "GTA V"],
    "侠盗猎车手5": ["Grand Theft Auto V", "GTA V"],
    "大表哥2": ["Red Dead Redemption 2"],
    "荒野大镖客2": ["Red Dead Redemption 2"],
    "老头环": ["ELDEN RING"],
    "艾尔登法环": ["ELDEN RING"],
    "博德之门3": ["Baldur's Gate 3", "Baldurs Gate 3"],
    "赛博朋克2077": ["Cyberpunk 2077"],
    "双人成行": ["It Takes Two"],
    "潜水员戴夫": ["DAVE THE DIVER"],
    "星露谷": ["Stardew Valley"],
}


class PriceLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class GameIdentity:
    appid: int
    label: str


JsonGetter = Callable[[str, dict[str, Any] | None, dict[str, str] | None], Any]


class XiaoheihePriceService:
    def __init__(
        self,
        *,
        timeout_seconds: int = 15,
        default_country: str = "CN",
        default_history_country: str = "CN",
        default_language: str = "schinese",
        history_days: int = 720,
        global_price_limit: int = 10,
        show_api_links: bool = False,
        http_get_json: JsonGetter | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.default_country = normalize_country(default_country) or "CN"
        self.default_history_country = normalize_country(default_history_country) or "UA"
        self.default_language = default_language or "schinese"
        self.history_days = history_days
        self.global_price_limit = global_price_limit
        self.show_api_links = show_api_links
        self.http_get_json = http_get_json or self._http_get_json

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "XiaoheihePriceService":
        return cls(
            timeout_seconds=int(config.get("timeout_seconds", 15)),
            default_country=str(config.get("default_country", "CN")),
            default_history_country=str(config.get("default_history_country", "CN")),
            default_language=str(config.get("default_language", "schinese")),
            history_days=int(config.get("history_days", 720)),
            global_price_limit=int(config.get("global_price_limit", 10)),
            show_api_links=bool(config.get("show_api_links", False)),
        )

    async def lookup_text(self, text: str) -> str:
        identity = await self.resolve_game(text)
        countries = countries_from_text(text)
        return await self.lookup_appid(identity, countries)

    async def resolve_game(self, text: str) -> GameIdentity:
        appid = extract_appid(text)
        query = steam_lookup_game_query(text)
        if appid:
            return GameIdentity(appid, query or f"appid={appid}")
        if not query:
            raise PriceLookupError("查小黑盒价格需要游戏名、Steam appid 或 Steam 链接。")

        results = await self.store_search_with_variants(query)
        candidate = choose_steam_candidate(query, results)
        if not candidate:
            raise PriceLookupError(f"没有从 Steam 商店搜索到游戏：{query}")

        appid = int(candidate["appid"])
        label = f"{candidate['name']} / appid={appid}"
        return GameIdentity(appid, label)

    async def lookup_appid(self, identity: GameIdentity, countries: list[str]) -> str:
        appid = identity.appid
        game_page = f"{XIAOHEIHE_WEB_BASE_URL}/app/topic/game/pc/{appid}"
        share_url = f"{XIAOHEIHE_GAME_SHARE_URL}?steam_appid={appid}"
        lines = [
            f"游戏：{identity.label}",
            f"小黑盒游戏页：{game_page}",
        ]

        history_countries = countries or [self.default_history_country]
        history_found = False
        for country in history_countries:
            cc = xiaoheihe_cc(country)
            history_url = (
                f"{XIAOHEIHE_PRICE_HISTORY_URL}?appid={appid}&platf=steam"
                f"&cc={cc}&days={self.history_days}"
            )
            if self.show_api_links:
                lines.append(f"小黑盒历史价格接口：{history_url}")
            try:
                history = await self.xiaoheihe_price_history(appid, cc)
            except Exception as exc:
                logger.warning("Xiaoheihe history price failed appid=%s cc=%s: %s", appid, cc, exc)
                lines.append(f"{country} 历史价格读取失败：{short_text(str(exc), 180)}")
                continue
            lines.extend(self.format_price_history(history, country))
            history_found = history_found or bool(history.get("prices") or history.get("lowest_info"))

        try:
            global_prices = await self.xiaoheihe_global_prices(appid)
        except Exception as exc:
            logger.warning("Xiaoheihe global prices failed appid=%s: %s", appid, exc)
            global_prices = []

        global_price_lines = self.target_price_lines(global_prices, countries)
        if global_price_lines:
            lines.append("小黑盒各区当前价（接口显示为折算人民币后的对比价）：")
            lines.extend(global_price_lines)

        try:
            mobile_detail = await self.xiaoheihe_mobile_detail(appid)
        except Exception as exc:
            logger.warning("Xiaoheihe mobile detail failed appid=%s: %s", appid, exc)
            mobile_detail = {}

        price_summary_lines = xiaoheihe_format_price_summary(mobile_detail)
        if price_summary_lines:
            lines.append("小黑盒当前价格补充汇总：")
            lines.extend(price_summary_lines)

        if not history_found:
            lines.append(f"小黑盒历史价格暂不可用，可查看分享页补充：{share_url}")
        lines.append("说明：价格历史、史低日期和促销走势优先以小黑盒历史价格接口为准；全球价格和 mobile detail 仅补充当前价。")
        return "\n".join(lines)

    async def store_search_with_variants(self, query: str) -> list[dict[str, Any]]:
        for candidate_query in unique_texts([query, *STATIC_QUERY_ALIASES.get(query, [])]):
            results = await self.steam_store_search(candidate_query)
            if results:
                return results
        return []

    async def steam_store_search(self, query: str) -> list[dict[str, Any]]:
        data = await self.get_json(
            STEAM_STORE_SEARCH_URL,
            {"term": query, "cc": self.default_country, "l": self.default_language},
            steam_browser_headers(),
        )
        items = data.get("items") if isinstance(data, dict) else []
        results = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            appid = item.get("id") or item.get("appid")
            name = str(item.get("name") or "").strip()
            if appid and name:
                results.append({"appid": int(appid), "name": name})
        return results

    async def xiaoheihe_global_prices(self, appid: int) -> list[dict[str, Any]]:
        data = await self.get_json(
            XIAOHEIHE_GLOBAL_PRICE_URL,
            {
                "lang": "zh-cn",
                "os_type": "web",
                "offset": 0,
                "limit": 100,
                "steam_appid": appid,
            },
            {
                **steam_browser_headers(),
                "Accept": "application/json,text/plain,*/*",
                "Referer": f"{XIAOHEIHE_GAME_SHARE_URL}?steam_appid={appid}",
            },
        )
        prices = data.get("result", {}).get("prices", []) if isinstance(data, dict) else []
        if not isinstance(prices, list):
            return []

        unique_prices = []
        seen = set()
        for item in prices:
            if not isinstance(item, dict):
                continue
            cc = str(item.get("cc") or "").casefold()
            if not cc or cc in seen:
                continue
            seen.add(cc)
            unique_prices.append(item)
        return unique_prices

    async def xiaoheihe_price_history(self, appid: int, cc: str) -> dict[str, Any]:
        data = await self.get_json(
            XIAOHEIHE_PRICE_HISTORY_URL,
            {
                "appid": appid,
                "platf": "steam",
                "cc": cc,
                "days": self.history_days,
            },
            {
                **steam_browser_headers(),
                "Accept": "application/json,text/plain,*/*",
                "Referer": f"{XIAOHEIHE_WEB_BASE_URL}/app/topic/game/pc/{appid}",
            },
        )
        if not isinstance(data, dict) or data.get("status") != "ok":
            raise ValueError(f"小黑盒历史价格接口返回异常：{short_text(str(data), 180)}")
        result = data.get("result")
        return result if isinstance(result, dict) else {}

    async def xiaoheihe_mobile_detail(self, appid: int) -> dict[str, Any]:
        data = await self.get_json(
            XIAOHEIHE_MOBILE_DETAIL_URL,
            {"lang": "zh-cn", "os_type": "web", "steam_appid": appid},
            {
                **steam_browser_headers(),
                "Accept": "application/json,text/plain,*/*",
                "Referer": f"{XIAOHEIHE_WEB_BASE_URL}/app/topic/game/pc/{appid}",
            },
        )
        result = data.get("result") if isinstance(data, dict) else None
        return result if isinstance(result, dict) else {}

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return await self.http_get_json(url, params, headers)

    async def _http_get_json(
        self,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> Any:
        return await asyncio.to_thread(
            sync_get_json,
            url,
            params or {},
            headers or {},
            self.timeout_seconds,
        )

    def format_price_history(
        self,
        history: dict[str, Any],
        country: str,
        point_limit: int = 40,
    ) -> list[str]:
        prices = history.get("prices")
        price_points = [item for item in prices if isinstance(item, dict)] if isinstance(prices, list) else []
        lowest = history.get("lowest_info") if isinstance(history.get("lowest_info"), dict) else {}
        lowest_v2 = history.get("lowest_info_v2") if isinstance(history.get("lowest_info_v2"), dict) else {}
        country_name = COUNTRY_NAMES.get(country, country)
        lines = [f"{country_name} / {country}，近 {self.history_days} 天："]

        if price_points:
            latest = price_points[-1]
            latest_discount = int(latest.get("discount") or 0)
            latest_text = f"- 最新价格（{xiaoheihe_history_date(latest.get('date'))}）：{xiaoheihe_history_price_text(latest)}"
            if latest_discount:
                latest_text += f"，折扣 {latest_discount}%"
            lines.append(latest_text)

        if lowest:
            currency = str(lowest_v2.get("currency") or "").strip()
            lowest_text = (
                f"- 历史最低（{xiaoheihe_history_date(lowest.get('date'))}）："
                f"{str(lowest.get('price') or '?').strip()} {currency}"
            ).rstrip()
            lowest_discount = int(lowest.get("discount") or 0)
            if lowest_discount:
                lowest_text += f"，折扣 {lowest_discount}%"
            lowest_count = int(lowest_v2.get("count") or 0)
            if lowest_count:
                lowest_text += f"，近 {self.history_days} 天出现 {lowest_count} 次"
            lines.append(lowest_text)

        if price_points:
            selected_points = price_points[-point_limit:]
            lines.append(f"- 价格变动点（共 {len(price_points)} 个，显示最近 {len(selected_points)} 个）：")
            for item in selected_points:
                point = f"  {xiaoheihe_history_date(item.get('date'))}：{xiaoheihe_history_price_text(item)}"
                discount = int(item.get("discount") or 0)
                if discount:
                    point += f"，折扣 {discount}%"
                lines.append(point)
        else:
            lines.append("- 接口没有返回历史价格点。")
        return lines

    def target_price_lines(self, prices: list[dict[str, Any]], countries: list[str]) -> list[str]:
        if not prices:
            return []

        by_cc = {str(item.get("cc") or "").casefold(): item for item in prices}
        lines = []
        if countries:
            for country in countries:
                item = by_cc.get(xiaoheihe_cc(country))
                if item:
                    lines.append("- " + xiaoheihe_format_global_price(item))
                else:
                    lines.append(f"- {country}：小黑盒全球价格接口没有返回该区域。")
            return lines

        cheapest = sorted(prices, key=xiaoheihe_price_number)[: self.global_price_limit]
        for item in cheapest:
            lines.append("- " + xiaoheihe_format_global_price(item))

        for country in ("CN", "US", "HK"):
            item = by_cc.get(xiaoheihe_cc(country))
            line = "- " + xiaoheihe_format_global_price(item) if item else ""
            if line and line not in lines:
                lines.append(line)
        return lines


def sync_get_json(
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
) -> Any:
    clean_params = {key: value for key, value in params.items() if value not in {None, ""}}
    if clean_params:
        url = f"{url}?{urllib.parse.urlencode(clean_params)}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def steam_browser_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def extract_appid(text: str) -> int:
    patterns = [
        r"store\.steampowered\.com/app/(\d+)",
        r"steam_appid[=:](\d+)",
        r"\bappid[=: ]+(\d+)\b",
        r"\b(\d{3,10})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1))
    return 0


def steam_lookup_game_query(query: str) -> str:
    text = query.strip()
    if not text:
        return ""

    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b(?:appid|steam_appid)[=: ]+\d+\b", " ", text, flags=re.I)
    for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
        alias_text = alias.casefold()
        if re.fullmatch(r"[a-z]{2}", alias_text):
            text = re.sub(rf"(?<![A-Za-z]){re.escape(alias)}(?:区|地区|服|服区)?(?![A-Za-z])", " ", text, flags=re.I)
        else:
            text = re.sub(re.escape(alias) + r"(?:区|地区|服|服区)?", " ", text, flags=re.I)
    text = re.sub(r"(?<![A-Za-z])(?:[A-Za-z]{2})(?:区|地区|服|服区)(?![A-Za-z])", " ", text)
    text = re.sub(
        r"(?:小黑盒|heybox|xiaoheihe|steamdb|steam|商店|游戏|查看|查询|查|帮我|看下|看看|"
        r"各区|区域|区|历史最低|史低|最低价|最低|价格走势|价格历史|价格|促销时间|"
        r"促销|折扣|预购|预订|预约|购买|买|开售|上架|开放|页面|是多少|多少|"
        r"什么|一下|的|了没|了吗|没)",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"[：:，,。？?！!、]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def countries_from_text(text: str) -> list[str]:
    countries = []
    lower_text = text.casefold()
    for alias, country in sorted(COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        alias_text = alias.casefold()
        if re.fullmatch(r"[a-z]{2}", alias_text):
            if re.search(rf"(?<![a-z]){re.escape(alias_text)}(?![a-z])", lower_text):
                add_unique(countries, country)
        elif alias_text in lower_text:
            add_unique(countries, country)

    for match in re.finditer(r"(?<![A-Za-z])([A-Za-z]{2})(?:区|地区|服|服区)?(?![A-Za-z])", text):
        code = match.group(1).upper()
        if code in COUNTRY_NAMES:
            add_unique(countries, code)
    return countries


def normalize_country(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in COUNTRY_NAMES:
        return upper
    return COUNTRY_ALIASES.get(text.casefold(), "")


def xiaoheihe_cc(country: str) -> str:
    normalized = normalize_country(country) or country.upper()
    return XIAOHEIHE_REGION_ALIASES.get(normalized, normalized.lower())


def choose_steam_candidate(query: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None

    normalized_query = normalize_game_title(query)
    exact_matches = [
        item for item in results if normalize_game_title(str(item.get("name") or "")) == normalized_query
    ]
    if exact_matches:
        return min(exact_matches, key=lambda item: len(str(item.get("name") or "")))

    plain_matches = [
        item
        for item in results
        if normalized_query and normalized_query in normalize_game_title(str(item.get("name") or ""))
    ]
    if plain_matches:
        return min(plain_matches, key=lambda item: len(str(item.get("name") or "")))

    return results[0]


def normalize_game_title(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def xiaoheihe_price_number(item: dict[str, Any]) -> float:
    for key in ("value", "current", "initial"):
        try:
            return float(item.get(key))
        except (TypeError, ValueError):
            pass
    return float("inf")


def xiaoheihe_price_region_label(item: dict[str, Any]) -> str:
    cc = str(item.get("cc") or "").upper()
    name = str(item.get("name") or "").strip()
    return f"{name} / {cc}" if cc and name else name or cc or "未知区域"


def xiaoheihe_format_global_price(item: dict[str, Any]) -> str:
    current = str(item.get("current") or "").strip()
    initial = str(item.get("initial") or "").strip()
    discount = item.get("discount")
    parts = [f"{xiaoheihe_price_region_label(item)}：约 ¥{current or '?'}"]
    if initial and initial != current:
        parts.append(f"原价约 ¥{initial}")
    try:
        discount_value = int(discount)
    except (TypeError, ValueError):
        discount_value = 0
    if discount_value:
        parts.append(f"折扣 {discount_value}%")
    return "，".join(parts)


def xiaoheihe_history_price_text(item: dict[str, Any]) -> str:
    price = str(item.get("price") or "").strip()
    currency = str(item.get("currency") or "").strip()
    rmb_price = str(item.get("rmb_price") or "").strip()
    parts = [f"{price} {currency}".strip()] if price else []
    if rmb_price:
        parts.append(f"约 ¥{rmb_price}")
    return "，".join(parts) or "价格未知"


def xiaoheihe_history_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "日期未知"
    try:
        return datetime.fromtimestamp(float(text)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return text


def xiaoheihe_coin_text(value: Any) -> str:
    try:
        amount = float(value) / 1000
    except (TypeError, ValueError):
        return ""
    text = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"¥{text}"


def xiaoheihe_format_price_summary(detail: dict[str, Any]) -> list[str]:
    lines = []
    price = detail.get("price") if isinstance(detail.get("price"), dict) else {}
    if price:
        current = str(price.get("current") or "").strip()
        initial = str(price.get("initial") or "").strip()
        lowest = str(price.get("lowest_price_raw") or price.get("lowest_price") or "").strip()
        discount = price.get("discount")
        lowest_discount = price.get("lowest_discount")
        parts = []
        if current:
            parts.append(f"当前 ¥{current}")
        if initial and initial != current:
            parts.append(f"原价 ¥{initial}")
        if discount:
            parts.append(f"当前折扣 {discount}%")
        if lowest:
            parts.append(f"历史最低 ¥{lowest}")
        if lowest_discount:
            parts.append(f"史低折扣 {lowest_discount}%")
        if price.get("new_lowest"):
            parts.append("当前为新史低")
        elif price.get("is_lowest"):
            parts.append("当前平史低")
        if parts:
            lines.append("- Steam 价格汇总：" + "，".join(parts))

    heybox_price = detail.get("heybox_price") if isinstance(detail.get("heybox_price"), dict) else {}
    if heybox_price:
        parts = []
        cost = xiaoheihe_coin_text(heybox_price.get("cost_coin"))
        original = xiaoheihe_coin_text(heybox_price.get("original_coin"))
        if cost:
            parts.append(f"小黑盒商城价 {cost}")
        if original and original != cost:
            parts.append(f"原价 {original}")
        coupon = heybox_price.get("coupon_info")
        if isinstance(coupon, dict):
            price_desc = str(coupon.get("price_desc") or "").strip()
            final_price = str(coupon.get("final_price") or "").strip()
            coupon_desc = str(coupon.get("coupon_desc") or "").strip()
            if price_desc:
                parts.append(price_desc)
            elif final_price:
                parts.append(f"券后 ¥{final_price}")
            if coupon_desc:
                parts.append(coupon_desc)
        if heybox_price.get("new_lowest"):
            parts.append("小黑盒商城当前为新史低")
        elif heybox_price.get("is_lowest"):
            parts.append("小黑盒商城当前平史低")
        if parts:
            lines.append("- 小黑盒商城汇总：" + "，".join(parts))
    return lines


def unique_texts(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def add_unique(items: list[str], item: str) -> None:
    if item and item not in items:
        items.append(item)


def short_text(value: str, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."
