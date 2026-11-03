# -*- coding: utf-8 -*-
"""v2.33.0 导出侧验收：HTML 三处统一 + font 块；docx 的字体/字号真的落到 run。"""
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
APP = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def chk(name, cond, note=""):
    print("  %s %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  ← " + str(note)) if (note and not cond) else ""))
    if not cond:
        FAIL.append(name)


def post(path, obj, timeout=120):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))


URL = "https://example.com/" + ("abcdefghij" * 22)
CODE = "x = '" + ("B" * 300) + "'"

body = (
    '<h1>导出验收</h1>'
    '<p style="font-size:14pt">块外正文。</p>'
    '<div class="mde-font" data-ff="1" data-ffw="1" data-fs="1" '
    "style=\"--mff:'Microsoft YaHei Light',sans-serif;--mff-w:290;--mfs:12pt;"
    "font-family:'Microsoft YaHei Light',sans-serif;font-weight:290;font-size:12pt\">"
    # 真实链路里 inlineStylesInto 会把计算样式内联到每个元素（computed 值
    # 带的是双引号，序列化后成 &quot;），所以这里直接写内联值 —— 测的是
    # docx 解析这一段，而非「前端有没有内联」（那条另有断言）
    '<p style="font-family:&quot;Microsoft YaHei Light&quot;,sans-serif;'
    'font-weight:290;font-size:12pt">块内正文 ZheGuang ABCDEFG</p>'
    '</div>'
    '<p style="font-size:14pt">块外正文。</p>'
    '<table><thead><tr><th>链接</th><th>备注</th></tr></thead>'
    '<tbody><tr><td>%s</td><td>说明</td></tr></tbody></table>'
    '<pre><code>%s</code></pre>' % (URL, CODE)
)

ts = "#preview p, .markdown-body p{font-size:14pt !important;}"

# ---------- 1. 导出 HTML ----------
print("[一] 导出 HTML")
out_html = os.path.join(APP, "Temp", "_v233_export.html")
r = post("/api/export-html", {"bodyHtml": body, "tsCss": ts, "path": out_html,
                              "page": {"paper": "A4", "ml": 18, "mr": 18}})
chk("导出成功", r.get("ok"), r)
raw = io.open(out_html, encoding="utf-8").read()
chk("带 .mde-font 规则", ".mde-font[data-ff]" in raw)
chk("th,td 有 anywhere", re.search(r"th,td\{[^}]*overflow-wrap:anywhere;?\}", raw) is not None)
chk("pre 已折行", re.search(r"pre\{[^}]*white-space:pre-wrap", raw) is not None)
chk("pre 不再 overflow:auto", "border-radius:8px;overflow:auto" not in raw)

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1200, "height": 900})
    pg.goto("file:///" + out_html.replace("\\", "/"), wait_until="domcontentloaded")
    pg.wait_for_timeout(600)
    m = pg.evaluate(r"""() => {
      const box = document.querySelector('.mde-font');
      const pIn = box ? box.querySelector('p') : null;
      const outs = [...document.querySelectorAll('p')].filter(e => e.textContent.indexOf('块外正文') >= 0);
      const cs = e => e ? getComputedStyle(e) : null;
      const t = document.querySelector('table');
      const pre = document.querySelector('pre');
      const body = document.body;
      return {
        pIn: pIn ? {ff: cs(pIn).fontFamily, fw: cs(pIn).fontWeight, fs: cs(pIn).fontSize} : null,
        out: outs[0] ? {fs: cs(outs[0]).fontSize} : null,
        tableOver: t ? Math.round(t.getBoundingClientRect().right - body.getBoundingClientRect().right) : null,
        tableW: t ? Math.round(t.getBoundingClientRect().width) : null,
        bodyW: Math.round(body.getBoundingClientRect().width),
        preScroll: pre ? {sw: pre.scrollWidth, cw: pre.clientWidth,
                          ox: cs(pre).overflowX, ws: cs(pre).whiteSpace} : null,
        docScrollW: document.documentElement.scrollWidth,
        winW: window.innerWidth,
      };
    }""")
    b.close()

print("\n[二] 导出 HTML 渲染")
pi = m["pIn"] or {}
chk("块内字体 = Light", "YaHei Light" in (pi.get("ff") or ""), pi.get("ff"))
chk("块内字重 = 290", pi.get("fw") == "290", pi.get("fw"))
chk("块内字号 = 16px（压过 ts 的 14pt）", pi.get("fs") == "16px", pi.get("fs"))
chk("块外仍 14pt/18.666px", (m["out"] or {}).get("fs", "").startswith("18.666"),
    (m["out"] or {}).get("fs"))
chk("表格不超出版心", (m["tableOver"] or 0) <= 1,
    "溢出 %spx，表宽 %s / body %s" % (m["tableOver"], m["tableW"], m["bodyW"]))
chk("代码块折行、不内滚",
    bool(m["preScroll"]) and m["preScroll"]["sw"] <= m["preScroll"]["cw"] + 1
    and m["preScroll"]["ws"] == "pre-wrap",
    json.dumps(m["preScroll"], ensure_ascii=False))
chk("页面无横向滚动", m["docScrollW"] <= m["winW"] + 1,
    "%s > %s" % (m["docScrollW"], m["winW"]))

# ---------- 2. 导出 docx ----------
print("\n[三] 导出 docx")
out_docx = os.path.join(APP, "Temp", "_v233_export.docx")
r2 = post("/api/export-docx", {"bodyHtml": body, "tsCss": ts, "path": out_docx,
                               "page": {"paper": "A4", "ml": 18, "mr": 18}}, timeout=240)
chk("docx 导出成功", r2.get("ok"), r2)
if r2.get("ok"):
    z = zipfile.ZipFile(out_docx)
    xml = z.read("word/document.xml").decode("utf-8")
    z.close()
    # 找包含「块内正文」的那一段
    seg = ""
    for m2 in re.finditer(r"<w:p\b.*?</w:p>", xml, re.S):
        if "块内正文" in m2.group(0):
            seg = m2.group(0)
            break
    chk("找到块内段落", bool(seg))
    if seg:
        chk("run 字体 = Microsoft YaHei Light", "Microsoft YaHei Light" in seg,
            re.findall(r'w:(?:ascii|eastAsia)="([^"]+)"', seg))
        chk("run 字号 = 24 半磅（12pt）", 'w:val="24"' in seg,
            re.findall(r'<w:sz w:val="(\d+)"', seg))
        chk("未被加成粗体", "<w:b/>" not in seg and "<w:b " not in seg)
    seg2 = ""
    for m2 in re.finditer(r"<w:p\b.*?</w:p>", xml, re.S):
        if "块外正文" in m2.group(0):
            seg2 = m2.group(0)
            break
    if seg2:
        chk("块外字号 = 28 半磅（14pt）", 'w:val="28"' in seg2,
            re.findall(r'<w:sz w:val="(\d+)"', seg2))

print("\n" + "=" * 46)
print("FAIL %d 项" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
