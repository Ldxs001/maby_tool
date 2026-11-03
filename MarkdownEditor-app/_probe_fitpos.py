# -*- coding: utf-8 -*-
"""o/c/f × 九宫 定位断言：用「红底 + 左上 60x60 蓝方块」的图，
   检查 fit/pos 是否真的作用在整张纸上。

   o + rb -> 原始尺寸贴在右下角：蓝块只在右下区域出现
   c + lt -> 撑满裁切、左上对齐：蓝块在左上
   f + cc -> 填充拉伸、居中：蓝块仍在左上（拉伸不改相对位置）
"""
import io, json, os, urllib.parse, urllib.request
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

APP = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:18766"
TMP = os.path.join(APP, "Temp")

# 1) 造图：1200x800 红底，左上 300x300 蓝块
src = os.path.join(TMP, "_probe_o_c_f.png")
im = Image.new("RGB", (1200, 800), (200, 30, 30))
im.paste((30, 30, 220), (0, 0, 300, 300))
im.save(src)
print("造图:", os.path.getsize(src), "bytes", im.size)

url_img = "/img?path=" + urllib.parse.quote(src)
cfg = {"paper": "A4", "tone": "light", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
       "pn": {"on": "off"}}


def build(mode, pos):
    body = ('<div class="full-page" data-full-pos="m"'
            ' data-bg-img="%s" data-bg-mode="%s" data-bg-pos="%s"'
            ' style="background-image:url(\'%s\');">'
            '</div><h1>正文</h1><p>正文。</p>' % (url_img, mode, pos, url_img))
    req = urllib.request.Request(
        BASE + "/api/export-paged",
        data=json.dumps({"bodyHtml": body, "tsCss": "", "cfg": cfg,
                         "mode": "native"}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    j = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    assert j.get("ok"), j


def sample(pdf, pts):
    d = fitz.open(pdf)
    pg = d[0]
    pix = pg.get_pixmap(matrix=fitz.Matrix(1, 1))
    W, H = pix.width, pix.height
    out = {}
    for name, (fx, fy) in pts.items():
        x, y = int(W * fx), int(H * fy)
        x = min(max(x, 0), W - 1)
        y = min(max(y, 0), H - 1)
        p = pix.pixel(x, y)
        out[name] = "#%02x%02x%02x" % (p[0], p[1], p[2])
    d.close()
    return out


PTS = {"左上": (0.02, 0.02), "右上": (0.98, 0.02),
       "左下": (0.02, 0.98), "右下": (0.98, 0.98),
       "中心": (0.5, 0.5)}


def blue(hexs):
    r = int(hexs[1:3], 16); g = int(hexs[3:5], 16); b = int(hexs[5:7], 16)
    return b > 120 and b > r + 60


def red(hexs):
    r = int(hexs[1:3], 16); g = int(hexs[3:5], 16); b = int(hexs[5:7], 16)
    return r > 120 and r > b + 60


cases = [("o", "rb"), ("c", "lt"), ("f", "cc")]
res = {}
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page()
    for mode, pos in cases:
        build(mode, pos)
        pg.goto(BASE + "/static/document.print.html", wait_until="networkidle")
        f = os.path.join(TMP, "_fit_%s_%s.pdf" % (mode, pos))
        pg.pdf(path=f, print_background=False, prefer_css_page_size=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        res[(mode, pos)] = sample(f, PTS)
    b.close()

FAIL = 0
for (mode, pos), s in res.items():
    print("\n%s + %s -> %s" % (mode, pos, s))
    if mode == "o" and pos == "rb":
        # o = 原始尺寸（1200x800px ≈ 317x211mm），右下锚定 → 图比纸矮，
        # 上方 86mm 露出纸色；图比纸宽，左右铺满。故：上白、下红。
        c1 = (not red(s["左上"])) and red(s["左下"]) and red(s["右下"])
        print("  断言：上露纸色、下铺满红 ->", "PASS" if c1 else "FAIL")
        FAIL += 0 if c1 else 1
    else:
        c1 = blue(s["左上"]) and not blue(s["右下"])
        print("  断言：左上蓝块、右下非蓝 ->", "PASS" if c1 else "FAIL")
        FAIL += 0 if c1 else 1

print("\nTOTAL FAIL:", FAIL, "/", len(res))
