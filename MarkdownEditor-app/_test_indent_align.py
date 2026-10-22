# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AG v3 (or later).
"""缩进档几何对齐测试（v2.2.1 px 统一基准，playwright）：
用户场景——正文首行缩进 2 字符 + 列表整体缩进 2 字符 + <<< 包围块，
且列表字号 < 正文字号（em 双尺漂移的触发条件）：
1. 列表「1.」与正文首字「正」x 坐标一致（±1px）
2. <<< 阶梯几何：块边界 + 列表档精确叠加（第三层 + 项 = 2×档 + 边界）
3. 导出 HTML 同口径（ts-style px 绝对值随导出走，无 em 漂移）
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

tmpdir = tempfile.mkdtemp(prefix="md_ind_align_")
html_path = os.path.join(tmpdir, "ind.html")

DOC = """<<<
正文模式
<<<
<<<
1. 第一项
2. 第二项
<<<
<<<
+ 再进一层
<<<
"""

# 显式排版：正文 14pt + 列表 11.25pt（字号差 = em 双尺漂移触发条件）；
# 正文首行缩进 2 / 列表整体缩进 2 / 引用整体缩进 2
SET_TS = """()=>{
  document.getElementById('btnTypeset').click();
  document.querySelector('input[data-tssz="p"]').value='14';
  document.querySelector('input[data-tssz="li"]').value='11.25';
  document.querySelector('select[data-algn="p"]').value='left';
  document.querySelector('select[data-ind="p"]').value='first';
  document.querySelector('input[data-indchars="p"]').value='2';
  document.querySelector('select[data-ind="li"]').value='block';
  document.querySelector('input[data-indchars="li"]').value='2';
  document.querySelector('select[data-ind="quote"]').value='block';
  document.querySelector('input[data-indchars="quote"]').value='2';
  document.getElementById('tsApply').click();
}"""

MEASURE = """()=>{
  var pv=document.getElementById('preview');
  var pvx=pv.getBoundingClientRect().left;
  function firstCharX(el){
    var n=el.firstChild;
    while(n){
      if(n.nodeType===3&&n.textContent.trim()){
        var rg=document.createRange();
        rg.setStart(n,0);rg.setEnd(n,1);
        return Math.round(rg.getBoundingClientRect().left-pvx);
      }
      if(n.nodeType===1){var x=firstCharX(n);if(x!==null)return x;}
      n=n.nextSibling;
    }
    return null;
  }
  /* marker（inside 模式）是 ::marker 伪元素不在 DOM 文本——li 内容盒左缘
     即 marker「1.」的字面起点（用户对齐感知对象） */
  function liBoxX(el){ return Math.round(el.getBoundingClientRect().left-pvx); }
  var pX=null,li1X=null,plusX=null,indBlks=[];
  pv.querySelectorAll('.ind-blk').forEach(function(b){
    indBlks.push(Math.round(parseFloat(getComputedStyle(b).marginLeft)));
  });
  pv.querySelectorAll('.pblk').forEach(function(pb){
    pb.querySelectorAll('p').forEach(function(el){
      var t=(el.textContent||'');
      if(t.indexOf('正文模式')===0&&pX===null)pX=firstCharX(el);
    });
    pb.querySelectorAll('ol>li').forEach(function(el){
      if((el.textContent||'').indexOf('第一项')===0&&li1X===null)li1X=liBoxX(el);
    });
    pb.querySelectorAll('ul>li').forEach(function(el){
      if((el.textContent||'').indexOf('再进一层')===0&&plusX===null)plusX=liBoxX(el);
    });
  });
  var ol=pv.querySelector('ol');
  return {pX:pX,li1X:li1X,plusX:plusX,blks:indBlks,
    pFont:getComputedStyle(pv.querySelector('p')).fontSize,
    liFont:ol?getComputedStyle(ol.querySelector('li')).fontSize:null,
    liMl:ol?getComputedStyle(ol).marginLeft:null};
}"""

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
        # 等渲染收敛到本文档（默认文档"使用指南"分块渲染残留会混入旧 p，
        # 曾把"正文模式"量到 475px 的深嵌套示例段上——DOC 全文恰 1 个 p）
        pg.wait_for_function(
            "()=>document.querySelectorAll('#preview p').length===1",
            timeout=15000)
        pg.wait_for_timeout(600)

        r = pg.evaluate(MEASURE)
        check("场景成立：正文字号≠列表字号（em 双尺条件）",
              r["pFont"] != r["liFont"],
              "p=%s li=%s" % (r["pFont"], r["liFont"]))
        check("列表档 px 基准=正文字号（2×18.67=37.33px）",
              r["liMl"] == "37.33px", "ml=%s" % r["liMl"])
        check("「1.」与「正」x 对齐（±1px）",
              r["pX"] is not None and r["li1X"] is not None
              and abs(r["pX"] - r["li1X"]) <= 1,
              "正=%s 1.=%s" % (r["pX"], r["li1X"]))
        check("<<< 阶梯边界 0/0/37.33px（px 域叠加）",
              r["blks"] == [0, 0, 37], str(r["blks"]))
        # 第三层：pv 内边距 32 + 块边界 37 + ul 档 37.33 ≈ 106.67
        check("第三层「+」= 块边界+档（≈107px）",
              r["plusX"] is not None and abs(r["plusX"] - 107) <= 2,
              "+=%s" % r["plusX"])

        # --- 导出 HTML：ts-style px 绝对值随导出，无 em 漂移 ---
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": html_path})))
        with pg.expect_response("**/api/export-html**", timeout=60000) as ri:
            pg.click("#btnExportHtml")
        rj = ri.value.json()
        check("HTML 导出 ok", rj.get("ok") is True)
        htm = open(html_path, encoding="utf-8").read()
        check("导出 HTML 缩进档为 px（37.33px）", "37.33px" in htm)
        check("导出 HTML 无 em 档位残留", "margin-left:2em" not in htm
              and "text-indent:2em" not in htm)
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