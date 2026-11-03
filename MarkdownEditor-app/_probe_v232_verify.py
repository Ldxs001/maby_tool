# -*- coding: utf-8 -*-
"""v2.32.0 验收探针：full 裁到版心 / 表格不胀破 / 代码块折行 / 开参考线仍见整张纸。

只读。截图两张（关参考线、开参考线）。
"""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
OUT = os.path.abspath("Temp")
IMG = "C:/Users/sm001/WorkBuddy/MarkdownEditor-app/docs/MDEditor 使用指南.assets/20261103_010158_8502.png"
LONGURL = "https://example.com/" + ("abcdefghij" * 22)
LONGCODE = "x = '" + ("B" * 300) + "'"

DOC = """@@ begin full{m:![](%s) f cc} color w
# 封面
@@ end full color

## 甲 正文第一节

正文一句话。

## 乙 长 URL 表格

| 链接 | 备注 |
|---|---|
| %s | 说明 |

## 丙 长行代码

```python
%s
```
""" % (IMG, LONGURL, LONGCODE)

MEASURE = r"""() => {
  const pv = document.querySelector('#preview');
  const pane = document.querySelector('#previewPane');
  const R = e => { const r = e.getBoundingClientRect();
    return {l: Math.round(r.left), r: Math.round(r.right),
            w: Math.round(r.width), h: Math.round(r.height)}; };
  const fp = pv.querySelector('.full-page');
  const pre = pv.querySelector('pre');
  const tb = pv.querySelector('table');
  return {
    preview: R(pv),
    previewOverflowX: getComputedStyle(pv).overflowX,
    previewPadding: getComputedStyle(pv).padding,
    full: fp ? R(fp) : null,
    pane: R(pane),
    paneScroll: [pane.scrollWidth, pane.clientWidth],
    table: tb ? R(tb) : null,
    pre: pre ? {w: Math.round(pre.getBoundingClientRect().width),
                h: Math.round(pre.getBoundingClientRect().height),
                sw: pre.scrollWidth, cw: pre.clientWidth,
                ws: getComputedStyle(pre).whiteSpace,
                ow: getComputedStyle(pre).overflowWrap} : null,
    guideOn: !!document.querySelector('#preview').style.outline
  };
}"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 2000, "height": 1100})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    # 视图状态是持久化的，不能假设起点：点到 body 带 view-preview 为止
    for _ in range(3):
        if pg.evaluate("() => document.body.classList.contains('view-preview')"):
            break
        pg.click("#btnView")
        pg.wait_for_timeout(400)
    pg.wait_for_timeout(500)

    def set_guide(on):
        pg.click("#btnTypeset")
        pg.wait_for_timeout(450)
        if on:
            pg.check("#tsGuide")
        else:
            pg.uncheck("#tsGuide")
        pg.click("#tsApply")
        pg.wait_for_timeout(1000)
        pg.evaluate("() => { const o = document.getElementById('tsOverlay'); if (o) o.hidden = true; }")
        pg.wait_for_timeout(500)

    set_guide(False)
    pg.evaluate("""(t) => { const e = document.getElementById('editor');
        e.textContent = t; e.dispatchEvent(new Event('input', {bubbles: true})); }""", DOC)
    pg.wait_for_timeout(2800)

    print("=== A 关参考线 ===")
    a = pg.evaluate(MEASURE)
    for k, v in a.items():
        print("  ", k, v)
    pg.screenshot(path=os.path.join(OUT, "_v232_off.png"))

    set_guide(True)

    print("\n=== B 开参考线 ===")
    c = pg.evaluate(MEASURE)
    for k, v in c.items():
        print("  ", k, v)
    pg.screenshot(path=os.path.join(OUT, "_v232_on.png"))
    # 收尾：把参考线恢复成默认关，别把探针状态留在用户设置里
    set_guide(False)
    print("收尾：参考线已恢复为关")
    b.close()

print("\n截图:", os.path.join(OUT, "_v232_off.png"), os.path.join(OUT, "_v232_on.png"))
