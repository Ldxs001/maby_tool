# MDEditor 快速手册 · Quick Reference

> **这是随程序分发的内置文件。** 在这里按 Ctrl+S 会直接写回安装目录（商店版会报"目标文件为只读"）。想改成自己的模板，请先「另存为」。
>
> **Built-in file.** Ctrl+S here writes straight back into the install directory (the Store build reports a read-only target). Use **Save as** first if you want your own copy.

一页看完最常用的写法。看**效果动画**去「配置 → 使用手册」，照着**练手**去「打开 → 内置文档 → 实操手册」。

---

## 一、基础写法 · Basics

| 写法 What you type | 效果 What you get |
| --- | --- |
| `**粗**`　`*斜*` | 加粗　斜体 · Bold / italic |
| `++下划线++` | 下划线，可与粗体混排 · Underline |
| `~~删除~~` | 删除线 · Strikethrough |
| `^{上}`　`_{下}` | 上下标，紧跟花括号 · Super / subscript |
| `@@ color r{字}` | 文字着色 · Text colour |
| `> 引用` | 引用块 · Block quote |
| `+ 项`　`- 项` | 实心点　空心圈，样式跟标记走 · Solid / hollow bullet |
| `1. 项` | 有序列表，编号自动生成 · Numbered list |
| `+ [ ] 待办` | 任务列表 · Task list |
| 整行 `---` | 分隔线 · Horizontal rule |
| 三个反引号围起来 | 代码块 · Code fence |
| `[文字](链接)` | 链接 · Link |
| `![说明](图片)` | 图片 · Image |
| `$x^2$`　`$$…$$` | 行内　块级公式 · Inline / block math |
| `<<< … <<<` | 缩进块，本工具的层级写法 · Indent block |

## 二、本工具特有 · This dialect only

| 写法 What you type | 效果 What you get |
| --- | --- |
| `![图](路径){30}` | 宽 = 版面的 30%，等比缩放，原图不动 · Width = N% of the text block |
| `![图](路径){30c}` | 宽度 + 对齐 `c`/`l`/`r` · Add c/l/r to align |
| `![图](路径 "题注"){50l:c t}` | 图题：引号内是题注，`:` 前图参后题参 · Figure caption |
| `@@ caption{c t} 表题` | 表题，紧贴表格上一行 · Table caption above |
| `@@ begin fill {50\|50}` … `@@ end fill` | 分栏并排，2~4 栏，比例和 =100 · Side-by-side columns |
| `@@ begin full{t}` … `@@ end full` | 独占一页，打印时前后断页 · Own page on print |
| `@@ blank{n}` | 恰好 n 行空白，与段距不叠加 · Exact blank space |
| `@@ blank{break}` | 就地断页，页码继续 · Page break, numbers keep running |
| `@@ begin page{noll\|1\|i\|I}` … `@@ end page` | 页区：区内重新编号 · Page-number region |
| `@@ begin font{"字体" c 12}` … `@@ end font` | 块级字体 / 对齐 / 字号（pt）· Block font & size |
| `@@ begin color r` … `@@ end color` | 块级着色 · Block colour |
| `@@ begin page{noll} full{t}` … | 并写，把嵌套压成一行 · Combine containers |
| `@@ MDE_池{键 == 值}` | 数据点，喂给 Python run · Data point |
| `@@ MDE from 文件 import 函数 is 池` | 执行点，结果替换这一行 · Exec point |

## 三、三条总规矩 · Three rules that cover everything

1. **块级语法必须独占一行**——前后不用空行，但不能写成 `前文 @@ blank{1}`。
   *Block syntax sits alone on its line; no blank lines around it, but never share the line with text.*
2. **所有 `{N}` 都是版面百分比**（1–100，超出钳到 100），图片基准是版面宽不是原图宽。
   *Every `{N}` is a percentage of the text block, clamped to 100 — not of the image.*
3. **写错不报错，原样显示**——非法值不生效，字面留在文面好让你看见笔误；`\X` 让标点逃出语法。
   *Invalid values are ignored and shown literally on purpose. Use `\X` to escape punctuation.*

## 四、再往下查 · Where to go next

| 想知道 | 去哪 |
| --- | --- |
| 这个写法**长什么样**、有哪些坑（示意动画） | 工具栏「配置 → 使用手册」 |
| 完整语法、排版参数、AI 与 low runner 配置 | 「打开 → 内置文档 → 实操手册」 |
| 真实效果、自己动手试 | 打开实操手册，改它、另存它 |

---

*以本表为准：本工具不是标准 Markdown 的照搬，而是在标准语法之上加了自有写法的增强方言。*
