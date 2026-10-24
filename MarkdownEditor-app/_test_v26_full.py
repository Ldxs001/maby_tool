# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""v2.6 全链路测试（playwright + 便携 python 服务）：
1. 三通道类型级断言：拦 /api/run 请求体——kv 真 dict、vals 真
   list/嵌套 list（六形式逐项）
2. global 执行点：'''p 标记收集进 marks、run 返回等长列表替换、
   数量不符走失败路径、缓存与重跑复位
3. 表格型数据点显示摘要
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

RUNS = os.path.join(HERE, "runtime", "runs")
os.makedirs(RUNS, exist_ok=True)
# 三通道回显 run：把收到的 data 各通道类型+内容原样返回
with open(os.path.join(RUNS, "通道回显.py"), "w", encoding="utf-8") as f:
    f.write(
        "def run(data):\n"
        "    kv = data['kv']\n"
        "    vals = data['vals']\n"
        "    parts = ['kv=' + str(type(kv).__name__) + str(sorted(kv.keys())),\n"
        "             'vals=' + str(type(vals).__name__) + str(vals)]\n"
        "    return '; '.join(parts)\n")
# global 序号 run：返回等长上标列表
with open(os.path.join(RUNS, "序号.py"), "w", encoding="utf-8") as f:
    f.write(
        "def run(data):\n"
        "    ms = data.get('marks', [])\n"
        "    return ['^{[' + str(i + 1) + ']}' for i in range(len(ms))]\n")
# 数量不符 run：固定返回 2 项
with open(os.path.join(RUNS, "数量错.py"), "w", encoding="utf-8") as f:
    f.write(
        "def run(data):\n"
        "    return ['a', 'b', 'c', 'd', 'e']\n")

TRI = "'''"
DOC = ("@@ MDE_{苹果 == 3}\n"
       "@@ MDE_{8%,1.5%,0.6%}\n"
       "@@ MDE_{A == 8%, B == 1.5%}\n"
       "@@ MDE_{今天买了苹果}\n"
       "@@ MDE_{2025年，我国GDP总体上涨((7%))，同比上涨((1.2%))}\n"
       "@@ MDE_:2(2x2){\n"
       "|职务|名称|年龄|\n"
       "|:-|:-|:-|\n"
       "|总经理|tony|59|\n"
       "|秘书|lily|18|\n"
       "}\n\n"
       "回显：@@ MDE import 通道回显。\n\n"
       "全局：@@ MDE import 序号{global p}\n\n"
       "台风" + TRI + "p 出现，扰动" + TRI + "p 结束。\n")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        bodies = []

        def cap(route):
            bodies.append(json.loads(route.request.post_data))
            route.continue_()

        pg.route("**/api/run*", cap)
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(900)
        # 本机可能持久化了 manual 模式（v2.5.3 服务端上云）——测试用 instant
        pg.evaluate("()=>{localStorage.setItem('md-editor-run-mode',"
                    "JSON.stringify({mode:'instant',waitSec:5}));}")
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        # 等两个执行点完成
        pg.wait_for_function(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return rs.length===2&&Array.prototype.every.call(rs,"
            "function(e){return e.hasAttribute('data-done');})}",
            timeout=30000)
        pg.wait_for_timeout(600)

        # ── 1. 三通道类型级断言（拦请求体） ──
        run_bodies = [bd for bd in bodies if "通道回显" in str(bd.get("mod"))]
        check("拦截到通道回显请求", len(run_bodies) >= 1,
              "n=%d mods=%s" % (len(bodies),
                                [bd.get("mod") for bd in bodies]))
        if run_bodies:
            d = run_bodies[0]["data"]
            kv, vals = d["kv"], d["vals"]
            check("kv 是 dict（含键值向量合并）",
                  isinstance(kv, dict)
                  and kv == {"苹果": "3", "A": "8%", "B": "1.5%"}, str(kv))
            check("vals 含 str（单值）",
                  any(isinstance(v, str) and v == "今天买了苹果"
                      for v in vals))
            check("vals 含 list（纯值向量）",
                  any(isinstance(v, list) and v == ["8%", "1.5%", "0.6%"]
                      for v in vals))
            # 行文抽取值
            check("vals 含行文抽取向量",
                  any(isinstance(v, list) and v == ["7%", "1.2%"]
                      for v in vals))
            # 表格嵌套
            check("vals 含二维嵌套 list（表格）",
                  any(isinstance(v, list) and v
                      and isinstance(v[0], list)
                      and v == [["tony", "59"], ["lily", "18"]]
                      for v in vals),
                  str(vals)[:150])
            check("raw 原文逃生舱（数据点原文列表）",
                  isinstance(d.get("raw"), list)
                  and any("苹果 == 3" in r for r in d["raw"]))

        # ── 2. global 执行点 ──
        g_bodies = [bd for bd in bodies if bd.get("mod") == "序号"]
        check("global 请求带 marks（2 个 p 标记）",
              g_bodies and len(g_bodies[0]["data"].get("marks", [])) == 2
              and g_bodies[0]["data"]["marks"][0]["mark"] == "p",
              str(g_bodies[0]["data"].get("marks"))[:80] if g_bodies else "-")
        mk = pg.evaluate(
            "()=>Array.from(document.querySelectorAll('.mde-mark'))"
            ".map(function(m){return m.textContent;})")
        check("标记替换为 ^{[1]} ^{[2]}",
              mk == ["^{[1]}", "^{[2]}"], str(mk))
        # ctx 含句子
        if g_bodies:
            ctx = g_bodies[0]["data"]["marks"][0]["ctx"]
            check("marks ctx 含所在句", "台风" in ctx, ctx[:40])
        # 执行点自身不可见
        gv = pg.evaluate(
            "()=>{var g=document.querySelector('.mde-run-global');"
            "return g?getComputedStyle(g).display:'(无)';}")
        check("global 执行点成功后不可见", gv == "none", gv)

        # ── 3. 数量不符 → 失败路径 ──
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}",
            DOC.replace("import 序号{global p}", "import 数量错{global p}"))
        pg.wait_for_timeout(2500)
        gfail = pg.evaluate(
            "()=>{var g=document.querySelector('.mde-run-global');"
            "return {done:g?g.getAttribute('data-done'):'-',"
            "disp:g?getComputedStyle(g).display:'-',"
            "err:g?!!g.querySelector('.mde-run-err'):false,"
            "txt:g?g.textContent.substring(0,60):''};}")
        check("数量不符走失败路径（红字可见）",
              gfail["done"] == "err" and gfail["disp"] != "none"
              and gfail["err"] and "≠" in gfail["txt"], str(gfail))
        mk2 = pg.evaluate(
            "()=>Array.from(document.querySelectorAll('.mde-mark'))"
            ".map(function(m){return m.textContent;})")
        check("失败时标记保持原文",
              mk2 == [TRI + "p", TRI + "p"], str(mk2))
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    for f in ("通道回显", "序号", "数量错"):
        pth = os.path.join(RUNS, f + ".py")
        if os.path.exists(pth):
            os.remove(pth)
    c = os.path.join(RUNS, "__pycache__")
    if os.path.isdir(c):
        shutil.rmtree(c, ignore_errors=True)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)