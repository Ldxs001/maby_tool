# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""low runner v2.5 四特性全链路测试（playwright + 便携 python 服务）：
1. 三运行模式（立即/等待N秒/手动）：等待模式 N 秒内不跑、超时跑；
   手动模式不自动跑 + 执行点显示"待运行+▶"
2. 手动单点 ▶：点击执行点按钮只跑该点；左下角"全部运行"跑全部
3. 失败跟随错误块（红色，替代 title）：不存在的 run / 缺包
4. lr 界面：模式设置持久化（localStorage）；保存后依赖提醒
   （缺包红色 + 安装命令）；导出剥离按钮/错误/待运行态
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
with open(os.path.join(RUNS, "模式测试.py"), "w", encoding="utf-8") as f:
    f.write("def run(data):\n    return str(len(data['raw']))+' 项'\n")
with open(os.path.join(RUNS, "缺包测试.py"), "w", encoding="utf-8") as f:
    f.write("import numpy_zzz_not_exist\ndef run(data):\n    return 'x'\n")
with open(os.path.join(RUNS, "numpy依赖.py"), "w", encoding="utf-8") as f:
    f.write("import numpy\ndef run(data):\n    return 'x'\n")

DOC = ("@@ MDE_{a == 1}\n\n"
       "值：@@ MDE import 模式测试。\n\n"
       "坏：@@ MDE import 不存在的run。\n")

SET_MODE = """(c)=>{
  localStorage.setItem('md-editor-run-mode',
    JSON.stringify({mode:c.mode,waitSec:c.waitSec||5}));
}"""

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(900)

        # ── 1. 等待模式（2 秒）：1.2s 时未跑、2.6s 后跑 ──
        pg.evaluate(SET_MODE, {"mode": "wait", "waitSec": 2})
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_timeout(1200)
        d1 = pg.evaluate(
            "()=>{var r=document.querySelector('.mde-run:not([data-done])');"
            "return !!r && !r.hasAttribute('data-done');}")
        check("等待模式：2 秒内不执行", d1)
        pg.wait_for_timeout(2500)
        d2 = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return Array.from(rs).map(function(e){"
            "return e.getAttribute('data-done')||'-';});}")
        check("等待模式：2 秒后自动执行", "1" in d2, str(d2))

        # ── 2. 手动模式：不自动跑 + 待运行态 + ▶ ──
        #    v2.7 起渲染收尾会按缓存重放已跑过的执行点（"改别处 = 白跑一次"
        #    的修法）。runCache 是内存态，重载页面即清空——不重载的话，上一
        #    阶段在等待模式下跑出的结果会被重放回来，"全部待运行"不再成立。
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(900)
        pg.evaluate(SET_MODE, {"mode": "manual", "waitSec": 2})
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC + "\n尾。")
        pg.wait_for_timeout(3000)
        st = pg.evaluate("""()=>{var rs=document.querySelectorAll('.mde-run');
          var out=[];
          rs.forEach(function(e){out.push({done:e.getAttribute('data-done')||'-',
            html:e.innerHTML.substring(0,60),
            hasBtn:!!e.querySelector('.mde-run-btn'),
            hasPend:!!e.querySelector('.mde-run-pending')});});
          return {runs:out,
            runAllBtn:!document.getElementById('btnRunAll').hidden};}""")
        check("手动模式：3 秒后仍未自动执行",
              all(r["done"] == "-" for r in st["runs"]), str(st["runs"])[:120])
        check("手动模式：执行点显示待运行+▶ 按钮",
              all(r["hasBtn"] and r["hasPend"] for r in st["runs"]),
              str(st["runs"])[:120])
        check("手动模式：全部运行按钮显示（融入状态栏）",
              st["runAllBtn"] and pg.evaluate(
                  "()=>!!document.querySelector('#status #btnRunAll')"))

        # ── 单点 ▶：只跑第一个执行点 ──
        pg.evaluate("()=>{document.querySelectorAll('.mde-run')[0]"
                    ".querySelector('.mde-run-btn').click();}")
        pg.wait_for_timeout(2000)
        s1 = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return Array.from(rs).map(function(e){"
            "return {done:e.getAttribute('data-done')||'-',"
            "txt:e.textContent.substring(0,20)};});}")
        check("单点 ▶：仅首个执行点运行（第二点仍待运行）",
              s1[0]["done"] == "1" and "1 项" in s1[0]["txt"]
              and s1[1]["done"] == "-", str(s1))

        # ── 全部运行按钮 ──
        pg.evaluate("()=>{document.getElementById('btnRunAll').click();}")
        pg.wait_for_timeout(3000)
        s2 = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return Array.from(rs).map(function(e){"
            "return e.getAttribute('data-done')||'-';});}")
        check("全部运行：所有执行点完成（含失败态 err）",
              all(v != "-" for v in s2), str(s2))

        # ── 用户场景复现（v2.5.1）：执行点已跑完（立即模式遗留），再切
        #    手动 → 全部重置为待运行（▶ 重现）；全部运行链式不卡死
        #    （此前的第一个执行点已 done → 缓存命中 → 链断 → 永远运行中） ──
        pg.evaluate(SET_MODE, {"mode": "instant", "waitSec": 2})
        pg.wait_for_timeout(2500)
        done_now = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return Array.from(rs).every(function(e){"
            "return e.hasAttribute('data-done');});}")
        check("复现前提：立即模式已跑完全部", done_now)
        pg.evaluate("(c)=>{localStorage.setItem('md-editor-run-mode',"
                    "JSON.stringify({mode:c.mode,waitSec:c.waitSec}));"
                    "document.getElementById('btnRun').click();"
                    "setTimeout(function(){"
                    "document.getElementById('lrModeManual').click();},300);}",
                    {"mode": "instant", "waitSec": 2})
        pg.wait_for_timeout(1500)
        rset = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return Array.from(rs).map(function(e){"
            "return {done:e.getAttribute('data-done')||'-',"
            "hasBtn:!!e.querySelector('.mde-run-btn')};});}")
        check("切手动：已 done 执行点也重置为待运行（▶ 重现）",
              all(r["done"] == "-" and r["hasBtn"] for r in rset),
              str(rset)[:120])
        # 全部运行（缓存命中链）：按钮必须回到可用态（不卡"运行中"）
        pg.evaluate("()=>{document.getElementById('btnRunAll').click();}")
        pg.wait_for_timeout(3000)
        btnst = pg.evaluate(
            "()=>{var b=document.getElementById('btnRunAll');"
            "return {dis:b.disabled,txt:b.textContent};}")
        check("全部运行：缓存命中链完成、按钮恢复（不卡死）",
              not btnst["dis"] and btnst["txt"] == "▶ 运行", str(btnst))

        # ── 3. 跟随错误块 ──
        err = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "var r=rs[rs.length-1];"
            "return {txt:r.textContent.substring(0,50),"
            "hasErr:!!r.querySelector('.mde-run-err'),"
            "hasBtn:!!r.querySelector('.mde-run-btn'),"
            "title:r.title};}")
        check("失败跟随错误块（红色文字，非 title）",
              err["hasErr"] and "不存在的run" in err["txt"]
              and not err["title"], str(err))

        # ── 4. lr 界面：模式持久化 + 依赖提醒 ──
        pg.evaluate("()=>{document.getElementById('btnRun').click();}")
        pg.wait_for_timeout(600)
        mode = pg.evaluate(
            "()=>({cur:document.querySelector('.lr-mode-seg .lr-btn.cur')"
            ".id, secDisabled:document.getElementById('lrModeWaitSec')"
            ".disabled,"
            " sec:document.getElementById('lrModeWaitSec').value})")
        check("lr 界面：手动模式选中（读 localStorage）",
              mode["cur"] == "lrModeManual" and mode["secDisabled"],
              str(mode))
        # 切等待模式：waitRow 显示、秒数框出现
        pg.evaluate("()=>{document.getElementById('lrModeWait').click();}")
        pg.wait_for_timeout(300)
        mode2 = pg.evaluate(
            "()=>({cur:document.querySelector('.lr-mode-seg .lr-btn.cur').id,"
            "secDisabled:document.getElementById('lrModeWaitSec').disabled,"
            "sec:document.getElementById('lrModeWaitSec').value})")
        check("lr 界面：切等待模式 N 秒输入可用（持久 2）",
              mode2["cur"] == "lrModeWait" and not mode2["secDisabled"]
              and mode2["sec"] == "2", str(mode2))
        # 保存缺包 run → 依赖提醒（numpy 未装红色 + 命令）
        pg.evaluate(
            "(c)=>{document.getElementById('lrName').value='numpy依赖';"
            "document.getElementById('lrCode').value=c;"
            "document.getElementById('lrSave').click();}",
            "import numpy\ndef run(data):\n    return 'x'")
        pg.wait_for_timeout(2500)
        deps = pg.evaluate(
            "()=>{var d=document.getElementById('lrDeps');"
            "return {hidden:d.hidden, txt:d.textContent.substring(0,150),"
            "hasCmd:!!d.querySelector('code'),"
            "cmd:d.querySelector('code')?d.querySelector('code')"
            ".textContent:''};}")
        check("保存后依赖提醒：缺 numpy 红色+安装命令",
              not deps["hidden"] and "numpy" in deps["txt"]
              and deps["hasCmd"] and "--target" in deps["cmd"],
              str(deps)[:160])
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()

    # ── 5. 服务端：缺包错误带 missing（/api/run） ──
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/run" % PORT,
        data=json.dumps({"mod": "缺包测试", "fn": "run",
                         "data": {"kv": {}, "raw": []}}).encode(),
        headers={"Content-Type": "application/json"})
    rj = json.loads(urllib.request.urlopen(req, timeout=30).read())
    check("/api/run 缺包错误带 missing（模块名+pip 名+命令）",
          rj.get("missing", {}).get("module") == "numpy_zzz_not_exist"
          and "pip install" in rj.get("missing", {}).get("cmd", ""),
          str(rj.get("missing"))[:120])

    # ── 6. 导出关口（v2.5.2 定案 D）+ 剥离兜底 ──
    # 手动模式未运行 → 拦截（无导出请求）；有失败也拦；全成功放行
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(900)
        pg.evaluate(SET_MODE, {"mode": "manual", "waitSec": 2})
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_timeout(1200)
        html_path = os.path.join(HERE, "_tmp_mode.html")
        reqs = []

        def count_exp(route):
            reqs.append(1)
            route.continue_()

        pg.route("**/api/export-html*", count_exp)
        pg.route("**/api/pick-save*",
                 lambda route: route.fulfill(
                     content_type="application/json",
                     body=json.dumps({"ok": True, "path": html_path})))

        # 6a. 未运行 → 拦截：无导出请求、无文件、toast 出现
        pg.click("#btnExportHtml")
        pg.wait_for_timeout(1500)
        toast1 = pg.evaluate(
            "()=>{var t=document.getElementById('mdToast');"
            "return t?t.textContent:'';}")
        check("导出关口：未运行拦截（无请求/无文件/带指引 toast）",
              len(reqs) == 0 and not os.path.exists(html_path)
              and "无法导出" in toast1 and "未运行" in toast1,
              "reqs=%d toast=%s" % (len(reqs), toast1[:60]))

        # 6b. 全部运行（含 1 个失败）→ 仍拦截（错误不得静默导出）
        pg.evaluate("()=>{document.getElementById('btnRunAll').click();}")
        pg.wait_for_timeout(4000)
        pg.click("#btnExportHtml")
        pg.wait_for_timeout(1500)
        toast2 = pg.evaluate(
            "()=>{var t=document.getElementById('mdToast');"
            "return t?t.textContent:'';}")
        check("导出关口：有失败仍拦截（防静默导出错误）",
              len(reqs) == 0 and "运行失败" in toast2,
              "reqs=%d toast=%s" % (len(reqs), toast2[:60]))

        # 6c. 删掉坏执行点行 → 全部成功 → 放行 + 剥离兜底
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}",
            "@@ MDE_{a == 1}\n\n值：@@ MDE import 模式测试。\n")
        pg.wait_for_timeout(800)
        pg.evaluate("()=>{document.getElementById('btnRunAll').click();}")
        pg.wait_for_timeout(4000)
        done_all = pg.evaluate(
            "()=>{var rs=document.querySelectorAll('.mde-run');"
            "return rs.length===1&&rs[0].getAttribute('data-done')==='1';}")
        check("修好后全部成功（放行前提）", done_all)
        with pg.expect_response("**/api/export-html**", timeout=60000):
            pg.click("#btnExportHtml")
        pg.wait_for_timeout(400)
        check("导出关口：全部成功放行", len(reqs) == 1, "reqs=%d" % len(reqs))
        b.close()
        htm = open(html_path, encoding="utf-8").read()
        if os.path.exists(html_path):
            os.remove(html_path)
    check("导出剥离兜底：▶ 按钮/错误块/待运行占位不进 HTML",
          "mde-run-btn" not in htm and "mde-run-err" not in htm
          and "待运行" not in htm)
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    for f in ("模式测试", "缺包测试", "numpy依赖"):
        pth = os.path.join(RUNS, f + ".py")
        if os.path.exists(pth):
            os.remove(pth)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)