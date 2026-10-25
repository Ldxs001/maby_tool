# run-name: plotimg
# 数据形式：形式4 键值对（kv：5 个配置键 + 一组「标签 == 数值」），键序＝文档书写顺序
# 数据点写法：@@ MDE__月度{标题 == 门店月度销量, 单位 == 元, 一月 == 128000, 二月 == 143500}
# 执行点写法：@@ MDE from plotimg import bar is 月度
# 执行点写法：@@ MDE from plotimg import line is 月度
# 执行点写法：@@ MDE from plotimg import donut is 月度
# 返回值：![](<标题>-<类型>.png) —— 图片写进 run 的当前目录（= 本文档资产目录），同名重跑覆盖
# 注意：配置键只有 标题 / 单位 / 宽 / 高 / 配色 五个，其余键一律当「标签 == 数值」按顺序画
# 注意：数值可写 128,000 / 12万 / 1.5万元 / 8%，读不懂的值跳过，不影响其它柱
# 注意：依赖 Pillow（便携版自带 python/Lib/site-packages/PIL 13.0.0），pip 安装版需先 pip install --target runtime/pylibs pillow

"""plotimg —— 数据点 → 图片。

实现要点：
- 取数只认 kv：五个配置键不参与绘图，其余键按书写顺序排；
- 刻度按 1/1.5/2/2.5/3/4/5/6/8×10^n 抬整，不出 148,591.50 这类小数刻度；
- 中文走系统字体（雅黑 → 黑体 → 苹方 → Noto），都没有则退 PIL 默认字体；
- _save() 写 cwd 并返回相对路径引用，框架只负责把它接到预览区。
"""

import math
import os
import re

from PIL import Image, ImageDraw, ImageFont

_CFG_KEYS = ("标题", "单位", "宽", "高", "配色")

# 每个色系一组同色系色阶（浅 → 深），柱状图按位置取深浅，饼图靠白描边分隔
_PALETTES = {
    "金": ("#EBD9AC", "#DCC287", "#D0AE63", "#C8A24A", "#A9883A"),
    "蓝": ("#CFE0F0", "#A5C4E2", "#7BA6D2", "#5288BF", "#35679B"),
    "绿": ("#D2E8DA", "#A8CFB7", "#7FB595", "#57A075", "#3A7A57"),
    "紫": ("#DED8EC", "#BFB4D9", "#A091C5", "#7F6FB0", "#5F4F8C"),
    "灰": ("#DCDCDC", "#BEBEBE", "#9E9E9E", "#7C7C7C", "#5A5A5A"),
}

_BG = "#FBFAF7"
_INK = "#2B2B2B"
_MUTED = "#8A8578"
_GRID = "#E6E2D8"


# ---------------------------------------------------------------- 基础工具

def _font(size, bold=False):
    """中文字体：Windows 微软雅黑 → 黑体，macOS/Linux 各留一个退路。"""
    win = os.environ.get("WINDIR") or r"C:\Windows"
    names = (["msyhbd.ttc", "msyh.ttc", "simhei.ttf"]
             if bold else ["msyh.ttc", "simhei.ttf", "simsun.ttc"])
    paths = [os.path.join(win, "Fonts", n) for n in names]
    paths += [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _num(raw):
    """'128,000' '12万' '8%' → (float, 是否百分数)；不是数字返回 (None, False)。"""
    t = str(raw if raw is not None else "").strip()
    if not t:
        return None, False
    t = t.replace(",", "").replace("，", "").replace(" ", "").replace("　", "")
    pct = False
    if t.endswith("%"):
        pct, t = True, t[:-1]
    mul = 1.0
    if t.endswith("万元"):
        mul, t = 10000.0, t[:-2]
    elif t.endswith("亿"):
        mul, t = 100000000.0, t[:-1]
    elif t.endswith("万"):
        mul, t = 10000.0, t[:-1]
    else:
        for suf in ("元", "个", "件", "台", "次", "人次", "人"):
            if t.endswith(suf):
                t = t[:-len(suf)]
                break
    if not re.match(r"^[+-]?\d+(\.\d+)?$", t):
        return None, False
    return float(t) * mul, pct


def _fmt(v, pct=False):
    if pct:
        return ("%g" % v) + "%"
    if abs(v - round(v)) < 1e-9:
        return "{:,}".format(int(round(v)))
    return "{:,.2f}".format(v)


def _nice_step(raw):
    """把任意步长抬到 1/1.5/2/2.5/3/4/5/6/8×10^n —— 刻度只出现整数。"""
    if raw <= 0:
        return 1.0
    exp = math.floor(math.log10(raw))
    base = 10.0 ** exp
    n = raw / base
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if n <= m:
            return m * base
    return 10 * base


def _items(data):
    """kv → (配置 dict, [(标签, 数值, 显示文本)])。"""
    kv = data.get("kv") if isinstance(data, dict) else None
    if not isinstance(kv, dict):
        kv = {}
    cfg, pts = {}, []
    for k, v in kv.items():
        key = str(k).strip()
        if key in _CFG_KEYS:
            cfg[key] = str(v).strip()
            continue
        n, pct = _num(v)
        if n is None:
            continue
        pts.append((key, n, _fmt(n, pct)))
    return cfg, pts


def _safe(name):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", str(name or "").strip())
    return (s[:40] or "图")


def _canvas(cfg):
    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(float(cfg.get(key) or default))))
        except (TypeError, ValueError):
            return default
    return _int("宽", 760, 320, 2400), _int("高", 420, 240, 2000)


def _palette(cfg):
    return _PALETTES.get(cfg.get("配色") or "金", _PALETTES["金"])


def _shade(hex_a, hex_b, t):
    ta = tuple(int(hex_a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    tb = tuple(int(hex_b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(ta, tb))


def _save(img, cfg, kind, tags=None):
    """落在 cwd（＝文档资产目录），返回前端能认的相对路径图片引用。

    文件名固定 = 同名重跑直接覆盖，资产目录不会越跑越大；没写标题时用
    前两个标签兜底，免得同文档里两张没标题的图互相覆盖。"""
    base = cfg.get("标题") or ""
    if not base and tags:
        base = "图-" + "-".join(str(t) for t in tags[:2])
    fn = "%s-%s.png" % (_safe(base or "图"), kind)
    img.save(fn)
    return "![](%s)" % fn


def _caption(d, cfg, pct_any, W=760):
    t = cfg.get("标题") or ""
    u = cfg.get("单位") or ("%" if pct_any else "")
    if t:
        size = 19
        f = _font(size, True)
        while size > 12 and d.textlength(t, font=f) + 90 > W - 44:
            size -= 1
            f = _font(size, True)
        d.text((44, 30 + (19 - size)), t, font=f, fill=_INK)
        if u:
            d.text((44 + d.textlength(t, font=f) + 9, 36), "/ " + u,
                   font=_font(12), fill=_MUTED)
    elif u:
        d.text((44, 32), "单位：" + u, font=_font(14, True), fill=_INK)


def _frame(d, cfg, W, H, vmax, pct_any, top=86):
    """算绘图区，返回 (x0, y0, x1, y1, ypos)。网格由 _grid() 后画。"""
    x0, y0, x1, y1 = 76, top, W - 34, H - 56
    step = _nice_step(vmax / 4.0)

    def ypos(v):
        return y1 - (y1 - y0) * (v / (step * 4.0))
    return x0, y0, x1, y1, ypos, step


def _grid(d, x0, x1, y0, y1, ypos, step, pct_any):
    for i in range(5):
        v = step * i
        y = ypos(v)
        d.line([(x0, y), (x1, y)], fill=_GRID, width=1)
        lab = _fmt(v, pct_any)
        d.text((x0 - 10 - d.textlength(lab, font=_font(11)), y - 7),
               lab, font=_font(11), fill=_MUTED)


def _clamp_label(d, cx, y, txt, font, x0, x1):
    tw = d.textlength(txt, font=font)
    x = min(max(cx - tw / 2, x0), x1 - tw)
    d.text((x, y), txt, font=font, fill=_INK)


def _empty():
    return "没有可画的数据。数据点写成「一月 == 128000, 二月 == 143500」这种形式。"


# ---------------------------------------------------------------- 三种图

def bar(data):
    """柱状图：每个「标签 == 数值」一根柱子，同色系由浅到深。"""
    cfg, pts = _items(data)
    if not pts:
        return _empty()
    W, H = _canvas(cfg)
    img = Image.new("RGB", (W, H), _BG)
    d = ImageDraw.Draw(img)
    pct_any = any(p[2].endswith("%") for p in pts)
    _caption(d, cfg, pct_any, W)
    vmax = max(p[1] for p in pts) * 1.15
    x0, y0, x1, y1, ypos, step = _frame(d, cfg, W, H, vmax, pct_any)
    _grid(d, x0, x1, y0, y1, ypos, step, pct_any)

    pal = _palette(cfg)
    n = len(pts)
    pw = x1 - x0
    gap = min(26.0, pw / n * 0.32)
    bw = (pw - gap * (n - 1)) / n
    for i, (lab, v, txt) in enumerate(pts):
        bx = x0 + i * (bw + gap)
        by = ypos(v)
        t = i / (n - 1) if n > 1 else 0.0
        d.rounded_rectangle([bx, by, bx + bw, y1], radius=3,
                            fill=_shade(pal[0], pal[3], t))
        _clamp_label(d, bx + bw / 2, by - 21, txt, _font(12, True), x0, x1)
        lw = d.textlength(lab, font=_font(12))
        d.text((min(max(bx + (bw - lw) / 2, x0), x1 - lw), y1 + 12),
               lab, font=_font(12), fill=_MUTED)
    d.line([(x0, y1), (x1, y1)], fill=_MUTED, width=1)
    return _save(img, cfg, "柱状图", [p[0] for p in pts])


def line(data):
    """折线图：同一批数据连成线，节点标值；面积填充压在网格下面。"""
    cfg, pts = _items(data)
    if not pts:
        return _empty()
    W, H = _canvas(cfg)
    img = Image.new("RGB", (W, H), _BG)
    pct_any = any(p[2].endswith("%") for p in pts)
    d = ImageDraw.Draw(img)
    _caption(d, cfg, pct_any, W)
    vmax = max(p[1] for p in pts) * 1.15
    x0, y0, x1, y1, ypos, step = _frame(d, cfg, W, H, vmax, pct_any)

    pal = _palette(cfg)
    c = pal[3]
    n = len(pts)
    stp = (x1 - x0) / (n - 1 if n > 1 else 1)
    xy = []
    for i, (lab, v, txt) in enumerate(pts):
        cx = x0 + stp * i if n > 1 else (x0 + x1) / 2
        xy.append((cx, ypos(v)))

    if n > 1:
        area = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(area).polygon(
            xy + [(xy[-1][0], y1), (xy[0][0], y1)], fill=_shade(c, "#FFFFFF", 0.55) + (68,))
        img = Image.alpha_composite(img.convert("RGBA"), area).convert("RGB")
        d = ImageDraw.Draw(img)

    _grid(d, x0, x1, y0, y1, ypos, step, pct_any)
    if n > 1:
        d.line(xy, fill=c, width=3, joint="curve")
    for i, (lab, v, txt) in enumerate(pts):
        cx, cy = xy[i]
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=c, outline=_BG, width=2)
        _clamp_label(d, cx, cy - 25, txt, _font(12, True), x0, x1)
        lw = d.textlength(lab, font=_font(12))
        d.text((min(max(cx - lw / 2, x0), x1 - lw), y1 + 12),
               lab, font=_font(12), fill=_MUTED)
    d.line([(x0, y1), (x1, y1)], fill=_MUTED, width=1)
    return _save(img, cfg, "折线图", [p[0] for p in pts])


def donut(data):
    """圆环图：看占比，图例在右侧带百分比。"""
    cfg, pts = _items(data)
    if not pts:
        return _empty()
    W, H = _canvas(cfg)
    img = Image.new("RGB", (W, H), _BG)
    d = ImageDraw.Draw(img)
    pct_any = any(p[2].endswith("%") for p in pts)
    _caption(d, cfg, pct_any, W)
    pal = _palette(cfg)

    total = sum(abs(p[1]) for p in pts) or 1.0
    cx, cy = W * 0.35, H * 0.56
    r = min(W * 0.21, H * 0.32)
    rw = max(16, int(r * 0.40))
    box = [cx - r, cy - r, cx + r, cy + r]

    start = -90.0
    for i, (lab, v, txt) in enumerate(pts):
        sweep = 360.0 * abs(v) / total
        d.arc(box, start + 0.6, start + sweep - 0.6,
              fill=pal[i % len(pal)], width=rw)
        start += sweep

    tot_txt = _fmt(total)
    d.text((cx - d.textlength(tot_txt, font=_font(17, True)) / 2, cy - 22),
           tot_txt, font=_font(17, True), fill=_INK)
    d.text((cx - d.textlength("合计", font=_font(11)) / 2, cy + 4),
           "合计", font=_font(11), fill=_MUTED)

    lx = W * 0.62
    ly = cy - len(pts) * 17
    for i, (lab, v, txt) in enumerate(pts):
        y = ly + i * 34
        d.rounded_rectangle([lx, y + 2, lx + 12, y + 14], radius=2,
                            fill=pal[i % len(pal)])
        d.text((lx + 20, y - 2), lab, font=_font(13), fill=_INK)
        d.text((lx + 20, y + 16), "%s   %.1f%%" % (txt, abs(v) * 100.0 / total),
               font=_font(12), fill=_MUTED)
    return _save(img, cfg, "圆环图", [p[0] for p in pts])
