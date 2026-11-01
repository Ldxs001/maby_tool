# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""外部 Markdown → 本方言 转换器回归测试（v2.26.0 / P2）。

判据分四层，缺一层都不算过：

1. **映射正确**：每条 A/B/C/D 类规则都有正例，输出串逐字比对。
2. **幂等**：convert(convert(x)) == convert(x)。输出已是方言语法，再跑一遍不该变。
   这条最容易被破坏——只要有一处把方言自己的写法当外部写法改掉，第二遍就漂。
3. **内容无损**：文字一个都不能少。取输入里的中文串与英文词作多重集，
   输出必须全含。格式可以降级，字不能丢。
4. **渲染对得上**：把转换结果喂真解析器（md-parser.js），检查缩进块个数与
   实心/空心标记序列——语法对不等于渲染对。

用法：python _test_convert.py
输出只有 PASS / FAIL；exit 0 = 全过。
"""
import html
import io
import os
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from md_convert import convert, deep_mark, mapping_table  # noqa: E402

JS = os.path.join(HERE, "md-parser.js")
RESULTS = []
BACKTICK = "`"


def check(name, ok, extra=""):
    RESULTS.append((name, ok))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                       (" | " + extra) if extra else ""))


# ---------------------------------------------------------------- 1. 映射

MAPPING_CASES = [
    # (名称, 输入, 期望输出)
    ("无序 - 转 +", "- a\n- b\n", "+ a\n+ b"),
    ("无序 * 转 +", "* a\n* b\n", "+ a\n+ b"),
    ("无序 + 保持", "+ a\n+ b\n", "+ a\n+ b"),
    ("有序 1) 转 1.", "1) 甲\n2) 乙\n", "1. 甲\n2. 乙"),
    ("有序 1. 保持", "1. 甲\n2. 乙\n", "1. 甲\n2. 乙"),
    ("波浪围栏转反引号", "~~~js\nls\n~~~\n", "```js\nls\n```"),
    ("波浪围栏包反引号时长度自适应", "~~~\n```\n~~~\n", "````\n```\n````"),
    ("Setext H1 转 ATX", "标题\n===\n", "# 标题"),
    ("Setext H2 转 ATX", "标题\n---\n", "## 标题"),
    ("缩进代码块转围栏", "前段\n\n    code\n", "前段\n\n```\ncode\n```"),
    ("实体解成字符", "版权 &copy; 2026\n", "版权 © 2026"),
    ("脚注标记转角标", "正文[^1]。\n\n[^1]: 内容\n", "正文^{[1]}。\n\n[1] 内容"),
    ("sup 转角标", "这是<sup>1</sup>末\n", "这是^{1}末"),
    ("sub 转下角标", "H<sub>2</sub>O\n", "H_{2}O"),
    ("b 转粗体", "<b>粗</b>\n", "**粗**"),
    ("i 转斜体", "<i>斜</i>\n", "*斜*"),
    ("del 转删除线", "<del>删</del>\n", "~~删~~"),
    ("br 转段内换行", "第一行<br>第二行\n", "第一行\n第二行"),
    ("hr 转分隔线", "<hr>\n", "---"),
    ("a 转链接", '<a href="https://a.com">文字</a>\n', "[文字](https://a.com)"),
    ("img 转图片", '<img src="a.png" alt="图">\n', "![图](a.png)"),
    ("span 带颜色转 @@ color", '<span style="color:#f00">红</span>\n', "@@ color f00{红}"),
    ("span 无颜色剥标签", '<span class="x">文</span>\n', "文"),
    ("引用式链接内联", "见[文字][id]\n\n[id]: https://a.com\n", "见[文字](https://a.com)"),
    ("孤儿定义原地留文字", "[nobody]: https://a.com\n", "[nobody]: https://a.com"),
    ("自动链接", "看 <https://a.com>\n", "看 [https://a.com](https://a.com)"),
    ("注释不删", "<!-- 说明 -->\n", "<!-- 说明 -->"),
    ("未知标签留文字露出来", "<div>框内</div>\n", "框内"),
]

for name, src, want in MAPPING_CASES:
    got = convert(src).strip()
    check(name, got == want, "" if got == want else "want %r / got %r" % (want, got))


# ---------------------------------------------------------------- 2. 层级

NEST_CASES = [
    ("二级列表", "- 甲\n  - 甲1\n- 乙\n",
     "+ 甲\n<<<\n- 甲1\n<<<\n+ 乙"),
    ("三级列表", "- 甲\n  - 甲1\n    - 甲1a\n- 乙\n",
     "+ 甲\n<<<\n- 甲1\n<<<<\n+ 甲1a\n<<<<\n<<<\n+ 乙"),
    ("四级列表", "- 甲\n  - 甲1\n    - 甲1a\n      - 甲1a-i\n- 乙\n",
     "+ 甲\n<<<\n- 甲1\n<<<<\n+ 甲1a\n<<<<<\n- 甲1a-i\n<<<<<\n<<<<\n<<<\n+ 乙"),
    ("回到同级（甲2 回二级）", "- 甲\n  - 甲1\n    - 甲1a\n  - 甲2\n- 乙\n",
     "+ 甲\n<<<\n- 甲1\n<<<<\n+ 甲1a\n<<<<\n- 甲2\n<<<\n+ 乙"),
    ("两个父项各带子项", "- a\n  - a1\n- b\n  - b1\n",
     "+ a\n<<<\n- a1\n<<<\n+ b\n<<<\n- b1\n<<<"),
    ("有序项带子项", "1. 一\n   1. 一一\n2. 二\n",
     "1. 一\n<<<\n1. 一一\n<<<\n2. 二"),
    ("四空格缩进也认层级", "- 甲\n    - 甲1\n",
     "+ 甲\n<<<\n- 甲1\n<<<"),
    ("任务项转一级标记", "- [ ] 待办\n- [x] 已办\n",
     "+ [ ] 待办\n+ [x] 已办"),
]

for name, src, want in NEST_CASES:
    got = convert(src).strip()
    check(name, got == want, "" if got == want else "want %r / got %r" % (want, got))

# deep_mark 的个数口径（最外层装二级项 = 3 个）
check("容器符号个数：二级 3 个", deep_mark(2) == "<" * 3, deep_mark(2))
check("容器符号个数：三级 4 个", deep_mark(3) == "<" * 4, deep_mark(3))


# ---------------------------------------------------------------- 3. 反引号直通

FENCE_CASES = [
    ("4 包 3 直通", "````\n```\n````\n", "````\n```\n````"),
    ("3 包 4 直通", "```md\n````bash\nls\n````\n```\n",
     "```md\n````bash\nls\n````\n```"),
    ("5 包 4 包 3 直通", "`````\n````\n```\nx\n```\n````\n`````\n",
     "`````\n````\n```\nx\n```\n````\n`````"),
    ("围栏内不转换", "```\n- a\n* b\n&copy;\n```\n", "```\n- a\n* b\n&copy;\n```"),
    ("围栏语言保留", "```python\nx=1\n```\n", "```python\nx=1\n```"),
]
for name, src, want in FENCE_CASES:
    got = convert(src).strip()
    check(name, got == want, "" if got == want else "want %r / got %r" % (want, got))


# ---------------------------------------------------------------- 4. 幂等

IDEMPOTENT_CASES = [c[1] for c in MAPPING_CASES + NEST_CASES + FENCE_CASES] + [
    "# 标题\n\n- 甲\n  - 甲1\n\n正文**粗**。\n\n> 引用\n",
    "- 甲\n<<<\n- 甲1\n<<<\n+ 乙\n",
    "---\ntitle: x\n---\n\n- a\n",
    "正文 [^a] 和 [^b]\n\n[^a]: 甲\n[^b]: 乙\n",
]
bad = []
for src in IDEMPOTENT_CASES:
    a = convert(src)
    b = convert(a)
    if a != b:
        bad.append((src, a, b))
check("幂等 %d 例" % len(IDEMPOTENT_CASES), not bad,
      "" if not bad else "首个失败 %r -> %r / %r" % bad[0])


# ---------------------------------------------------------------- 5. 内容无损

_LATIN = re.compile(r"[A-Za-z]{4,}")


def _words(s):
    """取"文字"的多重集：中文按单字、英文按 4 字母以上的词。

    先剥掉三类不是文字的东西，否则会误判：
      · HTML 标签本身（div / b / u 是标签名，不是正文）
      · 引用式链接的 id 部分（id 是标识符，URL 已内联进正文）
      · 引用定义行（`[id]: url` 这行本来就整体处理）
    中文按单字而非词切：`A与B` 合并成 `A与B` 和分开的 `A`、`与`、`B` 在词级
    多重集里不相等，用单字才比得准。
    """
    s = html.unescape(s)
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"^[ ]{0,3}\[[^\]]+\]:.*$", "", s, flags=re.M)
    s = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", s)
    han = Counter(c for c in s if "\u4e00" <= c <= "\u9fff")
    lat = Counter(_LATIN.findall(s))
    return han + lat


LOSS_CASES = [
    ("列表文字", "- 甲乙丙\n  - 丁戊\n"),
    ("脚注文字", "正文有脚注[^1]。\n\n[^1]: 这是脚注的文字\n"),
    ("HTML 文字", "<b>粗体文字</b>与<u>下划线文字</u>\n"),
    ("引用式链接文字", "见[说明文字][ref]\n\n[ref]: https://a.com\n"),
    ("未知标签文字", "<div>框内文字保留</div>\n"),
    ("注释文字", "<!-- 隐藏的说明 -->\n"),
    ("围栏内代码", "```\nconst 变量 = 1;\n```\n"),
    ("实体文字", "版权 &copy; 归属\n"),
]
loss_bad = []
for name, src in LOSS_CASES:
    out = convert(src)
    miss = _words(src) - _words(out)
    if miss:
        loss_bad.append((name, dict(miss)))
check("内容无损 %d 例" % len(LOSS_CASES), not loss_bad,
      "" if not loss_bad else "丢了 %r" % loss_bad)


# ---------------------------------------------------------------- 6. 真渲染校验

RENDER_HARNESS = r"""
const fs = require('fs');
const P = require(process.argv[1]);
const src = fs.readFileSync(process.argv[2], 'utf8');
const dg = [];
const h = P.parseMarkdown(src, 0, { indents: { p: 0, quote: 0, li: 30 }, diag: dg }, 0);
const marks = (h.match(/class="u-(?:solid|hollow)"/g) || [])
  .map(s => s.replace('class="u-', '').replace('"', ''));
console.log(JSON.stringify({
  ind: (h.match(/class="ind-blk"/g) || []).length,
  marks: marks,
  diag: dg.map(d => d.code)
}));
"""


def render_check(md_text):
    """把 md 文本喂真解析器，返回 {ind, marks, diag}；node 不可用返回 None。"""
    if not os.path.isfile(JS):
        return None
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(md_text)
        r = subprocess.run(["node", "-e", RENDER_HARNESS, JS, path],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0 or not r.stdout.strip():
            return {"err": (r.stderr or r.stdout).strip()[:200]}
        import json
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


r1 = render_check(convert("- 甲\n  - 甲1\n    - 甲1a\n  - 甲2\n- 乙\n"))
if r1 is None:
    print("SKIP 渲染校验（md-parser.js 不存在）")
elif "err" in r1:
    check("渲染校验", False, r1["err"])
else:
    check("渲染：三级列表 2 个缩进块", r1["ind"] == 2, str(r1["ind"]))
    check("渲染：标记序列 实/空/实/空/实",
          r1["marks"] == ["solid", "hollow", "solid", "hollow", "solid"], str(r1["marks"]))
    check("渲染：无诊断", r1["diag"] == [], str(r1["diag"]))

r2 = render_check(convert("- a\n  - a1\n- b\n  - b1\n"))
if r2 and "err" not in r2:
    check("渲染：两个父项各 1 个缩进块", r2["ind"] == 2, str(r2["ind"]))
    check("渲染：两个父项都是 实/空", r2["marks"] == ["solid", "hollow", "solid", "hollow"],
          str(r2["marks"]))

r3 = render_check(convert("- 甲\n  - 甲1\n    - 甲1a\n      - 甲1a-i\n- 乙\n"))
if r3 and "err" not in r3:
    check("渲染：四级列表 3 个缩进块", r3["ind"] == 3, str(r3["ind"]))
    check("渲染：无诊断（层级配对未错）", r3["diag"] == [], str(r3["diag"]))


# ---------------------------------------------------------------- 7. 映射表结构

tbl = mapping_table()
keys = [it["key"] for g in tbl for it in g["items"]]
check("映射表有分组", len(tbl) >= 4, str(len(tbl)))
check("映射表含无序列表项", "unordered.src" in keys)
check("映射表条目都有左右两栏",
      all("src" in it and "dst" in it for g in tbl for it in g["items"]))
check("每条都有 kind", all(it.get("kind") in ("set", "switch", "select", "fixed")
                          for g in tbl for it in g["items"]))

# 左改右不改：给 unordered.src 加个 ? 之后，输出里 ? 开头的行也该转成 +
cfg = {"unordered": {"src": ["-", "+", "*", "?"]}}
got = convert("? a\n? b\n", cfg).strip()
check("自定义源符号 ? 生效", got == "+ a\n+ b", got)
got = convert("- a\n", cfg).strip()
check("自定义后原有的 - 仍生效", got == "+ a", got)


# ---------------------------------------------------------------- 汇总

bad = [n for n, ok in RESULTS if not ok]
print("\n===== %d/%d PASS =====" % (len(RESULTS) - len(bad), len(RESULTS)))
sys.exit(0 if not bad else 1)
