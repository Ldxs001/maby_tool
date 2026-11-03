# -*- coding: utf-8 -*-
"""v2.34.0 i18n 探针：英文界面下面板单位标注全部为英文/同形符号，无中文残留。"""
import re, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
SHOT = r"C:\Users\sm001\WorkBuddy\MarkdownEditor-app\Temp\unit_bak_20261104\ts_en.png"
FAIL = []

def chk(name, cond, detail=""):
    print(("PASS" if cond else "FAIL") + " | " + name + ((" | " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(name)

HAN = re.compile(r"[\u4e00-\u9fff]")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 1100})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/", wait_until="networkidle", timeout=30000)
    pg.click("#btnLang")            # 中文 → English
    pg.wait_for_timeout(500)
    pg.click("#btnTypeset")
    pg.wait_for_timeout(600)

    # 1. 字体卡片头（新增条目）
    head = pg.evaluate("()=>document.querySelector('#tsBody .ts-card-h').textContent")
    chk("卡片头英文", not HAN.search(head), head)

    # 2. 字号框 placeholder = auto
    ph = pg.eval_on_selector('[data-tssz="p"]', "e=>e.placeholder")
    chk("字号 placeholder 英文", not HAN.search(ph), repr(ph))

    # 3. 段间距后缀 = ×（不是「倍」）
    gap = pg.eval_on_selector("#tsGapEm + i", "e=>e.textContent")
    chk("段间距后缀英文", gap == "×", repr(gap))

    # 4. 面板内所有 <i> 单位后缀无中文
    units = pg.evaluate("()=>[...document.querySelectorAll('#tsBody i')].map(e=>e.textContent)")
    bad = [u for u in units if HAN.search(u)]
    chk("<i> 单位后缀无中文", len(bad) == 0, str(bad))

    # 5. 面板内可见文本无中文残留（整块扫描，报出前几个）
    #    白名单：编号样式的英文条目故意保留中文示例（"Chinese  一、 1."），
    #    那是演示该样式长什么样，不是漏译。
    txt = pg.evaluate("()=>document.getElementById('tsBody').innerText")
    left = [ln.strip() for ln in txt.splitlines()
            if HAN.search(ln) and "Chinese" not in ln]
    chk("面板无中文残留", len(left) == 0, " | ".join(left[:4]))

    # 6. 无 JS 错误
    chk("无页面错误", len(errs) == 0, str(errs[:2]))

    pg.locator("#tsPanel").screenshot(path=SHOT)
    b.close()

print("\nFAIL %d" % len(FAIL))
sys.exit(1 if FAIL else 0)
