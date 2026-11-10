# -*- coding: utf-8 -*-
"""v2.41.0 docx：前置上下标（空 base 角标）→ OMML m:sPre 正规写法（方案 §7.9）。

latex2mathml 对 {}^{3}_{4}X 产出的是【兄弟结构】：
  <msubsup><mrow/><sub/><sup/></msubsup><mi>X</mi>
中心 X 是兄弟节点。正规映射 = 把兄弟吞进 m:sPre 的 m:e（子元素序 e、sub、sup）。

用例：
  S1 {}^{3}_{4}X → sPre(e=X, sub=4, sup=3)
  S2 {}^{3}X    → sPre(e=X, sub=空, sup=3)
  S3 {}_{i}X    → sPre(e=X, sub=i, sup=空)
  S4 \frac{{}^{a}_{b}X}{c} 嵌套（mrow 分支内的兄弟合并）
  S5 普通公式不误伤：x^2 → 仍是 sSup，不出 sPre
  S6 最小 docx 全链导出 + zip 重开（防"文件损坏"，v2.4.9 老坑口径）

跑法：python _test_v2410_spre.py   （本目录 = 仓库根；依赖 docxdeps 内置依赖）
"""
import io
import os
import sys
import zipfile

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "docxdeps"))
import docx_export as D  # noqa: E402

try:
    import latex2mathml.converter as l2m  # noqa: E402
except ImportError:
    print("FAIL  latex2mathml 不可用（docxdeps 内置依赖未就绪）")
    sys.exit(1)

PASS = FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (name, extra))


def qn(el):
    from lxml import etree
    return etree.QName(el).localname


def kids(el):
    return [c for c in el if isinstance(c.tag, str)]


def omml_of(tex):
    return D.mathml_to_omml(l2m.convert(tex))


def find_spre(om):
    for el in om.iter():
        try:
            if qn(el) == "sPre":
                return el
        except Exception:
            pass
    return None


def part_texts(el):
    return ["".join(k.itertext()) for k in kids(el)]


# ---- S1 {}^{3}_{4}X ----
om = omml_of("{}^{3}_{4}X")
sp = find_spre(om)
ok = False
detail = "无 sPre"
if sp is not None:
    names = [qn(k) for k in kids(sp)]
    txt = part_texts(sp)
    ok = (names == ["e", "sub", "sup"]
          and "X" in txt[0] and "4" in txt[1] and "3" in txt[2])
    detail = "names=%s txt=%s" % (names, txt)
ck("S1 {}^{3}_{4}X → sPre(e=X, sub=4, sup=3)", ok, detail)

# ---- S2 {}^{3}X ----
om = omml_of("{}^{3}X")
sp = find_spre(om)
ok = False
detail = "无 sPre"
if sp is not None:
    names = [qn(k) for k in kids(sp)]
    txt = part_texts(sp)
    ok = names == ["e", "sub", "sup"] and "X" in txt[0] and "3" in txt[2]
    detail = "names=%s txt=%s" % (names, txt)
ck("S2 {}^{3}X → sPre(e=X, sub=空, sup=3)", ok, detail)

# ---- S3 {}_{i}X ----
om = omml_of("{}_{i}X")
sp = find_spre(om)
ok = False
detail = "无 sPre"
if sp is not None:
    names = [qn(k) for k in kids(sp)]
    txt = part_texts(sp)
    ok = names == ["e", "sub", "sup"] and "X" in txt[0] and "i" in txt[1]
    detail = "names=%s txt=%s" % (names, txt)
ck("S3 {}_{i}X → sPre(e=X, sub=i, sup=空)", ok, detail)

# ---- S4 嵌套：分数里的四角标 ----
om = omml_of("\\frac{{}^{a}_{b}X}{c}")
sp = find_spre(om)
ok = sp is not None
detail = "无 sPre"
if ok:
    txt = part_texts(sp)
    ok = "X" in txt[0] and "b" in txt[1] and "a" in txt[2]
    detail = "txt=%s" % txt
ck("S4 \\frac{{}^{a}_{b}X}{c} → 分母内 sPre", ok, detail)

# ---- S5 普通公式不误伤 ----
om = omml_of("x^2")
sp = find_spre(om)
sup_cnt = 0
for el in om.iter():
    try:
        if qn(el) == "sSup":
            sup_cnt += 1
    except Exception:
        pass
ck("S5 x^2 仍是 sSup（不出 sPre）",
   sp is None and sup_cnt == 1, "sPre=%s sSup=%d" % (sp is not None, sup_cnt))

# ---- S6 全链导出 + zip 重开 ----
body = ('<div class="markdown-body">'
        "<p>前置角标 <span class=\"md-math-inline\" data-tex=\"{}^{3}_{4}X\"></span> "
        "与 <span class=\"md-math-inline\" data-tex=\"\\frac{{}^{a}_{b}X}{c}\"></span>。</p>"
        "</div>")
try:
    blob = D.build_docx(None, body, "", {"paper": "A4"})
    z = zipfile.ZipFile(io.BytesIO(blob))
    xml = z.read("word/document.xml").decode("utf-8")
    ok = blob and len(blob) > 4000 and "sPre" in xml \
        and z.testzip() is None
    ck("S6 最小 docx 导出 + zip/XML 完整（含 sPre）", ok,
       "bytes=%d sPre=%s" % (len(blob or b""), "sPre" in xml))
except Exception as e:
    ck("S6 最小 docx 导出 + zip/XML 完整（含 sPre）", False, repr(e))

print("\n====================================================")
print("PASS %d / FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
