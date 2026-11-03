# -*- coding: utf-8 -*-
"""v2.33.0 打印侧验收：@@ begin font 在产物里生效，且 PDF 真的用了 Light 面。

两条证据：
  a) 产物在 Chromium 里量 computed（fontFamily/fontWeight/fontSize）
  b) 出 PDF 后读 span 的字体名与字号（fitz 能拿到嵌入字体的名字）
"""
import json
import os
import subprocess
import sys
import urllib.request

import fitz
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
APP = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def chk(name, cond, note=""):
    print("  %s %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  ← " + str(note)) if (note and not cond) else ""))
    if not cond:
        FAIL.append(name)


def ff(fam, w, i, size):
    q = "'" + fam + "',sans-serif"
    s = "font-family:%s;font-weight:%s;font-size:%s" % (q, w, size)
    if i:
        s += ";font-style:italic"
    return 'style="--mff:%s;--mff-w:%s;--mfs:%s;%s"' % (q, w, size, s)


body = (
    '<h1>字体块打印验收</h1>'
    '<p>块外正文，默认字体字号。</p>'
    '<div class="mde-font" data-ff="1" data-ffw="1" data-fs="1" '
    + ff("Microsoft YaHei Light", 290, 0, "12pt") + '>'
    '<h2>块内标题</h2>'
    '<p>块内正文 ZheGuang ABCDEFG</p>'
    '<ul><li>块内列表项</li></ul>'
    '</div>'
    '<p>块外正文，默认字体字号。</p>'
)

# 模拟排版面板：给正文设 14pt、给标题设 22pt，且带 !important
ts = ("#preview p, .markdown-body p{font-size:14pt !important;}"
      "#preview h2, .markdown-body h2{font-size:22pt !important;}"
      "#preview li, .markdown-body li{font-size:14pt !important;}")

cfg = {"paper": "A4", "tone": "light", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
       "pn": {"on": "off"}, "toc": {"on": "off"}}

req = urllib.request.Request(
    BASE + "/api/export-paged",
    data=json.dumps({"bodyHtml": body, "tsCss": ts, "cfg": cfg}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
print("产物:", r.get("url"), "ok=", r.get("ok"))
if not r.get("ok"):
    raise SystemExit("产物生成失败")

prod = BASE + r["url"]

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1200, "height": 900})
    pg.goto(prod, wait_until="networkidle")
    pg.wait_for_timeout(900)
    m = pg.evaluate(r"""() => {
      const box = document.querySelector('.mde-font');
      const pIn = box ? box.querySelector('p') : null;
      const hIn = box ? box.querySelector('h2') : null;
      const lIn = box ? box.querySelector('li') : null;
      const outs = [...document.querySelectorAll('p')].filter(e => e.textContent.indexOf('块外正文') >= 0);
      const cs = e => e ? getComputedStyle(e) : null;
      const pick = e => e ? {ff: cs(e).fontFamily, fw: cs(e).fontWeight, fs: cs(e).fontSize} : null;
      return {box: !!box, pIn: pick(pIn), hIn: pick(hIn), lIn: pick(lIn),
              out: pick(outs[0]),
              cssHasRule: [...document.querySelectorAll('style')].some(s =>
                s.textContent.indexOf('.mde-font[data-ff]') >= 0)};
    }""")
    b.close()

print("\n[一] 产物 CSS 与容器")
chk("产物带 .mde-font 规则", m["cssHasRule"])
chk("产物里有 .mde-font 容器", m["box"])

print("\n[二] 块内压过 ts 的 !important")
pi = m["pIn"] or {}
chk("块内 p 字体 = Light", "YaHei Light" in (pi.get("ff") or ""), pi.get("ff"))
chk("块内 p 字重 = 290", pi.get("fw") == "290", pi.get("fw"))
chk("块内 p 字号 = 16px（12pt，压过 ts 的 14pt）", pi.get("fs") == "16px", pi.get("fs"))
hi = m["hIn"] or {}
chk("块内 h2 字号 = 16px（压过 ts 的 22pt）", hi.get("fs") == "16px", hi.get("fs"))
li = m["lIn"] or {}
chk("块内 li 字号 = 16px", li.get("fs") == "16px", li.get("fs"))

print("\n[三] 块外仍按 ts")
op = m["out"] or {}
chk("块外 p 字号 = 14pt/18.666px", (op.get("fs") or "").startswith("18.666"), op.get("fs"))
chk("块外 p 字体不是 Light", "YaHei Light" not in (op.get("ff") or ""), op.get("ff"))

# --- PDF ---
pdf = os.path.join(APP, "Temp", "_v233_font_print.pdf")
if os.path.exists(pdf):
    os.remove(pdf)
edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge):
    edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--print-to-pdf=" + pdf, "--print-to-pdf-no-header", prod],
               timeout=180, capture_output=True)
print("\n[四] PDF 实据（%d bytes）" % os.path.getsize(pdf))
d = fitz.open(pdf)
spans = []
for pg_ in d:
    for blk in pg_.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                if sp.get("text", "").strip():
                    spans.append(sp)
d.close()
fonts = {}
for sp in spans:
    fonts.setdefault(sp["font"], []).append(round(sp["size"], 2))
for k, v in fonts.items():
    print("  字体 %-34s 字号 %s" % (k, sorted(set(v))))
sizes = set(round(sp["size"], 2) for sp in spans)
chk("PDF 出现 12pt 字号（块内）", any(abs(s - 12.0) < 0.6 for s in sizes), sorted(sizes))
chk("PDF 出现 14pt 字号（块外，ts）", any(abs(s - 14.0) < 0.6 for s in sizes), sorted(sizes))
chk("PDF 出现 Light 面字体名",
    any(("Light" in k) or ("light" in k.lower()) for k in fonts), list(fonts))
chk("PDF 未出现 22pt（块内标题被压）",
    not any(abs(s - 22.0) < 0.6 for s in sizes), sorted(sizes))

print("\n" + "=" * 46)
print("FAIL %d 项" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
