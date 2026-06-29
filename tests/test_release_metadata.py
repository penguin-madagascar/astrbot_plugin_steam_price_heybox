from __future__ import annotations

import ast
import json
import struct
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.2.2"
EXPECTED_COMMAND_ALIASES = {"xhhprice", "heyboxprice", "steam查价", "小黑盒查价"}
EXPECTED_MARKET_DATA = {
    "name": "astrbot_plugin_steam_price_heybox",
    "display_name": "Steam 价格查询（小黑盒）",
    "desc": (
        "无需 API Key，查询 Steam 游戏当前价、历史最低价、促销记录、小黑盒跨区价格与游戏资料。"
    ),
    "author": "penguin-madagascar",
    "repo": "https://github.com/penguin-madagascar/astrbot_plugin_steam_price_heybox",
}


class ReleaseMetadataTests(unittest.TestCase):
    def test_market_metadata_matches_submission(self) -> None:
        metadata = yaml.safe_load((ROOT / "metadata.yaml").read_text(encoding="utf-8"))

        self.assertEqual(
            {key: metadata.get(key) for key in EXPECTED_MARKET_DATA},
            EXPECTED_MARKET_DATA,
        )
        self.assertEqual(metadata["version"], EXPECTED_VERSION)
        self.assertIn(
            f'PLUGIN_VERSION = "{EXPECTED_VERSION}"',
            (ROOT / "main.py").read_text(encoding="utf-8"),
        )
        self.assertNotIn("description", metadata)
        self.assertFalse(metadata["repo"].endswith(".git"))

    def test_required_release_files_exist(self) -> None:
        for filename in ("main.py", "metadata.yaml", "requirements.txt", "README.md", "LICENSE"):
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).is_file())

    def test_network_and_logging_implementation_follow_astrbot_guidance(self) -> None:
        python_source = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.glob("*.py"))

        self.assertNotIn("import logging", python_source)
        self.assertNotIn("import urllib", python_source)
        self.assertIn("from astrbot.api import AstrBotConfig, logger", python_source)
        self.assertIn("httpx.AsyncClient", python_source)

    def test_command_uses_runtime_greedy_string_annotation(self) -> None:
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom) and node.module == "__future__"
                for node in tree.body
            )
        )
        handler = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "steam_price_command"
        )
        query = next(argument for argument in handler.args.args if argument.arg == "query")
        self.assertIsInstance(query.annotation, ast.Name)
        self.assertEqual(query.annotation.id, "GreedyStr")
        self.assertEqual(handler.args.defaults, [])

    def test_command_declares_chinese_aliases(self) -> None:
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        handler = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "steam_price_command"
        )
        command_decorator = next(
            decorator
            for decorator in handler.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "command"
        )
        alias_keyword = next(
            keyword for keyword in command_decorator.keywords if keyword.arg == "alias"
        )
        aliases = {
            element.value
            for element in alias_keyword.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }

        self.assertEqual(aliases, EXPECTED_COMMAND_ALIASES)

    def test_optional_llm_configuration_defaults(self) -> None:
        schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))

        self.assertEqual(schema["llm_provider_id"]["_special"], "select_provider")
        self.assertEqual(schema["llm_provider_id"]["default"], "")
        self.assertEqual(schema["llm_name_retry_count"]["default"], 3)

    def test_logo_is_256_pixel_square_png(self) -> None:
        data = (ROOT / "logo.png").read_bytes()

        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (256, 256))


if __name__ == "__main__":
    unittest.main()
