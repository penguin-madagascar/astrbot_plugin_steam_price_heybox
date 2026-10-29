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
- 通过 `steam_price_query` 工具把价格查询能力开放给模型，支持对话式自动查询；
  工具结果可回给模型总结、直接发送到聊天，或两者都做。

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
- 只有纯数字、`appid=`／`steam_appid=` 前缀和商店链接才按 appid 解析；
  游戏名里的数字（如 `Battlefield 2042`）按名称搜索。
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

入口别名：`/xhhprice`、`/heyboxprice`、`/steam查价`、`/小黑盒查价`。

## 模型工具（Function Calling）

插件注册一个名为 `steam_price_query` 的 LLM 工具，模型可在对话中自行调用，用户不需要
输入命令。工具返回纯文本，交给用户的方式由 `llm_tool_output_mode` 决定，见[输出方式](#输出方式)。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `game` | string | 游戏名称、Steam appid 或 Steam 商店链接 |
| `mode` | string | `summary`（默认）、`history`、`regions`、`info`、`detailed_info` |
| `country` | string | 可选地区，如 `CN`、`US`、`香港`；仅 `summary` 与 `history` 生效 |

- 参数是结构化的，不需要 `-地区` 前缀或 `--` 终止符；`country` 直接填 `CN` 或 `中国`。
- `mode` 容错：大小写、`-`／空格分隔和常见别名（`global`、`basic`、`details` 等）会自动归一。
- 查询失败时返回 `查询失败：<原因>` 文本，由模型决定是否改写游戏名后重试。
- 与命令共用同一套 Steam／小黑盒客户端、超时时间和默认地区配置。
- 工具启停由 AstrBot 面板「工具」页和人设工具列表统一管理，命令查询仍可独立使用。
- 使用全部工具的人设会新增此查询能力，模型可在对话中决定是否调用。

> [!IMPORTANT]
> 如果人设（Persona）里配置了工具白名单，必须把 `steam_price_query` 加入该人设的工具列表，
> 否则模型看不到这个工具。人设没有配置工具列表（即使用全部工具）时不受影响。
> 另外，人设提示词里如果有「不要调用工具」这类禁令，也会让这个工具永远不被触发。

### 输出方式

`llm_tool_output_mode` 决定工具结果怎么交给用户：

| 取值 | 行为 | 是否继续请求模型 | 用户看到 |
| --- | --- | --- | --- |
| `model`（默认） | 结果作为工具返回值进入下一轮模型请求，由模型总结 | 是 | 模型组织的回复，数字可能有改写 |
| `direct` | 工具内直接发送格式化文本，并结束整个 Agent Loop | 否 | 格式化查询结果 |
| `both` | 工具内直接发送格式化文本，同时把结果回给模型继续分析 | 是 | 格式化查询结果和模型后续回复 |

- `direct` 成功发送后会结束整个 Agent Loop，不再请求模型继续分析，适用于单次查询。
- `both` 附带内置的平台通用提示，告知模型结果已发送，并可结合用户问题继续分析；提示不能保证模型不重复数据。
- 实际模型调用次数还受名称校正、重试和多个工具调用影响，不能按输出方式固定计算。
- 直接发送失败（如协议端掉线）时会自动退回 `model` 行为，把文本交回模型转述。
- 输出方式仅作用于模型工具，命令查询仍直接返回格式化结果。

选择建议：

- 单次查询，希望直接取得格式化数据：用 `direct`。
- 多游戏比较、值不值得买等需要结合上下文分析的问题：建议用 `model`。
- 希望先收到格式化数据，再由模型继续分析：用 `both`，但模型可能重复已发送的内容。

示例对话：

```text
用户：艾尔登法环现在多少钱，值不值得等打折？
模型：(调用 steam_price_query，game=艾尔登法环, mode=summary)
```

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
| `llm_tool_output_mode` | `model` | 工具结果输出方式：`model`/`direct`/`both` |
| `llm_provider_id` | 空 | 可选的游戏名与未知中文地区校正模型 |
| `llm_name_retry_count` | `3` | 首次校正失败后的额外 LLM 重试次数 |

选择 LLM 后，首次 Steam 名称搜索前会进行一次校正；未匹配时最多再调用
`max(llm_name_retry_count, 0)` 次。配置为 `0` 或负数时仍保留首次调用。
appid 和商店链接不会校正游戏名，只有未知中文地区可能触发 LLM。

## 数据与限制

- 当前价格优先使用 Steam 商店公开接口；Steam 商店不可达时可使用小黑盒价格兜底。
- 游戏资料来自 Steam 商店公开接口。
- 历史价格和全球区价来自小黑盒公开接口。
- 小黑盒未为本插件提供正式 API，接口变化可能导致部分查询暂时不可用。
- Steam 商店不可达时会在结果中注明数据来源；游戏名可使用此前取得的缓存。
- 促销起止时间由历史价格变化点推导，不代表 Steam 公布的精确截止时间。
- 插件不接入 ITAD，不需要 Steam Web API Key，也不会持久化查询内容。
- 只有选择 `llm_provider_id` 后，名称与地区校正请求才会发送给对应模型。
- 工具由当前会话模型发起；`model` 与 `both` 会将查询结果作为工具返回值交给当前模型。
  `direct` 成功发送时不再把结果交回当前模型，但名称与地区校正仍可能调用配置的 LLM。
- 价格仅供参考，购买前请以实际结算页面为准。

## 开发

```bash
python -m pip install -r requirements.txt ruff pyyaml
ruff check .
ruff format --check .
python -m unittest
python -m compileall -q __init__.py main.py models.py api_clients.py name_correction.py price_analysis.py steam_price.py
```

`tests/test_llm_tool_output.py` 用替身模块模拟 AstrBot 运行时，因此不安装 AstrBot
也能测试工具的三种输出分支；其余测试只依赖 `httpx` 和 `pyyaml`。

市场发布和人工检查步骤见 [PUBLISHING.md](PUBLISHING.md)。

## License

代码使用 [MIT](LICENSE) 许可证。`logo.png` 是小黑盒标识，不属于 MIT 授权范围；
详情见 [NOTICE.md](NOTICE.md)。本项目是非官方社区插件，与 Steam 或小黑盒不存在隶属或背书关系。
