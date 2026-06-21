# AstrBot 市场发布

## 发布前检查

1. 确认 `main` 已推送，GitHub Actions 全部通过。
2. 确认 `metadata.yaml` 的 `name`、`author`、`desc`、`repo` 与提交 JSON 完全一致。
3. 确认仓库为 public，根目录包含 `main.py`、`metadata.yaml` 和 `requirements.txt`。
4. 确认 release zip 小于 16MB，并使用最新 AstrBot `master` 完成插件加载 smoke test。
5. 创建并推送 `v1.2.1` 标签和 GitHub Release。

## 手动提交

1. 打开 <https://plugins.astrbot.app>，点击右下角 `+`。
2. 填写以下信息：

```json
{
  "name": "astrbot_plugin_steam_price_heybox",
  "display_name": "Steam 价格查询（小黑盒）",
  "desc": "无需 API Key，查询 Steam 游戏当前价、历史最低价、促销记录、小黑盒跨区价格与游戏资料。",
  "author": "penguin-madagascar",
  "repo": "https://github.com/penguin-madagascar/astrbot_plugin_steam_price_heybox",
  "tags": ["Steam", "价格查询", "史低", "小黑盒"],
  "social_link": "https://github.com/penguin-madagascar"
}
```

3. 点击 `提交到 GITHUB`，进入
   [AstrBot_Plugins_Collection](https://github.com/AstrBotDevs/AstrBot_Plugins_Collection)
   的发布 Issue。
4. 核对标题为 `[Plugin] astrbot_plugin_steam_price_heybox`，JSON 没有尾随逗号。
5. 勾选完整测试、无恶意代码和行为准则三个选项，然后创建 Issue。
6. 不要重复创建 Issue。若审核要求修改，在插件仓库修复并推送后于原 Issue 说明。
7. 等待 `astrbot-plugin-copybara` 同步并自动合并 PR；以“该插件已上架”评论为准。
8. 市场出现条目后，在干净 AstrBot 实例中安装并验证五种命令模式。

官方文档：<https://docs.astrbot.app/dev/star/plugin-publish.html>
