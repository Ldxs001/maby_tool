# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""编辑区查找替换 UI 真实浏览器验证（playwright，v2.11.1）：
- Ctrl+F/Ctrl+H 唤起浮层；Escape 关闭还焦点编辑器
- 输入即就近定位（从光标/当前命中起）：计数恒为 i/N，无"N 个结果"含糊态
- 光标就近定位：面板抢焦清选区的缺陷已修（快照光标），从光标处向后找
- 开关按钮 on 态有真实背景色反馈（v2.11.0 死 CSS 已修）
- Aa 大小写 / .* 正则 / \\b 全字三开关（含非法正则 fail-closed 提示）
- 单处替换进原生 undo 栈（Ctrl+Z 撤销）；全部替换整体一步写入
  （Ctrl+Z 一次还原全部）
- 替换值 \\n 展开、正则 $1 组引用
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

# 测试文档（各断言的命中数按此精确推演；偏移量含换行）
DOC = ("alpha Alpha ALPHA\n"        # 0-17   ci 命中: alpha@0 Alpha@6 ALPHA@12
       "alpha cat category cat\n"   # 18-40  alpha@18  cat@24 cat@28(catégory) cat@37
       "bob@test sue@test\n"        # 41-58
       "X Y X\n"                    # 59-64  y@62 y@64
       "alpha end\n")               # 65-74  alpha@65

SET_DOC = ("(function(){var e=document.getElementById('editor');"
           "e.textContent=%s;"
           "e.dispatchEvent(new Event('input',{bubbles:true}));})()")

# 把编辑器光标设到字符偏移 p（addRange 会让编辑器拿焦点，正是所需）
SET_CARET = ("(function(){var e=document.getElementById('editor'),"
             "n=e.firstChild,r=document.createRange(),s=window.getSelection();"
             "r.setStart(n,%d);r.setEnd(n,%d);s.removeAllRanges();s.addRange(r);"
             "return window.getSelection().anchorOffset;})")


def txt(pg):
    return pg.evaluate("document.getElementById('editor').textContent")


def clear_opts(pg):
    # 双清：服务端 ui-settings + 页面 localStorage（恢复走 localStorage，
    # 只清服务端会被上轮残留的开关状态污染本轮全部计数推演）
    pg.evaluate("try{localStorage.removeItem('md-editor-find-opts')}catch(e){};"
                "fetch('/api/ui-settings',{method:'POST',"
                "headers:{'Content-Type':'application/json'},"
                "body:JSON.stringify({'md-editor-find-opts':null})})")
    pg.reload()          # 重载使页面以干净开关态重新读取
    pg.wait_for_timeout(700)


def cnt(pg):
    return pg.inner_text("#fbCount")


def set_caret(pg, pos):
    got = pg.evaluate(SET_CARET % (pos, pos))
    assert got == pos, "caret set failed: %r != %d" % (got, pos)


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

    # ── 计数与导航（光标在文档头：输入即定位第 1 处）──
    pg.fill("#fbFind", "alpha")
    pg.wait_for_timeout(350)
    check("输入即定位 1/5", cnt(pg) == "1/5", cnt(pg))
    check("当前命中经 Highlight 高亮", pg.evaluate(
        "Array.from(CSS.highlights.get('fb-cur'),function(r){return r.toString();})") == ["alpha"],
        pg.evaluate("Array.from(CSS.highlights.get('fb-cur'),function(r){return r.toString();})"))
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(100)
    check("Enter 到 2/5", cnt(pg) == "2/5", cnt(pg))
    for _ in range(3):
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(60)
    check("连按到第 5 处 5/5", cnt(pg) == "5/5", cnt(pg))
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(100)
    check("文末循环回 1/5", cnt(pg) == "1/5", cnt(pg))
    check("循环提示语", pg.inner_text("#fbMsg") == "已到文末，从头继续",
          pg.inner_text("#fbMsg"))
    pg.keyboard.press("Shift+Enter")
    pg.wait_for_timeout(100)
    check("Shift+Enter 回退到 5/5", cnt(pg) == "5/5", cnt(pg))

    # ── 光标就近定位（v2.11.1：唤起抢焦清选区导致永远从头找，已修）──
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)
    set_caret(pg, 5)  # 第 1 个 alpha 之后：就近应命中文档第 2 处 Alpha@6
    pg.keyboard.press("Control+f")   # 查询词仍在输入框
    pg.wait_for_timeout(350)
    check("重开面板就近定位 2/5", cnt(pg) == "2/5", cnt(pg))
    check("就近命中的是 Alpha（非文档头 alpha）", pg.evaluate(
        "Array.from(CSS.highlights.get('fb-cur'),function(r){return r.toString();})") == ["Alpha"])
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(100)
    check("就近后 Enter 顺延 3/5", cnt(pg) == "3/5", cnt(pg))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)

    # ── 开关按钮 on 态真实视觉反馈（v2.11.1：死 CSS 已修）+ Aa 计数 ──
    pg.keyboard.press("Control+h")   # 后续要填替换值，直接开带替换行的面板
    pg.wait_for_timeout(350)
    check("再开定位 1/5", cnt(pg) == "1/5", cnt(pg))
    bg0 = pg.evaluate("getComputedStyle(document.getElementById('fbCase')).backgroundColor")
    pg.click("#fbCase")
    pg.wait_for_timeout(350)
    bg1 = pg.evaluate("getComputedStyle(document.getElementById('fbCase')).backgroundColor")
    check("Aa 点击后 class=on", pg.evaluate(
        "document.getElementById('fbCase').classList.contains('on')"))
    check("Aa on 态背景色真实变化", bg0 != bg1, "%s -> %s" % (bg0, bg1))
    check("Aa 开启后从当前命中就近 1/3", cnt(pg) == "1/3", cnt(pg))
    pg.click("#fbCase")
    pg.wait_for_timeout(350)
    check("Aa 关回 1/5", cnt(pg) == "1/5", cnt(pg))

    # ── 全字匹配（就近基准恒为开面板光标，改查询/切开关不漂移）──
    pg.fill("#fbFind", "cat")        # anchor=文档头 → cat@24
    pg.wait_for_timeout(350)
    check("cat 含 category 子串 3 命中 1/3", cnt(pg) == "1/3", cnt(pg))
    pg.click("#fbWord")              # 基准不变 → \\b 后仍 cat@24
    pg.wait_for_timeout(350)
    check("\\b 开启后就近 1/2", cnt(pg) == "1/2", cnt(pg))
    pg.click("#fbWord")              # 关回
    pg.wait_for_timeout(350)
    check("\\b 关回 1/3", cnt(pg) == "1/3", cnt(pg))

    # ── 正则模式 ──
    pg.click("#fbRe")                # 基准不变 → 1/3
    pg.wait_for_timeout(350)
    check("正则就近 1/3", cnt(pg) == "1/3", cnt(pg))
    pg.fill("#fbFind", "c[")
    pg.wait_for_timeout(350)
    check("非法正则计 无结果", cnt(pg) == "无结果", cnt(pg))
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

    # ── 单处替换：进原生 undo 栈（Aa 此刻关：ci 5 命中）──
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)
    set_caret(pg, 0)
    pg.keyboard.press("Control+h")   # 单处替换需要替换行
    pg.wait_for_timeout(150)
    pg.fill("#fbFind", "alpha")      # anchor=0 → 1/5
    pg.fill("#fbRepl", "BETA")
    pg.wait_for_timeout(350)
    check("定位第 1 处 1/5", cnt(pg) == "1/5", cnt(pg))
    pg.click("#fbRepOne")
    pg.wait_for_timeout(250)
    t = txt(pg)
    check("单处替换只改当前命中", t.startswith("BETA Alpha ALPHA\nalpha"),
          repr(t[:40]))
    check("替换后自动跳下一处 1/4", cnt(pg) == "1/4", cnt(pg))
    pg.evaluate("document.getElementById('editor').focus()")
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(200)
    check("单处替换 Ctrl+Z 撤销", txt(pg).startswith("alpha Alpha"))
    pg.click("#fbClose")
    pg.wait_for_timeout(100)

    # ── 滚动跟随（v2.11.1：点「下一个」视图跳回顶部的缺陷已修）──
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)
    pg.evaluate(SET_DOC % json.dumps(
        "target one\n" + "".join("filler %d\n" % i for i in range(60))
        + "target two\n" + "".join("stuff %d\n" % i for i in range(60))
        + "target three\n"))
    pg.wait_for_timeout(200)
    set_caret(pg, 0)
    pg.keyboard.press("Control+f")
    pg.wait_for_timeout(150)
    pg.fill("#fbFind", "target")
    pg.wait_for_timeout(350)
    st0 = pg.evaluate("document.getElementById('editor').scrollTop")
    pg.evaluate("document.getElementById('editor').scrollTop=2500")
    pg.wait_for_timeout(100)
    pg.click("#fbNext")
    pg.wait_for_timeout(300)
    st1 = pg.evaluate("document.getElementById('editor').scrollTop")
    check("滚动后点下一个视图跟随命中（不跳回顶部）", st1 > 800,
          "before=%s after=%s" % (2500, st1))
    check("跟随的是第 2 处命中", cnt(pg) == "2/3", cnt(pg))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)

    # ── 查找词转义语义（v2.11.1：非正则一律字面量，特殊字符只有正则这一条通道）──
    # 文档 4 行 → 4 个真实换行；字面反斜杠n 2 处
    NL_DOC = "code \\n lit\nhas \\n two\nalpha\nbeta\n"
    pg.evaluate(SET_DOC % json.dumps(NL_DOC))
    pg.wait_for_timeout(200)
    set_caret(pg, 0)
    pg.keyboard.press("Control+f")
    pg.wait_for_timeout(150)
    if pg.evaluate("document.getElementById('fbRe').classList.contains('on')"):
        pg.click("#fbRe")           # 前文可能留着 .* 开，先归一到关闭
        pg.wait_for_timeout(250)
    pg.fill("#fbFind", "\\n")       # 非正则：\n = 字面反斜杠n（2 处）
    pg.wait_for_timeout(350)
    check("非正则 \\n 搜字面量 1/2", cnt(pg) == "1/2", cnt(pg))
    pg.click("#fbRe")               # 开正则
    pg.wait_for_timeout(350)
    check("正则 \\n 搜换行符 1/4", cnt(pg) == "1/4", cnt(pg))
    pg.fill("#fbFind", "a\\n")      # 正则跨行锚定：alpha\\n、beta\\n → 2 处
    pg.wait_for_timeout(350)
    check("正则 a\\n 跨行锚定 1/2", cnt(pg) == "1/2", cnt(pg))
    pg.click("#fbRe")               # 关回非正则
    pg.wait_for_timeout(350)
    pg.fill("#fbFind", "\\n")
    pg.wait_for_timeout(350)
    check("关正则后回到字面 1/2", cnt(pg) == "1/2", cnt(pg))

    # ── ⇄ 展开/收起替换行（v2.11.1：.fb-row 的 display:flex 曾盖掉 [hidden]）──
    check("Ctrl+F 起手替换行收起", not pg.is_visible("#fbRepRow"))
    pg.click("#fbRepTgl")
    pg.wait_for_timeout(150)
    check("⇄ 展开替换行", pg.is_visible("#fbRepRow"))
    check("⇄ 展开时常亮", pg.evaluate(
        "document.getElementById('fbRepTgl').classList.contains('on')"))
    pg.click("#fbRepTgl")
    pg.wait_for_timeout(150)
    check("⇄ 再点收起", not pg.is_visible("#fbRepRow"))
    check("⇄ 收起后熄灭", not pg.evaluate(
        "document.getElementById('fbRepTgl').classList.contains('on')"))
    pg.keyboard.press("Escape")
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

    # ── 开关持久化：把 Aa 和 .* 点亮，刷新后应保持 on ──
    pg.keyboard.press("Control+f")
    pg.wait_for_timeout(100)
    if not pg.evaluate("document.getElementById('fbCase').classList.contains('on')"):
        pg.click("#fbCase")
    if not pg.evaluate("document.getElementById('fbRe').classList.contains('on')"):
        pg.click("#fbRe")
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
