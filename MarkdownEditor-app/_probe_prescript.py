# -*- coding: utf-8 -*-
"""探针：验证“左上/左下角标”序列化成 {}^{a}_{b}X 后，KaTeX 是否把角标放在正确位置。
输出每个用例的渲染盒位置，用坐标判断，不靠肉眼。"""
import io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Temp", "_prescript_probe")
os.makedirs(OUT, exist_ok=True)

CASES = [
    ("only-UL", "{}^{3}X"),
    ("only-LL", "{}_{4}X"),
    ("UL+LL", "{}^{3}_{4}X"),
    ("center+UL", "{}^{3}C"),
    ("sum-limits", "\\sum_{i=1}^{n}"),
    ("all-four", "{}^{a}_{b}X^{c}_{d}"),
]

html = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="../../katex/katex.min.css">
<style>body{background:#fff;margin:0;padding:8px;font-size:28px}
.a{height:70px}.b{display:inline-block}</style>
<div id="host"></div>
<script src="../../katex/katex.min.js"></script>
<script>
const cases = %s;
const host = document.getElementById('host');
const out = [];
for (const [name, tex] of cases) {
  const row = document.createElement('div');
  row.className = 'a';
  row.id = 'row-' + name;
  try {
    katex.render(tex, row, {throwOnError: true, displayMode: false});
  } catch (e) {
    row.textContent = 'ERR ' + e.message;
  }
  host.appendChild(row);
}
// 量每个用例里 .msupsub / .mfrac 等的位置
for (const [name] of cases) {
  const row = document.getElementById('row-' + name);
  const base = row.querySelector('.base') || row.firstElementChild;
  const rb = row.getBoundingClientRect();
  const items = [];
  row.querySelectorAll('.msupsub, .mop, .mord, .mi, .mn').forEach(el => {
    const r = el.getBoundingClientRect();
    items.push({cls: el.className, txt: el.textContent,
                x: Math.round(r.x - rb.x), y: Math.round(r.y - rb.y),
                w: Math.round(r.width), h: Math.round(r.height)});
  });
  out.push({name, items});
}
window.__RESULT__ = out;
</script>
"""

with io.open(os.path.join(OUT, "probe.html"), "w", encoding="utf-8", newline="") as f:
    f.write(html % json.dumps(CASES, ensure_ascii=False))

from playwright.sync_api import sync_playwright

url = "file:///" + os.path.join(OUT, "probe.html").replace("\\", "/")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 520, "height": 460}, device_scale_factor=2)
    pg.goto(url)
    pg.wait_for_timeout(400)
    res = pg.evaluate("() => window.__RESULT__ || []")
    pg.screenshot(path=os.path.join(OUT, "shot.png"))
    b.close()

for r in res:
    print("==", r["name"])
    for it in r["items"][:8]:
        print("   ", it)
