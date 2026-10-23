# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""用户真实文档复现：docs/MDEditor 使用指南.md（相对路径图片、带空格
目录名、{40} 宽度参数、mermaid 图表）三导出全链路：
1. docx：图片（普通+{40}）与图表全部嵌入，{40}→版心×0.4
2. HTML：图片 src 重写 file:///（空格路径），图表栅格化
3. 打印：同 HTML 口径
playwright + 便携 python 服务。导出到临时目录，不动用户文件。"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "docs", "MDEditor 使用指南.md")
# v2.5.2 后用户文档正文含裸 MDE 执行点（其中 process_words 不存在→
# 失败态→导出关口正确拦截）。本测试回归"导出产物"功能本身，用剔除
# 执行点行的临时副本测（用户文档零改动；速查表/章节示例带反引号
# 被行内代码保护，不在剔除范围）
import re as _re
_src_txt = open(SRC, encoding="utf-8").read()
_clean = "\n".join(
    ln for ln in _src_txt.splitlines()
    if not _re.search(r'@@ MDE (import|from)\b', ln)
    or ln.lstrip().startswith("|") or "`" in ln)
SRC_TEST = os.path.join(HERE, "docs", "_tmp_real_export.md")
open(SRC_TEST, "w", encoding="utf-8").write(_clean)
SRC = SRC_TEST
PORT = 18766
NO_WINDOW = 0x08000000

fails = []


def check(name, cond, detail=""):
    print("%-56s %s %s" % (name, "PASS" if cond else "FAIL", detail))
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

tmpdir = tempfile.mkdtemp(prefix="md_real_export_")
docx_path = os.path.join(tmpdir, "real.docx")
html_path = os.path.join(tmpdir, "real.html")
paged_path = os.path.join(tmpdir, "real-paged.html")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        url = "http://127.0.0.1:%d/?file=%s" % (
            PORT, urllib.parse.quote(SRC.replace("\\", "/")))
        pg.goto(url)
        # 显式设 A4+25/18/25/18：服务端 ui-state 会恢复本机真实排版（如 A3/
        # mt=30），{40}→版心×0.4 断言须在确定态下做（A4 版心 6.85in）
        pg.evaluate(
            "()=>{document.getElementById('btnTypeset').click();"
            "document.getElementById('tsPaper').value='A4';"
            "document.getElementById('tsMt').value=25;"
            "document.getElementById('tsMr').value=18;"
            "document.getElementById('tsMb').value=25;"
            "document.getElementById('tsMl').value=18;"
            "document.getElementById('tsApply').click();}")
        pg.wait_for_timeout(800)
        # 等全部内容渲染：图片加载 + 图表完成
        pg.wait_for_function(
            "()=>{var ds=document.querySelectorAll('.diagram');"
            "var done=ds.length===0||Array.prototype.every.call(ds,"
            "function(d){return d.hasAttribute('data-done');});"
            "var ims=document.querySelectorAll('#preview img');"
            "var imok=Array.prototype.every.call(ims,"
            "function(i){return i.complete;});"
            "return done&&imok&&ims.length>0;}", timeout=30000)
        pg.wait_for_timeout(800)

        prev = pg.evaluate(
            "()=>{var ims=document.querySelectorAll('#preview img');"
            "return {n:ims.length,"
            "srcs:Array.from(ims).map(function(i){"
            "return (i.getAttribute('src')||'').substring(0,60);}),"
            "allLoaded:Array.from(ims).every(function(i){"
            "return i.complete&&i.naturalWidth>0;})};}")
        check("预览图片全部加载（含空格路径）",
              prev["n"] >= 2 and prev["allLoaded"],
              "n=%d loaded=%s %s" % (prev["n"], prev["allLoaded"],
                                     str(prev["srcs"])[:160]))

        # --- docx ---
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": docx_path})))
        with pg.expect_response("**/api/export-docx**", timeout=60000) as ri:
            pg.click("#btnExportDocx")
        rj = ri.value.json()
        check("docx 导出 ok", rj.get("ok") is True, str(rj)[:120])
        xml = zipfile.ZipFile(docx_path).read(
            "word/document.xml").decode("utf-8")
        _zf = zipfile.ZipFile(docx_path)
        nxml = _zf.read("word/numbering.xml").decode("utf-8") \
            if "word/numbering.xml" in _zf.namelist() else ""
        media = [n for n in _zf.namelist()
                 if n.startswith("word/media/")]
        ndiag = pg.evaluate("()=>document.querySelectorAll('.diagram').length")
        from docx import Document as _Doc
        ddoc = _Doc(docx_path)
        shapes = ddoc.inline_shapes
        # 3 张普通图引用同一 PNG：media 按字节去重为 1，inline_shapes 才是
        # 全量口径（3 普通 + 5 图表 = 8）
        check("docx 图片+图表全量嵌入（inline_shapes）",
              len(shapes) == prev["n"] + ndiag,
              "shapes=%d imgs=%d diags=%d" % (len(shapes), prev["n"], ndiag))
        check("docx 无 [图片:..] 占位丢失", "[图片:" not in xml)
        check("docx 无 [图表] 占位回落（含 vega 工具栏图标）",
              "[图表]" not in xml)
        if len(shapes) >= 1:
            # {N} 参数从源文档动态读（用户会手动改文档如 {40}→{50}，
            # 硬编码断言会误报"回归失败"）；A4 版心 174mm
            _src = open(SRC, encoding="utf-8").read()
            _mm = re.search(r'!\[[^\]]*\]\([^)]+\)\{(\d+)\}', _src)
            _pct = int(_mm.group(1)) if _mm else 0
            if _pct:
                _want = (174 / 25.4) * _pct / 100.0
                check("docx {%d} 图片 → 版心×%.2f（A4）" % (_pct, _pct / 100.0),
                      any(abs(s.width.inches - _want) < 0.02
                          for s in shapes),
                      str(["%.2f" % s.width.inches for s in shapes])[:150])
        # 无序 marker 语义：- 空心圈 / + 实心点跟标记符走（li 级，+ 与 -
        # 可混排于同一 ul——"实心点列表项（加号）"与"空心圈列表项（减号）"
        # 同级混排、"嵌套子项"是嵌套 -）
        hollow_nids = set()
        for _m in re.finditer(
                r'<w:num w:numId="(\d+)"[^>]*>\s*<w:abstractNumId '
                r'w:val="(\d+)"', nxml or ""):
            _n, _a = _m.group(1), _m.group(2)
            _lt = re.search(
                r'<w:abstractNum w:abstractNumId="%s".*?<w:lvlText '
                r'w:val="([^"]*)"' % _a, nxml, re.S)
            if _lt and _lt.group(1) == "\uF0A7":
                hollow_nids.add(_n)
        _hollow_txts = ["空心圈列表项（减号）", "嵌套子项（缩进决定层级"]
        _solid_txts = ["实心点列表项（加号）", "已完成任务", "待办任务"]
        _bind = {}
        for _m in re.finditer(r"<w:p\b[^>]*>(.*?)</w:p>", xml, re.S):
            _t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", _m.group(1)))
            for _kw in _hollow_txts + _solid_txts:
                if _kw in _t:
                    _n = re.search(r'<w:numId w:val="(\d+)"', _m.group(1))
                    _bind[_kw] = _n.group(1) if _n else "-"
        check("docx '-' 项（含同级混排与嵌套）绑空心圈编号",
              bool(hollow_nids) and all(_bind.get(k) in hollow_nids
                                        for k in _hollow_txts),
              "hollowNums=%s bind=%s" % (sorted(hollow_nids),
                                         {k: _bind.get(k)
                                          for k in _hollow_txts}))
        check("docx '+' 项走默认实心（不绑空心）",
              all(_bind.get(k) not in hollow_nids
                  for k in _solid_txts if _bind.get(k) != "-"),
              str({k: _bind.get(k) for k in _solid_txts}))

        # --- HTML ---
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": html_path})))
        with pg.expect_response("**/api/export-html**", timeout=60000) as ri:
            pg.click("#btnExportHtml")
        rj = ri.value.json()
        check("HTML 导出 ok", rj.get("ok") is True)
        htm = open(html_path, encoding="utf-8").read()
        fsrcs = re.findall(r'src="(file:///[^"]+)"', htm)
        ok_path = all(os.path.exists(urllib.parse.unquote(
            s.replace("file:///", "")).replace("/", "\\"))
            for s in fsrcs) if fsrcs else False
        check("HTML 图片 file:/// 且路径真实（空格目录）",
              len(fsrcs) >= prev["n"] and ok_path,
              "n=%d real=%s %s" % (len(fsrcs), ok_path,
                                   str(fsrcs)[:160]))
        check("HTML 无 /img 代理残留", "/img?path=" not in htm)
        check("HTML 图表栅格化自包含",
              htm.count("data:image/png") >= ndiag,
              "png=%d diags=%d" % (htm.count("data:image/png"), ndiag))
        # marker 语义：+ 实心 / - 空心 CSS 规则随导出携带（缺失则浏览器
        # 默认按层级渲染：顶层 disc、嵌套 circle——用户报告的现象）
        _h2 = htm.replace(" ", "").replace("\n", "")
        import re as _re2
        check("HTML marker CSS（u-solid/u-hollow）随导出携带",
              bool(_re2.search(r"u-solid\{[^}]*disc", _h2))
              and bool(_re2.search(r"u-hollow\{[^}]*circle", _h2)),
              "solid=%s hollow=%s" % (
                  "u-solid" in htm, "u-hollow" in htm))
        check("HTML li 保留 u-hollow class（bodyHtml 未剥）",
              'class="u-hollow"' in htm)

        # --- 打印（paged）：系统浏览器打开服务端 http URL（用户真实流程）---
        with pg.expect_response("**/api/export-paged**", timeout=60000) as ri:
            pg.click("#btnExportPaged")
        rj = ri.value.json()
        purl = (rj or {}).get("url") or ""
        # /static/<name> 路由把前缀剥掉映射到 HERE：落盘文件名取 url 末段
        paged_path = os.path.join(HERE, os.path.basename(purl)) \
            if purl else ""
        pg.wait_for_timeout(500)
        check("打印 HTML 落盘", bool(paged_path) and os.path.exists(paged_path)
              and os.path.getsize(paged_path) > 5000,
              "url=%s size=%s" % (purl,
                                  os.path.getsize(paged_path)
                                  if paged_path and os.path.exists(paged_path)
                                  else 0))
        phtm = open(paged_path, encoding="utf-8").read() \
            if paged_path and os.path.exists(paged_path) else ""
        check("打印图表栅格化自包含",
              phtm.count("data:image/png") >= ndiag,
              "png=%d diags=%d" % (phtm.count("data:image/png"), ndiag))
        # 以 http 打开打印版（同用户系统浏览器），量真实图片实际加载：
        # /img 代理同源可用；file:/// 会被浏览器安全策略拦截（全挂）
        pg2 = b.new_page()
        pg2.goto("http://127.0.0.1:%d%s" % (PORT, purl))
        pg2.wait_for_timeout(1500)
        loaded = pg2.evaluate(
            "()=>{var ims=Array.from(document.querySelectorAll('img'));"
            "var real=ims.filter(function(i){"
            "return (i.getAttribute('src')||'').indexOf('data:')!==0;});"
            "return {n:real.length,"
            "ok:real.every(function(i){"
            "return i.complete&&i.naturalWidth>0;})};}")
        check("打印真实图片经 /img 代理全部加载",
              loaded["n"] >= prev["n"] and loaded["ok"],
              "n=%d ok=%s" % (loaded["n"], loaded["ok"]))
        check("no page errors", not errors, "; ".join(errors[:2]))
        pg2.close()
        if paged_path and os.path.exists(paged_path):
            os.remove(paged_path)
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)
    if os.path.exists(SRC_TEST):
        os.remove(SRC_TEST)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)