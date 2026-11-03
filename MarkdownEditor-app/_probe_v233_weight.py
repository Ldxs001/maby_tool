# -*- coding: utf-8 -*-
"""v2.33.0 判据：字体「样式后缀」能否折叠回 family + 真实字重。

三个待证：
 A. `font-family:"Microsoft YaHei Light"` 是否命中（预期不命中，与 2026-11-04 墨点实测一致）
 B. `font-family:"Microsoft YaHei";font-weight:300` 是否真的落到 Light 面（与 400 有差）
 C. 其它后缀（Bold / Bold Italic / Semibold / Black / Thin）折叠成 weight/style 后是否各自命中
"""
import io, json, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"

JS = r"""
(specs) => {
  const cv = document.createElement('canvas');
  cv.width = 1200; cv.height = 220;
  const cx = cv.getContext('2d');
  const TXT = '永A国';
  const probe = (font, txt) => {
    cx.clearRect(0, 0, 1200, 220);
    cx.fillStyle = '#000';
    cx.font = font;
    cx.textBaseline = 'top';
    cx.fillText(txt, 10, 10);
    const d = cx.getImageData(0, 0, 1200, 220).data;
    let ink = 0, minx = 1e9, maxx = -1;
    for (let y = 0; y < 220; y++) {
      for (let x = 0; x < 1200; x++) {
        if (d[(y * 1200 + x) * 4 + 3] > 40) {
          ink++; if (x < minx) minx = x; if (x > maxx) maxx = x;
        }
      }
    }
    return { ink: ink, w: Math.round((maxx - minx) * 100) / 100,
             adv: Math.round(cx.measureText(txt).width * 100) / 100 };
  };
  const out = [];
  for (const s of specs) {
    out.push({ name: s.name, r: probe(s.font, TXT) });
  }
  out.push({ name: '__base', r: probe('100px "NoSuchFont_zzz"', TXT) });
  return out;
}
"""

SPECS = [
    ("YaHei 400", '400 100px "Microsoft YaHei"'),
    ("YaHei 300", '300 100px "Microsoft YaHei"'),
    ("YaHei 200", '200 100px "Microsoft YaHei"'),
    ("YaHei 700", '700 100px "Microsoft YaHei"'),
    ('名带 Light', '400 100px "Microsoft YaHei Light"'),
    ('名带 Light +300', '300 100px "Microsoft YaHei Light"'),
    ("SimSun 400", '400 100px "SimSun"'),
    ("SimSun 700", '700 100px "SimSun"'),
    ("名带 Bold", '400 100px "Arial Bold"'),
    ("Arial 400", '400 100px "Arial"'),
    ("Arial 700", '700 100px "Arial"'),
    ("SegoeUI 400", '400 100px "Segoe UI"'),
    ("SegoeUI 300", '300 100px "Segoe UI"'),
    ("SegoeUI 600", '600 100px "Segoe UI"'),
    ("SegoeUILight", '400 100px "Segoe UI Light"'),
]

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1500)
    rows = pg.evaluate(JS, [{"name": n, "font": f} for n, f in SPECS])
    b.close()

base = [r for r in rows if r["name"] == "__base"][0]["r"]
rows = [r for r in rows if r["name"] != "__base"]
print("未命中基准  ink=%d w=%.2f adv=%.2f" % (base["ink"], base["w"], base["adv"]))
print("%-18s %7s %8s %8s  %s" % ("规格", "墨点", "字宽", "adv", "判定"))
prev = None
for r in rows:
    d = r["r"]
    miss = abs(d["ink"] - base["ink"]) < 60
    print("%-18s %7d %8.2f %8.2f  %s"
          % (r["name"], d["ink"], d["w"], d["adv"], "MISS(回落)" if miss else "HIT"))
    prev = d
