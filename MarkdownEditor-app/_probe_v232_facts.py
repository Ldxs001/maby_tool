# -*- coding: utf-8 -*-
"""v2.32.0 事实核对：表格 / 图片 / 代码块 到底会不会超出版心（100%）。

只读。用编辑器自己的纯文本通道写入（textContent + pre-wrap），
逐项量渲染后的盒子宽度与版心宽比对。
"""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
IMG = "C:/Users/sm001/WorkBuddy/MarkdownEditor-app/docs/MDEditor 实操手册.assets/20261103_010158_8502.png"

LONGWORD = "A" * 220
LONGURL = "https://example.com/" + ("abcdefghij" * 22)
LONGCJK = "这是一段很长很长的中文句子用来测试换行" * 8

DOC = """## 甲 普通表格

| 表头甲 | 表头乙 |
|---|---|
| 1 | 2 |

## 乙 指定 100

@@ table{100l:r(50|50)}
| 表头甲 | 表头乙 |
|---|---|
| 1 | 2 |

## 丙 指定 50

@@ table{50l:r(50|50)}
| 表头甲 | 表头乙 |
|---|---|
| 1 | 2 |

## 丁 200 非法

@@ table{200l:r(50|50)}
| 表头甲 | 表头乙 |
|---|---|
| 1 | 2 |

## 戊 单元格塞长 URL

| 表头甲 | 表头乙 |
|---|---|
| %s | 2 |

## 己 单元格塞长英文词

| 表头甲 | 表头乙 |
|---|---|
| %s | 2 |

## 庚 单元格塞长中文

| 表头甲 | 表头乙 |
|---|---|
| %s | 2 |

## 辛 图片

![](%s)

## 壬 代码块长行

```python
x = "%s"
```
""" % (LONGURL, LONGWORD, LONGCJK, IMG, LONGWORD)

MEASURE = r"""() => {
  const pv = document.querySelector('#preview');
  const pr = pv.getBoundingClientRect();
  const core = pr.width;
  const out = {core: Math.round(core), rows: [], leaks: []};
  const add = (kind, el) => {
    const r = el.getBoundingClientRect();
    const row = {kind, w: Math.round(r.width), over: Math.round(r.width - core),
                 sw: el.scrollWidth, cw: el.clientWidth,
                 ox: getComputedStyle(el).overflowX};
    out.rows.push(row);
    if (row.over > 1) out.leaks.push(kind);
    if (r.right > pr.right + 1) out.leaks.push(kind + ':right');
  };
  pv.querySelectorAll('table').forEach((t, i) => add('table' + (i + 1), t));
  pv.querySelectorAll('pre').forEach((p, i) => add('pre' + (i + 1), p));
  pv.querySelectorAll('img').forEach((m, i) => add('img' + (i + 1), m));
  out.tableCount = pv.querySelectorAll('table').length;
  out.imgCount = pv.querySelectorAll('img').length;
  out.has200Line = pv.textContent.indexOf('@@ table{200l') >= 0;
  return out;
}"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    pg.evaluate("""(t) => { const e = document.getElementById('editor');
        e.textContent = t;
        e.dispatchEvent(new Event('input', {bubbles: true})); }""", DOC)
    pg.wait_for_timeout(3000)
    r = pg.evaluate(MEASURE)
    print("版心宽 =", r["core"], "px | 表格", r["tableCount"], "| 图", r["imgCount"])
    print("%-9s %6s %7s %8s %8s %6s" % ("元素", "宽", "超版心", "scrollW", "clientW", "overflow"))
    for it in r["rows"]:
        print("%-9s %6d %7d %8d %8d %6s" %
              (it["kind"], it["w"], it["over"], it["sw"], it["cw"], it["ox"]))
    print("\n200% 行原文露出:", r["has200Line"])
    print("溢出项:", r["leaks"] if r["leaks"] else "无")
    pg.screenshot(path=os.path.abspath("Temp/_v232_facts2.png"))
    b.close()
