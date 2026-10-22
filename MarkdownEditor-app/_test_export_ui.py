# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""导出 docx 全链路 UI 验证（playwright + 便携 python 服务）：
真实渲染 mermaid 图表 -> 点击导出按钮 -> 拦截原生保存对话框 ->
前端栅格化 SVG->PNG -> 服务端 build_docx -> 落盘 docx 断言：
- 图片嵌入（栅格化成功，非 [图表] 占位回落）
- 标题/表格语义保留（pblk 裸 div 下钻）
- 无 SVG CSS 垃圾文本（#mmd 系列样式串）
服务须用便携 python 起（docxdeps cp311 与系统 python 3.14 不兼容）。"""
import json
import os
import re
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
    print("%-46s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def alive():
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=0.3).read()
        return True
    except Exception:
        return False




def kill_stale():
    """杀遗留服务（md_server 直启或 _md_run shim）——18766 被占时新进程
    bind 失败静默退出，测试打的会是旧代码（假性回归）。"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "($_.CommandLine -like '*md_server.py*' -or $_.CommandLine -like "
         "'*_md_run.py*') -and $_.Name -like '*python*' } | ForEach-Object "
         "{ Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True)
    time.sleep(0.3)

kill_stale()
srv = subprocess.Popen(
    [os.path.join(HERE, "python", "python.exe"), "md_server.py"],
    cwd=HERE, creationflags=NO_WINDOW)
t0 = time.time()
while not alive() and time.time() - t0 < 20:
    time.sleep(0.1)
assert alive(), "服务未就绪"

tmpdir = tempfile.mkdtemp(prefix="md_export_ui_")
docx_path = os.path.join(tmpdir, "全链路导出.docx")

DOC = ("# 导出全链路\n\n正文段落。\n\n"
       "```mermaid\ngraph LR\n  A[开始] --> B{判定}\n"
       "  B -->|是| C[结束]\n  B -->|否| B\n```\n\n"
       "```mermaid {30}\ngraph LR\n  A --> B --> C\n```\n\n"
       "| 列A | 列B |\n|----|----|\n| 1 | 2 |\n")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": docx_path})))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(800)
        # 显式设 A4+25/18/25/18：服务端 ui-state 会恢复本机真实排版（如 A3/
        # mt=30），版心断言须在确定态下做（版心 174mm=6.85in）
        pg.evaluate(
            "()=>{document.getElementById('btnTypeset').click();"
            "document.getElementById('tsPaper').value='A4';"
            "document.getElementById('tsMt').value=25;"
            "document.getElementById('tsMr').value=18;"
            "document.getElementById('tsMb').value=25;"
            "document.getElementById('tsMl').value=18;"
            "document.getElementById('tsApply').click();}")
        pg.wait_for_timeout(800)

        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        # 等 mermaid runtime 加载、全部（2 个）图表渲染完成（首个冷启动慢；
        # 分块渲染下第二块 .diagram 插入有延迟，须等精确数量）
        pg.wait_for_function(
            "()=>{var ds=document.querySelectorAll('.diagram');"
            "return ds.length===2&&Array.prototype.every.call(ds,"
            "function(d){return d.hasAttribute('data-done');})}",
            timeout=30000)
        pg.wait_for_timeout(500)
        # 记录两图预览显示宽（宽度规则断言基准）
        disp = pg.evaluate(
            "()=>Array.from(document.querySelectorAll("
            "'.diagram[data-done] svg')).map(function(s){"
            "return Math.ceil(s.getBoundingClientRect().width);})")

        with pg.expect_response("**/api/export-docx**", timeout=30000) as ri:
            pg.click("#btnExportDocx")
        resp = ri.value
        rj = resp.json()
        check("导出接口返回 ok", rj.get("ok") is True, str(rj)[:120])

        check("docx 文件落盘", os.path.exists(docx_path) and
              os.path.getsize(docx_path) > 2000,
              "size=%s" % (os.path.getsize(docx_path)
                           if os.path.exists(docx_path) else 0))

        xml = zipfile.ZipFile(docx_path).read(
            "word/document.xml").decode("utf-8")
        media = [n for n in zipfile.ZipFile(docx_path).namelist()
                 if n.startswith("word/media/")]
        check("栅格化图片嵌入 word/media", len(media) >= 1,
              "media=%s" % media)
        check("无 SVG CSS 垃圾文本（#mmd）", "mmd" not in xml)
        check("无 [图表] 占位回落", "[图表]" not in xml)
        check("标题语义保留（Heading1）",
              'w:val="Heading1"' in xml or "Heading1" in xml)
        check("表格语义保留（w:tbl）", "<w:tbl>" in xml)
        check("正文文字在", "正文段落" in xml)

        # --- 图片宽度规则（默认 A4 版心 174mm=6.85in）：{30} → 2.055in ---
        if len(disp) >= 2:
            from docx import Document as _Doc
            ddoc = _Doc(docx_path)
            shapes = ddoc.inline_shapes
            check("宽度规则：两图嵌入", len(shapes) == 2,
                  "shapes=%d" % len(shapes))
            if len(shapes) == 2:
                _usable = 174 / 25.4   # A4 版心 210−18−18mm
                check("图表{30} → 版心×0.3（2.055in）",
                      abs(shapes[1].width.inches - _usable * 0.3) < 0.02,
                      "%.3f in（预览显示 %dpx）" % (shapes[1].width.inches,
                                                     disp[1]))
                no_arg = min(disp[0] / 96.0, _usable)
                check("无参图表 → 显示宽/96 钳版心",
                      abs(shapes[0].width.inches - no_arg) < 0.02,
                      "%.3f in（预览显示 %dpx）" % (shapes[0].width.inches,
                                                     disp[0]))
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()

    # --- HTML 导出链路：同样栅格化（data URL 自包含），无 SVG 依赖 ---
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        html_path = os.path.join(tmpdir, "全链路导出.html")
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": html_path})))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(800)
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_function(
            "()=>{var ds=document.querySelectorAll('.diagram');"
            "return ds.length===2&&Array.prototype.every.call(ds,"
            "function(d){return d.hasAttribute('data-done');})}",
            timeout=30000)
        pg.wait_for_timeout(500)
        with pg.expect_response("**/api/export-html**", timeout=30000) as ri:
            pg.click("#btnExportHtml")
        rj = ri.value.json()
        check("HTML 导出接口返回 ok", rj.get("ok") is True)
        htm = open(html_path, encoding="utf-8").read() \
            if os.path.exists(html_path) else ""
        check("HTML 图表已栅格化（data:image/png 自包含）",
              "data:image/png" in htm)
        check("HTML 无 SVG 残留", "<svg" not in htm)
        check("HTML 栅格化图显式定宽（1x 显示尺寸，防 2x 物理像素放大）",
              'style="width:' in htm and "max-width:100%" in htm)
        check("HTML 图表 {30} 容器宽度语义保留",
              'width:30%' in htm)
        check("HTML 标题/表格结构保留",
              "<h1" in htm and "<table" in htm)
        check("HTML no page errors", not errors, "; ".join(errors[:2]))
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