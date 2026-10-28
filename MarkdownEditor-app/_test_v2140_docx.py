# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwProject. Licensed under GNU AGPL v3 (or later).
"""v2.14.0 docx 侧：列表标记外凸 + `- [ ]` 方框字符。

预览改成 outside 后，Word 必须同构，否则就是「预览和 Word 两套几何」。
口径：ts-style 里的 --mde-mark-ol/ul（px）为单一来源，docx 只做 px→pt。

判据：
1. 关态（ts_css 无 outside）：li 段落 left=档位、firstLine=0（与 v2.13.5 一致）
2. 开态 ol：left = 档位 + 16.875pt（22.5px）、firstLine = −16.875pt
3. 开态 ul：槽宽走 16.5px 那档（12.375pt）
4. 编号定义 suff=tab（开态）/ space（关态）
5. `- [ ]` → 普通段落（不绑编号，Word 里不许多一个圆点）+ 文字以 □ 起头
6. `- [x]` → ☑
7. 无 ts_css 时回落 inside（老调用方不受影响）
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "docxdeps"))

import docx_export as DX  # noqa: E402
from docx import Document  # noqa: E402
from lxml import etree  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print("%-56s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


BODY = (
    '<div class="markdown-body">'
    '<ol style="margin-left:37.33px">'
    '<li style="font-size:15px">首行方框□<br>续行方框□</li>'
    '<li style="font-size:15px">第二项</li>'
    '</ol>'
    '<ul style="margin-left:37.33px">'
    '<li class="task" style="font-size:15px">'
    '<input type="checkbox" disabled> 待办项</li>'
    '<li class="task" style="font-size:15px">'
    '<input type="checkbox" disabled checked> 已办项</li>'
    '<li style="font-size:15px">普通项</li>'
    '</ul>'
    '</div>'
)

CSS_ON = (":root{--mde-mark-ol:22.5px;--mde-mark-ul:16.5px;}"
          "#preview ol, .markdown-body ol{list-style-position:outside !important;"
          "margin-left:37.33px !important;padding-left:22.5px !important;}")


def _load(body, css):
    data = DX.build_docx(None, body, ts_css=css)
    return Document(io.BytesIO(data))


def _p_by_text(doc, needle):
    for p in doc.paragraphs:
        if needle in p.text:
            return p
    return None


def _suff(doc):
    """读 List Number 的 abstractNum lvl0 → w:suff 值。"""
    numbering = doc.part.numbering_part.element
    style_an = None
    for an in numbering.findall(qn("w:abstractNum")):
        for lvl in an.findall(qn("w:lvl")):
            if lvl.get(qn("w:ilvl")) != "0":
                continue
            lvltext = lvl.find(qn("w:lvlText"))
            txt = lvltext.get(qn("w:val")) if lvltext is not None else ""
            suff = lvl.find(qn("w:suff"))
            if txt == "%1." and suff is not None:
                style_an = suff.get(qn("w:val"))
    return style_an


def main():
    # --- 关态 ---
    off = _load(BODY, "")
    p1 = _p_by_text(off, "首行方框")
    check("关态 li 存在", p1 is not None)
    if p1 is not None:
        li_off = p1.paragraph_format.left_indent.pt
        fi_off = (p1.paragraph_format.first_line_indent.pt
                  if p1.paragraph_format.first_line_indent is not None else 0.0)
        check("关态 left = 档位 27.99pt（37.33px×0.75）",
              abs(li_off - 27.9975) <= 0.05, "left=%.2f" % li_off)
        check("关态 firstLine = 0（inside 语义）", abs(fi_off) <= 0.01,
              "first=%.2f" % fi_off)
    check("关态编号定义 suff=space", _suff(off) == "space", str(_suff(off)))

    # --- 开态 ---
    on = _load(BODY, CSS_ON)
    p2 = _p_by_text(on, "首行方框")
    check("开态 li 存在", p2 is not None)
    if p2 is not None:
        li_on = p2.paragraph_format.left_indent.pt
        fi_on = p2.paragraph_format.first_line_indent.pt
        check("开态 ol left = 档+槽 = 44.87pt（28+16.875）",
              abs(li_on - (27.9975 + 16.875)) <= 0.05, "left=%.3f" % li_on)
        check("开态 ol firstLine = −16.875pt（槽宽取反；twips 量化 ±0.05）",
              abs(fi_on + 16.875) <= 0.05, "first=%.3f" % fi_on)
    # ul 走另一档槽宽
    p3 = _p_by_text(on, "普通项")
    check("开态普通项存在", p3 is not None)
    if p3 is not None:
        li_u = p3.paragraph_format.left_indent.pt
        fi_u = p3.paragraph_format.first_line_indent.pt
        check("开态 ul left = 档+12.375pt（16.5px 档）",
              abs(li_u - (27.9975 + 12.375)) <= 0.05, "left=%.3f" % li_u)
        check("开态 ul firstLine = −12.375pt（同上容差）",
              abs(fi_u + 12.375) <= 0.05, "first=%.3f" % fi_u)
    check("开态编号定义 suff=tab", _suff(on) == "tab", str(_suff(on)))

    # --- task ---
    pt = _p_by_text(on, "待办项")
    check("task 项段落存在", pt is not None)
    if pt is not None:
        check("task 未绑 List Bullet（Word 里不多一个圆点）",
              pt.style.name != "List Bullet", "style=%s" % pt.style.name)
        check("task 文字以 □ 起头", pt.text.strip().startswith("□"),
              repr(pt.text[:8]))
        check("task firstLine = 0（无 marker 不悬挂）",
              abs(pt.paragraph_format.first_line_indent.pt) <= 0.01,
              "first=%.3f" % pt.paragraph_format.first_line_indent.pt)
    pc = _p_by_text(on, "已办项")
    check("勾选项输出 ☑", pc is not None and "☑" in pc.text,
          repr(pc.text[:8]) if pc else "None")

    # --- 无 ts_css 回落 ---
    d0 = DX._list_hang_from_css(None)
    check("无 ts_css → 回落 inside", d0[0] is False, str(d0))
    d1 = DX._list_hang_from_css("body{margin:0}")
    check("不含 outside 的 ts_css → inside", d1[0] is False, str(d1))

    print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
