# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""E2E: /api/export-paged v40 - base css / table split / img fit / ref-table"""
import io, json, urllib.request

BASE = "http://127.0.0.1:18766"
FAILS = []

def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL") + " | " + name + ((" | " + detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

body_a4 = (
    "<h1>打印测试</h1>"
    "<p>正文段落</p>"
    "<table><thead><tr><th>列1</th><th>列2</th></tr></thead>"
    "<tbody><tr><td>a</td><td>b</td></tr></tbody></table>"
    "<table><thead><tr><th>编号</th><th>引用</th><th>出处</th></tr></thead>"
    "<tbody><tr><td>[1]</td><td>x. t (2026)</td><td>KB demo</td></tr></tbody></table>"
    "<pre><code>long code line</code></pre>"
    "<img src=\"/img?path=C:/nonexistent/tall.png\" alt=\"tall\">"
)

# --- Case 1: A4 default ---
j = post("/api/export-paged", {"path": None, "bodyHtml": body_a4, "tsCss": "",
                               "cfg": {"paper": "A4", "mt": 25, "mb": 25}})
check("E1 api ok", j.get("ok") is True, str(j))
with urllib.request.urlopen(BASE + "/static/document.paged.html", timeout=10) as r:
    html = r.read().decode("utf-8")

check("E2 table border css", ".markdown-body th,.markdown-body td{border:1px solid #bbb" in html)
check("E3 th bg css", ".markdown-body th{background:#f0f2f6" in html)
check("E4 thead repeat", ".markdown-body thead{display:table-header-group;}" in html)
check("E5 tr no-split", ".markdown-body tr{break-inside:avoid;}" in html)
check("E6 table allow-split", ".markdown-body table{border-collapse:collapse;margin:1em 0;width:100%;table-layout:auto;font-size:.93em;break-inside:auto;}" in html)
check("E7 cell keep-all+anywhere", "word-break:keep-all;overflow-wrap:anywhere;}" in html)
check("E8 pre pre-wrap", "white-space:pre-wrap !important" in html)
check("E9 border-box", "*{box-sizing:border-box;}" in html)
check("E10 img max-height A4=245", "max-height:245.00mm" in html)
check("E11 ref-table class", '<table class="ref-table">' in html)
check("E12 ref-table col widths", "table.ref-table th:nth-child(2),.markdown-body table.ref-table td:nth-child(2){width:47%;}" in html)
check("E13 normal table untouched", '<table class="ref-table"><thead><tr><th>列1</th>' not in html)
check("E14 order: base before ts override zone", html.find("box-sizing:border-box") < html.find("md-editor-typeset") if "md-editor-typeset" in html else True)

# --- Case 2: custom paper 210x140, margins 20 -> img max-height = 99 ---
j2 = post("/api/export-paged", {"path": None, "bodyHtml": body_a4, "tsCss": "",
                                "cfg": {"paper": "custom", "pw": "210", "ph": "140", "mt": 20, "mb": 20}})
check("E15 api ok custom", j2.get("ok") is True, str(j2))
with urllib.request.urlopen(BASE + "/static/document.paged.html?t=2", timeout=10) as r:
    html2 = r.read().decode("utf-8")
check("E16 img max-height custom=98", "max-height:98.00mm" in html2)

# --- Case 3: three-line table ts_css override still wins (important later in doc) ---
ts = ".markdown-body table{border:none !important;border-top:2px solid currentColor !important;}"
j3 = post("/api/export-paged", {"path": None, "bodyHtml": body_a4, "tsCss": ts,
                                "cfg": {"paper": "A4"}})
check("E17 api ok ts", j3.get("ok") is True)
with urllib.request.urlopen(BASE + "/static/document.paged.html?t=3", timeout=10) as r:
    html3 = r.read().decode("utf-8")
check("E18 ts after base", html3.find("border:none !important") > html3.find("1px solid #bbb"))
check("E19 base still present with ts", "border:1px solid #bbb" in html3)

# --- Case 4: Legal paper map ---
j4 = post("/api/export-paged", {"path": None, "bodyHtml": body_a4, "tsCss": "",
                                "cfg": {"paper": "Legal"}})
with urllib.request.urlopen(BASE + "/static/document.paged.html?t=4", timeout=10) as r:
    html4 = r.read().decode("utf-8")
check("E20 img max-height Legal=303.60", "max-height:303.60mm" in html4)  # 355.6-25-25-2

# --- Case 5: TOC page numbering (v41) ---
j5 = post("/api/export-paged", {"path": None, "bodyHtml": body_a4, "tsCss": "",
                                "cfg": {"paper": "A4", "toc": {"on": "on", "pos": "top", "solo": True},
                                        "pn": {"on": "on", "pos": "bc"}}})
check("E21 api ok toc", j5.get("ok") is True, str(j5))
with urllib.request.urlopen(BASE + "/static/document.paged.html?t=5", timeout=10) as r:
    html5 = r.read().decode("utf-8")
check("E22 toc rule no target-counter", ".md-toc a::after{content:'  ' target-counter" not in html5)
check("E23 filler toc-only logic", "tocOnly" in html5 and "md-toc-pg" in html5)
check("E24 filler skip+shown mapping", "shown[i] = skip[i] ? 0 : ++c" in html5)

# --- Case 6: book-standard pagination + outer page numbers (v42) ---
j6 = post("/api/export-paged", {"path": None, "bodyHtml": body_a4, "tsCss": "",
                                "cfg": {"paper": "A4", "toc": {"on": "on", "pos": "top", "solo": True},
                                        "pn": {"on": "on", "pos": "outer", "tpl": "{p}", "size": 9}}})
check("E25 api ok v42", j6.get("ok") is True, str(j6))
with urllib.request.urlopen(BASE + "/static/document.paged.html?t=6", timeout=10) as r:
    html6 = r.read().decode("utf-8")
check("E26 h1 break-before", "h1{break-before:page;}" in html6)
check("E27 h2-h4 avoid", "h2,h3,h4{break-after:avoid;}" in html6)
check("E28 p orphans/widows", "p{orphans:2;widows:2;}" in html6)
check("E29 li orphans 1/1", "li{orphans:1;widows:1;}" in html6)
check("E30 hr rule", "hr{break-inside:avoid;break-after:avoid;}" in html6)
check("E31 pre no force-avoid", "white-space:pre-wrap !important;overflow-wrap:anywhere !important;break-inside:avoid" not in html6)
check("E32 img block centered", ".markdown-body img{display:block;margin:0 auto;max-width:100%;max-height:" in html6)
check("E33 toc dots css", ".md-toc .toc-dots{flex:1;" in html6)
check("E34 toc flex baseline", ".md-toc a{display:flex;align-items:baseline;" in html6)
check("E35 outer both boxes", '@bottom-right{content:" ";font-size:9pt;}@bottom-left{content:" ";font-size:9pt;}' in html6)
check("E36 filler parity sel", "(shown[i] % 2 === 1) ? sel.odd : sel.even" in html6)
check("E37 filler dots span", "dots.className = 'toc-dots'" in html6)
check("E38 filler gray", "'#666'" in html6)

# --- Case 7: v43 图片版面预算修正 + 超高长图切片 ---
import os as _os
import urllib.parse as _up
from PIL import Image as _Image

# 7a: A4 预算 297-25-25-2 = 245mm；p:has(>img) margin 0
check("E39 img maxh 245.00", "max-height:245.00mm" in html6)
check("E40 p:has(>img) margin0", ".markdown-body p:has(>img){margin:0;text-indent:0 !important;}" in html6)

# 7b: 造一张带空白行的长截图（1000x4000，黑条模拟文字行）
_td = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_tmp_slice_fixture")
_os.makedirs(_td, exist_ok=True)
_tall_png = _os.path.join(_td, "tall.png")
_small_png = _os.path.join(_td, "small.png")
_im = _Image.new("RGB", (1000, 4000), "white")
_px = _im.load()
for band in range(0, 4000, 120):  # 每 120px：60px 黑条 + 60px 空白
    for y in range(band, min(band + 60, 4000)):
        for x in range(100, 900):
            _px[x, y] = (20, 20, 20)
_im.save(_tall_png)
_Image.new("RGB", (800, 400), "white").save(_small_png)

body_slice = (
    '<h1>切片测试</h1><p>前置段落</p>'
    '<p><img src="/img?path=' + _up.quote(_tall_png.replace("\\\\", "/")) + '" alt="long"></p>'
    '<p><img src="/img?path=' + _up.quote(_small_png.replace("\\\\", "/")) + '" alt="small"></p>'
)
j7 = post("/api/export-paged", {"path": None, "bodyHtml": body_slice, "tsCss": "",
                                "cfg": {"paper": "A4", "mt": 25, "mb": 25}})
check("E41 api ok v43", j7.get("ok") is True, str(j7))
with urllib.request.urlopen(BASE + "/static/document.paged.html?t=7", timeout=10) as r:
    html7 = r.read().decode("utf-8")

check("E42 tall sliced to /static/_slice/", '/static/_slice/' in html7)
import re as _re
_strips = _re.findall(r'src="(/static/_slice/([0-9a-f]{12}-\d+)/strip-(\d+)\.png)"', html7)
check("E43 strip count 2..20", 2 <= len(_strips) <= 20, "n=%d" % len(_strips))
_check_ok = bool(_strips)
for _u, _dg, _n in _strips:
    if not _os.path.isfile(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                         "_slice", _dg, "strip-%02d.png" % int(_n))):
        _check_ok = False
check("E44 strip files on disk", _check_ok)
check("E45 small img unsliced", "/img?path=" in html7 and 'alt="small"' in html7)
check("E46 tall original gone", 'src="/img?path=' + _up.quote(_tall_png.replace("\\\\", "/")) + '"' not in html7)
# 幂等：重复导出切片文件数不变（复用不重切）
_n_before = len({(d, n) for _, d, n in _strips})
post("/api/export-paged", {"path": None, "bodyHtml": body_slice, "tsCss": "",
                           "cfg": {"paper": "A4", "mt": 25, "mb": 25}})
_n_after = len({(d, n) for _, d, n in
                _re.findall(r'src="(/static/_slice/([0-9a-f]{12}-\d+)/strip-(\d+)\.png)"',
                            urllib.request.urlopen(BASE + "/static/document.paged.html?t=8",
                                                   timeout=10).read().decode("utf-8"))})
check("E47 idempotent re-export", _n_before == _n_after, "%d vs %d" % (_n_before, _n_after))

# --- Case 8: v2.10 图题/表题 CSS 进打印模板（缺陷回归：此前模板一条
#     .mde-fig 规则都没有，题注 t 写了却恒显示在图下方、{N}/s/w 全丢） ---
check("E48 figcap side t flex", 'figure.mde-fig[data-fig-side="t"]{display:flex;flex-direction:column-reverse;align-items:flex-start;}' in html6)
check("E49 figcap width var(--figw)", "figure.mde-fig{margin:.9em 0;max-width:100%;width:var(--figw,auto);break-inside:avoid;}" in html6)
check("E50 figcap gap calc", 'figure.mde-fig[data-fig-side="b"]>figcaption{margin-top:calc(1em * var(--figgap,.3));}' in html6)
check("E51 figcap w-mode ellipsis", 'figure.mde-fig[data-fig-mode="w"]>figcaption{white-space:nowrap;text-overflow:ellipsis;}' in html6)
check("E52 tabwrap side margins", '.mde-tblwrap[data-tab-side="t"]>.mde-tabcap{margin-bottom:calc(1em * var(--tabgap,.3));}' in html6)
check("E53 fill img col-100", ".markdown-body .fill-col img{width:100% !important;height:auto;}" in html6)
check("E54 fill table img restore", ".markdown-body .fill-col table img{width:auto !important;max-width:100% !important;height:auto;}" in html6)
check("E55 fill fig auto", ".markdown-body .fill-col figure.mde-fig{width:auto !important;margin:0;}" in html6)
check("E56 old fill auto gone", ".markdown-body .fill-col img{width:auto !important" not in html6)

# --- Case 9: 导出 HTML 模板同口径（build_standalone_html） ---
_out_html = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_tmp_cap_export.html")
_fig_body = ('<figure class="mde-fig" data-fig-side="t" data-fig-gap="0.5" '
             'data-fig-w="40" data-fig-mode="" style="--figw:40%;--figgap:0.5;">'
             '<img src="data:image/png;base64,iVBORw0KGgo=" alt="x">'
             '<figcaption class="mde-figcap" style="text-align:center !important">题注</figcaption></figure>')
j8 = post("/api/export-html", {"path": _out_html, "bodyHtml": _fig_body, "tsCss": ""})
check("E57 export-html api ok", j8.get("ok") is True, str(j8))
with io.open(_out_html, encoding="utf-8") as f:
    html8 = f.read()
check("E58 export-html side t flex", 'figure.mde-fig[data-fig-side="t"]{display:flex;flex-direction:column-reverse;align-items:flex-start;}' in html8)
check("E59 export-html width var(--figw)", "width:var(--figw,auto);" in html8)
check("E60 export-html gap calc", "var(--figgap,.3)" in html8)
check("E61 export-html tabwrap css", ".markdown-body .mde-tblwrap{margin:.9em 0;}" in html8)
check("E62 export-html fill col-100", ".fill-col img{width:100% !important;height:auto;}" in html8)
check("E63 export-html figure markup passthrough", 'data-fig-side="t"' in html8 and "--figw:40%" in html8)
check("E64 export-html old fill auto gone", ".fill-col img{width:auto !important" not in html8)
if _os.path.exists(_out_html):
    _os.remove(_out_html)

print("---")
print("TOTAL: %d, FAIL: %d" % (64, len(FAILS)))
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
    raise SystemExit(1)
print("ALL PASS")
