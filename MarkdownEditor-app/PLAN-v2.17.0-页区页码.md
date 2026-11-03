# PLAN v2.17.0 页区页码（`@@ begin page{…}`）

任务地图。确认后一口气改到底；途中出现方案外问题即停手重汇报。

## 一、语法

```
@@ begin page{noll}
前言部分，不印页码
@@ end page

@@ begin page{i}
序，小写罗马 i ii iii
@@ end page

@@ begin page{1}
正文，阿拉伯数字从 1 起
@@ end page
```

参数只认四种：`noll`、`1`、`i`、`I`。区域外的文档仍按 v2.16.0 原样（阿拉伯、全文连续、纯目录页不计号）。

## 二、三方语义（定稿）

| 占位符 | 区域外 | 区域内 |
|---|---|---|
| `{p}` | 全文阿拉伯连续号 | 区内序号，形态随区（`1`→`3`、`i`→`iii`、`I`→`III`）；`noll` 区不印 |
| `{P}` | 全文可编号页数（不含纯目录页） | **一字不变，同左** |
| `{N}` | 同 `{P}` | **本区总页数**（`noll` 区无意义，不印） |

- 一个记号一个定义。`{N}` 是新增的、唯一承载「本区总页数」的记号，`{P}` 的含义永不被页区改写。
- 区域内 `{P}` 报全文页数 —— 前言页会印出 `ii / 共 20 页`；要 `ii / 共 v 页` 就写 `{p} / {N}`。
- `noll` 区的页**计入** `{P}`（它物理存在，只是不印号）；不计入任何 `{p}` 序列。

## 三、边界（全部 fail-closed）

| 情形 | 行为 |
|---|---|
| 区域起止 | 两端都 `break-before/after:page`，一页只属一个区 |
| 区域是文档最后一块 | `break-after` 由 `.page-region:last-child{break-after:auto}` 撤掉，不出空尾页；端到端验证 |
| 区域嵌套 | 不支持。内层 `begin`/`end` 两行都原样保留为正文（对称，不吞内容） |
| 未闭合 `@@ end page` | 标记行原样露出，其后内容照常渲染 |
| 参数非法（`{x}`、`{}`、`{ll}`、无参数） | 标记行原样露出 |
| 区域落在纯目录页 | 目录页仍不编号、不占区内序号（skip 优先于页区） |
| 预览 / 导出 HTML | 无页概念，按普通块渲染（导出 HTML 保留 break 规则） |
| docx | 不动（本来无页眉页脚） |

## 四、改动点位

| # | 文件 | 位置 | 内容 |
|---|---|---|---|
| 1 | `markdown-editor.html` | `PARSER_START` 段，`@@ begin full` 之后（约 1678 行） | 新块级指令，输出 `<div class="page-region" data-pn data-pr-id>`；模块级 `_pgRegSeq` |
| 2 | `markdown-editor.html` | 预览 CSS（约 224 行 `.full-page` 后） | `.page-region{margin:1.5em 0;}` 普通块 |
| 3 | `markdown-editor.html` | 面板 585 行 + I18N | 模板说明补 `{N}`，中英各一条 |
| 4 | `md_server.py` | `PAGED_FILLER_TMPL` | `toRoman`、按页取区档、`{p}/{P}/{N}` 三路渲染、目录回填改「该页显示串」 |
| 5 | `md_server.py` | `build_paged_html` 分页 CSS | `.page-region{break-before:page;break-after:page;}` + `:last-child` 撤尾断 |
| 6 | `md_server.py` | `build_standalone_html` CSS | 同上（导出 HTML 保留断页语义） |
| 7 | `md-parser.js` | 重抽 | `python _extract_parser.py` → `_test_parser_sync.py` PASS |
| 8 | 新增测试 | | 解析 8 项、页码映射（罗马边界 1/4/9/40/399）+ 区域映射 10 项、端到端 PDF 页数 4 项 |

## 五、罗马数字转换

标准减法对：`M CM D CD C XC L XL X IX V IV I`。验证边界：`1→i`、`4→iv`、`9→ix`、`14→xiv`、`40→xl`、`90→xc`、`399→cccxcix`、`1000→m`。大写档同表转大写。

## 六、不做

- 不做「区域外默认档可配」（全文默认仍是阿拉伯）
- 不做 docx 页码
- 不做嵌套
- 不改 `{P}` 一个字节

## 七、版本

`v2.17.0`（新语法，minor）；`MD_SERVER_VERSION` 107 → 108。
