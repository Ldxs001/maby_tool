# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""排版纸张/页边距四链路口径测试（playwright + 便携 python 服务）：
1. 预览栏宽度 = 纸宽−左右边距（A4 默认 174mm；改 A3 → 261mm 实时生效，
   超窗出横滚条）
2. 分屏联动在固定版心宽下依然锚对齐（编辑器滚到锚 → 预览锚可见）
3. docx section：纸张/四边距按配置（A3 → 297mm 宽、25/18/25/18 边距）；
   {40} 图片 = A3 版心 261mm × 0.4
4. 导出 HTML body 版心 = 261mm（与预览同口径）
跑前杀遗留 md_server（18766 被旧进程占用会打旧代码）。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18766
NO_WINDOW = 0x08000000

fails = []


def check(name, cond, detail=""):
    print("%-56s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def kill_stale():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "$_.CommandLine -like '*md_server.py*' -or $_.CommandLine -like '*_md_run.py*') -and $_.Name -like "
         "'*python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId "
         "-Force }"],
        capture_output=True)


def alive():
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=0.3).read()
        return True
    except Exception:
        return False


kill_stale()
time.sleep(0.3)
srv = subprocess.Popen(
    [os.path.join(HERE, "python", "python.exe"), "md_server.py"],
    cwd=HERE, creationflags=NO_WINDOW)
t0 = time.time()
while not alive() and time.time() - t0 < 20:
    time.sleep(0.1)
assert alive(), "服务未就绪"

tmpdir = tempfile.mkdtemp(prefix="md_paper_")
docx_path = os.path.join(tmpdir, "paper.docx")
html_path = os.path.join(tmpdir, "paper.html")

DOC = ("# 纸张口径测试\n\n" + "".join(
    "段落 %d 内容。\n\n" % i for i in range(1, 25))
    + "![宽图](%s){40}\n\n" % "__IMGSRC__"
    + "# 末章\n\n结尾。\n")

from PIL import Image
img_file = os.path.join(tmpdir, "宽图.png")
Image.new("RGB", (700, 300), (90, 130, 210)).save(img_file)
DOC = DOC.replace("__IMGSRC__", img_file.replace("\\", "/"))


def set_paper(pg, paper, mt=25, mr=18, mb=25, ml=18):
    """打开排版面板 → 显式设纸张/四边距（服务端 ui-state 会恢复本机真实
    配置如 mt=30，不显式设则断言口径漂移）→ 应用"""
    pg.evaluate("""(c)=>{
      document.getElementById('btnTypeset').click();
      document.getElementById('tsPaper').value=c.paper;
      document.getElementById('tsCustomRow').hidden=(c.paper!=='custom');
      document.getElementById('tsMt').value=c.mt;
      document.getElementById('tsMr').value=c.mr;
      document.getElementById('tsMb').value=c.mb;
      document.getElementById('tsMl').value=c.ml;
      document.getElementById('tsApply').click();
    }""", {"paper": paper, "mt": mt, "mr": mr, "mb": mb, "ml": ml})
    pg.wait_for_timeout(1000)


try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(800)
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_timeout(1200)

        MM = 96.0 / 25.4   # 1mm = 3.7795px

        # --- 1. 显式 A4：预览版心 174mm ---
        set_paper(pg, "A4")
        w1 = pg.evaluate(
            "()=>Math.round(document.getElementById('preview')"
            ".getBoundingClientRect().width)")
        check("预览 A4 版心 174mm（±3px）",
              abs(w1 - 174 * MM) <= 3, "got=%dpx want=%.0fpx" % (w1, 174 * MM))

        # --- 2. 改 A3（297×420）：版心 297-36=261mm，超窗出横滚条 ---
        set_paper(pg, "A3")
        w2 = pg.evaluate(
            "()=>Math.round(document.getElementById('preview')"
            ".getBoundingClientRect().width)")
        check("改 A3 后预览版心 261mm（±3px）",
              abs(w2 - 261 * MM) <= 3, "got=%dpx want=%.0fpx" % (w2, 261 * MM))
        pane_w = pg.evaluate(
            "()=>document.getElementById('previewPane').clientWidth")
        hscroll = pg.evaluate(
            "()=>document.getElementById('previewPane')"
            ".scrollWidth>document.getElementById('previewPane').clientWidth")
        check("A3 版心超窗 → pane 出横向滚动", hscroll,
              "pane=%dpx content=%dpx" % (pane_w, w2))

        # --- 3. 联动：固定版心宽下锚对齐 ---
        # 滚编辑器到"末章"行附近，断言预览"末章"锚进入视口
        pg.evaluate("""()=>{
          var ed=document.getElementById('editor');
          ed.scrollTop=ed.scrollHeight*0.8;
          ed.dispatchEvent(new Event('scroll'));
        }""")
        pg.wait_for_timeout(600)
        r = pg.evaluate("""()=>{
          var pane=document.getElementById('previewPane');
          var anchors=pane.querySelectorAll('[data-anchor-line]');
          var last=anchors[anchors.length-1];
          var pr=pane.getBoundingClientRect();
          var top=last?last.getBoundingClientRect().top-pr.top:-1;
          return {n:anchors.length,rel:top,vh:pane.clientHeight,
                  st:Math.round(pane.scrollTop)};
        }""")
        check("联动：末锚在预览视口内（固定版心宽）",
              r["n"] > 1 and 0 <= r["rel"] < r["vh"],
              "anchors=%d rel=%.0f vh=%d scrollTop=%d"
              % (r["n"], r["rel"], r["vh"], r["st"]))

        # --- 4. docx：A3 section + 边距 + {40}=261mm×0.4 ---
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": docx_path})))
        with pg.expect_response("**/api/export-docx**", timeout=60000) as ri:
            pg.click("#btnExportDocx")
        rj = ri.value.json()
        check("docx 导出 ok", rj.get("ok") is True, str(rj)[:100])
        from docx import Document as _Doc
        from docx.shared import Mm as _Mm
        d = _Doc(docx_path)
        sec = d.sections[0]
        check("docx 纸张 A3 297×420mm",
              abs(sec.page_width - _Mm(297)) < 1000
              and abs(sec.page_height - _Mm(420)) < 1000,
              "w=%s h=%s" % (sec.page_width, sec.page_height))
        check("docx 边距 上25 右18 下25 左18mm",
              abs(sec.top_margin - _Mm(25)) < 500
              and abs(sec.right_margin - _Mm(18)) < 500
              and abs(sec.bottom_margin - _Mm(25)) < 500
              and abs(sec.left_margin - _Mm(18)) < 500,
              "t=%s r=%s b=%s l=%s" % (sec.top_margin, sec.right_margin,
                                        sec.bottom_margin, sec.left_margin))
        shapes = d.inline_shapes
        if shapes:
            want_in = 261 * MM / 96.0
            check("docx {40} 图片 = A3 版心 261mm×0.4（10.24in±0.03）",
                  abs(shapes[0].width.inches - want_in * 0.4) < 0.03,
                  "%.3fin want=%.3fin" % (shapes[0].width.inches,
                                          want_in * 0.4))
        else:
            check("docx {40} 图片嵌入", False, "no shapes")

        # --- 5. 导出 HTML：body 版心 261mm ---
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": html_path})))
        with pg.expect_response("**/api/export-html**", timeout=60000) as ri:
            pg.click("#btnExportHtml")
        rj = ri.value.json()
        check("HTML 导出 ok", rj.get("ok") is True)
        htm = open(html_path, encoding="utf-8").read()
        check("HTML body 版心 width:261mm", "width:261mm" in htm)
        check("HTML 不再有 max-width:820px", "max-width:820px" not in htm)
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)