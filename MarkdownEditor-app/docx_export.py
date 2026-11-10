# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""HTML(内联样式) -> .docx 转换器 + 自有 MathML->OMML 转换器（零微软依赖）。

设计要点：
- 入参 body_html 已由前端 inlineStylesClone 把计算样式内联进每个元素的 style 属性，
  因此服务端只需解析 style="" 即可还原字体/颜色/对齐等，无需再解析排版 CSS。
- 公式：元素带 data-tex（原始 LaTeX，不含 $ 定界），走 latex2mathml -> MathML -> 自有 OMML，
  产出 Word 原生可编辑公式（<m:oMath>），不引入微软 XSL、不栅格化。
- 图片：按 src 还原磁盘文件字节嵌入（支持 /img?path= 代理、file://、相对路径）。
依赖（随应用内置于 docxdeps/）：python-docx、lxml、latex2mathml、Pillow。
"""
import base64
import copy
import io
import os
import re
import threading
import urllib.parse

from lxml import etree, html as lxml_html
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START
from docx.oxml.ns import qn
try:
    from docx.oxml import OxmlElement
except ImportError:  # python-docx < 1.1 仅暴露于 .parser
    from docx.oxml.parser import OxmlElement

import latex2mathml.converter

# ---------------------------------------------------------------------------
# OMML 命名空间与基础构造
# ---------------------------------------------------------------------------
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# 大运算符集（OMML nary 可承载：字形放大 + 极限位置）。∫∬∭∮∯∰ ∑∏∐
# ⋀⋁ ⨂⨀⨁ ⨄ ⊕⊗ ∪∩ 等；latex2mathml 的 \iiint 产出 ∭（U+222D）单字符
_NARY_OPS = set(
    "\u222b\u222c\u222d\u222e\u222f\u2230"   # ∫ ∬ ∭ ∮ ∯ ∰
    "\u2211\u220f\u2210"                     # ∑ ∏ ∐
    "\u22c0\u22c1"                           # ⋀ ⋁
    "\u2a02\u2a00\u2a01\u2a04"               # ⨂ ⨀ ⨁ ⨄
    "\u2295\u2297"                           # ⊕ ⊗
    "\u22c3\u22c2"                           # ∪ ∩
    "\u2210"                                 # ∐
)


def _mk(tag, *children, **attrib):
    e = etree.Element("{%s}%s" % (M_NS, tag), nsmap={"m": M_NS})
    for k, v in attrib.items():
        e.set("{%s}%s" % (M_NS, k), v)
    for c in children:
        e.append(c)
    return e


def _text_run(text):
    r = _mk("r")
    t = _mk("t")
    t.text = text
    r.append(t)
    return r


def _children(el):
    return [c for c in el if isinstance(c.tag, str)]


# ---------------------------------------------------------------------------
# MathML -> OMML 转换（覆盖常用构造子集）
# ---------------------------------------------------------------------------
def mathml_to_omml(mathml_str):
    root = etree.fromstring(mathml_str.encode("utf-8"))
    omml = _mk("oMath")
    for om in _tr_seq(_children(root)):
        omml.append(om)
    return omml


def _empty_mrow_base(el):
    """msub/msup/msubsup 的 base 是否为空 mrow（无子元素无文本）。

    latex2mathml 对 {}^{a}_{b}X 这类前置角标产出的是【兄弟结构】：
      <msubsup><mrow/>…sub…sup…</msubsup><mi>X</mi>
    中心 X 不在 msubsup 里。OMML 正规写法是 m:sPre（Pre-Sub-Superscript，
    ECMA-376 CT_SPre，Word 公式工具栏的"上下标前置"），且必须把后随
    兄弟吞进 m:e——v2.41.0 方案 §7.9 第七版定案，撤回"隐形定界符包空
    base"的方案 0（主人实测能显示但不是 OMML 正规结构）。"""
    if len(el) == 0:
        return False
    base = None
    for c in el:
        if isinstance(c.tag, str):
            base = c
            break
    if base is None:
        return False
    if etree.QName(base).localname != "mrow":
        return False
    return len(_children(base)) == 0 and not (base.text or "").strip()


def _tr_seq(elems):
    """按序转换一列 MathML 兄弟节点。遇到"空 base 上下标 + 后随兄弟"
    时合并成 m:sPre，一次吞掉两个节点；其余照常逐个 _tr。
    空底无兄弟（如手打的 {}^{3}）不进这里，走 _tr 原路径不崩。"""
    out = []
    i = 0
    n = len(elems)
    while i < n:
        el = elems[i]
        tag = etree.QName(el).localname
        if (tag in ("msub", "msup", "msubsup") and _empty_mrow_base(el)
                and i + 1 < n):
            kids = _children(el)[1:]  # 去掉空 base
            sub = sup = None
            if tag == "msub" and kids:
                sub = _mk("sub", _tr(kids[0]))
            elif tag == "msup" and kids:
                sup = _mk("sup", _tr(kids[0]))
            elif tag == "msubsup" and len(kids) >= 2:
                sub = _mk("sub", _tr(kids[0]))
                sup = _mk("sup", _tr(kids[1]))
            # 子元素序 e、sub、sup，与 sSubSup 同序；缺的一侧留空参数
            # （schema 允许，nary 分支的空 m:e 是先例）
            sp = _mk("sPre", _mk("e", _tr(elems[i + 1])))
            sp.append(sub if sub is not None else _mk("sub"))
            sp.append(sup if sup is not None else _mk("sup"))
            out.append(sp)
            i += 2
            continue
        out.append(_tr(el))
        i += 1
    return out


def _tr(el):
    """把一个 MathML 元素递归转成 OMML 元素。

    v2.4.10 渲染修正（Word COM 导 PDF 实测定位）：
    ① mrow/mstyle 等分组容器 → **无括号** m:d（begChr/endChr 空串）——
      空的 dPr 是默认括号 ( )，此前给所有分组都画上括号（全公式多层
      圆括号、连分式结构崩溃的根因）；真括号来自 \left( 的 mo 字符
      本身与 m:fenced 分支
    ② 大运算符（∑∏∫∭∮ 等）带上下标/limits → m:nary（Word 原生
      大运算符：字形变大、极限位置正确）——此前是普通 sSubSup（角标
      位置、普通字号）与 acc（\limits 的下限跑到上方）"""
    tag = etree.QName(el).localname
    kids = _children(el)
    txt = el.text or ""

    # 叶子：标识符 / 数字 / 算子 / 文本
    if tag in ("mi", "mn", "mo", "mtext", "ms", "annotation"):
        return _text_run(txt)
    if tag == "mspace":
        return _text_run(" ")
    # 分组容器：无括号定界（begChr/endChr 空串 = Word 的"括号-无"）；
    # 子节点走 _tr_seq——sPre 兄弟合并不只发生在顶层，mrow 里面同样要认
    if tag in ("mrow", "mstyle", "mpadded", "mphantom"):
        return _mk("d",
                   _mk("dPr", _mk("begChr", **{"val": ""}),
                       _mk("endChr", **{"val": ""})),
                   _mk("e", *_tr_seq(kids)))

    # 分式
    if tag == "mfrac" and len(kids) >= 2:
        return _mk("f", _mk("num", _tr(kids[0])), _mk("den", _tr(kids[1])))

    # 大运算符判定：base 是 mo 且字符在大运算符集
    def _nary_chr(base):
        if base is not None and etree.QName(base).localname == "mo":
            t = (base.text or "").strip()
            if t and t in _NARY_OPS:
                return t
        return None

    # nary：\limits（munder/mover/munderover）→ 极限在正上/正下
    if tag == "munder" and len(kids) >= 2 and _nary_chr(kids[0]):
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": _nary_chr(kids[0])}),
                       _mk("limLoc", **{"val": "undOvr"})),
                   _mk("sub", _tr(kids[1])), _mk("e"))
    if tag == "mover" and len(kids) >= 2 and _nary_chr(kids[0]):
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": _nary_chr(kids[0])}),
                       _mk("limLoc", **{"val": "undOvr"})),
                   _mk("sup", _tr(kids[1])), _mk("e"))
    if tag == "munderover" and len(kids) >= 3 and _nary_chr(kids[0]):
        # e 留空：nary 的 chr 已承载运算符本体——再放 base 会画出双
        # 运算符（实测 ∏_{j=1}^{m_i} ∏ 双画）
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": _nary_chr(kids[0])}),
                       _mk("limLoc", **{"val": "undOvr"})),
                   _mk("sub", _tr(kids[1])),
                   _mk("sup", _tr(kids[2])),
                   _mk("e"))
    # 普通上下标（_ ^）：base 是大运算符 → nary 角标式（行内式惯例）
    if tag == "msub" and len(kids) >= 2 and _nary_chr(kids[0]):
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": _nary_chr(kids[0])}),
                       _mk("limLoc", **{"val": "subSup"})),
                   _mk("sub", _tr(kids[1])), _mk("e"))
    if tag == "msup" and len(kids) >= 2 and _nary_chr(kids[0]):
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": _nary_chr(kids[0])}),
                       _mk("limLoc", **{"val": "subSup"})),
                   _mk("sup", _tr(kids[1])), _mk("e"))
    if tag == "msubsup" and len(kids) >= 3 and _nary_chr(kids[0]):
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": _nary_chr(kids[0])}),
                       _mk("limLoc", **{"val": "subSup"})),
                   _mk("sub", _tr(kids[1])),
                   _mk("sup", _tr(kids[2])),
                   _mk("e"))

    # 上下标
    if tag == "msub" and len(kids) >= 2:
        return _mk("sSub", _mk("e", _tr(kids[0])), _mk("sub", _tr(kids[1])))
    if tag == "msup" and len(kids) >= 2:
        return _mk("sSup", _mk("e", _tr(kids[0])), _mk("sup", _tr(kids[1])))
    if tag == "msubsup" and len(kids) >= 3:
        return _mk("sSubSup", _mk("e", _tr(kids[0])),
                   _mk("sub", _tr(kids[1])), _mk("sup", _tr(kids[2])))

    # 根式。OMML 结构铁律：m:deg 是 m:rad 的直接子元素（radPr,deg,e
    # 三者平级，radPr 里只允许 degHide）——v2.4.9 前把 deg 塞进 radPr
    # 内属 schema 违规，Word 严格校验直接报"文件损坏"（用户实测
    # \sqrt[3]{...} 全文档唯一触发：该分支自写下从未被真实用例覆盖，
    # 消融锁定 radPr(deg) 即凶手，剥 radPr/deg 均 OK、剥 rPr/degHide
    # 均 FAIL）
    if tag == "msqrt" and kids:
        return _mk("rad",
                   _mk("radPr", _mk("degHide", **{"val": "on"})),
                   _mk("e", _tr(kids[0])))
    if tag == "mroot" and len(kids) >= 2:
        return _mk("rad",
                   _mk("radPr", _mk("degHide", **{"val": "off"})),
                   _mk("deg", _tr(kids[1])),
                   _mk("e", _tr(kids[0])))

    # 上下附加符号（acc 仅向上，munder 降级同样处理）
    if tag in ("mover", "munder") and len(kids) >= 2:
        acc = (kids[1].text or "").strip()
        return _mk("acc",
                   _mk("accPr", _mk("chr", **{"val": acc})),
                   _mk("e", _tr(kids[0])),
                   _mk("sub", _text_run(acc)))

    # 矩阵 / 行列式
    if tag == "mtable":
        m = _mk("m", _mk("mPr", _mk("baseJc", **{"val": "center"})))
        for row in kids:
            if etree.QName(row).localname == "mtr":
                mr = _mk("mr")
                for cell in _children(row):
                    if etree.QName(cell).localname == "mtd":
                        mr.append(_mk("e", *_tr_seq(_children(cell))))
                m.append(mr)
        return m

    # 带框（enclose）：降级成定界分组
    if tag == "menclose":
        return _mk("d", _mk("dPr"), _mk("e", *[_tr(k) for k in kids]))

    # 兜底：把元素文本当普通 run 处理
    return _text_run(txt or "".join(el.itertext()))


# ---------------------------------------------------------------------------
# 样式解析辅助
# ---------------------------------------------------------------------------
def _style_dict(style_str):
    d = {}
    if not style_str:
        return d
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip().lower()] = v.strip()
    return d


def _color(rgb):
    """CSS 颜色字符串 → RGBColor。两种书写形式都必须认：
      ① #RRGGBB（@color 语法写的是 hex，八位 #RRGGBBAA 取前六位——
         w:color 只有一个 w:val，OOXML 没有 alpha 槽，透明度必然丢失）
      ② rgb(r, g, b) / rgba(r, g, b, a) —— 导出前 inlineStylesInto 把
         getComputedStyle 的结果写回 style，恒为 rgb()/rgba() 形式，
         hex 在那里已被抹掉。只认 hex 会让文字颜色全部进不了 Word。
    认不出返回 None（调用方不写颜色槽，保持默认黑）。"""
    s = rgb or ""
    m = re.match(r"#([0-9a-fA-F]{6})", s)
    if m:
        h = m.group(1)
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.match(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", s)
    if m:
        return RGBColor(min(int(m.group(1)), 255),
                        min(int(m.group(2)), 255),
                        min(int(m.group(3)), 255))
    return None


def _pt(size):
    m = re.match(r"([\d.]+)px", size or "")
    if m:
        return float(m.group(1)) * 0.75  # 96dpi 屏显 px -> pt
    m = re.match(r"([\d.]+)pt", size or "")
    if m:
        return float(m.group(1))
    return None


def _align(style_d):
    v = style_d.get("text-align", "")
    if v == "center":
        return WD_ALIGN_PARAGRAPH.CENTER
    if v == "right":
        return WD_ALIGN_PARAGRAPH.RIGHT
    if v == "left":
        return WD_ALIGN_PARAGRAPH.LEFT
    if v == "justify":
        return WD_ALIGN_PARAGRAPH.JUSTIFY
    return None


# ---------------------------------------------------------------------------
# 缩进（v2.2.1 起前端档位为 px 绝对值，正文字号基准；docx 侧换算 pt 消费）
# ---------------------------------------------------------------------------

def _px(key, style_d):
    m = re.match(r"([\d.]+)px", (style_d.get(key) or ""))
    if m:
        return float(m.group(1))
    # longhand 未单独出现时从 shorthand 提取（CSSOM 序列化会把与
    # shorthand 一致的 longhand 合并：margin:10.5px 0px 10.5px 37.33px）
    if key in ("margin-left", "padding-left"):
        sh = style_d.get(key.split("-")[0], "") or ""
        m2 = re.match(r"([\d.]+)px\s+[\d.]+px\s+[\d.]+px\s+([\d.]+)px", sh)
        if m2:
            return float(m2.group(2))
        m3 = re.match(r"([\d.]+)px\s+([\d.]+)px", sh)
        if m3:
            return float(m3.group(2))
    return None


def _bind_num(p, num_id):
    """段落绑定独立编号定义（numPr 位于 pStyle 之后，OOXML pPr 顺序）。"""
    ppr = p._p.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    nid = OxmlElement("w:numId")
    nid.set(qn("w:val"), str(num_id))
    numpr.append(ilvl)
    numpr.append(nid)
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is not None:
        pstyle.addnext(numpr)
    else:
        ppr.insert(0, numpr)


def _style_abstract_num(doc, style_id):
    """样式绑定的 abstractNum 元素（ListNumber/ListBullet 查找公共路径），
    找不到返回 None。"""
    try:
        numbering = doc.part.numbering_part.element
    except Exception:
        return None
    src_num = None
    for st in doc.styles.element.findall(qn("w:style")):
        if st.get(qn("w:styleId")) == style_id:
            numpr = st.find(qn("w:pPr") + "/" + qn("w:numPr"))
            if numpr is not None:
                nid = numpr.find(qn("w:numId"))
                if nid is not None:
                    src_num = int(nid.get(qn("w:val")))
            break
    if src_num is None:
        return None
    src_abs = None
    for num in numbering.findall(qn("w:num")):
        if int(num.get(qn("w:numId"))) == src_num:
            a = num.find(qn("w:abstractNumId"))
            if a is not None:
                src_abs = a.get(qn("w:val"))
            break
    if src_abs is None:
        return None
    for an in numbering.findall(qn("w:abstractNum")):
        if an.get(qn("w:abstractNumId")) == src_abs:
            return an
    return None


def _list_hang_from_css(ts_css):
    """从 ts-style 里读 v2.14.0「列表标记外凸」开关与 marker 槽宽。

    返回 (hang, slot_ol_pt, slot_ul_pt)。ts_css 由前端 applyTypeset 生成，
    开态会写出 `:root{--mde-mark-ol:22.5px;--mde-mark-ul:16.5px;}` 与
    `list-style-position:outside`。两端必须共用同一组数值，否则就是
    「Word 与预览两套几何」——用户反复吃过这类亏，故以 CSS 为单一来源，
    docx 只做 px→pt 换算（×0.75，与全文 `_px` 同口径）。"""
    if not ts_css or "list-style-position:outside" not in ts_css:
        return False, 0.0, 0.0

    def _slot(name, dflt):
        m = re.search(r"--%s:\s*([\d.]+)px" % name, ts_css)
        try:
            return float(m.group(1)) * 0.75
        except Exception:
            return dflt

    # 回落值 = 15px 字号下的 1.5em / 1.1em（与前端 _lBase=15 的缺省一致）
    return True, _slot("mde-mark-ol", 22.5 * 0.75), _slot("mde-mark-ul", 16.5 * 0.75)


def _prep_list_abstract(doc, hang=False):
    """清理列表编号定义的悬挂底座，落成与预览同构的编号语义。

    inside（默认，hang=False）与预览 list-style-position:inside 同构：

    模板 abstractNum lvl0 自带 <w:ind left="360" hanging="360"/> +
    <w:tabs><w:tab w:val="num" w:pos="360"/></w:tabs>，且无 w:suff
    （默认编号后是制表符）。历史缺陷：段落只写 left 时 hanging 从编号
    定义继承——编号被悬到 left−360、tab 跳到 360/720 stop，视觉即
    Word 默认悬挂列表（"1.□□□文字"，编号偏左大间隔）；段落侧曾用
    firstLine=0 防御，但 Word 保存规范化会丢弃 0 值属性（firstLine="0"
    被剥后防御失效）。

    修法（正攻编号定义本身）——lvl0 三件事：
    ① 加 <w:suff w:val="space"/>：编号后一个空格紧贴文字（inside 语义）；
    ② 删 w:ind：去掉悬挂底座，编号起点 = 段落 left（全权由段落定位）；
    ③ 删 w:tabs：去掉悬挂布局的 tab stop 干扰。
    本导出文档的所有 li 段落都显式写 left_indent，改共享定义安全。
    hollow 克隆发生在 prep 之后，自动继承干净定义。

    hang=True（v2.14.0 外凸态）时改为 ①' `<w:suff w:val="tab"/>`：编号后
    用 tab 顶到段落 left（= 档位 + 槽宽），段落侧再写 hanging=槽宽，编号
    就站在文字块外面的槽里，与预览 outside 同构；②③ 与 above 相同。"""
    suff_val = "tab" if hang else "space"
    for style_id in ("ListNumber", "ListBullet"):
        an = _style_abstract_num(doc, style_id)
        if an is None:
            continue
        for lvl in an.findall(qn("w:lvl")):
            if lvl.get(qn("w:ilvl")) != "0":
                continue
            ppr = lvl.find(qn("w:pPr"))
            if ppr is not None:
                for ind in ppr.findall(qn("w:ind")):
                    ppr.remove(ind)
                for tabs in ppr.findall(qn("w:tabs")):
                    ppr.remove(tabs)
            suff = lvl.find(qn("w:suff"))
            if suff is None:
                suff = OxmlElement("w:suff")
                lt = lvl.find(qn("w:lvlText"))
                if lt is not None:
                    lt.addprevious(suff)
                else:
                    lvl.append(suff)
            suff.set(qn("w:val"), suff_val)


def _bullet_num(doc, hollow, ctx):
    """按 marker 类型取 ul 编号实例：solid → List Bullet 样式原生绑定
    （Symbol 实心圆）；hollow → 懒建一次空心圈定义（克隆 List Bullet 的
    abstractNum，lvl0 marker 换 Wingdings 空心圈字符）并缓存于 ctx。
    克隆源已过 _prep_list_abstract（inside 语义），克隆体自动继承。

    语义（本工具规则）：+ 实心 / - 空心跟标记符走、与层级无关——不用
    ilvl 层级 marker（那是"层级换样式"），层级缩进由段落 left_indent
    承载。bullet 无计数语义，全文档共享一个 numId 无连号问题。
    marker 字体不同 → 结构不同，Word 保存规范化不会合并（对照 ol 的
    startOverride 教训：仅 start 差异的同构定义才会被并）。"""
    cache = ctx.setdefault("_bullet_nums", {})
    key = "hollow" if hollow else "solid"
    if key in cache:
        return cache[key]
    if not hollow:
        for st in doc.styles.element.findall(qn("w:style")):
            if st.get(qn("w:styleId")) == "ListBullet":
                numpr = st.find(qn("w:pPr") + "/" + qn("w:numPr"))
                if numpr is not None:
                    nid = numpr.find(qn("w:numId"))
                    if nid is not None:
                        cache[key] = int(nid.get(qn("w:val")))
                        return cache[key]
        return None
    try:
        numbering = doc.part.numbering_part.element
    except Exception:
        return None
    src_el = _style_abstract_num(doc, "ListBullet")
    if src_el is None:
        return None
    src_abs = src_el.get(qn("w:abstractNumId"))
    import copy as _copy
    new_abs = _copy.deepcopy(src_el)
    abs_ids = [int(an.get(qn("w:abstractNumId")))
               for an in numbering.findall(qn("w:abstractNum"))]
    new_abs_id = (max(abs_ids) if abs_ids else 0) + 1
    new_abs.set(qn("w:abstractNumId"), str(new_abs_id))
    # pStyle 引用指向 ListBullet 会造成样式↔编号交叉，摘掉保持定义独立
    for lvl in new_abs.findall(qn("w:lvl")):
        for ps in lvl.findall(qn("w:pStyle")):
            lvl.remove(ps)
        lt = lvl.find(qn("w:lvlText"))
        if lt is not None:
            lt.set(qn("w:val"), "\uF0A7")   # Wingdings 空心圆 ○
        rpr = lvl.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            lvl.append(rpr)
        for rf in rpr.findall(qn("w:rFonts")):
            rpr.remove(rf)
        rf = OxmlElement("w:rFonts")
        rf.set(qn("w:ascii"), "Wingdings")
        rf.set(qn("w:hAnsi"), "Wingdings")
        rf.set(qn("w:hint"), "default")
        rpr.insert(0, rf)
    first_num = numbering.find(qn("w:num"))
    if first_num is not None:
        first_num.addprevious(new_abs)
    else:
        numbering.append(new_abs)
    num_ids = [int(n.get(qn("w:numId")))
               for n in numbering.findall(qn("w:num"))]
    new_num_id = (max(num_ids) if num_ids else 0) + 1
    num_el = OxmlElement("w:num")
    num_el.set(qn("w:numId"), str(new_num_id))
    a_el = OxmlElement("w:abstractNumId")
    a_el.set(qn("w:val"), str(new_abs_id))
    num_el.append(a_el)
    numbering.append(num_el)
    cache[key] = new_num_id
    return new_num_id


def _new_ol_num(doc, start):
    """为单个 <ol> 建独立编号实例（Word 原生机制），返回新 numId。

    机制：所有 ol 共享 List Number 的同一 abstractNum（格式定义），
    每个 ol 建一个新 num 指向它，并在 num 上写
    <w:lvlOverride w:ilvl="0"><w:startOverride w:val="N"/>。
    这是 Word 自己生成"重新开始编号"用的结构——Word 按 num 实例
    分组计数，startOverride 决定起始值，打开/再保存永不丢失。

    历史缺陷两代：① 所有 List Number 段落共享样式绑定的同一 numId
    → 全局连续编号且 <ol start> 丢失；② 曾克隆 abstractNum 设各自
    w:start——非标准做法，Word 保存时做规范化把结构相同的
    abstractNum 合并成一个、start 差异全丢（实测三个 numId 归一后
    用户文档"有序列表项一=1、项二=2、第一项=3、第二项=4"全局连号）。"""
    try:
        numbering = doc.part.numbering_part.element
    except Exception:
        return None
    an = _style_abstract_num(doc, "ListNumber")
    if an is None:
        return None
    src_abs = an.get(qn("w:abstractNumId"))
    num_ids = [int(n.get(qn("w:numId")))
               for n in numbering.findall(qn("w:num"))]
    new_num_id = (max(num_ids) if num_ids else 0) + 1
    try:
        st_v = max(1, int(start))
    except Exception:
        st_v = 1
    num_el = OxmlElement("w:num")
    num_el.set(qn("w:numId"), str(new_num_id))
    a_el = OxmlElement("w:abstractNumId")
    a_el.set(qn("w:val"), src_abs)
    num_el.append(a_el)
    # startOverride 必写（含 1）：num 不带 override 时 Word 视为"继续
    # 序列"并回主序列，带 override 才是独立实例从 N 起计
    lvl = OxmlElement("w:lvlOverride")
    lvl.set(qn("w:ilvl"), "0")
    so = OxmlElement("w:startOverride")
    so.set(qn("w:val"), str(st_v))
    lvl.append(so)
    num_el.append(lvl)
    numbering.append(num_el)
    return new_num_id


# ---------------------------------------------------------------------------
# 图片解析
# ---------------------------------------------------------------------------
def _resolve_img_src(src, md_path):
    if not src:
        return None
    if src.startswith("file:///"):
        return src[len("file:///"):].replace("/", os.sep)
    if src.startswith("file://"):
        return src[len("file://"):].replace("/", os.sep)
    m = re.match(r"/img\?(.+)$", src)
    if m:
        # v2.16.0：src 可能带 &w=（预览缩略图参数），只取 path，别把参数拼进路径
        _q = urllib.parse.parse_qs(m.group(1))
        _p = (_q.get("path") or [""])[0]
        if not _p:
            return None
        return urllib.parse.unquote(_p).replace("\\", os.sep)
    if src.startswith("http://") or src.startswith("https://"):
        return None  # 外部图不内嵌
    # 相对路径：相对当前 md 文件目录
    if md_path:
        base = os.path.dirname(md_path)
        cand = os.path.join(base, src.replace("/", os.sep))
        if os.path.exists(cand):
            return cand
    return None


# ---------------------------------------------------------------------------
# 内联内容 -> docx runs
# ---------------------------------------------------------------------------
# v2.33.0 块级字体继承（@@ begin font）。
# 前端 inlineStylesInto 通常已把计算样式抄到每个元素，这条继承是第二道保险：
# 只要某个 run 自己没写 font-family/font-size（例如 tail 文本挂在无 style 的
# 容器上，或调用方没走内联通道），就沿用它所在的 .mde-font 容器。
# 用 threading.local 而不是全局：导出是逐请求同步的，但也别让并发请求互相串。
_TLS_FONT = threading.local()


def _push_font_style(style):
    prev = getattr(_TLS_FONT, "style", "")
    _TLS_FONT.style = style or ""
    return prev


def _pop_font_style(prev):
    _TLS_FONT.style = prev or ""


def _apply_run_style(run, style_node):
    _own = style_node.get("style", "") if style_node is not None else ""
    _base = getattr(_TLS_FONT, "style", "")
    # 自身声明在后，_style_dict 逐键覆盖 → 元素自己的值优先于容器继承
    sd = _style_dict((_base + ";" + _own) if _base else _own)
    fs = _pt(sd.get("font-size"))
    if fs:
        run.font.size = Pt(fs)
    col = _color(sd.get("color"))
    if col is not None:
        run.font.color.rgb = col
    fw = sd.get("font-weight", "")
    if fw in ("bold", "700", "800", "900") or (fw and fw.isdigit() and int(fw) >= 600):
        run.font.bold = True
    if sd.get("font-style") == "italic":
        run.font.italic = True
    if "underline" in sd.get("text-decoration", ""):
        run.font.underline = True
    fam = _font_family(sd.get("font-family", ""), fallback=getattr(_CTX, "default_font", None))
    if fam:
        run.font.name = fam
        # CJK：font.name 只写 ascii/hAnsi 槽位，中文走 eastAsia——
        # 不补则汉字回落 Word 主题默认字体（微软雅黑/黑体全失效，
        # python-docx 经典坑）。CSS 系统标识符（-apple-system 等）已被
        # _font_family 滤除，不会写进任何字体槽
        try:
            rpr = run._r.get_or_add_rPr()
            rfonts = rpr.get_or_add_rFonts()
            rfonts.set(qn("w:eastAsia"), fam)
        except Exception:
            pass


# 块级子元素：_fill_inline 不拉平（由 _walk 结构分支处理）。
# 历史缺陷：li 内嵌套 ul/ol 时，_fill_inline(li) 把嵌套列表的全部
# 文本拉平进父段落，随后 _walk 又完整处理嵌套列表——嵌套内容双份
# （实测"单行回车不断序单行回车不断序"父段拼接 + 子段重复输出）。
_SKIP_INLINE_TAGS = {"ul", "ol", "table", "blockquote", "pre", "div"}


def _fill_inline(node, para, doc, md_path, max_in=None):
    if node.text:
        _add_run(para, node.text, node)
    for child in _children(node):
        ctag = etree.QName(child).localname
        if ctag in _SKIP_INLINE_TAGS:
            continue
        if ctag == "br":
            para.add_run().add_break()
        elif ctag == "input":
            # v2.14.0：- [ ] / - [x] 的 <input type=checkbox> 在 Word 里没有
            # 对应物，原实现静默丢弃 → 导出的清单只剩文字、框消失。改成
            # 输出与预览同形的字符（checked 是布尔属性，lxml_html 读作 ''）。
            _checked = child.get("checked") is not None
            _add_run(para, "☑" if _checked else "□", child)
        elif ctag == "img":
            _add_image(para, child, md_path, doc, max_in=max_in)
        elif ctag == "svg":
            para.add_run("[图表]")
        elif ctag in ("sup", "sub"):
            # v2.6.10：正文 ^{...} / _{...} 由前端渲染成 <sup>/<sub>。
            # 不在这里转成 Word 的上下标位，文字会退化成普通基线（编号
            # 看着像正文，导出即失真）。样式沿用节点自带 style（字号/颜色）。
            _txt = "".join(child.itertext())
            if _txt:
                _run = _add_run(para, _txt, child)
                _run.font.superscript = (ctag == "sup")
                _run.font.subscript = (ctag == "sub")
        elif child.get("data-tex") is not None:
            _append_omml(para, child.get("data-tex"), child)
        else:
            _fill_inline(child, para, doc, md_path, max_in=max_in)
        if child.tail:
            # tail 在父容器里，样式用父容器的——用 child 会把前一个
            # 行内元素的样式（红/粗）出血到尾随文字（实测 <span>红</span>
            # 后的" 普通"被染红）
            _add_run(para, child.tail, node)


_CSS_NON_FONTS = {
    "apple-system", "blinkmacsystemfont", "system-ui", "sans-serif",
    "serif", "monospace", "cursive", "fantasy", "system",
}


def _font_family(ff, fallback=None):
    """CSS 字体栈 → 第一个真实字体名。过滤 WebKit 系统标识符与泛型族
    （-apple-system 不是字体名——写进 rFonts 时 Word 渲染回落且
    v2.4.7 曾把它带入 OMML run 触发"文件损坏"，见 _style_omml 注释）。
    无真实名返回 fallback（v2.35.1 默认字体显性传递：前端预览环境
    探出 sans-serif 实际命中的字体名随请求传来；Word 不是浏览器，
    泛型族落 Word 主题默认（等线/宋体），与预览从来不同字体——
    探出的名字写进三槽即与预览一致。探不出（None）不写，维持现状。
    调用方不写字体槽。"""
    if not ff:
        return fallback
    for part in re.split(r"[,;]", ff):
        fam = part.strip().strip('"').strip("'").strip()
        if not fam:
            continue
        if fam.lstrip("-").lower() in _CSS_NON_FONTS:
            continue
        return fam
    return fallback


def _add_run(para, text, style_node):
    if not text:
        return
    run = para.add_run(text)
    if style_node is not None and style_node.get("style"):
        _apply_run_style(run, style_node)
    return run


def _content_width_in(doc):
    """版心宽（英寸）——图片尺寸规则的"版面宽度"基准。"""
    try:
        sec = doc.sections[0]
        return (sec.page_width - sec.left_margin - sec.right_margin) / 914400
    except Exception:
        return 6.0


def _img_width_in(doc, img, natural_px, max_in=None):
    """图片显示宽（英寸），与前端 {N} 宽度规则同口径：
    ⓪ data-x-fill（fill 栏内直接图，v2.10.0）→ 直接取 usable：栏内图一律
      相对栏 100%（与不分栏 {N} 相对版心同一语义），usable 已被 max_in
      钳到栏宽——是定宽不是上限，小图同样放大到栏宽；
    ① data-x-pct（{N} 参数）→ 版心 × N%（钳 100），等比靠只传 width；
    ② data-x-w（前端栅格化图的 1x 显示宽）→ px/96dpi；
    ③ 自然尺寸（普通图片：小图原始、大图钳版心）。
    全部以版心为上限（"最大是版面宽度100%"）；max_in（fill 栏宽英寸）
    更小时进一步钳到栏宽。"""
    usable = _content_width_in(doc)
    if max_in is not None and max_in > 0:
        usable = min(usable, max_in)
    if img.get("data-x-fill"):
        return usable
    pct = img.get("data-x-pct")
    if pct:
        try:
            return usable * min(float(pct), 100.0) / 100.0
        except Exception:
            pass
    xw = img.get("data-x-w")
    if xw:
        try:
            return min(float(xw) / 96.0, usable)
        except Exception:
            pass
    if natural_px:
        return min(natural_px / 96.0, usable)
    return None


# ===== v2.16.0「实图输出」=====
# 导出期的目标 dpi 放线程局部：_add_image 被 _walk/_fill_inline 多层调用，
# 贯穿传参会污染一整串签名；md_server 是 ThreadingHTTPServer，模块级变量
# 又会串味，故用 threading.local。
_CTX = threading.local()


def _out_img_dpi():
    return getattr(_CTX, "img_dpi", 0) or 0


def _shrink_to_stream(path, need_px, min_ratio=0.84):
    """把图降到宽 need_px 并编码进内存，返回 BytesIO；不需要缩/没收益/出错 -> None。

    只在导出时用，产物不落盘（add_picture 直接吃 file-like），所以没有临时
    文件要清，也不会在只读的商城安装目录里写东西。

    三道闸与打印链路同口径：只缩不放 / 缩比 <= min_ratio 才动手 /
    编码后不小于原图就放弃。编码选型：带 alpha 或少色（截图、线稿、图表）
    走 PNG（JPEG 会把文字边缘压糊），其余 JPEG q92。
    """
    if not need_px or need_px < 16:
        return None
    if not path or not os.path.isfile(path) or path.lower().endswith(".svg"):
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        return None
    w, h = im.size
    if w <= 1 or h <= 1 or w <= need_px:
        return None
    if need_px / float(w) > min_ratio:
        return None
    has_a = im.mode in ("RGBA", "LA") or "transparency" in im.info
    few = False
    if not has_a:
        try:
            probe = im.convert("RGB").copy()
            probe.thumbnail((120, 120))
            cols = probe.getcolors(maxcolors=1 << 16)
            few = bool(cols) and len(cols) < 4096
        except Exception:
            few = False
    use_png = has_a or few
    try:
        small = im.resize((int(need_px),
                           max(1, int(round(need_px * h / float(w))))),
                          Image.LANCZOS)
        buf = io.BytesIO()
        if use_png:
            small.save(buf, "PNG", optimize=True)
        else:
            small.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
        if buf.tell() >= os.path.getsize(path):
            return None
    except Exception:
        return None
    buf.seek(0)
    return buf


def _add_image(para, img, md_path, doc=None, max_in=None):
    src = img.get("src", "") or ""
    # 前端栅格化的图表 PNG（data URL）：直接解码嵌入
    if src.startswith("data:image/"):
        try:
            data = base64.b64decode(src.split(",", 1)[1])
            natural_px = None
            try:
                from PIL import Image
                natural_px = Image.open(io.BytesIO(data)).size[0]
            except Exception:
                pass
            w_in = _img_width_in(doc, img, natural_px, max_in) if doc else None
            if w_in:
                para.add_run().add_picture(io.BytesIO(data), width=Inches(w_in))
            else:
                para.add_run().add_picture(io.BytesIO(data))
            return
        except Exception:
            para.add_run("[图表]")
            return
    path = _resolve_img_src(src, md_path)
    if not path or not os.path.exists(path):
        # 解析失败：放占位文本，避免丢图
        para.add_run("[图片:%s]" % os.path.basename(path or src))
        return
    try:
        natural_px = None
        try:
            from PIL import Image
            natural_px = Image.open(path).size[0]
        except Exception:
            pass
        w_in = _img_width_in(doc, img, natural_px, max_in) if doc else None
        # v2.16.0 实图输出：按「显示宽(in) × 目标 dpi」降采样，字节只在内存里。
        # 关键：w_in 必须由【原图】的 natural_px 算出，并显式 width= 传给
        # python-docx。若图换成降采样件后让它自己算宽（natural_px/96），
        # 472px 的图会塌成满页：实测显示宽从 40mm 变 166.5mm，版面全毁
        # ——虽然 docx 体积确实能省 97.6%。所以宽度口径与原图死死绑定。
        _dpi = _out_img_dpi()
        _stream = None
        if w_in and _dpi:
            _stream = _shrink_to_stream(path, int(round(w_in * _dpi)))
        _target = _stream if _stream is not None else path
        if w_in:
            para.add_run().add_picture(_target, width=Inches(w_in))
        else:
            para.add_run().add_picture(_target)
    except Exception:
        para.add_run("[图片:%s]" % os.path.basename(path))


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _style_omml(omml, style_node):
    """排版字号应用到公式全部 run（面板"公式字号"，此前从未传进来）。
    OMML run 样式走 w:rPr，Word 规则：m:r 内 rPr 须在 m:t 之前；
    sz 单位半磅。

    v2.4.10 渲染修正（Word COM 导 PDF 实测）：**只写字号、不写字体**——
    OMML 的数学字形（∫∑∏∭）只存在于 Cambria Math，写任何 rFonts
    （哪怕 Segoe UI）都会覆盖 Word 的数学默认字体 → 大运算符渲染为
    豆腐块。字号改变时 Word 仍用 Cambria Math 按比例缩放。"""
    if style_node is None or not style_node.get("style"):
        return
    sd = _style_dict(style_node.get("style", ""))
    fs = _pt(sd.get("font-size"))
    if not fs:
        return
    for r in omml.iter("{%s}r" % M_NS):
        rpr = etree.Element("{%s}rPr" % _W_NS)
        sz = etree.SubElement(rpr, "{%s}sz" % _W_NS)
        sz.set("{%s}val" % _W_NS, str(int(round(fs * 2))))
        szcs = etree.SubElement(rpr, "{%s}szCs" % _W_NS)
        szcs.set("{%s}val" % _W_NS, str(int(round(fs * 2))))
        r.insert(0, rpr)


def _append_omml(para, tex, style_node=None):
    try:
        mathml = None
        try:
            mathml = latex2mathml.converter.convert(tex)
        except Exception:
            # \!（负细空距）让 latex2mathml 直接抛异常（实测三重积分+
            # substack 组合整条退化）；零宽符号 OMML 本就不需要——剥离
            # 重试，仍失败才按纯文本退化
            cleaned = tex.replace("\\!", "")
            if cleaned != tex:
                mathml = latex2mathml.converter.convert(cleaned)
            else:
                raise
        omml = mathml_to_omml(mathml)
        _style_omml(omml, style_node)
        para._p.append(omml)
    except Exception:
        # 公式解析失败：退化为纯文本，保证文档不崩
        para.add_run(tex)


# ---------------------------------------------------------------------------
# 块级遍历
# ---------------------------------------------------------------------------
def _align_from_attr(node):
    """语法级对齐属性（{N c/l/r} 桥接）：img 的 data-img-align /
    图表容器的 data-diagram-align → WD_ALIGN_PARAGRAPH。"""
    v = node.get("data-img-align") or node.get("data-diagram-align")
    if v == "center":
        return WD_ALIGN_PARAGRAPH.CENTER
    if v == "right":
        return WD_ALIGN_PARAGRAPH.RIGHT
    if v == "left":
        return WD_ALIGN_PARAGRAPH.LEFT
    return None


def _img_only_para(node):
    """纯图片段判定：子元素只有 img（可有空白文本节点）且无实质文字——
    首行缩进对其无意义（与前端 p:has(>img) 口径一致）。"""
    has_img = False
    for ch in node:
        if not isinstance(ch.tag, str):
            continue
        t = etree.QName(ch).localname
        if t == "img":
            has_img = True
        elif (ch.text or "").strip() or (ch.tail or "").strip():
            return False
        elif t not in ("br",):
            return False
    if (node.text or "").strip():
        return False
    return has_img


class _CellDoc:
    """fill 单元格写入代理：拦截 add_paragraph/add_table 转投目标 cell
    （_walk 里 doc.add_paragraph 追加 body 末尾，不进单元格——代理转发）。"""

    def __init__(self, cell):
        self._cell = cell
        self.part = cell.part

    def add_paragraph(self, *args, **kw):
        p = self._cell.add_paragraph()
        # add_paragraph(style=...) 参数按需应用
        style = kw.get("style") or (args[0] if args else None)
        if style:
            p.style = style
        return p

    def add_table(self, *args, **kw):
        t = self._cell.add_table(*args, **kw)
        return t

    def add_heading(self, *args, **kw):
        p = self._cell.add_paragraph()
        p.style = kw.get("style") or "Heading %d" % (
            kw.get("level") or (args[0] if args and isinstance(args[0], int)
                                else 1))
        return p

    def add_page_break(self):
        return None

    @property
    def sections(self):
        return self._cell.part.document.sections

    @property
    def styles(self):
        return self._cell.part.document.styles

    @property
    def paragraphs(self):
        return self._cell.paragraphs

    @property
    def tables(self):
        return self._cell.tables


def _tbl_no_borders(tbl):
    """清边框（fill 分栏表格纯当布局骨架，视觉不可见）+ 单元格边距清零。"""
    tblPr = tbl._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right",
                 "insideH", "insideV"):
        el = OxmlElement("w:" + side)
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        borders.append(el)
    tblPr.append(borders)
    for old in tblPr.findall(qn("w:tblCellMar")):
        tblPr.remove(old)
    mar = OxmlElement("w:tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement("w:" + side)
        el.set(qn("w:w"), "0")
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)



def _walk(node, doc, md_path, ctx):
    if not isinstance(node.tag, str):
        return
    tag = etree.QName(node).localname
    cls = node.get("class", "") or ""
    tex = node.get("data-tex")

    # 公式（样式节点 = 公式元素自身：inlineStylesInto 的字号/字体快照
    # 随 data-tex 一起传给 OMML run）
    if tex is not None:
        if "md-math-block" in cls.split():
            p = doc.add_paragraph()
            _append_omml(p, tex, node)
        else:
            p = ctx.get("para") or doc.add_paragraph()
            _append_omml(p, tex, node)
        return

    # 标题
    if re.match(r"h[1-6]$", tag):
        level = int(tag[1])
        p = doc.add_heading(level=level)
        _fill_inline(node, p, doc, md_path, max_in=ctx.get("max_in"))
        ctx["para"] = None
        return

    # 引用：整体缩进（margin-left px，回落 0.3in）进 ctx 块级栈，
    # 直接文本与递归子块统一消费
    if tag == "blockquote":
        sd = _style_dict(node.get("style", ""))
        ml = _px("margin-left", sd)
        q_ind = float(ctx.setdefault("ind", 0.0)) + (
            ml * 0.75 if ml is not None else 21.6)
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(q_ind)
        if node.text and node.text.strip():
            _add_run(p, node.text, node)
        saved = ctx["ind"]
        ctx["ind"] = q_ind
        for ch in _children(node):
            ctag = etree.QName(ch).localname
            if ctag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol", "pre", "table"):
                _walk(ch, doc, md_path, ctx)
            else:
                _fill_inline(ch, p, doc, md_path, max_in=ctx.get("max_in"))
            if ch.tail and ch.tail.strip():
                _add_run(p, ch.tail, ch)
        ctx["ind"] = saved
        ctx["para"] = None
        return

    # 列表：每个 ol 独立编号定义（<ol start> 接力语义；共享 numId 会跨列表
    # 连号且 start 丢失）；ul 的 marker 在 li 级（+ 与 - 可混排于同一 ul，
    # data-li-marker 桥接自前端 class）；列表档 margin-left px + ctx 栈
    if tag in ("ul", "ol"):
        sd = _style_dict(node.get("style", ""))
        own_ml = (_px("margin-left", sd) or 0) * 0.75
        base = float(ctx.setdefault("ind", 0.0)) + own_ml
        # v2.14.0 外凸：槽宽随有序/无序分档，来自 ts-style 的 --mde-mark-*
        _lhang = ctx.get("lhang") or (False, 0.0, 0.0)
        hang_on = bool(_lhang[0])
        slot = float(_lhang[1] if tag == "ol" else _lhang[2])
        ol_num = None
        if tag == "ol":
            ol_num = _new_ol_num(doc, node.get("start") or 1)
        hollow_num = None   # 按需懒建：遇 data-li-marker=hollow 才取
        for li in _children(node):
            if etree.QName(li).localname == "li":
                is_task = "task" in (li.get("class") or "").split()
                if is_task:
                    # v2.14.0：- [ ] / - [x] 在预览里没有 marker（方框自己
                    # 就是标记），Word 侧同样不绑编号，否则会多出一个圆点。
                    p = doc.add_paragraph()
                else:
                    p = doc.add_paragraph(
                        style="List Bullet" if tag == "ul" else "List Number")
                    if ol_num is not None:
                        _bind_num(p, ol_num)
                    elif tag == "ul" and li.get("data-li-marker") == "hollow":
                        if hollow_num is None:
                            hollow_num = _bullet_num(doc, True, ctx)
                        if hollow_num is not None:
                            _bind_num(p, hollow_num)
                # 压掉编号级悬挂：ListNumber/ListBullet 的 abstractNum lvl0
                # 自带 <w:ind left="360" hanging="360"/>，段落只写 left 时
                # hanging 继承 → Word 把编号悬挂在 left-360 处（比块内
                # 正文浅一层半，"列表没继承缩进"）。显式 firstLine=0 让
                # 编号与文本都从容器左缘起（inside 语义，与预览同几何）。
                # 外凸态反过来：left = 档 + 槽、firstLine = −槽，编号站进
                # 槽里（Word 的悬挂列表标准写法），文字块整体右移一槽。
                if hang_on and not is_task:
                    p.paragraph_format.left_indent = Pt(base + slot)
                    p.paragraph_format.first_line_indent = Pt(-slot)
                elif hang_on and is_task:
                    # task 项无 marker，不悬挂：与兄弟项文字同一左沿
                    p.paragraph_format.left_indent = Pt(base + slot)
                    p.paragraph_format.first_line_indent = Pt(0)
                else:
                    p.paragraph_format.left_indent = Pt(base)
                    p.paragraph_format.first_line_indent = Pt(0)
                _fill_inline(li, p, doc, md_path, max_in=ctx.get("max_in"))
                # li 内嵌套列表：嵌套层缩进 = 本层容器档 + 嵌套自身档
                for sub in _children(li):
                    if etree.QName(sub).localname in ("ul", "ol"):
                        saved = ctx["ind"]
                        ctx["ind"] = base
                        _walk(sub, doc, md_path, ctx)
                        ctx["ind"] = saved
        ctx["para"] = None
        return

    # 代码块
    if tag == "pre":
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(
            float(ctx.setdefault("ind", 0.0)) + 14.4)
        text = node.text_content()
        run = p.add_run(text)
        run.font.name = "Consolas"
        run.font.size = Pt(10)
        ctx["para"] = None
        return

    # 图片题注容器（v2.10.0）：<figure><img><figcaption>——图与题注
    # 必须是两个段落（同段落时题注会被挤在图片行里）
    if tag == "figure":
        _add_figure(node, doc, md_path, ctx)
        return

    # 表格
    if tag == "table":
        _add_table(doc, node, md_path)
        ctx["para"] = None
        return

    # SVG（前端栅格化回落保留下来的）：占位，不把 SVG 文本抽成垃圾文字
    if tag == "svg":
        p = doc.add_paragraph("[图表]")
        ctx["para"] = None
        return

    # 独立成块的图片（图表容器 div 里的栅格化 PNG 等；历史上 img 只出现在
    # <p> 内，裸 div 下钻后 img 会直接进 _walk）：对齐优先级 = 语法级
    # （data-img-align / 容器 data-diagram-align）> 容器计算样式 text-align
    if tag == "img":
        p = doc.add_paragraph()
        al = _align_from_attr(node)
        if al is None:
            parent = node.getparent()
            if parent is not None:
                # 图表容器：桥接的 data-diagram-align 优先于内联样式
                al = _align_from_attr(parent)
                if al is None:
                    al = _align(_style_dict(parent.get("style", "")))
        if al is not None:
            p.alignment = al
        _add_image(p, node, md_path, doc, max_in=ctx.get("max_in"))
        ctx["para"] = None
        return

    # fill 分栏布局（data-fill-row 桥接自前端 .fill-row）：无边框表格
    # 当布局骨架（Word 原生多图并排做法），列宽 = 版心 × 比例；
    # 栏内容递归 _walk（图片/图表段在单元格内）；<<继承链的块级缩进
    # 由表格 left_indent 承载
    # @@ caption 表格包裹（v2.10.0）：题注段 + 表格，顺序由 data-tab-side
    # 定。必须排在通用 div 分支之前——否则题注会被当普通 div 下钻，
    # 表格与题注的相邻关系（keepNext / 段序）就丢了
    if tag == "div" and node.get("data-tab-wrap"):
        _add_tabwrap(node, doc, md_path, ctx)
        return

    if tag == "div" and node.get("data-fill-row"):
        cols = [ch for ch in _children(node)
                if isinstance(ch.tag, str)
                and etree.QName(ch).localname == "div"]
        if not cols:
            return
        usable_mm = _content_width_in(doc) * 25.4
        ratios = []
        for ch in cols:
            try:
                ratios.append(float(ch.get("data-fill") or 0))
            except Exception:
                ratios.append(0.0)
        total = sum(ratios) or 100.0
        n = len(cols)
        tbl = doc.add_table(rows=1, cols=n)
        tbl.autofit = False
        # 无边框（布局骨架视觉不可见）+ 固定列宽
        _tbl_no_borders(tbl)
        for ci in range(n):
            w_mm = usable_mm * ratios[ci] / total
            col_mm = Mm(max(5.0, w_mm))
            tbl.cell(0, ci).width = col_mm
            tbl.columns[ci].width = col_mm   # 列宽必须落 tblGrid 才生效
        for ci, ch in enumerate(cols):
            cell = tbl.cell(0, ci)
            base_saved = float(ctx.get("ind", 0.0))
            celldoc = _CellDoc(cell)
            # max_in：图宽上限=栏宽（v2.10.0）。栏内宽度参数失效后，栏内
            # 图片（含 figure/表格内图）的"自然尺寸钳版心"要换成钳栏宽，
            # 否则大图从单元格里溢出
            cell_ctx = {"para": None, "ind": 0.0,
                        "max_in": usable_mm * ratios[ci] / total / 25.4}
            for sub in _children(ch):
                _walk(sub, celldoc, md_path, cell_ctx)
            # 清掉单元格默认空首段（有后续内容时；OOXML 要求 cell ≥1 段）
            try:
                fp = cell.paragraphs[0]
                if (not fp.text.strip() and not fp.runs
                        and len(cell.paragraphs) > 1):
                    fp._p.getparent().remove(fp._p)
            except Exception:
                pass
            ctx["ind"] = base_saved
        # 表格整体缩进 = <<< 块级栈（Word 表格缩进走 tblInd）
        try:
            tblPr = tbl._tbl.tblPr
            ind = tblPr.find(qn("w:tblInd"))
            if ind is None:
                ind = OxmlElement("w:tblInd")
                tblPr.append(ind)
            base2 = float(ctx.get("ind", 0.0))
            ind.set(qn("w:w"), str(int(base2 * 20)))   # pt→twips
            ind.set(qn("w:type"), "dxa")
        except Exception:
            pass
        ctx["para"] = None
        return

    # 块级包裹 div（前端增量分块渲染的 .pblk / <<< 缩进包围块 .ind-blk，
    # class 已被内联样式流程剥掉）：margin-left 累入 ctx 块级缩进栈后
    # 下钻递归子块；直接文本节点兜底为段落，不丢内容
    if tag == "div":
        sd = _style_dict(node.get("style", ""))
        # v2.33.0：.mde-font 容器把字体/字号压进继承上下文，块内所有 run 生效
        _font_prev = _push_font_style(node.get("style", ""))             if "mde-font" in cls.split() else None
        ml = _px("margin-left", sd)
        base = float(ctx.setdefault("ind", 0.0)) + (
            ml * 0.75 if ml is not None else 0)
        if node.text and node.text.strip():
            p = doc.add_paragraph()
            if base:
                p.paragraph_format.left_indent = Pt(base)
            _add_run(p, node.text, node)
        saved = ctx["ind"]
        ctx["ind"] = base
        for ch in _children(node):
            _walk(ch, doc, md_path, ctx)
            if ch.tail and ch.tail.strip():
                tp = doc.add_paragraph()
                if base:
                    tp.paragraph_format.left_indent = Pt(base)
                _add_run(tp, ch.tail, ch)
        ctx["ind"] = saved
        ctx["para"] = None
        if _font_prev is not None:
            _pop_font_style(_font_prev)
        return

    # 段落（p）：首行缩进/悬挂缩进（前端 px 档位）+ ctx 块级缩进栈。
    # 纯图片段不参与首行缩进（与 .diagram 块级容器口径统一锚定版心左边；
    # 前端 CSS p:has(>img){text-indent:0} 同语义，docx 此处显式跳过）
    if tag == "p":
        p = doc.add_paragraph()
        sd = _style_dict(node.get("style", ""))
        al = _align(sd)
        # 语法级对齐（{N c/l/r}）优先于面板全局档（内联 text-align）
        _ia = None
        for ch in _children(node):
            if etree.QName(ch).localname == "img":
                _ia = _align_from_attr(ch)
                if _ia is not None:
                    break
        if _ia is not None:
            al = _ia
        if al is not None:
            p.alignment = al
        base = float(ctx.setdefault("ind", 0.0))
        _only_img = _img_only_para(node)
        ti = None if _only_img else _px("text-indent", sd)
        pl = None if _only_img else _px("padding-left", sd)
        if pl is not None and ti is not None and ti < 0:
            # 悬挂缩进（前端 padding-left + 负 text-indent 组合）
            p.paragraph_format.left_indent = Pt(base + pl * 0.75)
            p.paragraph_format.first_line_indent = Pt(ti * 0.75)
        elif ti is not None and ti > 0:
            p.paragraph_format.first_line_indent = Pt(ti * 0.75)
            if base:
                p.paragraph_format.left_indent = Pt(base)
        elif base:
            p.paragraph_format.left_indent = Pt(base)
        _fill_inline(node, p, doc, md_path, max_in=ctx.get("max_in"))
        ctx["para"] = None
        return

    # 其它：当作内联内容挂到当前段落（或新建）
    p = ctx.get("para") or doc.add_paragraph()
    _fill_inline(node, p, doc, md_path, max_in=ctx.get("max_in"))
    ctx["para"] = p


def _cap_pt(cap_node, default=9.0):
    """题注字号（pt）：取自内联 font-size（排版面板「图题/表题」档经
    inlineStylesInto 抄进来），认不出按 9pt。"""
    sd = _style_dict(cap_node.get("style", ""))
    return _pt(sd.get("font-size")) or default


def _narrow_para(p, doc, pct, al):
    """题注段落按图片显示宽缩窄 —— 这就是「按宽度换行」在 Word 里的
    落地方式：段落宽度 = 图宽，文字自然在框内折行。图居中则左右各留
    (版心-图宽)/2，居左右侧留白，居右左侧留白。pct 认不出（"auto" 或
    非法）时不缩窄，题注按版心宽折行（HTML 侧的 w 裁剪在 Word 无对应
    槽位，一律交给 Word 自己的折行规则）。"""
    try:
        ratio = float(pct)
    except (TypeError, ValueError):
        return
    usable = _content_width_in(doc)
    w = usable * min(max(ratio, 1.0), 100.0) / 100.0
    rest = max(usable - w, 0.0)
    if al == WD_ALIGN_PARAGRAPH.CENTER:
        left = right = rest / 2.0
    elif al == WD_ALIGN_PARAGRAPH.RIGHT:
        left, right = rest, 0.0
    else:
        left, right = 0.0, rest
    if left:
        p.paragraph_format.left_indent = Pt(left * 72)   # inch → pt
    if right:
        p.paragraph_format.right_indent = Pt(right * 72)


def _add_figure(node, doc, md_path, ctx):
    """<figure>（图 + 题注）：两段的先后由 data-fig-side 定（t=题注在上、
    b=在下，默认 b），间距 s<n> 是「题注字号 × n」，落在题注与图相邻的那
    一侧（题注在下写 space_before，在上写 space_after）；相邻段 keepNext
    保证图与题注不被分页拆开。v2.10.0：主体也可以是图表容器（围栏图题
    ```mermaid "题注" 产出 figure>div.diagram）——div.diagram 走既有
    _walk 下钻（栅格化 PNG 或 svg 占位），对齐沿用 data-diagram-align。"""
    img = None
    cap = None
    charts = []
    for ch in _children(node):
        t = etree.QName(ch).localname
        if t == "img" and img is None:
            img = ch
        elif t == "figcaption" and cap is None:
            cap = ch
        elif t == "div" and ch.get("data-diagram") is not None:
            charts.append(ch)
    if img is None and cap is None and not charts:
        return
    side = (node.get("data-fig-side") or "b").strip().lower()
    try:
        gap = float(node.get("data-fig-gap") or 0.3)
    except (TypeError, ValueError):
        gap = 0.3

    fig_al = _align_from_attr(img) if img is not None else None
    if fig_al is None and charts:
        fig_al = _align_from_attr(charts[0])
    if fig_al is None:
        fig_al = _align(_style_dict(node.get("style", "")))
    cap_al = _align(_style_dict(cap.get("style", ""))) if cap is not None else None
    if cap_al is None:
        cap_al = fig_al

    def mk_img():
        p = doc.add_paragraph()
        if fig_al is not None:
            p.alignment = fig_al
        _add_image(p, img, md_path, doc, max_in=ctx.get("max_in"))
        return p

    def mk_cap():
        p = doc.add_paragraph()
        try:
            p.style = doc.styles["Caption"]
        except KeyError:
            pass
        if cap_al is not None:
            p.alignment = cap_al
        gap_pt = _cap_pt(cap) * gap
        if side == "t":
            p.paragraph_format.space_after = Pt(gap_pt)
        else:
            p.paragraph_format.space_before = Pt(gap_pt)
        _narrow_para(p, doc, node.get("data-fig-w"), cap_al)
        _fill_inline(cap, p, doc, md_path, max_in=ctx.get("max_in"))
        return p

    order = [("cap", mk_cap), ("img", mk_img)] if side == "t" \
        else [("img", mk_img), ("cap", mk_cap)]
    made = []
    for kind, fn in order:
        if kind == "img":
            if img is not None:
                made.append(fn())
            elif charts:
                # 图表主体：逐个 diagram 容器下钻（各自成段），首段带对齐
                for ci, c in enumerate(charts):
                    p = doc.add_paragraph()
                    if ci == 0 and fig_al is not None:
                        p.alignment = fig_al
                    _walk(c, doc, md_path, ctx)
                    made.append(p)
        elif kind == "cap" and cap is not None:
            made.append(fn())
    if len(made) == 2:
        made[0].paragraph_format.keep_with_next = True
    ctx["para"] = None


def _add_tabwrap(node, doc, md_path, ctx):
    """@@ caption 生成的表格包裹：题注段 + 表格。题注位置由
    data-tab-side 定（t=表上、b=表下，默认 t）；表格宽 = 版心，
    题注不缩窄，只按 data-tab-align 对齐。"""
    cap = None
    tbl = None
    for ch in _children(node):
        t = etree.QName(ch).localname
        if t == "table" and tbl is None:
            tbl = ch
        elif t == "div" and cap is None:
            cap = ch
    if tbl is None and cap is None:
        return
    side = (node.get("data-tab-side") or "t").strip().lower()
    try:
        gap = float(node.get("data-tab-gap") or 0.3)
    except (TypeError, ValueError):
        gap = 0.3
    cap_al = _align(_style_dict(cap.get("style", ""))) if cap is not None else None

    def mk_cap():
        p = doc.add_paragraph()
        try:
            p.style = doc.styles["Caption"]
        except KeyError:
            pass
        if cap_al is not None:
            p.alignment = cap_al
        gap_pt = _cap_pt(cap) * gap
        if side == "b":
            p.paragraph_format.space_after = Pt(gap_pt)
        else:
            p.paragraph_format.space_before = Pt(gap_pt)
        _fill_inline(cap, p, doc, md_path, max_in=ctx.get("max_in"))
        return p

    def mk_tbl():
        _add_table(doc, tbl, md_path, max_in=ctx.get("max_in"))
        return None

    order = [("tbl", mk_tbl), ("cap", mk_cap)] if side == "b" \
        else [("cap", mk_cap), ("tbl", mk_tbl)]
    made = []
    for kind, fn in order:
        if (kind == "tbl" and tbl is None) or (kind == "cap" and cap is None):
            continue
        made.append((kind, fn()))
    # 题注在上时与表格同页；表格不得与题注分页拆开
    if side != "b" and made and made[0][1] is not None:
        made[0][1].paragraph_format.keep_with_next = True
    ctx["para"] = None


def _add_table(doc, table, md_path, max_in=None):
    # 真实前端结构为 <table><thead><tr><th>… 与 <tbody><tr><td>…（历史缺陷：
    # 只认 table 直接子级 tr，thead/tbody 包装下行收集为空，表格整块丢弃）
    trs = table.xpath(".//*[local-name()='tr']")
    rows = []
    for tr in trs:
        cells = [c for c in _children(tr)
                 if etree.QName(c).localname in ("td", "th")]
        if cells:
            rows.append(cells)
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    nrows = len(rows)
    dt = doc.add_table(rows=nrows, cols=ncols)
    dt.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if j >= ncols:
                continue
            # 直接在单元格预建的首段里填充 run：颜色/加粗/字号/上下标/公式
            # 才能进 Word。历史缺陷：cell.text_content() 只取纯文本，
            # 整张表的行内格式（含 @@ color）全部丢失。
            _fill_inline(cell, dt.cell(i, j).paragraphs[0], doc, md_path,
                         max_in=max_in)
    # 表头加粗首行（th 语义；单元格内已带 bold 时重复设置无害）
    for j in range(ncols):
        for r in dt.rows[0].cells[j].paragraphs[0].runs:
            r.font.bold = True


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
# 纸张尺寸 mm 表（与 md_server PAPER_W_MM/PAPER_H_MM 同源同值）
PAPER_MM = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
    "A4": (210, 297), "A5": (148, 210), "B0": (1000, 1414), "B1": (707, 1000),
    "B2": (500, 707), "B3": (353, 500), "B4": (250, 353), "B5": (176, 250),
    "Letter": (215.9, 279.4), "Legal": (215.9, 355.6), "Ledger": (279.4, 431.8),
}
MARGIN_DEFAULTS = {"mt": 25, "mr": 18, "mb": 25, "ml": 18}


def _apply_page_section(doc, page_cfg):
    """排版纸张/页边距 → docx section。默认 A4（与排版面板默认一致，
    替代 python-docx 模板的 Letter/1in-1.25in——历史缺陷：排版面板的
    纸张设置从未作用于 docx）。图片版心宽由 _content_width_in 动态读
    section，设完后 {N} 宽度规则自动按新版心换算，无需另改。"""
    cfg = page_cfg or {}
    paper = cfg.get("paper", "A4")
    if paper == "custom":
        try:
            w, h = float(cfg.get("pw") or 0), float(cfg.get("ph") or 0)
        except Exception:
            w = h = 0
        if w <= 0 or h <= 0:
            paper = "A4"
    if paper == "custom":
        w_mm, h_mm = w, h
    else:
        w_mm, h_mm = PAPER_MM.get(paper, (210, 297))
    try:
        sec = doc.sections[0]
        sec.page_width = Mm(w_mm)
        sec.page_height = Mm(h_mm)
        sec.top_margin = Mm(float(cfg.get("mt", MARGIN_DEFAULTS["mt"])))
        sec.right_margin = Mm(float(cfg.get("mr", MARGIN_DEFAULTS["mr"])))
        sec.bottom_margin = Mm(float(cfg.get("mb", MARGIN_DEFAULTS["mb"])))
        sec.left_margin = Mm(float(cfg.get("ml", MARGIN_DEFAULTS["ml"])))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 内置样式净化（标题 / 题注的主题蓝）
# ---------------------------------------------------------------------------
# python-docx 默认模板里这些样式自带主题色 + 加粗：
#   Title 17365D / Heading 1 365F91 / Heading 2~6 与 Caption 4F81BD，
#   全部带 w:themeColor="accent1"。add_heading() 套上 Heading 样式后，
#   段落与 run 上都没有 color 槽位（作者没显式上色时 inlineStylesInto
#   不再抄主题色——见 v2.9.0「导出字色」修复）→ Word 取样式值，
#   于是整篇标题和题注都是蓝的。
# 这里把颜色钉死为黑并删掉主题色属性（OOXML 里 themeColor 存在时 Word
# 优先用主题色，只改 val 无效），题注另摘掉加粗。
# 作者显式上色的标题（@@ color）不受影响：那是 run 级 w:color，优先级
# 高于样式级。
_BLUISH_STYLES = ("Title", "Heading 1", "Heading 2", "Heading 3",
                  "Heading 4", "Heading 5", "Heading 6", "Caption")


def _sanitize_builtin_styles(doc):
    """返回被处理的样式个数（自测/验收可断言）。"""
    clean = 0
    for name in _BLUISH_STYLES:
        try:
            st = doc.styles[name]
        except KeyError:
            continue
        rpr = st.element.find(qn("w:rPr"))
        if rpr is None:
            continue
        col = rpr.find(qn("w:color"))
        if col is not None:
            for attr in ("themeColor", "themeShade", "themeTint"):
                key = qn("w:" + attr)
                if key in col.attrib:
                    del col.attrib[key]
            col.set(qn("w:val"), "000000")
            clean += 1
        if name == "Caption":
            for t in ("w:b", "w:bCs"):
                b = rpr.find(qn(t))
                if b is not None:
                    rpr.remove(b)
    return clean


def _apply_char_spacing(doc, ts_css, page_cfg):
    """v2.40.0 每行字数 → Word 的字符间距（w:spacing，单位 1/20 pt）。

    尺子只有一把：ls_em 从 ts-style 里读（`:root{--mde-ls:0.5658em}`），
    这里只做 em→twips 的换算，绝不重算版心。重算就是「Word 与预览两套
    几何」，这类账以前吃过不止一次。

    豁免与面板六个勾选一一对应：标题按 Heading N 的级别跳过，表格按祖先
    w:tbl 跳过。z 顺序：w:spacing 必须落在 w:sz 之前（ECMA-376 的 rPr
    子元素序列），乱序 Word 会直接忽略这条属性。
    """
    if not ts_css:
        return 0
    m = re.search(r"--mde-ls:\s*([\d.]+)em", ts_css)
    if not m:
        return 0
    try:
        ls_em = float(m.group(1))
    except ValueError:
        return 0
    if ls_em <= 0:
        return 0
    # 正文档没写字号时，正文 run 没有 w:sz，只有段落样式的默认值：用 ts-style
    # 里 p 的 font-size 兜底，再不行才 10.5pt（Word 中文正文默认五号）。
    base_pt = 10.5
    mp = re.search(r"#preview p, \.markdown-body p\{[^}]*font-size:([\d.]+)pt", ts_css)
    if mp:
        try:
            base_pt = float(mp.group(1))
        except ValueError:
            pass

    ex = (page_cfg or {}).get("cjEx") or {}
    hall = bool(ex.get("hall"))
    by_lvl = {1: bool(ex.get("h1")), 2: bool(ex.get("h2")), 3: bool(ex.get("h3"))}
    skip_tbl = bool(ex.get("tbl"))
    body = doc.element.body
    n = 0
    for p in body.iter(qn("w:p")):
        anc = p.getparent()
        in_tbl = False
        while anc is not None and anc is not body:
            if anc.tag == qn("w:tbl"):
                in_tbl = True
                break
            anc = anc.getparent()
        if in_tbl and skip_tbl:
            continue
        lvl = 0
        ppr = p.find(qn("w:pPr"))
        if ppr is not None:
            ps = ppr.find(qn("w:pStyle"))
            if ps is not None:
                pm = re.match(r"Heading\s*(\d)$", ps.get(qn("w:val")) or "")
                if pm:
                    lvl = int(pm.group(1))
        if lvl and (hall or by_lvl.get(lvl) or lvl >= 4):
            continue
        # 标题 run 通常没有 w:sz（字号来自段落样式），不补这一档就会把标题
        # 按正文字号算字距：16pt 的 H1 会拿到 11.25pt 的值，整整小一圈。
        lvl_pt = None
        if lvl:
            try:
                _st = doc.styles["Heading %d" % lvl]
                if _st.font.size:
                    lvl_pt = _st.font.size.pt
            except Exception:
                lvl_pt = None
        for r in p.findall(qn("w:r")):
            rpr = r.find(qn("w:rPr"))
            pt = None
            if rpr is not None:
                szel = rpr.find(qn("w:sz"))
                if szel is not None:
                    try:
                        pt = int(szel.get(qn("w:val"))) / 2.0
                    except (TypeError, ValueError):
                        pt = None
            if not pt:
                pt = lvl_pt or base_pt
            val = int(round(ls_em * pt * 20))
            if val <= 0:
                continue
            if rpr is None:
                rpr = OxmlElement("w:rPr")
                r.insert(0, rpr)
            sp = rpr.find(qn("w:spacing"))
            if sp is None:
                sp = OxmlElement("w:spacing")
                szel = rpr.find(qn("w:sz"))
                if szel is not None:
                    szel.addprevious(sp)
                else:
                    rpr.append(sp)
            sp.set(qn("w:val"), str(val))
            n += 1
    return n


def build_docx(md_path, body_html, ts_css=None, page_cfg=None,
               default_font=None):
    """body_html: 已内联样式的 HTML 片段（含 .markdown-body 根）。
    page_cfg: 排版面板 page 节（纸张/页边距），None 用 A4 默认。
    default_font: 预览环境探出的默认字体名（v2.35.1 显性传递，None 维持
    Word 主题回落）。存 _CTX（threading.local）供模块级 _apply_run_style 取。
    返回 .docx 字节。"""
    _CTX.default_font = (str(default_font or "").strip().replace('"', "") or None)
    # v2.16.0 实图输出档位：orig（默认，全用原图）/ 300 / 150
    _mode = str((page_cfg or {}).get("img") or "orig")
    _CTX.img_dpi = 300 if _mode == "300" else (150 if _mode == "150" else 0)
    doc = Document()
    _sanitize_builtin_styles(doc)
    # v2.35.1 默认字体显性传递的落点：Word 不是浏览器，泛型族落主题默认
    # （等线/宋体），与预览从来不同字体。run 级 _font_family 只在 run 自带
    # CSS 时触发（绝大多数 run 无内联 style，兜不到）——必须在文档默认
    # 样式层写：Normal 覆盖正文/表格/列表，标题/题注各有样式一并写入。
    # 同时删 theme* 属性：w:rFonts 上 themeAscii/themeEastAsia 存在时
    # 优先于显式值，不删等于白写。
    if _CTX.default_font:
        for _sname in ("Normal", "Heading 1", "Heading 2", "Heading 3",
                       "Heading 4", "Heading 5", "Heading 6", "Caption",
                       "Title", "Subtitle"):
            try:
                _st = doc.styles[_sname]
            except KeyError:
                continue
            _rpr = _st.element.get_or_add_rPr()
            _rf = _rpr.get_or_add_rFonts()
            for _slot in ("ascii", "hAnsi", "eastAsia", "cs"):
                _rf.set(qn("w:" + _slot), _CTX.default_font)
            for _slot in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                _key = qn("w:" + _slot)
                if _key in _rf.attrib:
                    del _rf.attrib[_key]
    _apply_page_section(doc, page_cfg)
    # 列表编号定义要在建 li 段落之前定稿：外凸态编号后走 tab，inside 态走空格
    hang, slot_ol, slot_ul = _list_hang_from_css(ts_css)
    _prep_list_abstract(doc, hang)
    root = lxml_html.fromstring(body_html)
    # 找到正文根（兼容传 outerHTML 含 article.markdown-body，或裸片段）
    mb = root
    if isinstance(root.tag, str) and etree.QName(root).localname == "html":
        found = root.xpath(".//*[@class='markdown-body']")
        if found:
            mb = found[0]
    elif isinstance(root.tag, str) and "markdown-body" not in (root.get("class", "") or ""):
        found = root.xpath(".//*[@class='markdown-body']")
        if found:
            mb = found[0]
    ctx = {"para": None, "ind": 0.0, "lhang": (hang, slot_ol, slot_ul)}

    def _sect_valign_el(sectPr, val):
        """w:vAlign 施加到 sectPr 元素（schema：w:cols 之后、w:docGrid 之前）。"""
        for old in sectPr.findall(qn("w:vAlign")):
            sectPr.remove(old)
        if val:
            el = OxmlElement("w:vAlign")
            el.set(qn("w:val"), val)
            grid = sectPr.find(qn("w:docGrid"))
            if grid is not None:
                grid.addprevious(el)
            else:
                sectPr.append(el)

    def _sect_valign(sec, val):
        """v2.26.6 节垂直对齐（full 内容上/中/下）：Word 封面页的标准机制。
        val=None 移除（top 是 Word 缺省，add_section 克隆旧 sectPr 须清）。"""
        _sect_valign_el(sec._sectPr, val)

    def _end_section(val):
        """结束当前节并给**这一节**写上/中/下，随后开新节。
        python-docx 的 add_section 返回的是「之后」那一节：旧节的 sectPr
        是克隆体，落在新插进 body 末尾的承载段落里，故对齐要写到那个
        sectPr 上，而不是返回值上（v2.29.1 修正 v2.26.6 的错位）。
        承载段落会把内容顶下半行（它自身占一行），能并进前一段就并掉：
        只有 body 末尾确实是它、且前一个兄弟是段落时才并（前一个是表格
        时不能并，否则表格被划进下一节）。"""
        new_sec = doc.add_section(WD_SECTION_START.NEW_PAGE)
        _sect_valign(new_sec, None)          # 新节是克隆来的，先清回默认
        body = doc.element.body
        ps = body.findall(qn("w:p"))
        if not ps:
            return
        carrier = ps[-1]
        pPr = carrier.find(qn("w:pPr"))
        sectPr = None if pPr is None else pPr.find(qn("w:sectPr"))
        if sectPr is None:
            return
        # 显式 nextPage（缺省也是它，写出来免得 Word 版本差异）
        for old in sectPr.findall(qn("w:type")):
            sectPr.remove(old)
        tp = OxmlElement("w:type")
        tp.set(qn("w:val"), "nextPage")
        pgSz = sectPr.find(qn("w:pgSz"))
        if pgSz is not None:
            pgSz.addprevious(tp)
        else:
            sectPr.insert(0, tp)
        _sect_valign_el(sectPr, val)
        # 并进前一段（分节符仍在该段之后，节边界不变）。注意 body 末尾还有一个
        # 直接子元素 w:sectPr（sentinel，描述最后一节），不能把它当成邻居。
        kids = [k for k in body
                if isinstance(k.tag, str) and k.tag != qn("w:sectPr")]
        if len(kids) >= 2 and kids[-1] is carrier and kids[-2].tag == qn("w:p"):
            prev = kids[-2]
            pPr2 = prev.find(qn("w:pPr"))
            if pPr2 is None:
                pPr2 = OxmlElement("w:pPr")
                prev.insert(0, pPr2)
            if pPr2.find(qn("w:sectPr")) is None:
                pPr2.append(sectPr)
                body.remove(carrier)

    # v2.29.1 full 独占一页（docx 口径：不出背景图——Word 无逐页页面背景，
    # 用「节」实现：NEW_PAGE 分隔 + 节属性 w:vAlign 管上/中/下）：
    #   · 判定不看 class：前端 inlineStylesInto 出件前剥掉全部 class（实测
    #     docx payload 里 "full-page" 出现 0 次），只留 data-*；故按
    #     data-full-pos（t/m/b）认，同时兼容未剥 class 的调用方。
    #   · full 块在预览里被 pblk 壳包着（导出后是 div[data-h]），不在
    #     markdown-body 顶层，且壳里常混排别的块（指南封面 full 与副标题、
    #     版本说明同在一个 pblk，子元素=3）→ _lift 拆壳，兄弟内容 _rebox
    #     包回原壳再入下一节。
    #   · 文首 full 不预加节（会多一张空白首节），由「内容之后」那次
    #     add_section 闭环；文末 full 直接改 body 的 sentinel sectPr。
    def _is_full(el):
        if not isinstance(el.tag, str):
            return False
        if el.get("data-full-pos") in ("t", "m", "b"):
            return True
        return "full-page" in (el.get("class") or "").split()

    def _has_full(el):
        if not isinstance(el.tag, str):
            return False
        if _is_full(el):
            return True
        return any(_has_full(k) for k in _children(el))

    def _rebox(shell, node):
        """把摊平后的兄弟节点包回原壳（保住 pblk 的字体/边距等段落设置）。"""
        if shell is None:
            return node
        box = copy.deepcopy(shell)
        for k in list(box):
            box.remove(k)
        box.text = None
        box.append(node)
        return box

    def _lift(node, shell):
        """把含 full 的容器摊平成顶层序列：full 独立出来，兄弟内容包回壳。
        指南实测（2026-11-03）：封面 full 与它后面的副标题、版本说明同在一个
        pblk 壳里（子元素=3），「唯一子元素」型穿透认不出，必须真正拆壳。"""
        if not isinstance(node.tag, str):
            return [node]
        if _is_full(node):
            return [node]
        kids = _children(node)
        if not any(_has_full(k) for k in kids):
            return [_rebox(shell, node)]
        out = []
        for k in kids:
            if _has_full(k):
                out.extend(_lift(k, None if _is_full(k) else node))
            else:
                out.append(_rebox(node, k))
        return out

    blocks = []
    for child in _children(mb):
        blocks.extend(_lift(child, None))

    val_of = {"t": "top", "m": "center", "b": "bottom"}
    sections = []                      # [(valign, [blocks])]，valign=None 为正文节
    cur = []
    for blk in blocks:
        if _is_full(blk):
            if cur:
                sections.append((None, cur))
            sections.append((val_of.get(blk.get("data-full-pos") or "m", "center"),
                             list(_children(blk))))
            cur = []
        else:
            cur.append(blk)
    if cur or not sections:
        sections.append((None, cur))

    for si, (val, blks) in enumerate(sections):
        saved_ind = ctx["ind"]
        if val is not None:
            ctx["ind"] = 0.0              # full 内容不吃段落缩进
            ctx["para"] = None
        for b in blks:
            _walk(b, doc, md_path, ctx)
        ctx["ind"] = saved_ind
        ctx["para"] = None
        if si < len(sections) - 1:
            _end_section(val)
        elif val is not None:
            _sect_valign(doc.sections[-1], val)   # 文末就是 full：写 body sectPr
    _apply_char_spacing(doc, ts_css, page_cfg)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    # 简易自测
    sample = (
        '<div class="markdown-body">'
        '<h1>标题一</h1>'
        '<p style="text-align:center;color:#c00;font-size:18px">红色居中段落 <strong>加粗</strong> 与 <em>斜体</em>。</p>'
        '<ul><li>项目一</li><li>项目二</li></ul>'
        '<div class="md-math-block" data-tex="E = mc^2"></div>'
        '<p>行内公式 <span class="md-math-inline" data-tex="a^2+b^2=c^2"></span> 结束。</p>'
        '<table><tr><th>列A</th><th>列B</th></tr><tr><td>1</td><td>2</td></tr></table>'
        '</div>'
    )
    data = build_docx(None, sample)
    with open("__test_out.docx", "wb") as f:
        f.write(data)
    print("docx bytes:", len(data))
