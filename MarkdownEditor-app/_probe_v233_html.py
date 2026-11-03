# -*- coding: utf-8 -*-
"""导出 HTML 现状实测：长串表格 / 长代码行 / 长公式 在产物里是溢出还是滚动。

只读：产物写到 Temp/，不碰用户文档与设置。
"""
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
OUT = os.path.abspath("Temp")
U = "https://example.com/" + ("abcdefghij" * 22)
CODE = 'x = "' + ("A" * 220) + '"'

DOC = """## 长串表格

| 链接 | 备注 |
|---|---|
| %s | 说明 |

## 长代码

```python
%s
```

## 长公式

$$
%s
$$
""" % (U, CODE, " + ".join(["\\alpha_{%d}" % i for i in range(40)]))


def post(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1400, "height": 1000})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2000)
    pg.evaluate("""(t)=>{const e=document.getElementById('editor');
        e.textContent=t; e.dispatchEvent(new Event('input',{bubbles:true}));}""", DOC)
    pg.wait_for_timeout(3000)

    print("=" * 60)
    print("[预览] 版心与各元素宽度")
    print(pg.evaluate(r"""()=>{
      const pv=document.querySelector('#preview'); const core=pv.getBoundingClientRect().width;
      const o=[]; pv.querySelectorAll('table,pre,.md-math-block').forEach(e=>{
        const r=e.getBoundingClientRect();
        o.push({t:e.tagName, cls:e.className, w:Math.round(r.width), right:Math.round(r.right),
                sw:e.scrollWidth, cw:e.clientWidth, ox:getComputedStyle(e).overflowX});});
      return {core:Math.round(core), pvRight:Math.round(pv.getBoundingClientRect().right), o};}"""))

    body = pg.evaluate("()=>document.querySelector('#preview').innerHTML")
    ts = pg.evaluate("()=>(document.getElementById('ts-style')||{textContent:''}).textContent")
    dst = os.path.join(OUT, "_export_probe.html")
    r = post("/api/export-html", {"mdPath": None, "bodyHtml": body,
                                  "tsCss": ts, "page": {}, "path": dst})
    print("\n导出:", r.get("ok"), r.get("path"))

    pg2 = b.new_page(viewport={"width": 1400, "height": 1000})
    pg2.goto("file:///" + dst.replace("\\", "/"))
    pg2.wait_for_timeout(900)
    print("\n" + "=" * 60)
    print("[导出 HTML] body 与实际盒子")
    print(pg2.evaluate(r"""()=>{
      const bd=document.body, r=bd.getBoundingClientRect();
      const o=[]; bd.querySelectorAll('table,pre,.md-math-block').forEach(e=>{
        const q=e.getBoundingClientRect();
        o.push({t:e.tagName, cls:e.className, w:Math.round(q.width),
                left:Math.round(q.left), right:Math.round(q.right),
                sw:e.scrollWidth, cw:e.clientWidth, ox:getComputedStyle(e).overflowX});});
      return {bodyW:Math.round(r.width), bodyRight:Math.round(r.right),
              docSW:document.documentElement.scrollWidth,
              winW:window.innerWidth, o};}"""))
    pg2.screenshot(path=os.path.join(OUT, "_export_probe.png"), full_page=False)
    b.close()

print("\n截图:", os.path.join(OUT, "_export_probe.png"))
