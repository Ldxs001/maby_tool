# -*- coding: utf-8 -*-
"""真实 HTTP 链路端到端：POST /api/export-paged(mode=native) -> /static/... -> 打印 PDF

不直接调 build_paged_html，走前端实际用的那条路，连 cfg 的键名一起验。
"""
import io
import json
import os
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:18766"
HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PARA = "<p>%s</p>" % ("正文填充文字，用来把版面撑开。" * 16)
MK = '<span class="mkm">M%04d</span>'
MARK_CSS = ".mkm{font-size:1px;color:transparent;line-height:0;}"


def body():
    n = [0]

    def H(l, t):
        n[0] += 1
        return "<h%d>%s%s</h%d>" % (l, MK % n[0], t, l)

    return ('<div class="page-region" data-pn="noll" data-pr-id="r0">'
            + H(1, "封面") + "<p>副标题</p></div>"
            + H(1, "第一章 起") + PARA * 2
            + H(2, "第一节 甲") + PARA * 3
            + H(1, "第二章 承") + PARA * 2
            + '<div class="page-region" data-pn="1" data-pr-id="r1">'
            + H(2, "附录 甲") + PARA * 2 + "</div>"
            + H(1, "第三章 转") + PARA)


def post(payload):
    req = urllib.request.Request(
        BASE + "/api/export-paged",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    # 前端存的就是这个形状：localStorage['md-editor-typeset-v3'].page
    cfg = {"paper": "A4", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
           "tone": "light", "lang": "zh",
           "pn": {"on": "on", "pos": "outer", "size": 9,
                  "tpl": "p{p}/P{P}/N{N}"},
           "toc": {"on": "on", "solo": True, "pos": "top"}}
    j = post({"bodyHtml": body(), "tsCss": MARK_CSS, "cfg": cfg,
              "mode": "native"})
    print("响应：", j)
    assert j.get("ok"), j
    url = BASE + j["url"]

    from playwright.sync_api import sync_playwright
    pdf = os.path.join(HERE, "_e2e_http.pdf")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EDGE)
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url, wait_until="load")
        pg.wait_for_function("() => window.__pnReady === 1", timeout=20000)
        toc = pg.evaluate(
            "() => Array.from(document.querySelectorAll('.md-toc a'))"
            ".map(a=>(a.textContent||'').replace(/\\s+/g,'').trim())")
        has_dots = pg.evaluate(
            "() => document.querySelectorAll('.md-toc .toc-dots').length")
        pg.pdf(path=pdf, prefer_css_page_size=True, print_background=True)
        b.close()
    print("页面错误：", errs)
    print("目录条目：", toc)
    print("点线节点数：", has_dots)

    import pypdf
    rd = pypdf.PdfReader(pdf)
    print("物理页数：", len(rd.pages))
    for i, pgx in enumerate(rd.pages):
        t = " ".join((pgx.extract_text() or "").split())
        print("  P%d  %s" % (i + 1, t[:64]))


if __name__ == "__main__":
    main()
