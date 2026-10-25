# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""编辑区查找替换 UI 真实浏览器验证（playwright，v2.11.0）：
- Ctrl+F/Ctrl+H 唤起浮层；Escape 关闭还焦点编辑器
- 计数（n 个结果 / i/n / 无结果）、Enter 顺序导航、文末循环提示
- Aa 大小写 / .* 正则 / \b 全字三开关（含非法正则 fail-closed 提示）
- 单处替换进原生 undo 栈（Ctrl+Z 撤销）；全部替换整体一步写入
  （全文一次 insertText，Ctrl+Z 一次还原全部）
- 替换值 \n 展开、正则 $1 组引用
- 开关状态经 md-editor-find-opts 上服务端 ui-settings，刷新后仍在
端口 18766 有服务则复用（html 每请求读盘，必为新 JS），无则进程内起。"""
import json
import threading
import time
import sys
import os
import socket

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(name, cond, detail=""):
    print("%-46s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def port_in_use():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", 18766)) == 0
    finally:
        s.close()


httpd = None
if not port_in_use():
    sys.argv = ["md_server.py"]
    import md_server
    httpd = md_server.ReuseTCPServer(("127.0.0.1", 18766),
                                     md_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

from playwright.sync_api import sync_playwright  # noqa: E402

# 测试文档（各断言的命中数按此精确推演）
DOC = ("alpha Alpha ALPHA\n"
       "alpha cat category cat\n"
       "bob@test sue@test\n"
       "X Y X\n"
       "alpha end\n")

SET_DOC = ("(function(){var e=document.getElementById('editor');"
           "e.textContent=%s;"
           "e.dispatchEvent(new Event('input',{bubbles:true}));})()")


def txt(pg):
    return pg.evaluate("document.getElementById('editor').textContent")


def clear_opts(pg):
    pg.evaluate("fetch('/api/ui-settings',{method:'POST',"
                "headers:{'Content-Type':'application/json'},"
                "body:JSON.stringify({'md-editor-find-opts':null})})")


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:18766/?file=")
    pg.wait_for_timeout(700)
    clear_opts(pg)  # 防上轮残留影响初态
    pg.evaluate(SET_DOC % json.dumps(DOC))
    pg.wait_for_timeout(200)

    # ── 唤起与焦点 ──
    pg.keyboard.press("Control+f")
    pg.wait_for_timeout(150)
    check("Ctrl+F 唤起浮层", pg.evaluate("!document.getElementById('findBar').hidden"))
    check("焦点落查找输入框", pg.evaluate(
        "document.activeElement&&document.activeElement.id==='fbFind'"))

    # ── 计数与导航 ──
    pg.fill("#fbFind", "alpha")
    pg.wait_for_timeout(350)
    check("输入即计数（大小写关 5 命中）", pg.inner_text("#fbCount") == "5 个结果",
          pg.inner_text("#fbCount"))
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(100)
    check("Enter 选中第 1 处 1/5", pg.inner_text("#fbCount") == "1/5",
          pg.inner_text("#fbCount"))
    check("当前命中经 Highlight 高亮", pg.evaluate(
        "Array.from(CSS.highlights.get('fb-cur'),function(r){return r.toString();})") == ["alpha"],
        pg.evaluate("Array.from(CSS.highlights.get('fb-cur'),function(r){return r.toString();})"))
    for _ in range(4):
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(60)
    check("连按到第 5 处 5/5", pg.inner_text("#fbCount") == "5/5",
          pg.inner_text("#fbCount"))
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(100)
    check("文末循环回 1/5", pg.inner_text("#fbCount") == "1/5",
          pg.inner_text("#fbCount"))
    check("循环提示语", pg.inner_text("#fbMsg") == "已到文末，从头继续",
          pg.inner_text("#fbMsg"))
    pg.keyboard.press("Shift+Enter")
    pg.wait_for_timeout(100)
    check("Shift+Enter 回退到 5/5", pg.inner_text("#fbCount") == "5/5",
          pg.inner_text("#fbCount"))

    # ── 大小写开关 ──
    pg.click("#fbCase")
    pg.wait_for_timeout(350)
    check("Aa 开启后 3 命中", pg.inner_text("#fbCount") == "3 个结果",
          pg.inner_text("#fbCount"))
    check("Aa 按钮高亮", pg.evaluate("document.getElementById('fbCase').classList.contains('on')"))

    # ── 全字匹配 ──
    pg.fill("#fbFind", "cat")
    pg.wait_for_timeout(350)
    check("cat 含 category 子串 3 命中", pg.inner_text("#fbCount") == "3 个结果",
          pg.inner_text("#fbCount"))
    pg.click("#fbWord")
    pg.wait_for_timeout(350)
    check("\\b 开启后 2 命中", pg.inner_text("#fbCount") == "2 个结果",
          pg.inner_text("#fbCount"))
    pg.click("#fbWord")  # 关回

    # ── 正则模式 ──
    pg.click("#fbRe")
    pg.wait_for_timeout(150)
    pg.fill("#fbFind", "c[a-z]+")
    pg.wait_for_timeout(350)
    check("正则 3 命中", pg.inner_text("#fbCount") == "3 个结果",
          pg.inner_text("#fbCount"))
    pg.fill("#fbFind", "c[")
    pg.wait_for_timeout(350)
    check("非法正则计 无结果", pg.inner_text("#fbCount") == "无结果",
          pg.inner_text("#fbCount"))
    check("非法正则 fail-closed 提示", pg.inner_text("#fbMsg") == "正则表达式无效",
          pg.inner_text("#fbMsg"))

    # ── 全部替换：正则 $1 引用 + 一步撤销 ──
    pg.fill("#fbFind", "(\\w+)@test")
    pg.fill("#fbRepl", "$1-ok")
    pg.wait_for_timeout(250)
    pg.click("#fbRepAll")
    pg.wait_for_timeout(300)
    t = txt(pg)
    check("全部替换 $1 组引用", "bob-ok sue-ok" in t and "@test" not in t, repr(t[40:120]))
    pg.evaluate("document.getElementById('editor').focus()")
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(200)
    check("全部替换 Ctrl+Z 一步还原", txt(pg) == DOC)

    # ── 替换值 \n 展开 ──
    pg.fill("#fbFind", "Y")
    pg.fill("#fbRepl", "\\n")
    pg.wait_for_timeout(250)
    pg.click("#fbRepAll")
    pg.wait_for_timeout(300)
    t = txt(pg)
    check("替换值 \\n 展开为换行", "X \n X" in t, repr(t.split("\n")[3:6]))
    pg.evaluate("document.getElementById('editor').focus()")
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(200)
    check("\\n 替换同样一步撤销", txt(pg) == DOC)

    # ── 单处替换：进原生 undo 栈 ──
    pg.fill("#fbFind", "alpha")
    pg.fill("#fbRepl", "BETA")
    pg.wait_for_timeout(350)
    pg.keyboard.press("Enter")   # 定位第 1 处
    pg.wait_for_timeout(100)
    check("定位后 1/3", pg.inner_text("#fbCount") == "1/3", pg.inner_text("#fbCount"))
    pg.click("#fbRepOne")
    pg.wait_for_timeout(250)
    t = txt(pg)
    check("单处替换只改当前命中", t.startswith("BETA Alpha ALPHA\nalpha"),
          repr(t[:40]))
    check("替换后自动跳下一处 1/2", pg.inner_text("#fbCount") == "1/2",
          pg.inner_text("#fbCount"))
    pg.evaluate("document.getElementById('editor').focus()")
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(200)
    check("单处替换 Ctrl+Z 撤销", txt(pg).startswith("alpha Alpha"))
    pg.click("#fbClose")
    pg.wait_for_timeout(100)

    # ── 关闭还焦点 / Ctrl+H ──
    check("Escape 外的 × 关闭浮层", pg.evaluate("document.getElementById('findBar').hidden"))
    pg.keyboard.press("Control+h")
    pg.wait_for_timeout(150)
    check("Ctrl+H 唤起且替换行展开", pg.evaluate(
        "!document.getElementById('findBar').hidden && !document.getElementById('fbRepRow').hidden"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)
    check("Escape 关闭浮层", pg.evaluate("document.getElementById('findBar').hidden"))
    check("关闭后焦点还编辑器", pg.evaluate(
        "document.activeElement&&document.activeElement.id==='editor'"))

    # ── 开关持久化：Aa/.* 此刻均已 on（前文各点过一次），刷新后仍应 on ──
    pg.keyboard.press("Control+f")
    pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)  # 等 lsSet 300ms 节流 POST 上云
    pg.reload()
    pg.wait_for_timeout(700)
    pg.keyboard.press("Control+f")
    pg.wait_for_timeout(200)
    check("刷新后 Aa 状态保持", pg.evaluate(
        "document.getElementById('fbCase').classList.contains('on')"))
    check("刷新后 .* 状态保持", pg.evaluate(
        "document.getElementById('fbRe').classList.contains('on')"))

    # ── 页面无 JS 错误 ──
    check("无页面错误", not errors, "; ".join(errors[:3]))

    clear_opts(pg)  # 清理测试键，不污染用户 ui-settings
    b.close()

if httpd is not None:
    httpd.shutdown()
    httpd.server_close()

print("FIND-REPLACE " + ("ALL PASS" if not fails else "FAILED: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
