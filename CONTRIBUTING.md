# 贡献指南：为规则库添加一条规则

FocusLens 最重要的社区资产是中文应用/网站规则库。加一条规则 = 加一行 JSON，这是门槛最低、价值最高的 PR。

## 规则格式

### 应用规则 `rules/apps.json`

```json
{"match": {"exe": ["进程名.exe"]}, "category": "dev", "name": "显示名"}
```

- `match.exe`：进程名精确匹配（不分大小写），一个应用有多个进程可写进同一个数组；
- `category`：见下表；
- `name`：可选，报表里的显示名；不填时回退为进程名。

### 网站规则 `rules/sites.json`

只对浏览器（Chrome/Edge/Firefox/360/QQ浏览器…）生效，按窗口标题关键词细分：

```json
{"match": {"title": ["哔哩哔哩", "bilibili", "B站"]}, "category": "browse-fun", "name": "哔哩哔哩"}
```

- 关键词对标题做**包含匹配**（不分大小写）；同一文件**自上而下**命中即停，请把更具体的关键词放在更generic的之前；
- 选关键词时避免过于通用的词（比如不要用「设置」「首页」），以免误伤其他页面标题。

## 可用类别

| category | 含义 |
|---|---|
| `dev` | 开发（IDE、编辑器、终端…） |
| `work` | 办公（Office/WPS/笔记…） |
| `im` | 沟通（微信/QQ/钉钉…） |
| `video` / `music` / `game` | 视频 / 音乐 / 游戏 |
| `design` | 设计 |
| `browse-fun` / `browse-dev` | 浏览器里的娱乐站点 / 技术站点 |
| `ai` | AI 助手（ChatGPT/DeepSeek/Kimi…） |
| `shopping` | 购物 |
| `browser` | 浏览器（未细分时的兜底） |
| `tool` | 工具 |

新增类别需要同步改 `agent/categories.py`，普通规则 PR 不需要。

## 提交前自测

```bash
# 1) 验证你的规则能命中（--title 可选，模拟窗口标题）
.venv/Scripts/python.exe run.py classify --exe Weixin.exe
.venv/Scripts/python.exe run.py classify --exe chrome.exe --title "某个视频 - 哔哩哔哩"

# 2) 跑一遍测试（确认没破坏别的规则）
.venv/Scripts/python.exe -m unittest discover -s tests -t .
```

## 其他 PR

- 代码 PR 请附最小可复现的单元测试（`tests/` 目录，只用合成数据）；
- 任何真实个人数据（窗口标题、进程列表等）**不要**写进测试或 issue。

谢谢！
