# -*- coding: utf-8 -*-
"""v2.32.0 探针：预览栏关参考线时，full 块是否应裁到版心。

只读验证，不改任何产物。做法：
  1) 在编辑器里放一份带 full 背景的文档；
  2) 量 full 块 / #preview / #previewPane 的几何与溢出；
  3) 注入候选 CSS（#preview{overflow-x:clip}），量注入后；
  4) 各截一张图，供目视。
"""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
OUT = os.path.abspath("Temp")
IMG = "docs/MDEditor 实操手册.assets/20261103_010158_8502.png"

DOC = """@@ begin full{m:![](%s) f cc} color w
# 封面
@@ end full color

## 第一章

正文。

```python
print("x")
```
""" % IMG


def geo(pg):
    return pg.evaluate(r"""() => {
      const R = e => { const r = e.getBoundingClientRect();
        return {l: Math.round(r.left), r: Math.round(r.right),
                w: Math.round(r.width), h: Math.round(r.height)}; };
      const pv = document.querySelector('#preview');
      const pane = document.querySelector('#previewPane');
      const fp = pv.querySelector('.full-page');
      return {
        pv: R(pv),
        fp: fp ? R(fp) : null,
        pane: R(pane),
        scroller: {scrollLeft: pane.scrollLeft, scrollWidth: pane.scrollWidth,
                   clientWidth: pane.clientWidth,
                   overflowX: getComputedStyle(pane).overflowX},
        pvStyle: {overflowX: getComputedStyle(pv).overflowX,
                  padding: getComputedStyle(pv).padding,
                  width: getComputedStyle(pv).width},
        img: (() => { const s = fp ? getComputedStyle(fp) : null;
          return s ? {bgSize: s.backgroundSize, bgPos: s.backgroundPosition} : null; })(),
        docScrollW: document.documentElement.scrollWidth
      };
    }""")


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 2300, "height": 1200})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    pg.click("#btnViewPreview") if pg.query_selector("#btnViewPreview") else None
    pg.wait_for_timeout(800)
    pg.evaluate("""(t) => { const e = document.getElementById('editor');
        e.value = t; e.dispatchEvent(new Event('input', {bubbles: true})); }""", DOC)
    pg.wait_for_timeout(2500)

    print("[A] 注入前（现状）")
    a = geo(pg)
    for k, v in a.items():
        print("   ", k, v)
    pg.screenshot(path=os.path.join(OUT, "_v232_before.png"))

    # 候选：只给 #preview 单轴 clip，不动任何 DOM、不动 pane
    pg.add_style_tag(content="#preview{overflow-x:clip !important;}")
    pg.wait_for_timeout(600)
    print("\n[B] 注入 #preview{overflow-x:clip} 后")
    c = geo(pg)
    for k, v in c.items():
        print("   ", k, v)
    pg.screenshot(path=os.path.join(OUT, "_v232_after.png"))

    # 直接量：版心区域里，full 图的可见左右边界是否正好落在 #preview 的左右沿
    print("\n[C] 裁切判定")
    if c["fp"] and c["pv"]:
        print("    full 块左右:", c["fp"]["l"], c["fp"]["r"], "宽", c["fp"]["w"])
        print("    版心左右  :", c["pv"]["l"], c["pv"]["r"], "宽", c["pv"]["w"])
        print("    full 块比版心宽出:", c["fp"]["w"] - c["pv"]["w"], "px（左右各约",
              round((c["fp"]["w"] - c["pv"]["w"]) / 2), "px = 页边距）")
    print("    pane 溢出:", c["scroller"]["scrollWidth"], "vs", c["scroller"]["clientWidth"])

    b.close()
print("\n截图:", os.path.join(OUT, "_v232_before.png"), "/", os.path.join(OUT, "_v232_after.png"))
