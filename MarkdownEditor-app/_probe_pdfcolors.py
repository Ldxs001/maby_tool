# -*- coding: utf-8 -*-
"""采样 PDF：页数 / 四角颜色 / 中心颜色"""
import os, sys
import fitz

p = sys.argv[1] if len(sys.argv) > 1 else "Temp/_probe_v231.pdf"
p = os.path.abspath(p)
d = fitz.open(p)
print("页数:", d.page_count)


def hx(pix):
    return "#%02x%02x%02x" % (pix[0], pix[1], pix[2])


for i in range(min(d.page_count, 4)):
    pg = d[i]
    r = pg.rect
    zoom = 72.0 / 72.0
    pix = pg.get_pixmap(matrix=fitz.Matrix(1, 1))
    W, H = pix.width, pix.height
    pts = {
        "左上": (4, 4), "右上": (W - 5, 4),
        "左下": (4, H - 5), "右下": (W - 5, H - 5),
        "中心": (W // 2, H // 2),
        "左中边距": (10, H // 2), "右中边距": (W - 10, H // 2),
    }
    ser = {k: hx(pix.pixel(x, y)) for k, (x, y) in pts.items()}
    print("P%d %dx%d %s" % (i + 1, W, H, ser))
d.close()
