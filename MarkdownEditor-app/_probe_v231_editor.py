# -*- coding: utf-8 -*-
"""编辑器侧验收：
   1) 预览栏左右对称（full 块不再向左被切）
   2) 点「打印」→ 预览栏不动、无覆盖层、隐藏 iframe 拿到产物
"""
import json, os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
OUT = os.path.abspath(os.path.dirname(__file__))

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 950})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)

    geo = pg.evaluate("""() => {
      const q = s => document.querySelector(s);
      const pane = q('#previewPane'), pv = q('#preview');
      const cs = getComputedStyle(pane);
      const fp = pv.querySelector('.full-page');
      const r = el => { const b = el.getBoundingClientRect();
                        return {l: Math.round(b.left), r: Math.round(b.right),
                                w: Math.round(b.width)}; };
      return {
        pane: r(pane),
        padL: Math.round(parseFloat(cs.paddingLeft)),
        padR: Math.round(parseFloat(cs.paddingRight)),
        pv: r(pv),
        fp: fp ? r(fp) : null,
        overflowX: cs.overflowX,
        pagedWrap: !!q('#pagedWrap'),
        framePos: (() => { const f = q('#pagedFrame');
                           const s = getComputedStyle(f);
                           return {position: s.position, left: s.left,
                                   w: s.width, h: s.height}; })(),
      };
    }""")
    print("几何:", json.dumps(geo, ensure_ascii=False, indent=2))

    ok_sym = (geo["padL"] == geo["padR"] and geo["padL"] > 0)
    print("P1 左右 padding 对称:", "PASS" if ok_sym else "FAIL")

    if geo["fp"]:
        # 完整纸宽 = 版心宽 + 左右边距，两侧超出量应等于各自边距
        overL = geo["pv"]["l"] - geo["fp"]["l"]
        overR = geo["fp"]["r"] - geo["pv"]["r"]
        print("full 块左伸出 %dpx / 右伸出 %dpx（边距 18mm≈68px）" % (overL, overR))
        clipped = geo["fp"]["l"] < geo["pane"]["l"] - 2
        print("P2 左侧是否被 pane 边界切掉:", "FAIL(被切)" if clipped else "PASS")

    # 点打印
    pg.click("#btnExportPaged")
    pg.wait_for_timeout(3500)
    after = pg.evaluate("""() => {
      const f = document.querySelector('#pagedFrame');
      return {
        src: f ? f.getAttribute('src') : null,
        previewVisible: getComputedStyle(document.querySelector('#preview')).display,
        overlay: !!document.querySelector('#pagedWrap'),
        err: window.__lastErr || null,
      };
    }""")
    print("点打印后:", json.dumps(after, ensure_ascii=False))
    print("P3 预览栏未被接管:", "PASS" if after["previewVisible"] != "none"
          and not after["overlay"] else "FAIL")
    print("P4 打印通道已装载产物:", "PASS" if after["src"] and ".html" in after["src"]
          else "FAIL")
    print("JS 错误:", errs if errs else "无")
    b.close()
