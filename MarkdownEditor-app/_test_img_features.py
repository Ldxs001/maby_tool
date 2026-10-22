# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""图片排版三特性测试（v2.3，playwright + 便携 python 服务）：
1. 图片段不参与正文首行缩进（与图表容器口径统一锚定版心左边）
2. 对齐：面板全局档 + 语法 {N c/l/r} 单图覆盖（预览几何 + docx jc）
3. fill 分栏：{50|50} 预览几何（栏宽/图缩放/{N} 失效）+ docx 无边框
   表格列宽；四栏/比例和校验 fail-closed
跑前杀遗留服务。"""
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
    print("%-58s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def kill_stale():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "($_.CommandLine -like '*md_server.py*' -or $_.CommandLine -like "
         "'*_md_run.py*') -and $_.Name -like '*python*' } | ForEach-Object "
         "{ Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True)
    time.sleep(0.3)


def alive():
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=0.3).read()
        return True
    except Exception:
        return False


kill_stale()
srv = subprocess.Popen(
    [os.path.join(HERE, "python", "python.exe"), "md_server.py"],
    cwd=HERE, creationflags=NO_WINDOW)
t0 = time.time()
while not alive() and time.time() - t0 < 20:
    time.sleep(0.1)
assert alive(), "服务未就绪"

from PIL import Image
tmpdir = tempfile.mkdtemp(prefix="md_imgfeat_")
img1 = os.path.join(tmpdir, "图1.png")
Image.new("RGB", (400, 160), (80, 120, 200)).save(img1)
img2 = os.path.join(tmpdir, "图2.png")
Image.new("RGB", (400, 160), (200, 120, 80)).save(img2)

S = (img1.replace("\\", "/"), img2.replace("\\", "/"))
DOC = """第一段正文，验证图片段与图表的起点口径。

![普通图]({s0})

![居中图]({s0}){{c}}

![右对齐图]({s0}){{r}}

@@ begin fill {{50|50}}
![左图]({s0}){{30}}

![右图]({s1})
@@ end fill

@@ begin fill {{25|25|50}}
![A]({s0})

![B]({s1})

![C]({s0})
@@ end fill

@@ begin fill {{60|60}}
![坏]({s0})

![坏2]({s1})
@@ end fill
""".format(*S) if False else (
    "第一段正文，验证图片段与图表的起点口径。\n\n"
    "![普通图](%s)\n\n" % S[0] +
    "![居中图](%s){c}\n\n" % S[0] +
    "![右对齐图](%s){r}\n\n" % S[0] +
    "@@ begin fill {50|50}\n" +
    "![左图](%s){30}\n\n" % S[0] +
    "![右图](%s)\n" % S[1] +
    "@@ end fill\n\n" +
    "@@ begin fill {25|25|50}\n" +
    "![A](%s)\n\n" % S[0] +
    "![B](%s)\n\n" % S[1] +
    "![C](%s)\n" % S[0] +
    "@@ end fill\n\n" +
    "@@ begin fill {60|60}\n" +
    "![坏](%s)\n\n" % S[0] +
    "![坏2](%s)\n" % S[1] +
    "@@ end fill\n")

docx_path = os.path.join(tmpdir, "out.docx")
SET_TS = """()=>{
  document.getElementById('btnTypeset').click();
  document.querySelector('input[data-tssz="p"]').value='14';
  document.querySelector('select[data-ind="p"]').value='first';
  document.querySelector('input[data-indchars="p"]').value='2';
  document.querySelector('select[data-algn="img"]').value='center';
  document.getElementById('tsApply').click();
}"""

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1100, "height": 900})
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
        pg.wait_for_function(
            "()=>document.querySelectorAll('#preview img').length>=8"
            "&&document.querySelectorAll('.fill-row').length>=2",
            timeout=15000)
        pg.wait_for_timeout(800)

        g = pg.evaluate("""()=>{
          var pv=document.getElementById('preview');
          var pvx=pv.getBoundingClientRect().left;
          var out={imgs:[],fills:[]};
          pv.querySelectorAll('img').forEach(function(im){
            var r=im.getBoundingClientRect();
            var p=im.closest('p');
            out.imgs.push({alt:im.alt,w:Math.round(r.width),
              x:Math.round(r.left-pvx),
              align:im.getAttribute('data-img-align')||'',
              pTA:p?getComputedStyle(p).textAlign:'',
              pTI:p?parseFloat(getComputedStyle(p).textIndent):0});
          });
          pv.querySelectorAll('.fill-row').forEach(function(fr){
            var cols=fr.querySelectorAll(':scope > .fill-col');
            var cw=[];
            cols.forEach(function(c){
              cw.push(Math.round(c.getBoundingClientRect().width));
            });
            out.fills.push({n:cols.length,cw:cw,
              rowW:Math.round(fr.getBoundingClientRect().width)});
          });
          return out;
        }""")
        byalt = {x["alt"]: x for x in g["imgs"]}
        # 1. 图片段不参与首行缩进（text-indent 归零；几何居中由全局档
        #    承载，锚定验证用 computed textIndent）
        check("图片段不参与正文首行缩进",
              abs(byalt["普通图"].get("pTI", 0)) <= 0.5,
              "pTI=%s" % byalt["普通图"].get("pTI"))
        # 2. 语法级对齐（全局档居中 + {r} 单图覆盖为右）
        check("面板全局档：图片居中",
              byalt["普通图"]["pTA"] == "center",
              byalt["普通图"]["pTA"])
        check("语法 {c} 居中", byalt["居中图"]["pTA"] == "center",
              byalt["居中图"]["pTA"])
        check("语法 {r} 覆盖全局档为右对齐（图几何靠右）",
              byalt["右对齐图"]["x"] > byalt["居中图"]["x"] + 50,
              "r_x=%s c_x=%s" % (byalt["右对齐图"]["x"],
                                 byalt["居中图"]["x"]))
        # 3. fill 两栏 50|50：栏宽基准 = 行宽（行宽≈版心减 gap）
        f1 = g["fills"][0] if g["fills"] else None
        pv_w = pg.evaluate(
            "()=>Math.round(document.getElementById('preview')"
            ".getBoundingClientRect().width)")
        check("fill 两栏渲染", f1 is not None and f1["n"] == 2,
              str(g["fills"])[:120])
        if f1 and f1["n"] == 2:
            check("50|50 栏宽各半（±4px）",
                  abs(f1["cw"][0] - f1["cw"][1]) <= 4,
                  "cw=%s" % f1["cw"])
        # {N} 失效：两栏同宽（180px 栏），若 {30} 生效左图会被缩到
        # 栏宽 30%（54px）——实测两图同宽即证明 {N} 被 CSS 压制
        check("栏内 {N} 失效（{30} 未缩图，与无参图同宽）",
              abs(byalt["左图"]["w"] - byalt["右图"]["w"]) <= 2,
              "L=%s R=%s" % (byalt["左图"]["w"], byalt["右图"]["w"]))
        # 4. 三栏 25|25|50
        f2 = g["fills"][1] if len(g["fills"]) > 1 else None
        check("fill 三栏 25|25|50",
              f2 is not None and f2["n"] == 3
              and abs(f2["cw"][2] - 2 * f2["cw"][0]) <= 6,
              str(f2["cw"]) if f2 else "-")
        # 5. 60|60（和=120）fail-closed：无第三个 fill-row，文本字面
        check("60|60 比例和≠100 fail-closed",
              len(g["fills"]) == 2,
              "rows=%d" % len(g["fills"]))

        # --- docx ---
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

    from docx import Document as _Doc
    d = _Doc(docx_path)
    xml = zipfile.ZipFile(docx_path).read(
        "word/document.xml").decode("utf-8")
    # 图片段无文本——按含 drawing 的段落顺序断言 jc（doc 顺序 =
    # 普通图(全局center) 居中图(c) 右图(r) …fill 栏内图）
    jc_seq = []
    for m in re.finditer(r"<w:p\b[^>]*>(.*?)</w:p>", xml, re.S):
        if "<w:drawing>" in m.group(1):
            j = re.search(r'<w:jc w:val="([^"]+)"', m.group(1))
            jc_seq.append(j.group(1) if j else "")
    check("docx 全局档图片 jc=center（首图）",
          bool(jc_seq) and jc_seq[0] == "center", str(jc_seq[:4]))
    check("docx 语法 {r} 图片 jc=right（第三图）",
          len(jc_seq) > 2 and jc_seq[2] == "right", str(jc_seq[:4]))
    # fill：无边框表格×2（两栏+三栏），60|60 不出表
    tbls = d.tables
    check("docx fill 表格 2 张（两栏+三栏）", len(tbls) == 2,
          "tables=%d" % len(tbls))
    if len(tbls) == 2:
        t1, t2 = tbls
        _c1 = [c.width for c in t1.columns]
        check("docx 两栏表列宽各半",
              len(_c1) == 2 and abs(int(_c1[0]) - int(_c1[1])) <= 30000,
              str(_c1))
        _c2 = [int(c.width) for c in t2.columns]
        check("docx 三栏表 25|25|50（第 3 列 = 2×第 1 列）",
              len(_c2) == 3 and abs(_c2[2] - 2 * _c2[0]) <= 60000
              and abs(_c2[0] - _c2[1]) <= 30000,
              str(_c2))
        # 无边框：tblBorders 全 none（布局骨架不可见）
        _tb = re.search(r"<w:tblBorders>(.*?)</w:tblBorders>", xml, re.S)
        check("docx fill 表无边框",
              _tb is not None and _tb.group(1).count('w:val="none"') >= 6,
              _tb.group(1)[:80] if _tb else "no tblBorders")
        check("docx fill 单元格含图片",
              len(d.inline_shapes) >= 8,
              "shapes=%d" % len(d.inline_shapes))
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)