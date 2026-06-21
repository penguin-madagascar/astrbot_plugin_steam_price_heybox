# AstrBot Steam 价格查询（小黑盒）

无需 API Key 的 AstrBot 插件，使用 Steam 商店和小黑盒公开数据查询当前价格、
历史最低价、促销记录、全球区价和游戏资料。

## 功能

- 支持游戏名、Steam appid 和 Steam 商店链接。
- 使用 Steam 官方当前价格，并通过小黑盒补充史低和促销历史。
- 计算当前或上次促销的起止时间、持续天数、最大折扣和史低出现次数。
- 对比全球区价，显示最低价区服及相对国区的差额。
- 提供基础和详细两级 Steam 游戏资料。
- 可选用 AstrBot 已配置的 LLM 校正拼写、翻译和未知中文地区。

## 安装

在 AstrBot 管理面板中选择从 GitHub 仓库安装：

```text
https://github.com/penguin-madagascar/astrbot_plugin_steam_price_heybox
```

也可以将仓库克隆到：

```text
AstrBot/data/plugins/astrbot_plugin_steam_price_heybox
```

## 命令

```text
/steamprice [-地区] [--] <游戏名|appid|Steam URL>
/steamprice history [-地区] [--] <目标>
/steamprice regions [--] <目标>
/steamprice info [--] <目标>
/steamprice detailed_info [--] <目标>
```

- 默认模式：当前价、史低、促销状态和最低价区服摘要。
- `history`：最近促销记录与历史统计。
- `regions`：全球区价排行和相对国区差额。
- `info`：发行日期、开发商、发行商和平台等基础资料。
- `detailed_info`：语言、分类、成就、DLC、评分和内容提示等扩展资料。
- 地区必须位于游戏名前并带 `-`，支持两字母代码或正式中文国名。
- 地区参数仅适用于默认价格模式和 `history`，不再支持名称后的旧写法。
- 游戏名内部的连字符会原样保留，例如 `Half-Life 2`。
- `--` 是显式参数终止符；当游戏名以类似地区参数的 `-XX` 或 `-中文` 开头时，
  其后的全部文本会原样作为游戏名。

示例：

```text
/steamprice 艾尔登法环
/steamprice history -CN 1245620
/steamprice regions https://store.steampowered.com/app/1091500/
/steamprice info Stardew Valley
/steamprice detailed_info 2277560
```

显式终止参数解析：

```text
/steamprice -- -US Game Name
/steamprice -US -- -Game Name
```

入口别名：`/xhhprice`、`/heyboxprice`。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `timeout_seconds` | `15` | HTTP 请求超时时间，单位为秒 |
| `default_country` | `CN` | Steam 搜索和资料的默认地区 |
| `default_language` | `schinese` | Steam 商店语言 |
| `default_history_country` | `CN` | 历史价格默认地区 |
| `history_days` | `720` | 传递给小黑盒的历史查询天数 |
| `history_event_limit` | `5` | `history` 显示的最近促销次数 |
| `global_price_limit` | `10` | `regions` 显示的区服数量 |
| `show_api_links` | `false` | 是否显示数据接口链接 |
| `llm_provider_id` | 空 | 可选的游戏名与未知中文地区校正模型 |
| `llm_name_retry_count` | `3` | 首次校正失败后的额外 LLM 重试次数 |

选择 LLM 后，首次 Steam 名称搜索前会进行一次校正；未匹配时最多再调用
`max(llm_name_retry_count, 0)` 次。配置为 `0` 或负数时仍保留首次调用。
appid 和商店链接不会校正游戏名，只有未知中文地区可能触发 LLM。

## 数据与限制

- 当前价格和游戏资料来自 Steam 商店公开接口。
- 历史价格和全球区价来自小黑盒公开接口。
- 小黑盒未为本插件提供正式 API，接口变化可能导致部分查询暂时不可用。
- 促销起止时间由历史价格变化点推导，不代表 Steam 公布的精确截止时间。
- 插件不接入 ITAD，不需要 Steam Web API Key，也不会持久化查询内容。
- 只有选择 `llm_provider_id` 后，游戏名、地区和失败猜测才会发送给对应模型。
- 价格仅供参考，购买前请以实际结算页面为准。

## 开发

```bash
python -m pip install -r requirements.txt ruff pyyaml
ruff check .
ruff format --check .
python -m unittest
python -m compileall -q __init__.py main.py models.py api_clients.py name_correction.py price_analysis.py steam_price.py
```

市场发布和人工检查步骤见 [PUBLISHING.md](PUBLISHING.md)。

## License

代码使用 [MIT](LICENSE) 许可证。`logo.png` 是小黑盒标识，不属于 MIT 授权范围；
详情见 [NOTICE.md](NOTICE.md)。本项目是非官方社区插件，与 Steam 或小黑盒不存在隶属或背书关系。
