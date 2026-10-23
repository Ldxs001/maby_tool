# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""low runner UI 全链路测试（playwright + 便携 python 服务）：
1. 数据点渲染：@@ MDE_{a == 3} 显示 3；@@ MDE__{...} 隐性不显示
2. 执行点：@@ MDE import 名字 → run 结果替换（中文 run 名）
3. from 形式：@@ MDE from 文件 import 函数
4. 缓存：内容不变二次渲染不重调（服务调用计数）
5. fail-closed：不存在的 run 显示执行点原文
6. 管理界面：列表加载、保存入库（保存后重跑）
跑前杀遗留服务。"""
import json
import os
import shutil
import subprocess
import sys
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

# 自建测试 run（不依赖外部库状态）
os.makedirs(os.path.join(HERE, "runtime", "runs"), exist_ok=True)
with open(os.path.join(HERE, "runtime", "runs", "水果统计.py"),
          "w", encoding="utf-8") as f:
    f.write("def run(data):\n"
            "    kv = data[\"kv\"]\n"
            "    a = int(kv.get(\"苹果\", \"0\"))\n"
            "    b = int(kv.get(\"梨\", \"0\"))\n"
            "    return \"%d 个水果\" % (a + b)\n\n"
            "def 单独合并(data):\n"
            "    return \"；\".join(data[\"raw\"])\n")

DOC = ("我今天买了苹果 @@ MDE_{苹果 == 3} 个，\n"
       "买了梨 @@ MDE_{梨 == 2} 个。\n"
       "@@ MDE__{备注 == 隐性数据不显示}\n\n"
       "我买了 @@ MDE import 水果统计 个水果。\n\n"
       "合并：@@ MDE from 水果统计 import 单独合并。\n\n"
       "坏的：@@ MDE import 不存在的run。\n")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        calls = []

        def count_run(route):
            calls.append(1)
            route.continue_()

        pg.route("**/api/run*", count_run)
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(900)
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        # 等执行点全部完成（3 个执行点：2 成功 1 fail-closed）
        pg.wait_for_function(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return rs.length===3&&Array.prototype.every.call(rs,"
            "function(e){return e.hasAttribute('data-done');})}",
            timeout=30000)
        pg.wait_for_timeout(500)

        r = pg.evaluate("""()=>{
          var out={dps:[],runs:[]};
          document.querySelectorAll('#preview .mde-dp').forEach(function(d){
            out.dps.push({cls:d.className,txt:d.textContent,
              hidden:getComputedStyle(d).display==='none'});
          });
          document.querySelectorAll('#preview .mde-run').forEach(function(e){
            out.runs.push({txt:e.textContent,done:e.getAttribute('data-done')});
          });
          return out;
        }""")
        dpx = {d["txt"]: d for d in r["dps"]}
        check("数据点显性：{苹果 == 3} 显示 3",
              "3" in dpx and not dpx["3"]["hidden"], str(list(dpx.keys())))
        check("数据点显性：{梨 == 2} 显示 2",
              "2" in dpx and not dpx["2"]["hidden"], str(list(dpx.keys())))
        # 隐性：span 自身 display:none 不渲染；其内容进 raw 可被 run 用
        # （from 合并的执行点结果里出现"备注 == 隐性数据不显示"是设计内行为）
        check("数据点隐性：span 不渲染（display:none）",
              sum(1 for d in r["dps"] if d["hidden"]) == 1,
              "hidden=%d" % sum(1 for d in r["dps"] if d["hidden"]))
        hid_txt = pg.evaluate(
            "()=>{var h=document.querySelector('.mde-dp-hidden');"
            "return h?h.textContent:'(无)';}")
        check("隐性 span 内容为空（不显示值）", hid_txt == "",
              repr(hid_txt))
        rtxt = [x["txt"] for x in r["runs"]]
        check("执行点 import 替换：5 个水果",
              any("5 个水果" in t for t in rtxt), str(rtxt))
        check("执行点 from 替换（合并 raw，含隐性数据点）",
              any("苹果 == 3；梨 == 2" in t
                  and "隐性数据不显示" in t for t in rtxt), str(rtxt))
        check("fail-closed：不存在的 run 显示原文",
              any("不存在的run" in t for t in rtxt), str(rtxt))
        check("no page errors", not errors, "; ".join(errors[:2]))

        # 缓存：追加纯文本触发重渲（数据点不变），不应新增 /api/run 调用
        n1 = len(calls)
        pg.evaluate(
            "()=>{var ed=document.getElementById('editor');"
            "ed.textContent=ed.textContent+'\\n\\n尾段。';"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}")
        pg.wait_for_timeout(2500)
        n2 = len(calls)
        check("缓存：数据不变不重跑（%d→%d 次调用）" % (n1, n2),
              n2 == n1, "calls=%d" % n2)

        # 管理界面：列表 + 保存
        pg.evaluate("()=>{document.getElementById('btnRun').click();}")
        pg.wait_for_timeout(600)
        items = pg.evaluate(
            "()=>Array.from(document.querySelectorAll('#lrList .lr-item'))"
            ".map(function(d){return d.textContent.replace('删','').trim();})")
        check("管理界面列表含中文 run", "水果统计" in items, str(items))
        pg.evaluate("""()=>{
          document.getElementById('lrNew').click();
          document.getElementById('lrName').value='链路测试';
          document.getElementById('lrCode').value=
            'def run(data):\\n    return str(len(data[\"raw\"]))+\" 个数据点\"';
          document.getElementById('lrSave').click();
        }""")
        pg.wait_for_timeout(800)
        items2 = pg.evaluate(
            "()=>Array.from(document.querySelectorAll('#lrList .lr-item'))"
            ".map(function(d){return d.textContent.replace('删','').trim();})")
        check("保存入库成功（列表新增 链路测试）",
              "链路测试" in items2, str(items2))
        check("no page errors（终）", not errors, "; ".join(errors[:2]))
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    for f in ("链路测试", "水果统计"):
        p = os.path.join(HERE, "runtime", "runs", f + ".py")
        if os.path.exists(p):
            os.remove(p)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)