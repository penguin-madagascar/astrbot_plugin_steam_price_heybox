# AstrBot 小黑盒 Steam 价格查询

一个无需 API Key 的 AstrBot 插件，通过 Steam 商店搜索和小黑盒公开接口查询游戏价格。

## 功能

- 支持游戏名、Steam appid 和 Steam 商店链接。
- 查询指定地区的当前价格、历史最低价和近期价格变化。
- 补充小黑盒全球区价与小黑盒商城价格。
- 支持国区、美区、港区、日区、乌克兰区等常用地区名称或代码。
- 仅使用 Python 标准库，无额外运行时依赖。

本插件直接使用小黑盒价格数据，不依赖 IsThereAnyDeal、Steam Web API Key 或大模型。AstrBot 中已有的通用 Steam 价格插件覆盖价格和史低查询；本插件的定位是补充小黑盒历史数据与小黑盒商城价格。

## 安装

在 AstrBot 管理面板的插件页选择从 GitHub 仓库安装，并填写：

```text
https://github.com/penguin-madagascar/astrbot_plugin_xiaoheihe_price
```

也可以将仓库克隆到 AstrBot 的 `data/plugins/astrbot_plugin_xiaoheihe_price` 目录，然后重启 AstrBot 或重载插件。

## 命令

```text
/steamprice <游戏名|Steam appid|Steam 链接> [地区]
```

示例：

```text
/steamprice 艾尔登法环
/steamprice 730 CN
/steamprice https://store.steampowered.com/app/1245620/ US
```

可用别名：`/xhhprice`、`/heyboxprice`。所有命令名均为英文，游戏名和地区参数仍支持中文。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `timeout_seconds` | `15` | HTTP 请求超时时间，单位为秒 |
| `default_country` | `CN` | Steam 商店搜索区域 |
| `default_language` | `schinese` | Steam 商店搜索语言 |
| `default_history_country` | `CN` | 未指定地区时查询的历史价格区域 |
| `history_days` | `720` | 历史价格查询天数 |
| `global_price_limit` | `10` | 未指定地区时最多显示的全球区价数量 |
| `show_api_links` | `false` | 是否在回复中显示接口链接 |

## 数据与限制

- 游戏名解析使用 Steam 商店搜索接口；价格与史低数据来自小黑盒公开接口。
- 小黑盒并未为此插件提供正式 API，接口变化可能导致查询暂时不可用。
- 价格仅供参考，购买前请以 Steam 或小黑盒实际结算页面为准。
- 查询内容会发送到 Steam 和小黑盒的接口，不会由插件持久化。

## 开发

```bash
python -m unittest
python -m compileall .
```

## License

[MIT](LICENSE)
