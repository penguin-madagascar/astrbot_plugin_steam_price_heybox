"""校验 steam_price_query 的三种输出方式。

AstrBot 运行时不在测试依赖里，这里注入最小替身模块后导入插件主体，
只验证分支逻辑：结果回给模型、直接发给用户、两者都做。
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


class StubMessageChain:
    def __init__(self, chain=None, type: str = "") -> None:
        self.chain = list(chain or [])
        self.type = type


class StubPlain:
    def __init__(self, text: str = "") -> None:
        self.text = text


class StubStar:
    def __init__(self, context=None) -> None:
        self.context = context


class StubLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def debug(self, message, *args, **kwargs) -> None:
        self.records.append(str(message))

    info = debug
    warning = debug

    def exception(self, message, *args, **kwargs) -> None:
        self.records.append(str(message))


class StubFilter:
    @staticmethod
    def command(*args, **kwargs):
        return lambda function: function

    @staticmethod
    def llm_tool(*args, **kwargs):
        return lambda function: function


def _module(name: str, **attributes) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _install_astrbot_stubs() -> None:
    if "astrbot" in sys.modules:
        return
    _module("astrbot")
    _module(
        "astrbot.api",
        AstrBotConfig=dict,
        logger=StubLogger(),
    )
    _module(
        "astrbot.api.event",
        AstrMessageEvent=object,
        MessageChain=StubMessageChain,
        filter=StubFilter,
    )
    _module("astrbot.api.message_components", Plain=StubPlain)
    _module(
        "astrbot.api.star",
        Context=object,
        Star=StubStar,
        register=lambda *args, **kwargs: lambda cls: cls,
    )
    _module("astrbot.core")
    _module("astrbot.core.star")
    _module("astrbot.core.star.filter")
    _module("astrbot.core.star.filter.command", GreedyStr=str)


_install_astrbot_stubs()
main = importlib.import_module("astrbot_plugin_steam_price_heybox.main")
steam_price = importlib.import_module("astrbot_plugin_steam_price_heybox.steam_price")


class FakeEvent:
    def __init__(self, send_error: Exception | None = None) -> None:
        self.sent: list[StubMessageChain] = []
        self.send_error = send_error

    async def send(self, message_chain: StubMessageChain) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(message_chain)

    def texts(self) -> list[str]:
        return [part.text for chain in self.sent for part in chain.chain]


class FakeService:
    def __init__(self, result: str = "游戏：Test Game / appid=123", error=None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    async def query(self, target: str, mode: str = "summary", country: str = "") -> str:
        self.calls.append((target, mode, country))
        if self.error is not None:
            raise self.error
        return self.result


class LlmToolOutputModeTests(unittest.IsolatedAsyncioTestCase):
    def build(
        self,
        output_mode: str = "model",
        enabled: bool = True,
        service=None,
        note=None,
    ):
        config = {
            "llm_tool_enabled": enabled,
            "llm_tool_output_mode": output_mode,
        }
        if note is not None:
            config["llm_tool_both_note"] = note
        plugin = main.SteamPriceHeyboxPlugin(context=None, config=config)
        self.addAsyncCleanup(plugin.terminate)
        plugin.service = service or FakeService()
        return plugin

    async def test_model_mode_returns_text_without_sending(self) -> None:
        plugin = self.build("model")
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertEqual(result, "游戏：Test Game / appid=123")
        self.assertEqual(event.sent, [])

    async def test_direct_mode_sends_and_returns_none(self) -> None:
        plugin = self.build("direct")
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertIsNone(result)
        self.assertEqual(event.texts(), ["游戏：Test Game / appid=123"])

    async def test_both_mode_sends_and_keeps_text_for_the_model(self) -> None:
        plugin = self.build("both")
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertEqual(event.texts(), ["游戏：Test Game / appid=123"])
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("游戏：Test Game / appid=123"))
        self.assertIn("请勿重复", result)
        self.assertIn("已经直接发送到 QQ", result)

    async def test_both_note_can_be_customized(self) -> None:
        plugin = self.build("both", note="自定义提示：已经发到 QQ 了。")
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertTrue(result.endswith("自定义提示：已经发到 QQ 了。"))
        self.assertIn("游戏：Test Game / appid=123", result)
        self.assertEqual(event.texts(), ["游戏：Test Game / appid=123"])

    async def test_blank_both_note_falls_back_to_default(self) -> None:
        plugin = self.build("both", note="   ")

        self.assertEqual(plugin.llm_tool_both_note, main.DEFAULT_BOTH_NOTE)

    async def test_unknown_output_mode_falls_back_to_model(self) -> None:
        plugin = self.build("BOTHISH")
        event = FakeEvent()

        self.assertEqual(plugin.llm_tool_output_mode, "model")
        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertEqual(event.sent, [])
        self.assertEqual(result, "游戏：Test Game / appid=123")

    async def test_output_mode_is_case_insensitive(self) -> None:
        plugin = self.build("  DIRECT  ")

        self.assertEqual(plugin.llm_tool_output_mode, "direct")

    async def test_direct_send_failure_falls_back_to_model_text(self) -> None:
        plugin = self.build("direct")
        event = FakeEvent(send_error=RuntimeError("bot offline"))

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertIsInstance(result, str)
        self.assertIn("游戏：Test Game / appid=123", result)
        self.assertIn("直接发送失败", result)
        self.assertIn("bot offline", result)

    async def test_disabled_tool_skips_the_service(self) -> None:
        service = FakeService()
        plugin = self.build("model", enabled=False, service=service)
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertIn("已被管理员关闭", result)
        self.assertEqual(service.calls, [])
        self.assertEqual(event.sent, [])

    async def test_lookup_error_is_returned_as_text(self) -> None:
        plugin = self.build(
            "direct",
            service=FakeService(error=steam_price.PriceLookupError("没有搜索到游戏")),
        )
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="不存在")

        self.assertEqual(result, "查询失败：没有搜索到游戏")
        self.assertEqual(event.sent, [])

    async def test_unexpected_error_is_returned_as_text(self) -> None:
        plugin = self.build("model", service=FakeService(error=RuntimeError("boom")))
        event = FakeEvent()

        result = await plugin.steam_price_query_tool(event, game="测试游戏")

        self.assertEqual(result, "Steam 价格查询失败：boom")

    async def test_arguments_are_forwarded_to_the_service(self) -> None:
        service = FakeService()
        plugin = self.build("model", service=service)

        await plugin.steam_price_query_tool(
            FakeEvent(),
            game="艾尔登法环",
            mode="history",
            country="US",
        )

        self.assertEqual(service.calls, [("艾尔登法环", "history", "US")])


if __name__ == "__main__":
    unittest.main()
