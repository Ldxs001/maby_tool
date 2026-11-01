# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""外部标准 Markdown → 本方言转换器（v2.26.0 / P1 转换核心）

设计约束（全部来自任务地图 Temp/_taskmap_mdconv.md，改代码前先读它）：

1. **只做语法映射**。外部写法 → 方言语义等价的写法。渲染出来跟外部不一样就不一样，
   绝不为了让"转完就好看"去补缩进、改面板、动解析器。
2. **内容无损**：格式可以降级，文字一个字都不能少。方言表达不了的，剥标签留文字、
   留 URL、留标记本身，原位保留。
3. **三趟走**：先切块（围栏/front matter 原样）→ 逐块转换 → 拼回。代码块里的
   `* 项`、`&copy;`、`1)` 是**数据**不是语法，整篇正则替换必改坏内容。
4. **幂等**：convert(convert(x)) == convert(x)。输出已是方言语法，再跑一遍不该再变。

CLI：
    python md_convert.py in.md [-o out.md] [--config cfg.json]
    python md_convert.py -            < in.md        （标准输入）
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

# ---------------------------------------------------------------- 默认配置

DEFAULT_RULES = {
    # 无序列表：源标记 → 一级输出 | 二级及以下按 deeper 循环
    # 层深靠 `<` 个数表达（最外层 3、第 n 层 n+2），那是方言语义，不可配
    "unordered": {
        "src": ["-", "+", "*"],
        "level1": "+",
        "deeper": ["-", "+"],
    },
    # 有序列表：源标记 → 统一输出
    "ordered": {"src": [".", ")"], "out": "."},
    # 围栏：波浪线围栏与缩进代码块都转反引号围栏（反引号围栏本身直通）
    "fence": {"tilde": True, "indented": True},
    # Setext 标题（=== / --- 下划线式）转 ATX
    "heading": {"setext": True},
    # C 类：默认开
    "inline": {"entity": True, "refLink": True, "autoLink": True, "html": True},
    # 脚注：text = 标记转 ^{[n]}、定义行转普通段落；keep = 两处原样
    "footnote": "text",
    # 松散列表：删掉项与项之间的空行（否则编号重置）
    "list": {"dropBlank": True},
}

# HTML 标签 → 方言语法。方言把所有 HTML 转义成字面文本，所以这些不是"可选优化"，
# 是不管就会露出来的东西。值里的 {c} 表示原内容，{a} 表示取第 a 个属性。
HTML_INLINE = [
    ("b", "**{c}**"),
    ("strong", "**{c}**"),
    ("i", "*{c}*"),
    ("em", "*{c}*"),
    ("del", "~~{c}~~"),
    ("s", "~~{c}~~"),
    ("strike", "~~{c}~~"),
    ("sup", "^{{c}}"),
    ("sub", "_{{c}}"),
    ("u", "{c}"),       # 方言无下划线，剥标签留文字
    ("mark", "{c}"),    # 方言无高亮底色，不拿 @@ color 冒充（那是字色）
    ("kbd", "{c}"),
    ("samp", "{c}"),
    ("var", "{c}"),
    ("tt", "{c}"),
    ("small", "{c}"),
    ("center", "{c}"),
    ("font", "{c}"),
    ("span", "{c}"),    # 带 style="color:…" 的另走 _html_span
]


# ---------------------------------------------------------------- 默认映射表
#
# 界面「导入」第一个页签直接照这张表渲染，所以它是数据结构，不是文档。
# 左边（src）可改：用户能加符号、能删、能换顺序。
# 右边（dst）只读：方言标记 + 它的呈现形式，一个字都不许动。
#   kind = "set"    左边是一组源符号，逗号分隔可增删
#   kind = "switch" 左边是一个开关（这条规则开不开）
#   kind = "select" 左边在固定几档里选
#   kind = "fixed"  左边不给改（方言侧已定，或本来就没有可配的源）

MAPPING_TABLE = [
    {
        "group": "列表",
        "items": [
            {"key": "unordered.src", "kind": "set", "label": "一级标记",
             "src": ["-", "+", "*"], "write": "+", "draw": "· 实心圆",
             "dst": "+  →  实心 ·",
             "note": "别人的 Markdown 写 - + * 都算列表，这里都能认。星号 * 建议留着——删了以后，以 * 开头的行会被当斜体。"},
            {"key": "unordered.deeper", "kind": "set", "label": "二级起的标记",
             "src": ["-", "+"], "write": "- ／ +", "draw": "○ ／ ·",
             "dst": "- → 空心 ○ ； + → 实心 ·",
             "note": "二级及以下按层级交替取用：一级实心、二级空心、三级实心……层深由 <<< 的个数表示，这里只管用哪个符号。"},
            {"key": "ordered.src", "kind": "set", "label": "编号后缀",
             "src": [".", ")"], "write": ".", "draw": "1. 编号",
             "dst": ".  →  1.",
             "note": "源里写 1) 的转成 1.。源数字本身不参与编号——本编辑器一律从 1 显示。"},
        ],
    },
    {
        "group": "代码",
        "items": [
            {"key": "fence.tilde", "kind": "switch", "label": "波浪围栏",
             "src": ["~~~"], "write": "```", "draw": "代码块",
             "dst": "```  →  代码块",
             "note": "本编辑器不认 ~~~（会渲染成删除线），必须转成反引号围栏。"},
            {"key": "fence.indented", "kind": "switch", "label": "缩进代码块",
             "src": ["4 空格起首"], "write": "```", "draw": "代码块",
             "dst": "```  →  代码块",
             "note": "行首四个空格起的一段，转成围栏后不再受缩进影响。"},
            {"key": "fence.backtick", "kind": "fixed", "label": "反引号围栏",
             "src": ["```…````"], "write": "原样", "draw": "代码块",
             "dst": "原样  →  代码块",
             "note": "本编辑器开 N 收 N，4 包 3、3 包 4、5 包 4 包 3 都成立，一个字节都不动。"},
        ],
    },
    {
        "group": "标题",
        "items": [
            {"key": "heading.setext", "kind": "switch", "label": "下划线式标题",
             "src": ["===", "---"], "write": "# ／ ##", "draw": "两级标题",
             "dst": "#  →  一级标题 ； ##  →  二级标题",
             "note": "紧跟在文字下一行的 === 或 ---。本编辑器不认这种写法，会原样显示成两行字。"},
        ],
    },
    {
        "group": "行内",
        "items": [
            {"key": "footnote", "kind": "select", "label": "脚注",
             "src": ["[^1]"], "write": "^{[1]}", "draw": "[1] 上标",
             "dst": "^{[1]}  →  [1] 上标", "options": ["text", "keep"],
             "note": "text＝引用标记转上标角标、定义行转普通段落；keep＝两处原样。内容一个字都不删。"},
            {"key": "inline.entity", "kind": "switch", "label": "HTML 实体",
             "src": ["&copy;"], "write": "©", "draw": "©",
             "dst": "©  →  ©",
             "note": "本编辑器不解析实体，不转的话屏幕上就是 &amp;copy; 这串字。"},
            {"key": "inline.refLink", "kind": "switch", "label": "引用式链接",
             "src": ["[文字][id]"], "write": "[文字](url)", "draw": "可点链接",
             "dst": "[文字](url)  →  链接",
             "note": "没人引用的孤儿定义原样留成文字——删了那行 URL 就没了。"},
            {"key": "inline.autoLink", "kind": "switch", "label": "自动链接",
             "src": ["<https://x>"], "write": "[x](x)", "draw": "可点链接",
             "dst": "[x](x)  →  链接",
             "note": "尖括号包住的裸地址。"},
            {"key": "inline.html", "kind": "switch", "label": "HTML 标签",
             "src": ["<b>", "<sup>", "<br>"], "write": "** ／ ^{} ／ 换行", "draw": "粗体 · 上标 · 换行",
             "dst": "**  →  粗体 ； ^{}  →  上标",
             "note": "本编辑器把 HTML 全部转义成字面文本，不转就会把标签露在正文里。对不上语法的标签剥掉留文字。"},
        ],
    },
    {
        "group": "结构",
        "items": [
            {"key": "list.dropBlank", "kind": "switch", "label": "松散列表空行",
             "src": ["项与项之间的空行"], "write": "删掉空行", "draw": "编号不断",
             "dst": "删空行  →  编号不断",
             "note": "本编辑器里空行会打断列表并重置编号，所以项与项之间的空行要删掉。"},
        ],
    },
]


def mapping_table():
    """给界面用的映射表（带当前取值，便于渲染成可编辑控件）。"""
    return json.loads(json.dumps(MAPPING_TABLE))


# ---------------------------------------------------------------- 工具

def _unescape_entity(text: str) -> str:
    """&copy; / &#169; → 字面字符。方言不认实体，原样会显示成 &amp;copy;。"""
    return re.sub(r"&([a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#x[0-9a-fA-F]{1,6});",
                  lambda m: html.unescape(m.group(0)), text)


def _count_ticks(s: str) -> int:
    """一行里最长连续反引号串的长度（用于围栏长度自适应）。"""
    best = cur = 0
    for ch in s:
        if ch == "`":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _longest_tick_run(text: str) -> int:
    best = cur = 0
    for ch in text:
        if ch == "`":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# ---------------------------------------------------------------- 第一趟：切块

_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*(.*)$")


def split_blocks(text: str):
    """把文本切成块序列：[(kind, payload), ...]

    kind:
      ("fm", 原文)      文首 YAML front matter —— 原样，方言原生认
      ("fence", (info, code, char, width))  围栏块 —— 内部逐字不动
      ("body", [行, ...])  正文行

    围栏配对用「开 N 收 N」（严格相等），与解析器 v2.26.0 同口径：
    `4 包 3` 的中间那行 3 个不算收尾，`3 包 4` 的 4 个也不算。
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    i = 0
    n = len(lines)

    # 文首 front matter：第 0 行 --- ，下一处 --- 结束。内容必须全是 key: value 或空，
    # 否则不认（与解析器 D501 同口径），按正文处理。
    if n and lines[0].strip() == "---":
        j = 1
        while j < n and lines[j].strip() != "---":
            j += 1
        if j < n and j > 1:
            blocks.append(("fm", "\n".join(lines[: j + 1])))
            i = j + 1

    body = []
    while i < n:
        m = _FENCE_RE.match(lines[i])
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            char = m.group(1)[0]
            width = len(m.group(1))
            start = i
            i += 1
            code = []
            while i < n:
                m2 = re.match(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*$", lines[i])
                if m2 and m2.group(1)[0] == char and len(m2.group(1)) == width:
                    break
                code.append(lines[i])
                i += 1
            if i < n:                     # 找到收尾
                if body:
                    blocks.append(("body", body))
                    body = []
                blocks.append(("fence", (m.group(2).strip(), "\n".join(code), char, width)))
                i += 1
                continue
            else:                          # 未闭合 → 整段回退成正文（fail-open，别吞）
                i = start
                body.append(lines[i])
                i += 1
                continue
        body.append(lines[i])
        i += 1
    if body:
        blocks.append(("body", body))
    return blocks


# ---------------------------------------------------------------- 列表层级

_LIST_RE = re.compile(r"^([ \t]*)([-+*]|\d+[.)])[ \t]+(.*)$")


def list_re(rules):
    """按配置的 unordered.src 生成列表匹配正则。

    用户可以在映射表里往源符号集合加字符（比如 ?），所以不能写死 [-+*]。
    `*` 必须留在默认集合里，删了那些行会被当斜体。
    """
    chars = "".join(re.escape(c) for c in rules["unordered"]["src"])
    return re.compile(r"^([ \t]*)([%s]|\d+[.)])[ \t]+(.*)$" % chars)


def _indent_width(s: str) -> int:
    w = 0
    for ch in s:
        w += 4 if ch == "\t" else 1
    return w


def parse_list_tree(lines, lre=None):
    """把一段连续的列表行解析成层级树。

    返回 [ {'indent':n, 'marker':'-', 'ordered':False, 'content':'…',
            'cont':[续行…], 'children':[…] }, … ]
    层级只按「相对上一项的缩进增量」判，不卡具体空格数（外部 2/3/4 空格混用都能吃）。
    """
    lre = lre or _LIST_RE
    roots = []
    stack = []          # [(indent, node)]
    for raw in lines:
        m = lre.match(raw)
        if not m:
            # 续行：挂到最近一项（保留原文，缩进去掉）
            if stack:
                stack[-1][1]["cont"].append(raw.strip())
            else:
                roots.append({"indent": 0, "marker": "", "ordered": False,
                              "content": raw.strip(), "cont": [], "children": []})
            continue
        ind = _indent_width(m.group(1))
        mark = m.group(2)
        node = {"indent": ind, "marker": mark, "ordered": mark[0].isdigit(),
                "content": m.group(3), "cont": [], "children": []}
        while stack and ind <= stack[-1][0]:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)
        stack.append((ind, node))
    return roots


def deep_mark(level: int) -> str:
    """装第 level 层（2 起）那一批列表项的容器符号。

    方言规则（v2.26.0）：最外层 `<<<` 装二级项，向内递增
    —— 二级容器 3 个 `<`、三级 4 个、四级 5 个。严格相等才收口。
    这是方言语义，不是转换器的选择，所以配置里不开放。
    """
    return "<" * (level + 1)


def render_list_tree(roots, rules, level=1):
    """层级树 → 方言文本。

    一级项直出 level1 标记；某项有子项时，在该项后写一个开符（个数 = 子层层级 + 2），
    子树全部写进去，写完立即写同个数收符。逐层关闭、不跳层。
    标记按 depth 交替（全按层级算，不看源标记）。
    """
    un = rules["unordered"]
    out = []
    nxt = un["deeper"] or ["-"]
    for node in roots:
        if node["ordered"]:
            # 有序项保留源序号，只把 `1)` 换成本地认的 `1.`——源数字在本方言里只是标记，
            # 渲染一律从 1 起，但保留原数字能让源文读起来不乱
            marker = re.sub(r"[.)]$", ".", node["marker"])
        else:
            marker = un["level1"] if level == 1 else nxt[(level - 2) % len(nxt)]
        line = (marker + " " + node["content"]).rstrip()
        out.append(line)
        for c in node["cont"]:
            # 续行：方言里同层续行直接顶格写（缩进会让它被当成子列表）
            out.append(c)
        if node["children"]:
            mark = deep_mark(level + 1)
            out.append(mark)
            out.extend(render_list_tree(node["children"], rules, level + 1))
            out.append(mark)
    return out


# ---------------------------------------------------------------- 行内规则

def convert_inline(text: str, rules: dict) -> str:
    """行内：HTML 标签、脚注、引用式链接、自动链接、实体。不含列表/块级。"""
    if not text:
        return text

    # HTML 实体先解（否则 &copy; 双转义）
    if rules["inline"].get("entity"):
        text = _unescape_entity(text)

    if rules["inline"].get("html"):
        # 块级/空元素
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"<hr\s*/?>", "---", text, flags=re.I)
        # <a href="u" title="t">x</a> → [x](u "t")
        def _a(m):
            attrs, inner = m.group(1), m.group(2)
            href = _attr(attrs, "href")
            title = _attr(attrs, "title")
            if not href:
                return inner
            return "[%s](%s%s)" % (inner, href, (' "%s"' % title) if title else "")
        text = re.sub(r"<a\b([^>]*)>(.*?)</a>", _a, text, flags=re.I | re.S)
        # <img src alt title> → ![alt](src "title")
        def _img(m):
            attrs = m.group(1)
            src = _attr(attrs, "src")
            if not src:
                return ""
            alt = _attr(attrs, "alt") or ""
            title = _attr(attrs, "title")
            return "![%s](%s%s)" % (alt, src, (' "%s"' % title) if title else "")
        text = re.sub(r"<img\b([^>]*)/?>", _img, text, flags=re.I)
        # <code>x</code> → 反引号，N 按内容最长反引号串加长
        def _code(m):
            inner = m.group(1)
            tick = "`" * max(1, _longest_tick_run(inner) + 1)
            pad = " " if inner.startswith("`") or inner.endswith("`") else ""
            return tick + pad + inner + pad + tick
        text = re.sub(r"<code\b[^>]*>(.*?)</code>", _code, text, flags=re.I | re.S)
        # <span style="color:C">x</span> → @@ color {HEX}{x}
        def _span(m):
            attrs, inner = m.group(1), m.group(2)
            col = _attr(attrs, "style") or ""
            mc = re.search(r"color\s*:\s*([#\w\(\),.\s%]+)", col, flags=re.I)
            if not mc:
                return inner
            hexv = _norm_color(mc.group(1).strip())
            return "@@ color %s{%s}" % (hexv, inner) if hexv else inner
        text = re.sub(r"<span\b([^>]*)>(.*?)</span>", _span, text, flags=re.I | re.S)
        # 其余成对标签
        for tag, tpl in HTML_INLINE:
            if tag == "span":
                continue
            pat = re.compile(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), flags=re.I | re.S)
            text = pat.sub(lambda m, t=tpl: t.replace("{c}", m.group(1)), text)
        # 落单的标签一律抹掉本体、留内容（已经保不住结构的，别让标签露出来）
        text = re.sub(r"</?(?:div|p|blockquote|ul|ol|li|pre|h[1-6]|table|thead|tbody|tr|td|th)\b[^>]*>", "", text, flags=re.I)

    # 脚注引用 [^1] → ^{[1]}（方言上标角标）
    if rules.get("footnote", "text") == "text":
        text = re.sub(r"\[\^([^\]\s]+)\]", r"^{[\1]}", text)

    # 自动链接 <https://x> → [https://x](https://x)
    if rules["inline"].get("autoLink"):
        text = re.sub(r"<((?:https?|mailto):[^>\s]+)>", r"[\1](\1)", text)

    return text


def _attr(attrs: str, name: str):
    m = re.search(r"\b%s\s*=\s*[\"']([^\"']*)[\"']" % re.escape(name), attrs, flags=re.I)
    if not m:
        m = re.search(r"\b%s\s*=\s*([^\s\"'>]+)" % re.escape(name), attrs, flags=re.I)
    return m.group(1) if m else None


def _norm_color(v: str):
    """颜色值 → 方言认的 3/6/8 位 HEX（不带 #）；归一不了返回 None，不猜色。"""
    v = v.strip().lower()
    if v.startswith("#"):
        h = v[1:]
        return h if re.fullmatch(r"[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8}", h) else None
    named = {
        "red": "e53935", "green": "43a047", "blue": "1e88e5", "yellow": "f9a825",
        "orange": "fb8c00", "purple": "8e24aa", "cyan": "00acc1", "magenta": "d81b60",
        "black": "000000", "white": "ffffff", "gray": "757575", "grey": "757575",
    }
    if v in named:
        return named[v]
    m = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", v)
    if m:
        a, b, c = (max(0, min(255, int(x))) for x in m.groups())
        return "%02x%02x%02x" % (a, b, c)
    return None


# ---------------------------------------------------------------- 正文块转换

_INDENT_MARK_RE = re.compile(r"^[ ]{0,3}(<{3,})[ ]*$")


def _indent_mark_len(line: str) -> int:
    """该行是不是 `<<<` 类层级标记行；是则返回 `<` 个数，否则 0。"""
    m = _INDENT_MARK_RE.match(line)
    return len(m.group(1)) if m else 0


def _skip_indent_block(lines, i, n, width):
    """从 i（开符行）起，返回整块结束后的下一行下标。

    按层数配对：遇到同个数即本层闭合；遇到更多个数就递归跳过整棵子树；
    遇到更少个数说明外层提前收了口，本层未闭合，就地返回（不兜底）。
    """
    j = i + 1
    while j < n:
        w = _indent_mark_len(lines[j])
        if w == width:
            return j + 1
        if w > width:
            j = _skip_indent_block(lines, j, n, w)
            continue
        if w:
            return j
        j += 1
    return n


def convert_body(lines, rules: dict):
    """正文行 → 方言行。列表块整块解析成树再渲染，其余逐行套规则。"""
    out = []
    i = 0
    n = len(lines)
    # 先把引用式链接的定义收集起来（转换后按"是否被引用"决定去留）
    refs = {}
    ref_lines = {}
    for k, ln in enumerate(lines):
        m = re.match(r"^[ ]{0,3}\[([^\]]+)\]:[ \t]*(\S+)", ln)
        if m and not m.group(1).startswith("^"):
            refs[m.group(1).lower()] = m.group(2)
            ref_lines[k] = m.group(1)

    used_refs = set()
    if rules["inline"].get("refLink"):
        for ln in lines:
            for m in re.finditer(r"\[([^\]]+)\]\[([^\]]*)\]", ln):
                key = (m.group(2) or m.group(1)).lower()
                if key in refs:
                    used_refs.add(key)

    lre = list_re(rules)

    while i < n:
        line = lines[i]

        # `<<<` 层级块：方言原生语法，整块原样保留，块内一行都不动。
        # 不这么做就会把块内 `- 甲1`（二级空心标记）当外部源标记重新映射成 `+`，
        # 层级全乱——同时幂等性也会崩（第二遍结果 ≠ 第一遍）。
        _w = _indent_mark_len(line)
        if _w:
            end = _skip_indent_block(lines, i, n, _w)
            out.extend(lines[i:end])
            i = end
            continue

        # 引用式链接定义行
        mdef = re.match(r"^[ ]{0,3}\[([^\]]+)\]:[ \t]*(\S+)(.*)$", line)
        if mdef and not mdef.group(1).startswith("^"):
            key = mdef.group(1).lower()
            if key in used_refs:
                i += 1                      # URL 已内联进正文，这行可以不要
                continue
            out.append("[%s]: %s%s" % (mdef.group(1), mdef.group(2), mdef.group(3)))
            i += 1
            continue

        # 脚注定义行 [^1]: 内容 → 一段「[1] 内容」
        mfn = re.match(r"^[ ]{0,3}\[\^([^\]]+)\]:[ \t]*(.*)$", line)
        if mfn and rules.get("footnote", "text") == "text":
            out.append("[%s] %s" % (mfn.group(1), convert_inline(mfn.group(2), rules)))
            i += 1
            continue

        # 列表块：连续列表行 + 其续行
        if lre.match(line):
            j = i
            chunk = []
            while j < n:
                if lre.match(lines[j]):
                    chunk.append(lines[j])
                    j += 1
                elif lines[j].strip() == "" and rules["list"].get("dropBlank") \
                        and j + 1 < n and lre.match(lines[j + 1]):
                    j += 1                  # 松散列表的空行：吃掉（否则编号重置）
                elif lines[j].strip() and not _block_start(lines[j], lre):
                    chunk.append(lines[j])
                    j += 1
                else:
                    break
            tree = parse_list_tree(chunk, lre)
            for ln in render_list_tree(tree, rules):
                out.append(ln if _indent_mark_len(ln) else convert_inline(ln, rules))
            i = j
            continue

        # Setext 标题：=== / --- 紧跟一行文字
        if rules["heading"].get("setext") and re.match(r"^[ ]{0,3}(=+|-+)[ \t]*$", line) \
                and out and out[-1].strip() and not _block_start(out[-1], lre):
            lvl = "#" if line.strip()[0] == "=" else "##"
            out[-1] = "%s %s" % (lvl, out[-1].strip())
            i += 1
            continue

        # 缩进代码块：4 空格 / Tab 起首、上一行不是列表项
        if rules["fence"].get("indented") and re.match(r"^(?: {4}|\t)", line) \
                and (not out or not lre.match(out[-1])):
            code = []
            while i < n and (re.match(r"^(?: {4}|\t)", lines[i]) or lines[i].strip() == ""):
                code.append(re.sub(r"^(?: {4}|\t)", "", lines[i]))
                i += 1
            while code and code[-1].strip() == "":
                code.pop()
            tick = "`" * max(3, _longest_tick_run("\n".join(code)) + 1)
            out.append(tick)
            out.extend(code)
            out.append(tick)
            continue

        # 普通行
        out.append(convert_inline(line, rules))
        i += 1

    # 引用式链接的内联替换（在全部行处理完之后做，避免定义行先被改写）
    if rules["inline"].get("refLink") and used_refs:
        joined = "\n".join(out)

        def _inline_ref(m):
            txt = m.group(1)
            key = (m.group(2) or m.group(1)).lower()
            if key in refs:
                return "[%s](%s)" % (txt, refs[key])
            return m.group(0)

        joined = re.sub(r"\[([^\]]+)\]\[([^\]]*)\]", _inline_ref, joined)
        out = joined.split("\n")

    return out


_BLOCK_START_RE = re.compile(
    r"^[ ]{0,3}(#{1,6}[ \t]|>|`{3,}|~{3,}|@@|<{3,}|\|)")


def _block_start(line: str, lre=None) -> bool:
    return bool(_BLOCK_START_RE.match(line)) or bool((lre or _LIST_RE).match(line))


# ---------------------------------------------------------------- 围栏

def render_fence(info: str, code: str, char: str, width: int) -> str:
    """围栏块输出。

    反引号围栏**原样输出**（保留原个数）：方言 v2.26.0 起最外层不限个数、开 N 收 N，
    `4 包 3`、`3 包 4`、`5 包 4 包 3` 都成立。若在这里重算成长度自适应，`3 包 4` 会
    被推成 `5 包 4`，且每转一遍就再长一截——违反幂等。
    波浪围栏必须转反引号（方言渲染层不认 `~~~`），个数按内容算，避开内容里所有反引号串。
    """
    if char == "`":
        tick = "`" * width
        head = tick + (info if info else "")
        return head + "\n" + code + ("\n" if code else "") + tick
    tick = "`" * max(3, _longest_tick_run(code) + 1)
    head = tick + (info if info else "")
    return head + "\n" + code + ("\n" if code else "") + tick


# ---------------------------------------------------------------- 主入口

def convert(text: str, rules: dict | None = None) -> str:
    """外部 Markdown → 本方言 Markdown。纯文本进、纯文本出。"""
    cfg = json.loads(json.dumps(DEFAULT_RULES))          # 深拷贝，别污染默认值
    if rules:
        _deep_update(cfg, rules)

    out = []
    for kind, payload in split_blocks(text):
        if kind == "fm":
            out.append(payload)                          # front matter 原样
        elif kind == "fence":
            info, code, char, width = payload
            out.append(render_fence(info, code, char, width))
        else:
            out.extend(convert_body(payload, cfg))
    return "\n".join(_squeeze_blank(out))


def _squeeze_blank(lines):
    """连续空行压到一个（只在行列表层面做——不能对拼好的整串跑正则，
    否则围栏内部的空行也会被吃掉）。"""
    res = []
    blank = 0
    for ln in lines:
        if ln.strip() == "":
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        res.append(ln)
    while res and res[-1].strip() == "":
        res.pop()
    return res


def _deep_update(base: dict, patch: dict) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def convert_file(src_path: str, dst_path: str | None, rules: dict | None = None) -> str:
    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    res = convert(text, rules)
    if dst_path:
        with open(dst_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(res)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="外部 Markdown → 本方言转换器")
    ap.add_argument("src", nargs="?", default="-", help="源文件，- 表示标准输入")
    ap.add_argument("-o", "--out", help="输出文件；不给则打到标准输出")
    ap.add_argument("--config", help="JSON 配置文件（覆盖默认映射）")
    a = ap.parse_args(argv)

    rules = None
    if a.config:
        with open(a.config, "r", encoding="utf-8") as f:
            rules = json.load(f)

    if a.src == "-":
        text = sys.stdin.read()
        res = convert(text, rules)
        if a.out:
            with open(a.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(res)
        else:
            sys.stdout.write(res)
    else:
        res = convert_file(a.src, a.out, rules)
        if not a.out:
            sys.stdout.write(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
