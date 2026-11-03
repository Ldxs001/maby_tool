# 任务地图：列表标记外凸 + `- [ ]` 归队 + 中英双语（v2.14.0 / v2.15.0）

> 本文件是施工方案，不是交付物。确认后按阶段推进，阶段内一口气做到底；
> 途中出现方案外问题则停手重汇报。基准版本 v2.13.5（提交 718f90c）。

---

## 0. 本轮决策留档

| 事项 | 决策 | 依据 |
|---|---|---|
| 折叠语法 | **不做** | 风险大（打印必须展开、5 条链路）、收益不确定 |
| 列表标记 | **改为外凸（`list-style-position: outside`），做成开关，默认关** | 现有 inside 是 v2.1 为 `<<<` 继承链定的口径，直接改默认会让存量文档全部变样 |
| `- [ ]` | 保留原生 `<input>`，但**删掉离群负 margin**，跟随列表几何 | 用户指认它是所有列表里唯一不听缩进档的特例 |
| `<<<` / 正文段落缩进 | **不动** | 正文是 `text-indent` 型（只作用首行），与列表容器几何无关 |
| EN 界面 | 短标签（TS / AI / Run / Save / As…） | 工具栏 14 按钮 + 12 格式位，全称会溢出；说明里注明一次 |
| 指南 | 速查表加 EN 列 + 版权全文双语 + 开头 12 行 EN「At a glance」，正文不译 | 全文双语 = 28594 字符 ×2，每改一条规则写两遍，漂移风险高 |

---

## 1. 列表外凸（阶段 A，v2.14.0 主体）

### 1.1 现状（代码锚点）

| 事实 | 位置 |
|---|---|
| 列表定位两分支都写死 `list-style-position: inside` | `markdown-editor.html:3951` / `3954` |
| 档位 = `margin-left: N px`，容器 `padding-left: 0` 收编归零 | 同上 |
| `li.task` 自带 `margin-left: -1.4em`（离群根源） | `165` |
| tsCss 经 `#ts-style` 进打印（`3087`/`3091`/`3424`）与 HTML 导出（`3713`） | 自动覆盖，无需另写 |
| docx 的 `_prep_list_abstract()` 按 inside 同构写死（每个 li 显式 `left_indent`） | `docx_export.py:343–359` |

### 1.2 目标几何

档位语义**不变**：`margin-left: N` 仍然定位 **marker 左沿**（现在 inside 时 marker 左沿 = 容器 padding 边 = 档位；
outside 时 marker 画在 padding 区，marker 左沿 = padding 左沿 = 同一个 x）。
所以开开关后 **marker 位置一动不动，只有文字块右移一个 marker 槽**，续行自然落到首行 □ 的 x。

```
关（inside）           开（outside）
1. □xxxx               1. □xxxx        ← marker x 不变
□zzzz  ← 缩到 1. 下面      □zzzz        ← 与首行 □ 齐
```

### 1.3 改动点位（4 处）

| # | 文件 | 改动 |
|---|---|---|
| A1 | `markdown-editor.html` `tsCfg`（约 3843–3860） | 新增 `o.listHang=!!(raw.listHang)`，随 `TS_KEY` 持久化，默认 `false` |
| A2 | 同上，`applyTypeset` 列表分支（3951/3954） | 拆成四态：`{inside, outside} × {无档位, 有档位}`；outside 时容器加 `padding-left: 2em !important`（marker 槽，跟随列表自身字号）；两处 `list-style-position` 由常量改按 `listHang` 取值 |
| A3 | 同上，`165` | `.markdown-body li.task{list-style:none}`，删 `margin-left:-1.4em` |
| A4 | 同上，排版面板（546–548 之间） | 「引用块」行之后、「列表」行之前插一行：`<label>列表标记外凸</label><input type="checkbox" id="tsHang">` + 事件绑定与回填 |

> **顺序铁律**：outside 规则必须写在同一段 tsCss 的**末尾**。`!important` 同级按源序，主 CSS 的
> `padding-left:1.6em` 与这里同权重，写前面会被盖掉（v2.13.2 统一段间距踩过同一个坑）。

### 1.4 已知行为变更（要写进 CHANGELOG）

1. **开关开启后，嵌套列表首次出现视觉缩进**：`padding-left:2em` 逐层叠加，而现状是 `padding-left:0` 收编 →
   嵌套层此前只靠 marker 形状区分、无水平缩进。开开关后 2 层 +2em、3 层 +4em。
2. **`- [ ]` 项右移 1.4em**（删负 margin 的直接结果），从此与兄弟项同列。
3. **关闭开关时**：现有文档（简历等）应逐字节不变 —— 验收项。

### 1.5 档位与槽宽是两把尺（有意为之，禁止后人"修正"）

- 档位 = px，按**正文字号**换算（`indBase`，`3910–3920`），保证跨元素同一把尺；
- marker 槽 = `2em`，跟**列表自身字号**（`data-tssz="li"` 可单独设磅值）——槽必须包住 marker 字形本身，
  跟着 marker 走才是对的。两把尺在这里不是缺陷。

### 1.6 验收（缺一不可）

| 项 | 判据 |
|---|---|
| 关态零影响 | 真实简历 `个人工作简历2026.md` 走预览 + `/api/export-paged`，产物与 v2.13.5 逐字节比对（除版本戳） |
| 开态几何 | 注入 `window.__IND_PX__={p:0,quote:0,li:32}` 后 `render(true)`；量 `li` 内容左沿与首行文本 Range 左沿，开启后二者差 = 2em，marker 左沿与开启前**同一 x**（误差 ≤0.5px） |
| 续行对齐 | `1. □xxxx` + 续行 `□zzzz`：两个 □ 的 `getBoundingClientRect().left` 相等 |
| 编号接力 | 开态下 `1..12` 连续、`start=` 正确（`_test_v2132_rules.cjs` 46 条全过） |
| 打印 | Paged.js 三页、`_slice` 条带 0 条、`fill-row` 4 处，与 v2.13.5 一致 |
| HTML 导出 | 导出件内 tsCss 含 outside 规则、浏览器打开几何一致 |
| docx | 见 3.3 |
| 无回归 | `_test_parser_sync.py` PASS（本阶段不触解析器）、95 项方言回归、`_test_v213_matrix.cjs`、`_test_list_parse.py 20/20`、`_test_splitblocks_wrap.cjs 20/20` |

---

## 2. 正文 / `<<<` 不动（确认项）

用户记忆正确，落成文字存档：

- 正文「首行缩进」= `text-indent: Npx`（`3930`），**只作用块的首行**，与列表几何无交集；
- 正文「悬挂缩进」= `padding-left + 负 text-indent`（`3934`），同样只在段落内部；
- `<<<` 只管**容器级** `margin`（`1489–1516`），不碰内部列表的 `list-style-position`。
- 结论：本方案的开关**只改 `ol/ul` 的定位与内边距**，段落与 `<<<` 行为逐字节不变（验收里加一条）。

---

## 3. docx 同步（阶段 A 的硬依赖，不能拖）

### 3.1 为什么要改

`docx_export.py:343` 的 `_prep_list_abstract()` 明确按 `list-style-position:inside` 同构建模
（每个 li 段落显式写 `left_indent`）。预览改 outside 而 docx 不动，就是"Word 与预览不一致"，
这是用户反复吃过亏的一类问题。

### 3.2 改法

`_prep_list_abstract()` 增加 outside 分支：
`left_indent = 档位 + 槽宽`，`first_line_indent = -槽宽`（Word 的悬挂语义），
`li.task` 走"无编号、无负数悬挂"，与预览同构。

### 3.3 验收

- `_test_docx_export.py` 40/40、`_test_v213_docx.py` 全过；
- python-docx 读回 `left_indent` / `first_line_indent` 断言与 tsCss 推算值一致；
- LibreOffice 转 PDF 后量首行与续行 x 差 = 0（悬挂成立）。

### 3.4 顺手补（可选，10 行）

`<input type="checkbox">` 在 docx 里目前会被丢弃 → Word 里头没有框。加一个分支输出 `□` / `☑` 文本。
预览侧保持原生复选框不变（用户已确认"原生不原生无所谓"）。

---

## 4. 中英双语（阶段 B，独立成版 v2.15.0）

### 4.1 规模实测

| 层 | 量 |
|---|---|
| 静态界面（标签 + 属性） | **215 条**：排版 61、AI 36、run 24、举报 15、保存 11、批注 9、改写 7、工具栏+状态栏 50 |
| 脚本内中文串（去重） | **494 条**，其中短串（≤14 字）为提示/选项/对话框，长串多为错误详情 |
| 合计 | **709 条**；中文总字符 17672 |

**必翻集** ≈ 400 条（静态 215 + 脚本短串）；**不翻集** ≈ 100 条（技术错误详情、日志、low runner 代码模板、AI 提示词）。

### 4.2 架构

- 字典**内联进 html**（不新增路由、不新增文件，保持单文件自包含）：`var I18N={zh:{...},en:{...}}`。
- 静态节点：`data-i18n`（text）/ `data-i18n-title`（title）/ `data-i18n-ph`（placeholder），`applyLang()` 统一刷。
- 脚本串：`T('key', [参数])`，禁止拼接整句（英文语序不同）；确实拼接的用 `{0}` 占位。
- 切换入口：状态栏 `▶ 运行` 右侧 `<button id="btnLang">EN</button>`，`localStorage['mde.lang']`，默认 `zh`；
  切到 EN 后需 `render(true)` 重渲染一次（图/表编号前缀属于产物串）。
- 服务端 `runtime/ui-settings.json` 另存副本那一份（同排版档的两副本坑）需同步，避免重装后语言回弹。

### 4.3 产物串（漏了就是露馅）

| 串 | 位置 |
|---|---|
| `目 录` | `md_server.py:3215` |
| `图 ` / `表 ` 编号前缀 | `markdown-editor.html:2680` |
| 页码 / 页眉文案 | paged 模板 |
| 导出 HTML `<html lang>` | 按当前语言写 `zh-CN` / `en` |
| docx 题注前缀 | `docx_export.py` |

### 4.4 验收

- 两态截图：中文态与 v2.13.5 像素级一致（同样式位）；英文态无截断、工具栏单行不换行（1366×768 与 1920×1080 各测一次）。
- 全仓 grep：EN 态下界面区域不残留中文（白名单：文档内容、代码模板、错误详情）。
- 语言持久化：切 EN → 关窗重开 → 仍 EN。
- 既有测试：断言中文文案的用例（`_test_export_ui` / `_test_list_ui` / `_test_lr_*` 等）逐条改为按 key 断言或双语兼容。

### 4.5 风险

英文变长是本阶段唯一真风险（`排版→Typeset`、`另存为→Save As…`）。规则：**按钮类一律 ≤4 字符**
（TS / AI / Run / Save / As… / PDF），长文案走 title 提示。

---

## 5. 文档（跟每阶段一起做，不单独排期）

- 使用指南：「十七、语法速查」表**加一列 EN**（同表同源，不另起一节，避免两套漂移）；
  开头插 12 行 EN「At a glance」（打开 / 保存 / 导出 / `@@` 家族 / run）；
  正文补「列表标记外凸」小节（含开关位置、嵌套缩进变化、`- [ ]` 归队说明）；
- `版权与开源组件声明.md`：全文双语（48 行，法律文本常双写）；
- CHANGELOG：按体例分组（新增 / 变更 / 修复 / 文档 / 测试），行为变更单独标出。

---

## 6. 发版

| 阶段 | 版本 | 内容 |
|---|---|---|
| A | **v2.14.0** | 列表外凸开关 + `li.task` 归队 + docx 同步 + 指南补节 + 速查表中文行 |
| B | **v2.15.0** | 中英双语（界面 + 产物串）+ 速查表 EN 列 + 版权双语 + EN At a glance |

每版收尾：`MD_SERVER_VERSION` 按需 +1（A 阶段服务端零改动则不动）→ 重打 `MDEditor-Setup-vX.exe`（**不碰 MSIX**）
→ 两端 Release 挂 exe → 工作区日志。

---

## 7. 待确认

1. **拆两版（A→v2.14.0，B→v2.15.0）**，还是合成一版一起发？建议拆：A 是纯几何改动、可当天验完发；
   B 动 700+ 文案，回归面大，混在一起出问题难定位。
2. docx 里 `- [ ]` 补 `□/☑` 字符（3.4，10 行）做不做。
