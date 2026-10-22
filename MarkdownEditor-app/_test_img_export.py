# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""普通本地图片（.assets 相对路径，非图表）三导出复现：
md 存临时目录，图片在同目录 .assets/ 下，经 ?file= 打开（currentFile 生效）：
1. docx：图片应嵌入 word/media（用户报"图没有加进来"）
2. HTML：src 应重写为 file:/// 且路径正确
3. 打印：同 HTML 口径
playwright + 便携 python 服务（docxdeps）。"""
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
    print("%-52s %s %s" % (name, "PASS" if cond else "FAIL", detail))
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

tmpdir = tempfile.mkdtemp(prefix="md_img_export_")
assets = os.path.join(tmpdir, "文档.assets")
os.makedirs(assets, exist_ok=True)

from PIL import Image
img_path = os.path.join(assets, "示例图.png")
Image.new("RGB", (240, 150), (80, 120, 200)).save(img_path)

md_path = os.path.join(tmpdir, "文档.md")
DOC = ("# 图片导出测试\n\n正文段落。\n\n"
       "![示例](文档.assets/示例图.png)\n\n段落结尾。\n")
open(md_path, "w", encoding="utf-8").write(DOC)

docx_path = os.path.join(tmpdir, "out.docx")
html_path = os.path.join(tmpdir, "out.html")
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
        url = "http://127.0.0.1:%d/?file=%s" % (
            PORT, urllib.parse.quote(md_path.replace("\\", "/")))
        pg.goto(url)
        pg.wait_for_selector("#preview img", timeout=15000)
        pg.wait_for_timeout(600)

        prev = pg.evaluate(
            "()=>{var i=document.querySelector('#preview img');"
            "return {src:i.getAttribute('src'),"
            "loaded:i.complete&&i.naturalWidth>0};}")
        check("预览图片已加载（/img 代理）",
              prev["loaded"] and prev["src"].startswith("/img?path="),
              str(prev)[:150])

        # --- docx ---
        with pg.expect_response("**/api/export-docx**", timeout=30000) as ri:
            pg.click("#btnExportDocx")
        rj = ri.value.json()
        check("docx 导出 ok", rj.get("ok") is True, str(rj)[:100])
        xml = zipfile.ZipFile(docx_path).read(
            "word/document.xml").decode("utf-8")
        media = [n for n in zipfile.ZipFile(docx_path).namelist()
                 if n.startswith("word/media/")]
        check("docx 普通图片嵌入 word/media", len(media) >= 1,
              "media=%s" % media)
        check("docx 无 [图片:..] 占位", "[图片:" not in xml)

        # --- HTML（同页切换保存路径）---
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": html_path})))
        with pg.expect_response("**/api/export-html**", timeout=30000) as ri:
            pg.click("#btnExportHtml")
        rj = ri.value.json()
        check("HTML 导出 ok", rj.get("ok") is True)
        htm = open(html_path, encoding="utf-8").read()
        srcs = re.findall(r'src="([^"]+)"', htm)
        imgsrcs = [s for s in srcs if "img" not in s or s.startswith("file")]
        file_srcs = [s for s in srcs if s.startswith("file:///")]
        check("HTML 图片 src 重写为 file:///", len(file_srcs) >= 1,
              str(srcs)[:200])
        if file_srcs:
            fp = urllib.parse.unquote(
                file_srcs[0].replace("file:///", "")).replace("/", "\\")
            check("HTML file:/// 路径指向真实文件", os.path.exists(fp),
                  fp)
        check("HTML 无 /img?path 代理残留", "/img?path=" not in htm)
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