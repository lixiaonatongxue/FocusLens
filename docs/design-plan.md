# 焦点时间统计器（FocusLens）完整开发方案

## 1. 一句话定位

100% 本地的 Windows"屏幕使用时间"：自动记录你在每个应用上花的时间，每天生成一张可分享的日报卡片——今天写了几时代码、刷了几时视频，一目了然。

## 2. 痛点与卖点

**痛点**
- iPhone 有"屏幕使用时间"，Windows 没有对等物；用户对"我这一天到底花哪了"有真实好奇
- RescueTime 是云服务+订阅制，隐私敏感用户不接受
- 现有开源方案（ActivityWatch 等）对中文应用/网站识别弱、上手繁琐

**核心卖点（按优先级）**
1. **隐私优先**：纯本地、零网络请求、数据可一键清除——开源让这句话可被验证
2. **开箱即用的中文规则库**：微信/QQ/钉钉/网易云音乐/B 站网页/知乎网页…装完即正确分类，规则库接受社区 PR（长期护城河）
3. **可分享的日报卡片**：漂亮的时间线 + 类别占比图，自带传播属性
4. **极轻**：常驻内存 < 50 MB，无弹窗打扰

## 3. 合规边界

- 只读取当前前台窗口信息（进程名/窗口标题），这是普通桌面 API，无涉法律问题
- 不做键盘记录、不截屏、不上传
- 唯一要注意的产品伦理：这是"自己的时间统计器"，README 明确不建议装在他人电脑上

## 4. 功能规划

### MVP（v0.1）
| 编号 | 功能 |
|---|---|
| F1 | 前台应用采集：事件驱动监听窗口切换，记录（应用, 标题, 起止时间） |
| F2 | 空闲识别：键鼠无输入超 5 分钟记为"离开"，不计入任何应用 |
| F3 | 分类规则引擎：进程名/窗口标题正则 → 类别（开发/浏览器/IM/视频/游戏/工具/摸鱼） |
| F4 | 今日报告页：24h 时间线条 + 类别占比环图 + Top5 应用 + 专注时段统计 |
| F5 | 历史查看：按日/周聚合 |

### v0.2
- 日报卡片导出为图片（复用"年报美学"，传播钩子）
- 浏览器网站级分类：靠窗口标题关键词（"Bilibili""知乎""GitHub"在标题里"）细分浏览器时间
- 摸鱼预警：可开关的每日提醒"今天已在视频类应用花费 X 小时"

### v1.0
- UWP 应用正确识别（见技术点 4，Windows 深度适配的差异化）
- 托盘常驻 + 开机自启 + SQLite 数据库一键导出 CSV/清除
- 周报/月报页

## 5. 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 采集 | Python + ctypes/pywin32 调 Win32 API | MVP 最快路径 |
| 存储 | SQLite | 单文件、好备份 |
| 界面 | FastAPI + Vue3 本地 web（同前两个项目架构，技术复用） | |
| 图表 | ECharts | 时间线/环图/treemap 全覆盖 |
| 打包 | PyInstaller → v1.0 可用 Rust/Tauri 重写采集器做轻量常驻 | |

> 若你对前端熟，也可直接 Tauri 2 起步（采集用 Rust 的 `windows-rs`），一步到位获得小体积安装包。MVP 建议先 Python 验证产品。

## 6. 架构与数据设计

```
focuslens/
├── agent/
│   ├── collector.py    # SetWinEventHook + 轮询兜底 + 空闲检测
│   ├── classifier.py   # 规则引擎（进程名/标题正则 → 类别）
│   └── store.py        # SQLite 写入
├── rules/
│   ├── apps.json       # 进程名规则库（内置 100+ 常见中文应用）
│   └── sites.json      # 窗口标题网站规则（B站/知乎/微博/GitHub...）
├── server.py           # FastAPI 报表接口
└── web/                # 今日卡片 / 历史页 / 设置页
```

**SQLite 表**

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  start_ts INTEGER,      -- epoch 秒
  duration INTEGER,      -- 秒
  exe TEXT,              -- 进程名，如 Code.exe
  title TEXT,            -- 窗口标题（受隐私开关控制，可仅存哈希或留空）
  category TEXT          -- dev/browser/im/video/game/idle/other
);
```

**apps.json 规则形态**

```json
[
  {"match": {"exe": ["Code.exe", "idea64.exe", "pycharm64.exe"]}, "category": "dev"},
  {"match": {"exe": ["WeChat.exe", "QQ.exe", "DingTalk.exe", "wxwork.exe"]}, "category": "im"},
  {"match": {"title": ["哔哩哔哩", "bilibili", "知乎", "微博"]}, "category": "browse-fun"},
  {"match": {"title": ["淘宝", "京东", "拼多多"]}, "category": "shopping"}
]
```

## 7. 关键技术点

**（1）采集：事件驱动 + 轮询兜底**
- 主：`SetWinEventHook(EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT)` 收窗口切换事件，精度高、几乎零 CPU
- 兜底：每 2 秒 `GetForegroundWindow()` 轮询一次，防漏事件
- 进程名：`OpenProcess` + `QueryFullProcessImageNameW`；标题：`GetWindowTextW`
- 会话切分：前台窗口/进程变化即结束上一段、开新一段；睡眠/锁屏（`WM_WTSSESSION_CHANGE`）直接封段

**（2）空闲检测**
`GetLastInputInfo()` 返回上次键鼠输入时间，与当前 tick 差值 > 5 分钟（可配）判定离开，该段时间标记为 `idle`，报表单列。

**（3）浏览器细分**
Chrome/Edge 的窗口标题含页面名（如 "xxx - 哔哩哔哩"），用 `sites.json` 标题关键词匹配到网站级；匹配不到归入"浏览器-其他"。可另写一份《如何为本项目添加网站规则》CONTRIBUTING 指南，降低 PR 门槛。

**（4）UWP 应用识别（v1.0 差异化技术点）**
UWP 应用（计算器、照片、设置等）宿主进程都是 `ApplicationFrameHost.exe`，需要 `GetApplicationUserModelId` 才能拿到真实应用身份——这是市面上轻量工具普遍没做好的细节，做好了就是"Windows 深度适配"口碑。

**（5）隐私开关分级**
- 默认：只存进程名 + 类别，不存标题
- 进阶：存标题（本地）
- 极致：只存标题哈希（用于区分同类应用不同文档，但不可回读）
设置页提供数据清除按钮，README 与代码双重可见。

## 8. 开发路线图（三个周末）

| 周末 | 交付 |
|---|---|
| W1 | collector + classifier + SQLite + CLI 周报（先命令行看数据，最快验证采集正确性） |
| W2 | web 端今日卡片 + 规则库初版 100 条 → **发布 v0.1** |
| W3 | 日报卡片导出图 + 托盘常驻/自启 + README → v0.2 |

## 9. 开源运营

- **命名候选**：FocusLens / TimeOn / 屏迹（repo 英文名 + 中文副标题）
- README 必放：一张真实"我的一天"卡片截图（这是点击 star 的瞬间）+ 隐私声明（零网络请求，可搜代码验证）
- **规则库共建**：`apps.json`/`sites.json` 接受 PR，贡献门槛极低（加一行 JSON），是持续获得 star 与 contributor 的飞轮
- 投放：HelloGitHub、V2EX、少数派、知乎"电脑屏幕使用时间"相关问答
- License：MIT

## 10. 竞品与差异化

| 竞品 | 情况 | 差异 |
|---|---|---|
| RescueTime | 云服务、订阅 | 100% 本地免费 |
| ManicTime | 付费 | 免费开源 |
| ActivityWatch | 开源全平台、功能全 | 更轻、中文规则库开箱即用、日报卡片好看、Windows 深度适配（UWP） |
| Tockler 等 | 维护弱 | 活跃维护 + 社区规则库 |

> 与 ActivityWatch 正面撞型，立项前建议花半天用它实际一天，把"不好用的点"列成本项目的需求清单——竞品即需求池。

## 11. 风险清单

| 风险 | 应对 |
|---|---|
| PyInstaller 打包体积大、常驻感笨重 | v1.0 用 Rust/Tauri 重写采集端；或先接受 MVP 体积 |
| 标题关键词误判（页面名不含站名） | 规则库持续完善 + "其他"兜底 + 用户自定义规则 UI |
| 虚拟桌面/多显示器切换事件 | W1 实测补齐，属工程细节非架构风险 |
| 用户对"后台记录"天然警惕 | 隐私分级开关 + 零网络请求 + 开源可审计，README 首屏讲透 |
