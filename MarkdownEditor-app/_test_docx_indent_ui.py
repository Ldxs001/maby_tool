# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""docx 缩进/对齐/有序列表编号 UI 端到端测试（playwright + 便携 python）：
真实浏览器设排版（正文 14pt、首行缩进 2、列表整体缩进 2、正文居中）→
构造文档（含 <<< 包围块、接力列表 start=2、引用）→ 导出 → XML 断言：
1. 普通段落 first_line_indent = 28pt（37.33px×0.75，正文字号基准）
2. 全局对齐 jc=center 生效（left/right 走同一 _align 路径，构造测试覆盖）
3. 接力列表：独立 numId，abstract lvl0 start=2（共享 numId 会跨列表连号）
4. 列表 li left_indent = 28pt；两个 ol 的 numId 互不相同
5. 引用 left_indent；ind-blk 块内列表 = 块边界+档叠加
跑前杀遗留 md_server（18766 被旧进程占用会打旧代码）。"""
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

DOC = """普通段落，首行应缩进两字符。

1. 第一项
- 无序一项
1. 接力应为2

<<<
块内列表
<<<
<<<
1. 块内有序
<<<

> 引用一句话
"""

SET_TS = """()=>{
  document.getElementById('btnTypeset').click();
  document.querySelector('input[data-tssz="p"]').value='14';
  document.querySelector('select[data-algn="p"]').value='center';
  document.querySelector('select[data-ind="p"]').value='first';
  document.querySelector('input[data-indchars="p"]').value='2';
  document.querySelector('select[data-ind="li"]').value='block';
  document.querySelector('input[data-indchars="li"]').value='2';
  document.querySelector('select[data-ind="quote"]').value='block';
  document.querySelector('input[data-indchars="quote"]').value='2';
  document.getElementById('tsApply').click();
}"""

tmpdir = tempfile.mkdtemp(prefix="md_docx_ind_")
docx_path = os.path.join(tmpdir, "ind.docx")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(800)
        pg.evaluate(SET_TS)
        pg.wait_for_timeout(500)
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_timeout(1200)
        pv = pg.evaluate(
            "()=>{var o=document.querySelectorAll('#preview ol');"
            "return Array.from(o).map(function(x){"
            "return x.getAttribute('start')||'1';});}")
        check("预览接力语义正确（start 1/2/1）", pv == ["1", "2", "1"],
              str(pv))
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": docx_path})))
        with pg.expect_response("**/api/export-docx**", timeout=60000) as ri:
            pg.click("#btnExportDocx")
        rj = ri.value.json()
        check("docx 导出 ok", rj.get("ok") is True, str(rj)[:100])
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()

    xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode()
    nxml = zipfile.ZipFile(docx_path).read(
        "word/numbering.xml").decode() \
        if "word/numbering.xml" in zipfile.ZipFile(docx_path).namelist() \
        else ""

    def para_info(text):
        for m in re.finditer(r"<w:p>(.*?)</w:p>", xml, re.S):
            seg = m.group(1)
            t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", seg))
            if text in t:
                ppr = re.search(r"<w:pPr>(.*?)</w:pPr>", seg, re.S)
                ppr = ppr.group(1) if ppr else ""
                ind = re.search(
                    r'<w:ind [^/>]*/>', ppr)
                jc = re.search(r'<w:jc w:val="([^"]+)"', ppr)
                nid = re.search(r'<w:numId w:val="(\d+)"', ppr)
                return {"text": t, "ind": ind.group(0) if ind else "",
                        "jc": jc.group(1) if jc else "",
                        "numId": nid.group(1) if nid else ""}
        return None

    # 1. 首行缩进 37.33px → 28pt=560twips
    pi = para_info("普通段落")
    check("段落首行缩进 firstLine=560twips（28pt）",
          pi is not None and 'w:firstLine="560"' in (pi or {}).get("ind", ""),
          str(pi))
    # 2. 全局对齐
    check("对齐 jc=center 生效",
          pi is not None and pi.get("jc") == "center", str(pi))
    # 3. 接力列表独立编号：num 上 startOverride（Word 原生"重新开始"
    #    机制；克隆 abstractNum 设 start 会被 Word 保存时规范化合并丢弃）
    li2 = para_info("接力应为2")
    nid2 = (li2 or {}).get("numId")
    li1 = para_info("第一项")
    nid1 = (li1 or {}).get("numId")
    check("两个 ol 绑定不同 numId（独立编号实例）",
          nid1 and nid2 and nid1 != nid2,
          "n1=%s n2=%s" % (nid1, nid2))
    so1 = so2 = None
    abs_set = set()
    if nid1 and nid2 and nxml:
        for nid_v in (nid1, nid2):
            m = re.search(
                r'<w:num w:numId="%s"[^>]*>(.*?)</w:num>' % nid_v, nxml,
                re.S)
            if not m:
                continue
            aid = re.search(
                r'<w:abstractNumId w:val="(\d+)"', m.group(1))
            so = re.search(
                r'<w:startOverride w:val="(\d+)"', m.group(1))
            if aid:
                abs_set.add(aid.group(1))
            if nid_v == nid1:
                so1 = so.group(1) if so else None
            else:
                so2 = so.group(1) if so else None
        check("两个 num 共享同一 abstractNum（Word 原生机制）",
              len(abs_set) == 1, str(abs_set))
        check("每个 num 都带 startOverride（否则 Word 并回主序列）",
              so1 is not None and so2 is not None,
              "so1=%s so2=%s" % (so1, so2))
        check("接力 ol startOverride=2、首个=1",
              so1 == "1" and so2 == "2",
              "so1=%s so2=%s" % (so1, so2))
    else:
        check("接力 ol startOverride=2", False, "no numbering")
    # 4. 列表缩进 28pt=560twips + 压掉编号级悬挂（hanging=360 会让
    #    Word 把编号悬在 left-360，比块内正文浅一层半）
    check("列表 li left_indent=560twips",
          li1 is not None and 'w:left="560"' in (li1 or {}).get("ind", ""),
          str(li1))
    check("列表 li firstLine=0（压编号级悬挂，编号在容器左缘）",
          li1 is not None and 'w:firstLine="0"' in (li1 or {}).get("ind", ""),
          str(li1))
    check("列表 li 无 hanging 继承泄漏",
          li1 is not None and "hanging" not in (li1 or {}).get("ind", ""),
          str(li1))
    # 4b. 编号定义 inside 化（v2.2.7）：ListNumber 的 abstractNum lvl0
    #     须 suff=space（编号后空格紧贴文字）且无 ind/tabs 悬挂底座——
    #     段落 firstLine=0 防御会被 Word 保存时剥 0 值属性，编号定义
    #     不清理则回退 Word 默认悬挂布局（"1.□□□文字"）
    _abs_ok = False
    _m = re.search(
        r'<w:num w:numId="%s"[^>]*>\s*<w:abstractNumId w:val="(\d+)"'
        % nid1, nxml) if nid1 else None
    if _m:
        _seg = re.search(
            r'<w:abstractNum w:abstractNumId="%s".*?</w:abstractNum>'
            % _m.group(1), nxml, re.S)
        if _seg:
            _s = _seg.group(0)
            _lvl0 = re.search(
                r'<w:lvl w:ilvl="0".*?</w:lvl>', _s, re.S)
            if _lvl0:
                _l = _lvl0.group(0)
                _abs_ok = ('<w:suff w:val="space"' in _l
                           and "<w:ind " not in _l
                           and "<w:tabs" not in _l)
    check("编号定义 inside 化（suff=space、无 ind/tabs 底座）",
          _abs_ok,
          "numId=%s" % nid1)
    # 5. 引用缩进：本机 ui-state 恢复 quote 整体缩进 2 字符=37.33px→560；
    #    无档时才回落 0.3in（432）
    qi = para_info("引用一句话")
    check("引用 left_indent=560twips（排版档 37.33px）",
          qi is not None and 'w:left="560"' in (qi or {}).get("ind", ""),
          str(qi))
    # 6. ind-blk 块内列表：边界 0 + 档 560
    bi = para_info("块内有序")
    check("块内列表缩进=块边界+档（560twips）",
          bi is not None and 'w:left="560"' in (bi or {}).get("ind", ""),
          str(bi))
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)