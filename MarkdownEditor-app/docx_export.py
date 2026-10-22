# -*- coding: utf-8 -*-
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

import io
import os
import re
import urllib.parse

from lxml import etree, html as lxml_html
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
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
    for c in _children(root):
        omml.append(_tr(c))
    return omml


def _tr(el):
    """把一个 MathML 元素递归转成 OMML 元素。"""
    tag = etree.QName(el).localname
    kids = _children(el)
    txt = el.text or ""

    # 叶子：标识符 / 数字 / 算子 / 文本
    if tag in ("mi", "mn", "mo", "mtext", "ms", "annotation"):
        return _text_run(txt)
    if tag == "mspace":
        return _text_run(" ")
    if tag == "mstyle" or tag == "mpadded" or tag == "mphantom":
        # 透明/带间距容器：直接透传子节点
        d = _mk("d", _mk("dPr"), _mk("e", *[_tr(k) for k in kids]))
        return d
    if tag == "mrow":
        return _mk("d", _mk("dPr"), _mk("e", *[_tr(k) for k in kids]))

    # 分式
    if tag == "mfrac" and len(kids) >= 2:
        return _mk("f", _mk("num", _tr(kids[0])), _mk("den", _tr(kids[1])))

    # 上下标
    if tag == "msub" and len(kids) >= 2:
        return _mk("sSub", _mk("e", _tr(kids[0])), _mk("sub", _tr(kids[1])))
    if tag == "msup" and len(kids) >= 2:
        return _mk("sSup", _mk("e", _tr(kids[0])), _mk("sup", _tr(kids[1])))
    if tag == "msubsup" and len(kids) >= 3:
        return _mk("sSubSup", _mk("e", _tr(kids[0])),
                   _mk("sub", _tr(kids[1])), _mk("sup", _tr(kids[2])))

    # 根式
    if tag == "msqrt" and kids:
        return _mk("rad",
                   _mk("radPr", _mk("degHide", **{"val": "on"})),
                   _mk("e", _tr(kids[0])))
    if tag == "mroot" and len(kids) >= 2:
        return _mk("rad",
                   _mk("radPr", _mk("deg", _tr(kids[1]))),
                   _mk("e", _tr(kids[0])))

    # 上下附加符号（acc 仅向上，munder 降级同样处理）
    if tag in ("mover", "munder") and len(kids) >= 2:
        acc = (kids[1].text or "").strip()
        return _mk("acc",
                   _mk("accPr", _mk("chr", **{"val": acc})),
                   _mk("e", _tr(kids[0])),
                   _mk("sub", _text_run(acc)))

    # 求和 / 积分 / 连乘 等大运算符（munderover -> nary）
    if tag == "munderover" and len(kids) >= 3:
        op = (kids[0].text or "").strip()
        return _mk("nary",
                   _mk("naryPr", _mk("chr", **{"val": op}),
                       _mk("limLoc", **{"val": "subSup"})),
                   _mk("sub", _tr(kids[1])),
                   _mk("sup", _tr(kids[2])),
                   _mk("e", _tr(kids[0])))

    # 矩阵 / 行列式
    if tag == "mtable":
        m = _mk("m", _mk("mPr", _mk("baseJc", **{"val": "center"})))
        for row in kids:
            if etree.QName(row).localname == "mtr":
                mr = _mk("mr")
                for cell in _children(row):
                    if etree.QName(cell).localname == "mtd":
                        mr.append(_mk("e", *[_tr(c) for c in _children(cell)]))
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
    m = re.match(r"#([0-9a-fA-F]{6})", rgb or "")
    if m:
        h = m.group(1)
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
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


def _prep_list_abstract(doc):
    """清理列表编号定义的悬挂底座，落成 inside 语义（与预览
    list-style-position:inside 同构）：

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
    hollow 克隆发生在 prep 之后，自动继承干净定义。"""
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
            if lvl.find(qn("w:suff")) is None:
                suff = OxmlElement("w:suff")
                suff.set(qn("w:val"), "space")
                lt = lvl.find(qn("w:lvlText"))
                if lt is not None:
                    lt.addprevious(suff)
                else:
                    lvl.append(suff)


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
    m = re.match(r"/img\?path=(.+)$", src)
    if m:
        p = urllib.parse.unquote(m.group(1)).replace("\\", os.sep)
        return p
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
def _apply_run_style(run, style_node):
    sd = _style_dict(style_node.get("style", ""))
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
    ff = sd.get("font-family", "")
    if ff:
        # 取第一个字体族，去掉引号
        fam = re.split(r"[,;]", ff)[0].strip().strip('"').strip("'")
        if fam:
            run.font.name = fam


# 块级子元素：_fill_inline 不拉平（由 _walk 结构分支处理）。
# 历史缺陷：li 内嵌套 ul/ol 时，_fill_inline(li) 把嵌套列表的全部
# 文本拉平进父段落，随后 _walk 又完整处理嵌套列表——嵌套内容双份
# （实测"单行回车不断序单行回车不断序"父段拼接 + 子段重复输出）。
_SKIP_INLINE_TAGS = {"ul", "ol", "table", "blockquote", "pre", "div"}


def _fill_inline(node, para, doc, md_path):
    if node.text:
        _add_run(para, node.text, node)
    for child in _children(node):
        ctag = etree.QName(child).localname
        if ctag in _SKIP_INLINE_TAGS:
            continue
        if ctag == "br":
            para.add_run().add_break()
        elif ctag == "img":
            _add_image(para, child, md_path, doc)
        elif ctag == "svg":
            para.add_run("[图表]")
        elif child.get("data-tex") is not None:
            _append_omml(para, child.get("data-tex"))
        else:
            _fill_inline(child, para, doc, md_path)
        if child.tail:
            _add_run(para, child.tail, child)


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


def _img_width_in(doc, img, natural_px):
    """图片显示宽（英寸），与前端 {N} 宽度规则同口径：
    ① data-x-pct（{N} 参数）→ 版心 × N%（钳 100），等比靠只传 width；
    ② data-x-w（前端栅格化图的 1x 显示宽）→ px/96dpi；
    ③ 自然尺寸（普通图片：小图原始、大图钳版心）。
    全部以版心为上限（"最大是版面宽度100%"）。"""
    usable = _content_width_in(doc)
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


def _add_image(para, img, md_path, doc=None):
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
            w_in = _img_width_in(doc, img, natural_px) if doc else None
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
        w_in = _img_width_in(doc, img, natural_px) if doc else None
        if w_in:
            para.add_run().add_picture(path, width=Inches(w_in))
        else:
            para.add_run().add_picture(path)
    except Exception:
        para.add_run("[图片:%s]" % os.path.basename(path))


def _append_omml(para, tex):
    try:
        mathml = latex2mathml.converter.convert(tex)
        omml = mathml_to_omml(mathml)
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

    # 公式
    if tex is not None:
        if "md-math-block" in cls.split():
            p = doc.add_paragraph()
            _append_omml(p, tex)
        else:
            p = ctx.get("para") or doc.add_paragraph()
            _append_omml(p, tex)
        return

    # 标题
    if re.match(r"h[1-6]$", tag):
        level = int(tag[1])
        p = doc.add_heading(level=level)
        _fill_inline(node, p, doc, md_path)
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
                _fill_inline(ch, p, doc, md_path)
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
        ol_num = None
        if tag == "ol":
            ol_num = _new_ol_num(doc, node.get("start") or 1)
        hollow_num = None   # 按需懒建：遇 data-li-marker=hollow 才取
        for li in _children(node):
            if etree.QName(li).localname == "li":
                p = doc.add_paragraph(
                    style="List Bullet" if tag == "ul" else "List Number")
                if ol_num is not None:
                    _bind_num(p, ol_num)
                elif tag == "ul" and li.get("data-li-marker") == "hollow":
                    if hollow_num is None:
                        hollow_num = _bullet_num(doc, True, ctx)
                    if hollow_num is not None:
                        _bind_num(p, hollow_num)
                p.paragraph_format.left_indent = Pt(base)
                # 压掉编号级悬挂：ListNumber/ListBullet 的 abstractNum lvl0
                # 自带 <w:ind left="360" hanging="360"/>，段落只写 left 时
                # hanging 继承 → Word 把编号悬挂在 left-360 处（比块内
                # 正文浅一层半，"列表没继承缩进"）。显式 firstLine=0 让
                # 编号与文本都从容器左缘起（inside 语义，与预览同几何）
                p.paragraph_format.first_line_indent = Pt(0)
                _fill_inline(li, p, doc, md_path)
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
        _add_image(p, node, md_path, doc)
        ctx["para"] = None
        return

    # fill 分栏布局（data-fill-row 桥接自前端 .fill-row）：无边框表格
    # 当布局骨架（Word 原生多图并排做法），列宽 = 版心 × 比例；
    # 栏内容递归 _walk（图片/图表段在单元格内）；<<继承链的块级缩进
    # 由表格 left_indent 承载
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
            cell_ctx = {"para": None, "ind": 0.0}
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
        _fill_inline(node, p, doc, md_path)
        ctx["para"] = None
        return

    # 其它：当作内联内容挂到当前段落（或新建）
    p = ctx.get("para") or doc.add_paragraph()
    _fill_inline(node, p, doc, md_path)
    ctx["para"] = p


def _add_table(doc, table, md_path):
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
            text = cell.text_content()
            dt.cell(i, j).text = text
    # 表头加粗首行
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


def build_docx(md_path, body_html, ts_css=None, page_cfg=None):
    """body_html: 已内联样式的 HTML 片段（含 .markdown-body 根）。
    page_cfg: 排版面板 page 节（纸张/页边距），None 用 A4 默认。
    返回 .docx 字节。"""
    doc = Document()
    _apply_page_section(doc, page_cfg)
    _prep_list_abstract(doc)
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
    ctx = {"para": None, "ind": 0.0}
    for child in _children(mb):
        _walk(child, doc, md_path, ctx)
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
