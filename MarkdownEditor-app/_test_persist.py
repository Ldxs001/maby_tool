# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""UI 状态服务端持久化 + 排版即时重渲验证（playwright，真实服务）：
背景：WebView2 内嵌窗口下 localStorage 只活在内存（关窗即丢，leveldb 零增长
实锤），持久化单一来源迁移至服务端 runtime/ui-settings.json。
断言：
1. 应用设置后（节流 flush）服务端文件出现对应键值
2. 全新 context（LS 空=模拟关窗）重开：恢复引导把配置回放 LS，面板/渲染一致
3. render(force)：改排版应用后不碰编辑器，ind-blk 内联 margin 即时更新
端口 18766 有服务则复用（html/py 每请求读盘），无则进程内起。"""
import json
import sys
import os
import socket
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SET_PATH = os.path.join(HERE, "runtime", "ui-settings.json")

fails = []


def check(name, cond, detail=""):
    print("%-50s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


PORT = 18767  # 独立端口：不复用 18766（可能被用户旧版服务占用，绝不误杀）


def port_in_use():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


httpd = None
if not port_in_use():
    sys.argv = ["md_server.py"]
    import md_server
    httpd = md_server.ReuseTCPServer(("127.0.0.1", PORT),
                                     md_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

BASE = "http://127.0.0.1:%d" % PORT
TS_KEY = "md-editor-typeset-v3"

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    # ---------- 会话 1：设置、应用、断言服务端落盘 ----------
    ctx = p.chromium.launch()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:18767/?file=")
    pg.wait_for_timeout(700)
    # 干净基线：清 LS 与服务端文件（服务端经由页面 API 删键不可行，直接删文件）
    pg.evaluate("localStorage.clear()")
    if os.path.exists(SET_PATH):
        os.remove(SET_PATH)
    pg.reload()
    pg.wait_for_timeout(700)

    # 输入含 <<< 包围块的文档（供 render(force) 即时性断言）
    pg.click("#editor")
    pg.keyboard.type("有如下几种形式：")
    pg.keyboard.press("Enter")
    pg.keyboard.type("<<<")
    pg.keyboard.press("Enter")
    pg.keyboard.type("1. 第一项")
    pg.keyboard.press("Enter")
    pg.keyboard.type("<<<")
    pg.wait_for_timeout(900)

    pg.click("#btnTypeset")
    pg.wait_for_timeout(200)
    pg.select_option('select[data-ind="p"]', "first")
    pg.fill('input[data-indchars="p"]', "2")
    pg.select_option('select[data-ind="li"]', "block")
    pg.fill('input[data-indchars="li"]', "2")
    pg.fill('input[data-tssz="p"]', "14")
    pg.check("#tsThree")
    pg.fill("#tsMt", "30")
    pg.click("#tsApply")
    pg.wait_for_timeout(600)   # > 节流 300ms，flush 必已触发

    def read_settings():
        try:
            with open(SET_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    st = read_settings()
    check("应用后服务端 ui-settings.json 有 TS 键", TS_KEY in st,
          "keys=%s" % (sorted(st.keys())[:6],))
    if TS_KEY in st:
        cfg = json.loads(st[TS_KEY])
        check("服务端 TS: li=block/2 & p 字号 14",
              cfg.get("indent", {}).get("li", {}).get("mode") == "block"
              and cfg.get("fonts", {}).get("p", {}).get("s") == 14,
              str(cfg.get("indent", {}).get("li"))
              + "/" + str(cfg.get("fonts", {}).get("p", {}).get("s")))
    check("会话1无页面异常", not errors, "; ".join(errors[:2]))

    # render(force) 即时性：p 档从 first/2 改为 none（或字符改 3），应用后
    # 不碰编辑器，ind-blk 内联 margin 即时随继承链更新
    def ind_blk_margin():
        return pg.evaluate(
            "(()=>{const d=document.querySelector('.ind-blk');"
            "return d?d.style.marginLeft:null;})()")
    m2 = ind_blk_margin()
    check("初设排版后 ind-blk margin 即时=2em", m2 == "2em", str(m2))
    pg.click("#btnTypeset")
    pg.wait_for_timeout(200)
    pg.fill('input[data-indchars="p"]', "3")
    pg.click("#tsApply")
    pg.wait_for_timeout(900)   # render 队列 + 节流
    m3 = ind_blk_margin()
    check("改排版后 ind-blk margin 即时 2em->3em（无需编辑操作）",
          m2 == "2em" and m3 == "3em", "%s -> %s" % (m2, m3))
    ctx.close()

    # ---------- 会话 2：全新 context（LS 空=模拟关窗），恢复引导回放 ----------
    ctx2 = p.chromium.launch()
    pg2 = ctx2.new_page()
    errors2 = []
    pg2.on("pageerror", lambda e: errors2.append(str(e)))
    pg2.goto("http://127.0.0.1:18767/?file=")
    pg2.wait_for_timeout(900)

    ls_ts = pg2.evaluate("localStorage.getItem('%s')" % TS_KEY)
    ok_ls = False
    if ls_ts:
        c2 = json.loads(ls_ts)
        ok_ls = (c2.get("indent", {}).get("li", {}).get("mode") == "block"
                 and c2.get("fonts", {}).get("p", {}).get("s") == 14)
    check("重开（LS 空）后恢复引导回放 TS 配置", ok_ls,
          (ls_ts or "NULL")[:80])

    pg2.click("#btnTypeset")
    pg2.wait_for_timeout(200)
    li_v = pg2.eval_on_selector('select[data-ind="li"]', "e=>e.value")
    fz_v = pg2.eval_on_selector('input[data-tssz="p"]', "e=>e.value")
    th_v = pg2.eval_on_selector("#tsThree", "e=>e.checked")
    mt_v = pg2.eval_on_selector("#tsMt", "e=>e.value")
    check("重开面板列表档回填 block", li_v == "block", str(li_v))
    check("重开面板字号回填 14", fz_v == "14", str(fz_v))
    check("重开面板三线表回填 on", th_v is True, str(th_v))
    check("重开面板页边距回填 30", mt_v == "30", str(mt_v))
    pg2.click("#tsClose")
    pg2.wait_for_timeout(200)

    # 渲染层：直接敲一个列表（不依赖默认指南的加载时序）
    pg2.click("#editor")
    pg2.keyboard.press("Control+a")
    pg2.keyboard.press("Delete")
    pg2.keyboard.type("1. a")
    pg2.wait_for_timeout(900)
    cs = pg2.evaluate(
        "(()=>{const o=document.querySelector('#preview ol')||"
        "document.querySelector('.markdown-body ol');"
        "if(!o)return null;const s=getComputedStyle(o);"
        "const fs=parseFloat(getComputedStyle(document.getElementById('preview')||o).fontSize);"
        "return {ml:s.marginLeft,pos:s.listStylePosition,fs:fs};"
        "})()")
    want_ml = str((cs["fs"] if cs else 15) * 2) + "px"
    check("重启后 ol margin=2em(容器字号)/inside",
          cs and cs["pos"] == "inside" and cs["ml"] == want_ml,
          str(cs))

    check("会话2无页面异常", not errors2, "; ".join(errors2[:2]))
    ctx2.close()

if httpd:
    httpd.shutdown()

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)
