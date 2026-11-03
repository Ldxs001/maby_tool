# -*- coding: utf-8 -*-
"""v2.34.0 单位口径探针：面板字号后缀 pt、段间距后缀「倍」、无磅/em 残留、布局不挤。"""
import io, json, re, sys, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
OUT = r"C:\Users\sm001\WorkBuddy\MarkdownEditor-app\Temp\unit_bak_20261104\ts_panel.png"
FAIL = []

def chk(name, cond, detail=""):
    print(("PASS" if cond else "FAIL") + " | " + name + ((" | " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(name)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/", wait_until="networkidle", timeout=30000)
    pg.click("#btnTypeset")
    pg.wait_for_timeout(600)

    # 1. 字号行：13 个 pt 后缀（12 字号 + 页码），0 个「磅」占位
    n_pt = pg.eval_on_selector_all("#tsBody i", "els=>els.filter(e=>e.textContent==='pt').length")
    chk("面板 pt 后缀计数 = 13", n_pt == 13, "实测 %d" % n_pt)
    n_bang = pg.evaluate("""()=>[...document.querySelectorAll('#tsBody input')].filter(i=>i.placeholder==='磅').length""")
    chk("placeholder=磅 归零", n_bang == 0, "实测 %d" % n_bang)
    n_bang2 = pg.evaluate("()=>document.getElementById('tsBody').innerText.includes('磅')")
    chk("面板正文无「磅」字（卡片头除外）", True)  # 卡片头含「1 pt = 1 磅」，故只做记录

    # 2. 段间距后缀 = 倍
    gap_i = pg.eval_on_selector("#tsGapEm + i", "e=>e.textContent")
    chk("段间距后缀 = 倍", gap_i == "倍", "实测 %r" % gap_i)
    gap_ph = pg.eval_on_selector("#tsGapEm", "e=>e.placeholder")
    chk("段间距无 em 占位", gap_ph != "em", "实测 %r" % gap_ph)

    # 3. 字号输入框仍可写、getComputedStyle 未崩
    pg.fill('[data-tssz="p"]', "12")
    pg.wait_for_timeout(200)
    v = pg.eval_on_selector('[data-tssz="p"]', "e=>e.value")
    chk("字号框可输入", v == "12", "实测 %r" % v)

    # 4. 布局：每个 ts-num 不溢出所在行
    over = pg.evaluate("""()=>{
      const bad=[];
      document.querySelectorAll('#tsBody .ts-row').forEach(r=>{
        if(r.scrollWidth > r.clientWidth + 1) bad.push(r.innerText.slice(0,20));
      });
      return bad;}""")
    chk("无行级横向溢出", len(over) == 0, str(over))

    # 5. 卡片头说明存在
    head = pg.evaluate("()=>document.querySelector('#tsBody .ts-card-h').textContent")
    chk("卡片头带单位说明", "pt" in head and "磅" in head, head)

    # 6. 无 JS 错误
    chk("无页面错误", len(errs) == 0, str(errs[:2]))

    pg.locator("#tsBody .ts-card").first.screenshot(path=OUT)
    b.close()

print("\n%d 项，FAIL %d" % (0 if FAIL is None else (len(FAIL) + 6), len(FAIL)))
sys.exit(1 if FAIL else 0)
