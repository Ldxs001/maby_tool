# -*- coding: utf-8 -*-
"""v2.32.0 断词口径对比：anywhere vs break-word vs 不写。

只读。同一份文档换三种规则各渲染一次，量：
  1) 表格总宽（是否超版心）
  2) 窄列里的英文短词有没有被压成单字符（行高 / 列宽）
  3) 长 URL / 长英文串是否被折断
"""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
LONGURL = "https://example.com/" + ("abcdefghij" * 22)
LONGWORD = "A" * 220

DOC = """## 甲 窄列短英文（判据：Task 不能被拆）

| 状态 | 说明说明说明说明说明说明说明说明说明说明说明 |
|---|---|
| Task | 一两句话的说明文字，长度中等，用来把第二列撑开 |

## 乙 长 URL

| 链接 | 备注 |
|---|---|
| %s | x |

## 丙 长英文串

| 串 | 备注 |
|---|---|
| %s | x |
""" % (LONGURL, LONGWORD)

MEASURE = r"""() => {
  const pv = document.querySelector('#preview');
  const pr = pv.getBoundingClientRect(); const core = pr.width;
  const out = {core: Math.round(core), tabs: []};
  pv.querySelectorAll('table').forEach((t, i) => {
    const r = t.getBoundingClientRect();
    const td0 = t.querySelector('td');
    const rr = td0.getBoundingClientRect();
    // 该格第一行的行数：用 clientHeight / lineHeight 估
    const cs = getComputedStyle(td0);
    const lh = parseFloat(cs.lineHeight) || 0;
    out.tabs.push({
      i: i + 1,
      w: Math.round(r.width),
      over: Math.round(r.width - core),
      cell0w: Math.round(rr.width),
      cell0h: Math.round(rr.height),
      lines: lh ? Math.round(rr.height / lh) : null,
      text: td0.textContent.slice(0, 24)
    });
  });
  return out;
}"""

RULES = {
    "不写": "",
    "anywhere": ".markdown-body th,.markdown-body td{overflow-wrap:anywhere !important;}",
    "break-word": ".markdown-body th,.markdown-body td{overflow-wrap:break-word !important;}",
}

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    for name, css in RULES.items():
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.goto(BASE + "/", wait_until="domcontentloaded")
        pg.wait_for_timeout(2000)
        pg.evaluate("""(t) => { const e = document.getElementById('editor');
            e.textContent = t; e.dispatchEvent(new Event('input', {bubbles: true})); }""", DOC)
        pg.wait_for_timeout(2600)
        if css:
            pg.add_style_tag(content=css)
            pg.wait_for_timeout(500)
        r = pg.evaluate(MEASURE)
        print("\n=== %s ===  版心 %d" % (name, r["core"]))
        print("  %-4s %6s %7s %8s %8s %6s  %s" %
              ("表", "宽", "超版心", "首格宽", "首格高", "行数", "首格文字"))
        for t in r["tabs"]:
            print("  %-4d %6d %7d %8d %8d %6s  %s" %
                  (t["i"], t["w"], t["over"], t["cell0w"], t["cell0h"], t["lines"], t["text"]))
        pg.close()
    b.close()
