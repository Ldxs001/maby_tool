# -*- coding: utf-8 -*-
"""v2.32.0 打印侧验收：长 URL 表格 / 长代码行是否收在版心内。

走真实 /api/export-paged，headless 出 PDF，再用 fitz 量文字 bbox。
A4 + 左右 18mm 边距 → 版心 x 区间 51.02 ~ 544.25 pt（页宽 595.28）。
"""
import json
import os
import subprocess
import urllib.request

import fitz

BASE = "http://127.0.0.1:18766"
APP = os.path.dirname(os.path.abspath(__file__))
URL = "https://example.com/" + ("abcdefghij" * 22)
CODE = "x = '" + ("B" * 300) + "'"

body = (
    '<h1>打印侧验收</h1>'
    '<table><thead><tr><th>链接</th><th>备注</th></tr></thead>'
    '<tbody><tr><td>%s</td><td>说明</td></tr></tbody></table>'
    '<p>正文。</p>'
    '<pre><code>%s</code></pre>'
    '<p>末尾段落。</p>' % (URL, CODE)
)

cfg = {"paper": "A4", "tone": "light", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
       "pn": {"on": "off"}, "toc": {"on": "off"}}

req = urllib.request.Request(
    BASE + "/api/export-paged",
    data=json.dumps({"bodyHtml": body, "tsCss": "", "cfg": cfg}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
print("产物:", r.get("url"), "ok=", r.get("ok"))
if not r.get("ok"):
    raise SystemExit("产物生成失败")

pdf = os.path.join(APP, "Temp", "_v232_print_table.pdf")
if os.path.exists(pdf):
    os.remove(pdf)
edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge):
    edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--print-to-pdf=" + pdf, "--print-to-pdf-no-header",
                BASE + r["url"]], timeout=180, capture_output=True)
print("PDF:", os.path.getsize(pdf), "bytes")

CORE_L, CORE_R = 51.02, 544.25
d = fitz.open(pdf)
print("页数:", d.page_count)
bad = 0
for pno in range(d.page_count):
    for blk in d[pno].get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                t = sp["text"]
                x0, y0, x1, y1 = sp["bbox"]
                tag = None
                if "example.com" in t or t.startswith("abcdefghij"):
                    tag = "URL行"
                elif "BBBB" in t:
                    tag = "CODE行"
                if tag:
                    over = round(x1 - CORE_R, 1)
                    flag = "OK" if x1 <= CORE_R + 1.5 else "溢出"
                    if flag == "溢出":
                        bad += 1
                    print("  p%d %-6s x %.1f..%.1f  %s  %s" %
                          (pno + 1, tag, x0, x1, flag, t[:40]))
d.close()
print("\n溢出 span 数:", bad)
