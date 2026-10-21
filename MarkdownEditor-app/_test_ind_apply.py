# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""排版面板缩进档应用/回读 UI 验证（playwright，真实服务）：
回归 v2.0.x「列表/引用选整体缩进，应用后重开面板回到无」——
根因：tsApply 收集守卫白名单缺 'block'，被兜底吃成 'none'。
断言：
- 应用后重开面板，列表/引用下拉仍为「整体缩进」（block）
- localStorage tsCfg.indent.li/quote.mode==='block'
- 预览 ol/ul 计算样式 margin-left=2em / padding-left=0px / inside
- window.__IND_EM__.li===2（解析器继承链桥接值）
端口 18766 有服务则复用（html 每请求读盘，必为新 JS），无则进程内起。"""
import sys
import os
import socket
import threading
import time

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

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:18766/?file=")
    pg.wait_for_timeout(700)

    # 干净基线：清排版配置后刷新
    pg.evaluate("localStorage.removeItem('md-editor-typeset-v3')")
    pg.reload()
    pg.wait_for_timeout(700)

    def sel_ind(key, val):
        pg.select_option('select[data-ind="%s"]' % key, val)
        pg.fill('input[data-indchars="%s"]' % key, "2")

    # 1. 打开排版面板，列表/引用选「整体缩进」，应用
    pg.click("#btnTypeset")
    pg.wait_for_timeout(200)
    sel_ind("li", "block")
    sel_ind("quote", "block")
    pg.click("#tsApply")
    pg.wait_for_timeout(400)

    # 2. 存储层断言
    raw_ls = pg.evaluate("localStorage.getItem('md-editor-typeset-v3')")
    st = pg.evaluate(
        "JSON.parse(localStorage.getItem('md-editor-typeset-v3')||'{}')")
    li_m = (st.get("indent") or {}).get("li", {}).get("mode")
    q_m = (st.get("indent") or {}).get("quote", {}).get("mode")
    check("应用后 localStorage li.mode=block", li_m == "block",
          "raw=%s" % (raw_ls or "NULL"))
    check("应用后 localStorage quote.mode=block", q_m == "block", str(q_m))
    check("应用阶段无页面异常", not errors, "; ".join(errors[:2]))

    # 3. 重开面板回读
    pg.click("#btnTypeset")
    pg.wait_for_timeout(200)
    li_v = pg.eval_on_selector('select[data-ind="li"]', "e=>e.value")
    q_v = pg.eval_on_selector('select[data-ind="quote"]', "e=>e.value")
    li_c = pg.eval_on_selector('input[data-indchars="li"]', "e=>e.value")
    check("重开面板列表下拉仍为 block", li_v == "block", str(li_v))
    check("重开面板引用下拉仍为 block", q_v == "block", str(q_v))
    check("重开面板列表字符数仍为 2", li_c == "2", str(li_c))

    # 4. 渲染层断言：关面板，输入列表，量计算样式
    pg.click("#tsClose")
    pg.wait_for_timeout(200)
    pg.click("#editor")
    pg.keyboard.type("1. a")
    pg.keyboard.press("Enter")
    pg.keyboard.type("2. b")
    pg.wait_for_timeout(900)
    cs = pg.evaluate(
        "(()=>{const o=document.querySelector('#preview ol')||"
        "document.querySelector('.markdown-body ol');"
        "if(!o)return null;const s=getComputedStyle(o);"
        "const fs=parseFloat(getComputedStyle(o.closest('#preview')||o.parentElement).fontSize);"
        "return {ml:s.marginLeft,pad:s.paddingLeft,pos:s.listStylePosition,fs:fs};"
        "})()")
    want_ml = str(cs["fs"] * 2) + "px"
    check("ol margin-left=2em(按容器字号 %s)" % want_ml,
          cs and cs["ml"] == want_ml,
          "got=%s" % cs["ml"])
    check("ol padding-left=0px", cs and cs["pad"] == "0px", str(cs))
    check("ol list-style-position=inside",
          cs and cs["pos"] == "inside", str(cs))

    iem = pg.evaluate("window.__IND_EM__")
    check("__IND_EM__.li===2", iem and iem.get("li") == 2, str(iem))
    check("__IND_EM__.quote===2", iem and iem.get("quote") == 2, str(iem))

    check("no page errors", not errors, "; ".join(errors[:2]))
    b.close()

if httpd:
    httpd.shutdown()

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)
