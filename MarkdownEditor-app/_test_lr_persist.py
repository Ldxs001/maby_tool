# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""run 模式跨重启持久化测试（v2.5.3）：
A. 页面切模式 → lsSet 双通道 → 服务端 /api/ui-settings 落 md-editor-run-mode
B. 全新浏览器上下文（localStorage 空，模拟关程序重开）→ 启动恢复
   _uiRemoteGetAll 写回 → runModeCfg=manual + 面板 UI 还原
C. 迁移：服务端无键 + 本地旧值 → 启动后补上云
"""
import json
import os
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


def ui_get():
    return json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/api/ui-settings" % PORT, timeout=5).read())


def ui_seed(k, v):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/ui-settings" % PORT,
        data=json.dumps({k: v}).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # ── A. 切模式 → 双通道上云 ──
        ctx = p.chromium.launch().new_context()
        pg = ctx.new_page()
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(1000)
        pg.evaluate(
            "()=>{document.getElementById('btnRun').click();"
            "setTimeout(function(){"
            "document.getElementById('lrModeManual').click();},200);}")
        pg.wait_for_timeout(1500)   # 300ms 防抖 + 网络
        ui = ui_get()
        saved = (ui.get("data") or {}).get("md-editor-run-mode")
        check("A. 切手动 → 服务端落 md-editor-run-mode",
              saved and json.loads(saved).get("mode") == "manual",
              str(saved)[:80])
        ctx.close()

        # ── B. 全新上下文（localStorage 空 = 关程序重开）→ 服务端恢复 ──
        ctx2 = p.chromium.launch().new_context()
        pg2 = ctx2.new_page()
        pg2.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg2.wait_for_timeout(1200)
        r2 = pg2.evaluate("""()=>{
          var cur=document.querySelector('.lr-mode-seg .lr-btn.cur');
          var raw=localStorage.getItem('md-editor-run-mode');
          var btn=document.getElementById('btnRunAll');
          return {modeRaw:raw, uiCur:cur?cur.id:'-',
                  runAllVisible:!btn.hidden};
        }""")
        check("B. 重开后模式恢复 manual（localStorage 回写）",
              r2["modeRaw"] and json.loads(r2["modeRaw"]).get("mode") == "manual",
              str(r2["modeRaw"])[:60])
        check("B. 面板 UI 选中手动", r2["uiCur"] == "lrModeManual", r2["uiCur"])
        check("B. 状态栏运行按钮按 manual 显示", r2["runAllVisible"])
        ctx2.close()

        # ── C. 迁移：清掉服务端键 + 预置本地旧值 → 启动补上云 ──
        ui_seed("md-editor-run-mode", None)   # 删除服务端键
        ctx3 = p.chromium.launch().new_context()
        pg3 = ctx3.new_page()
        # 先开一次页面写本地旧值，再刷新触发迁移？迁移在启动时执行——
        # 直接预置：goto 后先 set，再 reload（reload = 二次启动）
        pg3.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg3.wait_for_timeout(900)
        pg3.evaluate("()=>localStorage.setItem('md-editor-run-mode',"
                     "JSON.stringify({mode:'wait',waitSec:9}))")
        pg3.reload()
        pg3.wait_for_timeout(1200)
        ui3 = ui_get()
        m3 = (ui3.get("data") or {}).get("md-editor-run-mode")
        check("C. 迁移：本地旧值补上云（wait/9s）",
              m3 and json.loads(m3).get("mode") == "wait"
              and json.loads(m3).get("waitSec") == 9, str(m3)[:60])
        # 清理：恢复 instant，避免污染本机真实配置
        pg3.evaluate(
            "()=>{document.getElementById('btnRun').click();"
            "setTimeout(function(){"
            "document.getElementById('lrModeInstant').click();},200);}")
        pg3.wait_for_timeout(1200)
        ctx3.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)