# Maby Tool

> 本地优先的 Windows 桌面写作工具。当前版本 **v2.8.1**（2026-10-25）。
> 最后更新：2026-10-25

编辑器界面、本地后端、便携 Python 运行时与全部渲染引擎都在仓库内，解压双击即用。除 AI 润色需接本机 LLM 服务外，其余功能全部离线。

---

## 工具

| 目录 | 版本 | 状态 | 说明 |
|---|---|---|---|
| `MarkdownEditor-app/` | **v2.8.1** | 当前开发版 | 主项目。左侧写作、右侧实时渲染，内置 low runner 文档内计算 |
| `MarkdownEditor/` | v1.5.0（最后更新 2026-10-17） | 归档 | 停止更新，仅保留供追溯；功能与下载以 `MarkdownEditor-app/` 为准 |

## 核心能力

| 板块 | 内容 |
|---|---|
| 写作与渲染 | 单页编辑 + 实时预览；KaTeX 公式；四种图表围栏本地渲染（Mermaid / Graphviz `dot` / WaveDrom / Vega-Lite）；图片三种写法（网络 URL、本地路径、相对路径）与宽度 `{N}`、对齐 `c`/`l`/`r`、`@@ fill` 分栏 |
| 排版与导出 | 按元素设置字体 / 字号 / 对齐、首行与悬挂缩进、三线表；导出 `.md` / `.html` / 分页（A0–B5、页边距、页码模板、自动目录，Ctrl+P 出 PDF）/ `.docx` |
| **low runner** | 正文里写数据点，run 库在子进程里算，结果落回正文。数据走四个通道（`kv` / `vals` / `raw` / `marks`），六种数据形式，返回文本 / 表格 / 图片皆可 |
| 文档格式 | `.smd` 自包含文档（正文 + 图片单文件 ZIP 容器，改后缀为 `.zip` 即可解包，无私有格式）；`.docx` 导出为真 Word 表格与原生上下标 |
| AI | 选区润色与解释，接本地 LM Studio / Ollama，预览对照确认后才替换；AI 生成 run 库代码 |
| 工程 | 便携 Python 3.11.9（内嵌，无需安装）；版本自愈后端；运行缓存按数据哈希，数据不变不重跑 |

## low runner 速览

正文写数据点，另起一行写执行点，默认手动点一下才跑：

```markdown
示例数据在 `示例销售数据.csv`，下面把整表按 ×1.1 输出：

@@ MDE__销售{表格 == 示例销售数据.csv, 运算 == *, 数 == 1.1}

@@ MDE from csvcalc import table is 销售
```

- **数据点**：`@@ MDE_池名{…}` 显性（原地显示值）、`@@ MDE__池名{…}` 隐性（不占版面）。六种形式——单值文本、单键值对、纯值向量、键值对向量、二维表格 `:2(rxc){}`、三维表格 `:3(){}`；`(( ))` 可长在正文句子里。
- **执行点**：`@@ MDE import 库名` 吃公共池，`@@ MDE import 库名 is 池名` 只吃别名池，`@@ MDE from 库 import 函数 is 池名` 指定函数，`{global p}` 走全文 `'''p` 标记批量替换。
- **run 代码协议**：函数签名 `run(data) -> str`，结果直接替换执行点。返回 GFM 表格字符串渲染成真表格，返回 `![](x.png)` 渲染成图片——图片由 run 自己 `save()` 到子进程当前目录（即文档资产目录），框架不改名、不生成图。
- **外部文件**：从资源管理器复制 `.xlsx` / `.pdf` / `.csv` 到编辑区 `Ctrl+V`，落进本文档资产目录并在光标处插入一行数据点；执行时服务端把相对路径换成绝对路径交给 run。框架不解析文件，怎么读由 run 决定。
- **内置 run 库**（`runtime/runs/`，全部随包分发）：`stats` / `wordcount` / `mergecontent` / `auto_cite` / `tablecalc` / `csvcalc` / `plotimg`。

完整规范见 [`docs/MDEditor-2.8 发布说明与 low runner 规范.md`](MarkdownEditor-app/docs/MDEditor-2.8%20发布说明与%20low%20runner%20规范.md) 与 [`docs/low runner 数据形式规范.md`](MarkdownEditor-app/docs/low%20runner%20数据形式规范.md)。

## 演示视频

四支，1600×900 / 25fps，均为实机录屏：

| 主题 | 时长 | GitHub | Gitee |
|---|---|---|---|
| 入门总览 | 1:41 | [播放](https://github.com/Ldxs001/maby_tool/blob/main/MarkdownEditor-app/MDEditor-intro.mp4) | [播放](https://gitee.com/wUwproject/maby_tool/blob/main/MarkdownEditor-app/MDEditor-intro.mp4) |
| 语法与特殊写法 | 1:46 | [播放](https://github.com/Ldxs001/maby_tool/blob/main/MarkdownEditor-app/MDEditor-syntax.mp4) | [播放](https://gitee.com/wUwproject/maby_tool/blob/main/MarkdownEditor-app/MDEditor-syntax.mp4) |
| low runner 机制 | 2:04 | [播放](https://github.com/Ldxs001/maby_tool/blob/main/MarkdownEditor-app/MDEditor-lowrunner.mp4) | [播放](https://gitee.com/wUwproject/maby_tool/blob/main/MarkdownEditor-app/MDEditor-lowrunner.mp4) |
| **v2.8 更新** | 1:55 | [播放](https://github.com/Ldxs001/maby_tool/blob/main/MarkdownEditor-app/MDEditor-2.8.mp4) | [播放](https://gitee.com/wUwproject/maby_tool/blob/main/MarkdownEditor-app/MDEditor-2.8.mp4) |

## 文档

| 文档 | 内容 |
|---|---|
| [`使用指南`](MarkdownEditor-app/docs/MDEditor%20使用指南.md) | 16 章语法与操作手册：基础语法、列表方言、表格、公式、四种图表、图片、low runner（数据点 / 外部文件 / 执行点 / 代码协议 / 数据写作 / 完整示例 / 管理界面）、排版、缩进块、保存导出、滚动联动、批注、AI 润色、语法速查 |
| [`low runner 数据形式规范`](MarkdownEditor-app/docs/low%20runner%20数据形式规范.md) | 六种数据形式、类型契约、fail-closed 清单、全局执行、返回值渲染、外部文件引用的设计定稿 |
| [`v2.8 发布说明与 low runner 规范`](MarkdownEditor-app/docs/MDEditor-2.8%20发布说明与%20low%20runner%20规范.md) | v2.8 更新说明 + 输入输出规范（四通道、`vals` 四形状、输出四形状、图片落点与文件名一致性边界） |
| [`更新日志`](MarkdownEditor-app/CHANGELOG.md) | v1.0.0 至 v2.8.1 逐版现象 / 根因 / 修法 / 验证 |
| [`版权与开源组件声明`](MarkdownEditor-app/docs/版权与开源组件声明.md) | 第三方组件版本与许可 |

## 下载与安装

- **GitHub**：<https://github.com/Ldxs001/maby_tool/releases/tag/v2.8.1>
- **Gitee**：<https://gitee.com/wUwproject/maby_tool/releases/tag/v2.8.1>

`MDEditor-Setup-v2.8.1.exe`，32.07 MB，1203 个文件，双击安装。安装后：双击 `.md` 文件、右键 `.md` 选「Open with Markdown Editor」、或双击桌面快捷方式，三种入口任选。

> 不要直接双击 `markdown-editor.html`——`file://` 方式没有后端，页面会引导到正确入口。

## 目录结构

```
maby_tool/
├── MarkdownEditor-app/          # 当前版本（v2.8.1）
│   ├── markdown-editor.html     # 编辑器单页（HTML/CSS/JS 全内联）
│   ├── md-parser.js             # 方言解析器（由 html 内 PARSER 段抽取，字节级同步）
│   ├── md_server.py             # 本地后端：文件读写、图片代理、run 调度、导出、批注、LLM 路由
│   ├── md_launch.pyw / md_app.pyw / md_assets.py / _smd.py
│   ├── llm_client.py / rag_client.py / web_search.py
│   ├── runtime/runs/            # 内置 run 库（7 个）
│   ├── docs/                    # 使用指南、数据形式规范、发布说明、分发清单
│   ├── katex/ pagedjs/ mermaid/ viz/ wavedrom/ vega/   # 渲染引擎（全部本地部署）
│   ├── python/                  # 便携 Python 3.11.9（含 Pillow）
│   ├── installer/               # 安装包构建脚本
│   ├── CHANGELOG.md
│   └── LICENSE（AGPL-3.0-or-later）、COPYRIGHT、LICENSES/
├── MarkdownEditor/              # v1.x 归档，不再更新
└── README.md
```

## 许可

- **MarkdownEditor**：GNU AGPL-3.0-or-later，Copyright (C) 2026 wUwproject。任何人可使用、修改、再分发，但衍生作品（包括仅以网络或本地服务形式对外提供的修改版）须同样以 AGPL-3.0-or-later 开源。许可正文见 `MarkdownEditor-app/LICENSE`（FSF 原文，逐字节未改动），版权人与「or later」声明见 `MarkdownEditor-app/COPYRIGHT`。
- 随附第三方组件（KaTeX、Paged.js、Mermaid、viz-js / Graphviz、WaveDrom、Vega、Python、Pillow 等）按其原始许可证分发，全文见 `MarkdownEditor-app/LICENSES/` 与编辑器内置「版权与开源组件声明」。
- 本仓库整体同样以 AGPL-3.0-or-later 发布，声明见根目录 `COPYRIGHT`；源码文件头部均带 `SPDX-License-Identifier` 标识。

## 发布方式

提交到 `main` → 打 `vX.Y.Z` 标签 → 推送 Gitee 与 GitHub → 两端 Release 挂安装包。安装包由 `MarkdownEditor-app/installer/_build_installer.py` 构建，构建产物与 staging 目录不入库。

仓库内 `_video*/` 目录是视频合成工程（`demo.html` + `record.js` + `narration.py` + `compose.py` + 字体 + 静帧）；配音 wav、录制帧、中间视频按 `.gitignore` 排除。
