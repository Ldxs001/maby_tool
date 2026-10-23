# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""别名隔离 UI 全链路测试（v2.4.5，playwright + 便携 python 服务）：
同一 run 两处调用 is 甲/is 乙 各喂各的；无 is 吃公共池；
run 协议不变（收到的还是 {kv, raw}，只是内容按别名过滤）。
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
# 同一 run：求和（喂哪个桶就加哪个桶的数）
with open(os.path.join(RUNS, "别名求和.py"), "w", encoding="utf-8") as f:
    f.write("def run(data):\n"
            "    nums = [int(v) for v in data['kv'].values()]\n"
            "    return str(sum(nums))\n")

DOC = ("@@ MDE_甲{x == 10}\n"
       "@@ MDE_乙{y == 20}\n"
       "@@ MDE_{z == 1}\n"
       "@@ MDE__甲{w == 100}\n\n"
       "甲：@@ MDE import 别名求和 is 甲。\n\n"
       "乙：@@ MDE from 别名求和 import run is 乙。\n\n"
       "公共：@@ MDE import 别名求和。\n")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(900)
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_function(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return rs.length===3&&Array.prototype.every.call(rs,"
            "function(e){return e.hasAttribute('data-done');})}",
            timeout=30000)
        pg.wait_for_timeout(400)
        txts = pg.evaluate(
            "()=>Array.from(document.querySelectorAll('.mde-run'))"
            ".map(function(e){return e.textContent;})")
        # 甲池 kv={x:10,w:100}→110；乙池 {y:20}→20；公共池 {z:1}→1
        check("is 甲：只吃甲池（x10+w100=110）", "110" in txts[0], str(txts))
        check("is 乙：只吃乙池（y20=20）", "20" in txts[1], str(txts))
        check("无 is：只吃公共池（z1=1）", "1" in txts[2], str(txts))
        check("隔离：甲不见乙数据（110≠30）", "30" not in txts[0], str(txts))
        # 数据点渲染照旧
        dps = pg.evaluate(
            "()=>Array.from(document.querySelectorAll('.mde-dp'))"
            ".map(function(d){return {t:d.textContent,"
            "h:d.className.indexOf('hidden')>=0,"
            "a:d.getAttribute('data-dp-alias')};})")
        vis = [d["t"] for d in dps if not d["h"]]
        check("显性别名数据点显示值（10/20/1）",
              all(v in vis for v in ("10", "20", "1")), str(vis))
        check("隐性别名数据点不显示",
              sum(1 for d in dps if d["h"]) == 1)
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    p = os.path.join(RUNS, "别名求和.py")
    if os.path.exists(p):
        os.remove(p)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)