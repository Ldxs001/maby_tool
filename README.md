# Maby Tool

> **用户工具仓库** — 由 git-sync 同步维护。
> 最后更新：2026-10-15

本仓库托管 wUwproject 工具项目，Gitee 与 GitHub 双平台同步。

---

## 工具列表

| 工具名 | 版本 | 描述 |
|--------|------|------|
| `MarkdownEditor` | v1.1.0 | 本地 Markdown 编辑器：单页编辑 + 实时预览（KaTeX 公式、图片三写法、分块增量渲染）、排版面板（字体/字号/对齐/公式/表格样式）、分页导出（Paged.js，纸张/页边距/页码/自动目录）、本地后端（文件读写、图片代理、字体枚举、版本自愈）。内嵌便携 Python 运行时，双击即用。 |

---

## 演示

<video src="https://github.com/user-attachments/assets/98d178ba-e74f-4129-adf5-ae05333df098" controls width="680"></video>

*▲ 演示视频（51 秒）：GitHub 端上方为内嵌播放器；若未加载，[点此到 Release 页播放](https://github.com/Ldxs001/maby_tool/releases/tag/v1.1.0)*

▶ **备用观看**：[GitHub（Release 页在线播放）](https://github.com/Ldxs001/maby_tool/releases/tag/v1.1.0) ｜ [Gitee（直接下载）](https://gitee.com/wUwproject/maby_tool/releases/download/v1.1.0/MDEditor-intro.mp4)

---

## 目录结构

```
maby_tool/
└── MarkdownEditor/
    ├── markdown-editor.html    # 编辑器单页（HTML/CSS/JS 全内联）
    ├── md_server.py            # 本地 HTTP 后端
    ├── md_launch.pyw / md_app.pyw / md_assets.py
    ├── install.cmd / uninstall.cmd / desktop-shortcut.cmd
    ├── katex/                  # 公式渲染（KaTeX 发行版）
    ├── pagedjs/                # 分页排版（Paged.js）
    ├── python/                 # 内嵌便携 Python 运行时
    ├── LICENSES/               # 第三方组件许可全文
    └── LICENSE                 # 工具本体：GNU AGPL-3.0
```

---

## 许可

- **MarkdownEditor**：GNU AGPL-3.0-or-later（Copyright (C) 2026 wUwproject），完整文本见 `MarkdownEditor/LICENSE`
- 随附第三方组件（KaTeX、Paged.js、Python）按其原始许可证分发，全文见 `MarkdownEditor/LICENSES/`

## 维护说明

- 本仓库由 **git-sync** 技能同步维护（筛除 → 脱敏 → 提交 → 双端推送）
- 仅同步工具运行所需文件；过程/缓存/测试/宣传材料不入库


https://github.com/user-attachments/assets/148ee88c-5c17-4dc2-a6ea-a867624635cb

