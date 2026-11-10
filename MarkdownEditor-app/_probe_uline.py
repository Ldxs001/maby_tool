# -*- coding: utf-8 -*-
"""下划线线型实证探针（v2.41.0 方案依据）

验证三件事，全部靠像素，不靠肉眼：
  1. text-decoration:underline / dotted / double 的上沿是否对齐（批注要同 y）
  2. double 的两条线间距
  3. border-bottom 与 underline 的 y 差（说明为什么批注不能再用 border-bottom）

用法： python _probe_uline.py
依赖： playwright（Chromium）+ Pillow
产出： Temp/_uline_probe/*.png，控制台打印 y 表
"""
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Temp", "_uline_probe")
HTML = os.path.join(OUT, "probe.html")

PAGE = """<!doctype html><meta charset="utf-8">
<style>
body{background:#1c1f26;color:#d8dce6;font:17px/1.9 "Segoe UI",system-ui;margin:0;padding:0;width:320px}
p{margin:0;height:40px;padding:0 10px}
u.uline{text-decoration:underline;text-underline-offset:3px;text-decoration-thickness:1px;text-decoration-color:#ff9933}
u.uline[data-ul="double"]{text-decoration:underline double;text-decoration-color:#ff9933}
span[data-aid]{border-bottom:0;text-decoration:underline dotted;text-decoration-color:#7aa2f7;
  text-decoration-thickness:2px;text-underline-offset:3px}
span[data-bid]{border-bottom:2px dotted #7aa2f7;text-decoration:none}
</style>
<p><u class="uline">测试文字</u></p>
<p><span data-aid="1">测试文字</span></p>
<p><u class="uline" data-ul="double">测试文字</u></p>
<p><span data-bid="1">测试文字</span></p>
"""


def _px(img, pred, y):
    w = img.size[0]
    xs = [x for x in range(w) if pred(img.getpixel((x, y)))]
    return (min(xs), max(xs), len(xs)) if xs else None


def _orange(p):
    r, g, b = p
    return r > 200 and 120 < g < 200 and b < 120


def _blue(p):
    r, g, b = p
    return 90 < r < 190 and 130 < g < 210 and b > 200


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(PAGE)

    shot = os.path.join(OUT, "probe.png")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 320, "height": 170}, device_scale_factor=4)
        pg.goto("file:///" + HTML.replace("\\", "/"))
        pg.wait_for_timeout(250)
        pg.screenshot(path=shot)
        b.close()

    img = Image.open(shot).convert("RGB")
    rows = []
    for y in range(img.size[1]):
        o = _px(img, _orange, y)
        bl = _px(img, _blue, y)
        if o or bl:
            rows.append((y, o, bl))

    # 只留"整行连续"的线：长度 > 30 像素且横向覆盖超过文本 1/3
    def is_line(r):
        for box in (r[1], r[2]):
            if box and box[2] > 30:
                return True
        return False

    print("y(物理,DPR=4)  橙线 x范围        蓝线 x范围")
    for y, o, bl in rows:
        if is_line((y, o, bl)):
            print("%4d  %-18s %-18s" % (y, str(o[:2]) if o else "-", str(bl[:2]) if bl else "-"))

    print("\n判定口径：")
    print("  同一条线的 y 区间 = 连续出现的物理 y；上沿即区间起点。")
    print("  四组线（underline / dotted / double×2 / border-bottom）各取上沿比较。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
