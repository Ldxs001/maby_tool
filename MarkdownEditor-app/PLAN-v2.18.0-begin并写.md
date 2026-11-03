# PLAN v2.18.0 —— `@@ begin` 并写 + 嵌套规则收敛

## 一、要解决的问题

封面／扉页的常见诉求是「**单独一页 + 不写页码**」，现在只能套两层：

```
@@ begin page{noll}
@@ begin full
封面
@@ end full
@@ end page
```

能跑（实测 3 页、封面单独起页、无页码），但四行标记、两层 div、一个块被拆成两个声明。

## 二、范围裁决（用户定）

- **并写只支持 `page` / `full` / `color`** 三个家族。
- **`fill` 不参与并写**：它要 `display:flex` 横向分栏，`full` 要 `display:flex` 纵向居中，两种布局意图不该压进同一个元素；它自带 begin/end，嵌套即可。
- 单行家族（`blank` / `caption` / 行内 `color` / `MDE`）**不并写**：没有容器，参数归属无法确定。

## 三、为什么这三个能真合并（实测依据）

| 家族 | 给容器加的东西 | 与另两个冲突 |
|---|---|---|
| `page` | `class=page-region` + `data-pn` + `data-pr-id`，`break-before/after:page` | 无 |
| `full` | `class=full-page` + `data-full-pos`，`height:页心` + `display:flex;column;justify-content` | 无 |
| `color` | `class=mde-color` + 内联 `color` | 无 |

`page` 与 `full` 的断页规则**完全重合**（都是 `break-before:page;break-after:page`），叠在同一个元素上不产生两次断页；`color` 只设颜色。

实测（同一段 body，直接喂 `build_paged_html`）：

| 写法 | 页数 | 页脚 | 封面是否单独起页 |
|---|---|---|---|
| 只 `full` | 3 | `[1] [2] [3]` | 是，但**有**页码 |
| `full` + `page{noll}` 同 div | 3 | `[1] **空** [2]` | 是，**无**页码 |

结论：合并成立，零冲突。

## 四、嵌套规则（v2.18.0 定稿，用户裁决）

### 4.1 同族禁止自嵌套（四族全部）

`page` / `full` / `color` / `fill` 都不允许自己套自己。内层 begin/end 加零宽前缀退回纯文本（与 v2.17 `page` 同法），内容仍归外层。

**理由（实测，不是审美）**：`fill` / `color` / `full` 三个分支原本都是「遇到第一个 `@@ end <本族>` 就关闭」，**没有深度计数**。套自己时外层被内层的 `end` 提前关掉，内层 `begin` 与末尾那个 `end` 无接收者，**直接印在纸面上**：

| 写法 | 实测出纸 |
|---|---|
| `full{t}` 套 `full{b}` | 3 页，p2 印着 `@@ begin full{b}`，p3 印着 `@@ end full`，全文只有 1 个 `full-page` |
| `color r` 套 `color {1e88e5}` | 纸面印出 `@@ begin color {1e88e5}`，内层不生效 |

`color` 不需要自嵌套还能覆盖：行内 `@@ color r{文字}` 本来就是"就近优先"的局部覆盖手段。

### 4.2 主链层级 `page > full > fill`，严格

| 家族 | 主链 rank | 要求 |
|---|---|---|
| `page` | 1 | 只能出现在 `_lv = 0`（文档流，或 color 里） |
| `full` | 2 | 只能出现在 `_lv ≤ 1`（page 里 / 文档流 / color 里） |
| `fill` | 3 | 只能出现在 `_lv ≤ 2`（page/full 里 / 文档流 / color 里） |
| `color` | — | 不占层级，透明；套在哪都行，内层 `_lv` 原样透传 |

判据是 `rank > _lv`，**同族自动被拒**（进入同族后 `_lv == rank`），所以 4.1 与 4.2 是同一套机制的两面。

实测支撑：`full` 套 `fill`✓（`full-page[930px]` + `fill-row[87px]`）；`fill` 套 `full`✗（`full` 的标记行直接印在栏里）。

### 4.3 并写顺序锁定 `page → full → color`

三者压在同一个 div 上，顺序不影响渲染结果。锁定的唯一目的是**唯一写法**：不锁的话 `full page` 与 `page full` 输出逐字节相同，同一份文档两种写法，diff 出噪音、报错也没法指名。顺序与 4.2 的嵌套层级同构。

顺序错 → 整行 fail-closed 露出。

## 五、机制（三处）

1. **`_scanBeginBlock(lines, i, teams)`** —— 统一收集器。`teams` = 本块声明的家族数组。内容遇到「与 teams 有交集的 begin」→ 零宽 + 压栈；栈非空时遇到匹配栈顶的 `end` → 弹栈 + 零宽；栈空时遇到 `teams` 内的 `end` → 收尾。五个分支（fill / color / full / page / 并写）共用。
2. **`parseMarkdown(src, _lv)`** —— 加可选层级参数，默认 0。只有五个容器分支把它传给内层递归：page→1、full→2、fill→3、color 原样透传、并写取块内最高 rank。
3. **并写顺序校验** —— 解析出 `_mgl` 后检查 rank 单调递增，递减即 fail-closed。

## 六、改动点位

| # | 文件 / 位置 | 改什么 |
|---|---|---|
| 1 | `markdown-editor.html` PARSER 段 | 新增 `_LV` 常量、`_scanBeginBlock`、`_familiesOfBegin`；`parseMarkdown` 加 `_lv` |
| 2 | 同上 · fill 分支 | 换用 `_scanBeginBlock`；`rank 3 > _lv` 校验；每栏 `parseMarkdown(cols[ci], 3)` |
| 3 | 同上 · color 分支 | 换用 `_scanBeginBlock`；内层 `parseMarkdown(cinner, _lv)` 透传 |
| 4 | 同上 · full 分支 | 换用 `_scanBeginBlock`；`rank 2 > _lv` 校验；内层传 2 |
| 5 | 同上 · page 分支 | 换用 `_scanBeginBlock`；`rank 1 > _lv` 校验（即 `_lv==0`）；内层传 1 |
| 6 | 同上 · 并写分支 | 换用 `_scanBeginBlock`；顺序校验；内层传块内最高 rank |
| 7 | `md-parser.js` | `_extract_parser.py` 重抽，`_test_parser_sync.py` 校验 |
| 8 | `CHANGELOG.md` | v2.18.0「说明」段补嵌套规则与实测 |
| 9 | `docs/MDEditor 使用指南.md` | 并写小节补「嵌套规则」三条 + 层级表 |

## 七、测试

新增 `_test_v2180_nest.cjs`：
1. `full` 套 `full` → 1 个 `full-page`，内层两行零宽（输出里含 `\u200b@@ begin full`）
2. `color` 套 `color` → 1 个 `mde-color`
3. `fill` 套 `fill` → 1 个 `fill-row`
4. `page` 套 `page` → 1 个 `page-region`（v2.17 行为保持）
5. `fill` 套 `full` → full 被拒（零宽），只有 1 个 `fill-row`、0 个 `full-page`
6. `full` 套 `page` → page 被拒，只有 1 个 `full-page`、0 个 `page-region`
7. `page` 套 `full` → 正常，各 1 个
8. `page` 套 `fill` → 正常
9. `full` 套 `fill` → 正常
10. `color` 套 `page` → 正常（color 透明）
11. `page` 套 `color` 套 `fill` → 正常三层
12. `fill` 套 `color` → 正常
13. `color` 套 `full` → 正常
14. 并写 `page full color` 顺序正确 → 正常
15. 并写 `full page` → fail-closed（原文露出）
16. 并写 `color page` → fail-closed
17. 并写 `page color full` → fail-closed
18. 单家族输出与 v2.17 逐字节一致（移除并写分支对照）

回归：`md-parser.test.cjs` 95、`_test_v2170_parse` 14、`_test_v2170_filler` 30、`_test_v2170_e2e` 17、`_test_v2180_merge` 26、`_test_v2180_e2e` 14、`_test_v2132_rules` 46、`_test_parser_sync` PASS。

## 八、风险

- **改的是解析器核心**，`parseMarkdown` 加参数会波及所有调用点。缓解：参数默认 0，非容器调用点不传，行为不变；有 200+ 项既有测试兜底。
- **字节级同步**：`md-parser.js` 与 HTML 内嵌段必须逐字节一致，改完必须重抽 + 校验。
- **fail-closed 口径统一**：越界/同族 → 标记行露出、内容照常渲染，结束行不重复露出。

## 九、执行记录（2026-10-29 · 规则修正完成）

最终规则（用户定稿）：**四族同族禁自嵌套；color 不占主链任意层；主链 page(1) > full(2) > fill(3) 严格递增、跳级合法、逆序/同级拒绝；并写顺序锁死 page→full→color（fill 不参与并写）。**

改动落点：
- `markdown-editor.html`：parseMarkdown 增 `_lv` 参数；`_LV`/`_MGORD`/`_beginFams`/`_scanBeginBlock` 裁决层；fill/color/full/page 四分支 rank 前置 + 统一扫描；并写分支顺序校验 + teams 扫描 + 容器 `_lv` 下传；`<<<`/引用/数据点表/各递归点补传 `_lv`。
- **关键修正**：rank 裁决必须**前置于块扫描**——否则非法 begin 的配对 end 会被扫描器当闭合吃掉，begin 露出而 end 消失（不对称吞行）。现行为：拒绝时 begin 按原文露出、i++ 推进，end 走孤 end 兜底同样露出，内容照常渲染。
- `_extract_parser.py` / `_test_parser_sync.py`：锚点更新为 `parseMarkdown(src,_lv)` → `parseMarkdown(src, _lv, opts)`；`md-parser.test.cjs` 的 indents 用例改三参。
- `md-parser.js` 已重抽，`_test_parser_sync` PASS。
- 测试：`_test_v2180_nest.cjs` 新增 22 项全过；`_test_v2180_merge.cjs` 26 项（2 条旧「顺序任意」用例改错序 fail-closed）；全量回归全绿（见 CHANGELOG v2.18.0 测试段）。
- 环境备注：系统默认 python 已变 3.14，`docxdeps/lxml` 为 cp311 二进制——docx 类测试须 `py -3.11`。另修 `_test_v26_parse.py` PM5 陈旧断言（v2.6.12 起表格数据点渲染真表、不再造 `[数据表 R×C]` 标签）。
