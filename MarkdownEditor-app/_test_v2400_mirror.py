# -*- coding: utf-8 -*-
"""v2.40.0 镜像出片测试（PASS/FAIL，不接受"看起来对"）

为什么必须量坐标：镜像的唯一产出就是"每页内容整体平移"。页数、版心宽、
{P}/{N} 全都不变，任何字符串断言都能全绿而实际没生效。唯一判据是拿
Edge 无头真打一份 PDF，用 pypdf 量每页左/右标记的 x 坐标。

相位口径（v2.40.0 定死）：**奇数页左右对调，偶数页按用户设定**。
所以点镜像后第一页立刻变，用户一眼能确认生效；"首页不镜像"也因此
有实际效果（把第一页拉回设定）。若反过来，第一页恒不变，那个开关
就是死的。

硬约束（都在这份测试里）：
  1. 版心宽 = 纸宽 − ml − mr，对调不改变这个和 → 分页点不动。
  2. 命名页（noll / roman / toc / pnrK）必须补 :left/:right，
     否则被 @page:left/:right 的 (0,1,0) 级联吃掉。
  3. mdefbgN（整页背景图）必须强制 margin:0，否则图缩进露白边。
  4. mirror=False 的 <style id="pnpage"> 与 v2.39.1 逐字节相同。

跑法：./python/python.exe _test_v2400_mirror.py
"""
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import md_server as m

try:
    import pypdf
except Exception:                                    # pragma: no cover
    pypdf = None

PASS, FAIL = [], []
MM = 2.835   # 1mm = 2.835bp


def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (
        "" if not detail else "   [" + str(detail)[:180] + "]"))


def find_edge():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return ""


EDGE = find_edge()
PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
       "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


# ---------------------------------------------------------------- PDF 出片

def build(body, cfg, mirror=False):
    cfg = dict(cfg)
    return m.build_paged_html(None, body, "", cfg, native=True, mirror=mirror)


def to_pdf(html, tag):
    hp = os.path.join(HERE, "_t2400_%s.html" % tag)
    pp = os.path.join(HERE, "_t2400_%s.pdf" % tag)
    with io.open(hp, "w", encoding="utf-8") as f:
        f.write(html)
    if os.path.exists(pp):
        os.remove(pp)
    subprocess.run([EDGE, "--headless=new", "--disable-gpu",
                    "--no-pdf-header-footer", "--print-to-pdf=" + pp,
                    "file:///" + hp.replace("\\", "/")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=180)
    if not os.path.exists(pp):
        return None
    return pp


def marks(pdf):
    """返回 [(页号, {标记名: x_mm})]，x 取 cm×tm 复合变换后的起点。"""
    r = pypdf.PdfReader(pdf)
    rows = []
    for i, p in enumerate(r.pages, 1):
        h = {}

        def v(text, cm, tm, fd, fs):
            t = text.strip()
            key = t.split("=")[0]
            if key.endswith("MARK") and key not in h:
                h[key] = round((tm[4] * cm[0] + tm[5] * cm[2] + cm[4]) / MM, 1)

        p.extract_text(visitor_text=v)
        rows.append((i, h))
    return len(r.pages), rows


def near(a, b, tol=0.6):
    return a is not None and abs(a - b) <= tol


# ---------------------------------------------------------------- 用例

BASE = {"paper": "A4", "mt": 25, "mr": 30, "mb": 25, "ml": 18,
        "tone": "light", "pn": {"on": "off"}, "toc": {"on": "off"}}


def four_page_body():
    return "".join(
        '<div>LMARK=%d</div><div style="text-align:right">RMARK=%d</div>'
        '<div style="height:200mm"></div>' % (i, i) for i in range(1, 5))


def test_geometry():
    body = four_page_body()
    p_plain = to_pdf(build(body, BASE, False), "plain")
    p_mir = to_pdf(build(body, BASE, True), "mirror")
    if not p_plain or not p_mir:
        chk("Edge 出片（几何用例）", False, "PDF 未生成")
        return
    n1, r1 = marks(p_plain)
    n2, r2 = marks(p_mir)
    chk("镜像前后总页数相等", n1 == n2, "%d vs %d" % (n1, n2))
    l1 = [h.get("LMARK") for _, h in r1 if h.get("LMARK") is not None]
    chk("非镜像：所有页左缘 = ml(18)", all(near(x, 18.0) for x in l1), l1)

    got = [(i, h.get("LMARK"), h.get("RMARK")) for i, h in r2
           if h.get("LMARK") is not None]
    odd_ok = all(near(h.get("LMARK"), 30.0) for i, h in r2
                 if i % 2 == 1 and h.get("LMARK") is not None)
    even_ok = all(near(h.get("LMARK"), 18.0) for i, h in r2
                  if i % 2 == 0 and h.get("LMARK") is not None)
    chk("镜像：奇数页左缘 = mr(30)（对调）", odd_ok, got)
    chk("镜像：偶数页左缘 = ml(18)（设定）", even_ok, got)

    # 版心宽必须逐页相同——这是"镜像不改分页点"的全部依据
    widths = [round(h["RMARK"] - h["LMARK"], 1) for _, h in r2
              if h.get("LMARK") is not None and h.get("RMARK") is not None]
    chk("镜像：各页版心宽相等", len(widths) >= 2 and max(widths) - min(widths) <= 0.3,
        widths)
    wp = [round(h["RMARK"] - h["LMARK"], 1) for _, h in r1
          if h.get("LMARK") is not None and h.get("RMARK") is not None]
    chk("镜像前后版心宽一致", widths and wp and near(widths[0], wp[0], 0.3),
        "%s vs %s" % (widths[:3], wp[:3]))


def test_first():
    cfg = dict(BASE)
    cfg["nm"] = {"first": True}
    body = four_page_body()
    pp = to_pdf(build(body, cfg, True), "first")
    if not pp:
        chk("Edge 出片（首页用例）", False)
        return
    n, rows = marks(pp)
    p1 = next((h.get("LMARK") for i, h in rows if i == 1), None)
    p3 = next((h.get("LMARK") for i, h in rows if i == 3), None)
    chk("首页不镜像：第 1 页 = ml(18)", near(p1, 18.0), p1)
    chk("首页不镜像：第 3 页仍对调 = 30", near(p3, 30.0), p3)


def test_toc():
    body = ('<div class="md-toc-wrap"><div>TMARK=1</div>'
            '<div style="height:200mm"></div></div>' + four_page_body())
    cfg = dict(BASE)
    cfg["toc"] = {"on": "on", "solo": True, "pos": "top"}
    # 目录命名页只在页码开启时生成（门控 pn_on）——真机上目录页码也依赖它，
    # 关掉页码时目录块就是普通页，勾"目录不镜像"本就无从生效。
    cfg["pn"] = {"on": "on", "pos": "outer", "size": 9, "tpl": "{p}"}
    p0 = to_pdf(build(body, cfg, True), "toc_off")
    cfg2 = dict(cfg)
    cfg2["nm"] = {"toc": True}
    p1 = to_pdf(build(body, cfg2, True), "toc_on")
    if not p0 or not p1:
        chk("Edge 出片（目录用例）", False)
        return
    _, r0 = marks(p0)
    _, r1 = marks(p1)
    t0 = [h.get("TMARK") for _, h in r0 if h.get("TMARK") is not None]
    t1 = [h.get("TMARK") for _, h in r1 if h.get("TMARK") is not None]
    chk("目录不勾：目录页对调（x=30）", t0 and near(t0[0], 30.0), t0)
    chk("目录勾上：目录页按设定（x=18）", t1 and near(t1[0], 18.0), t1)


def test_noll():
    body = ('<div class="page-region" data-pn="noll" data-pr-id="a">'
            '<div>NMARK=1</div></div>' + four_page_body())
    cfg = dict(BASE)
    cfg["pn"] = {"on": "on", "pos": "outer", "size": 9, "tpl": "{p}"}
    p0 = to_pdf(build(body, cfg, True), "noll_off")
    cfg2 = dict(cfg)
    cfg2["nm"] = {"noll": True}
    p1 = to_pdf(build(body, cfg2, True), "noll_on")
    if not p0 or not p1:
        chk("Edge 出片（noll 用例）", False)
        return
    _, r0 = marks(p0)
    _, r1 = marks(p1)
    n0 = [h.get("NMARK") for _, h in r0 if h.get("NMARK") is not None]
    n1 = [h.get("NMARK") for _, h in r1 if h.get("NMARK") is not None]
    chk("不编号区不勾：区页对调（x=30）", n0 and near(n0[0], 30.0), n0)
    chk("不编号区勾上：区页按设定（x=18）", n1 and near(n1[0], 18.0), n1)


def test_fullbg():
    body = ('<div class="full-page" data-bg-img="%s" data-bg-mode="c" '
            'data-bg-pos="cc"><div>FMARK=1</div></div>' % PNG
            + four_page_body())
    pp = to_pdf(build(body, BASE, True), "fullbg")
    if not pp:
        chk("Edge 出片（整页图用例）", False)
        return
    _, rows = marks(pp)
    fx = [h.get("FMARK") for _, h in rows if h.get("FMARK") is not None]
    # .full-page 自身 padding = ml(18)；@page margin 若被镜像污染成 30，
    # 这里会读到 48。量到 18 才说明命名页的 margin:0 压住了级联。
    chk("整页背景图：内容仍在 x=18（@page margin:0 生效）",
        fx and near(fx[0], 18.0), fx)


def test_equal_margins():
    cfg = dict(BASE)
    cfg["mr"] = 18
    body = four_page_body()
    pp = to_pdf(build(body, cfg, True), "eq")
    if not pp:
        chk("Edge 出片（左右相等用例）", False)
        return
    _, rows = marks(pp)
    xs = [h.get("LMARK") for _, h in rows if h.get("LMARK") is not None]
    chk("左右相等(18/18)时镜像不出错、坐标不变",
        xs and all(near(x, 18.0) for x in xs), xs)


# ---------------------------------------------------------------- CSS 断言

def test_css():
    pn = {"on": "on", "pos": "outer", "size": 9, "tpl": "{p}"}
    cfg = {"mt": 25, "mr": 30, "mb": 25, "ml": 18, "pn": pn,
           "toc": {"on": "on"}}
    a = m._native_page_css("A4", 25, 30, 25, 18, pn, cfg, 174.0)
    b = m._native_page_css("A4", 25, 30, 25, 18, pn, cfg, 174.0, mirror=True)
    chk("非镜像不产生 margin 补丁",
        "@page:left{margin:" not in a and "@page:right{margin:" not in a,
        a[:80])
    chk("镜像：@page:right 四值全写且左右对调",
        "@page:right{margin:25mm 18mm 25mm 30mm;" in b, b[:120])
    chk("镜像：@page:left 按设定",
        "@page:left{margin:25mm 30mm 25mm 18mm;" in b, b[:120])
    chk("镜像：命名页补齐 :left/:right（pn-noll）",
        "@page pn-noll:left{margin:" in b and "@page pn-noll:right{margin:" in b)
    chk("镜像：命名页补齐（pn-roman / pn-roman-uc / pn-toc）",
        all(("@page %s:left{margin:" % n) in b
            for n in ("pn-roman", "pn-roman-uc", "pn-toc")))
    # 首页名单才出 :first
    chk("未勾首页时不出 @page:first", "@page:first" not in b)
    cfg2 = dict(cfg)
    cfg2["nm"] = {"first": True}
    c = m._native_page_css("A4", 25, 30, 25, 18, pn, cfg2, 174.0, mirror=True)
    chk("勾首页时 @page:first 回到设定值",
        "@page:first{margin:25mm 30mm 25mm 18mm;}" in c)
    chk("勾首页时命名页 :first 一并压回",
        "@page pn-toc:first{margin:25mm 30mm 25mm 18mm;}" in c)

    # 整页背景图：强制 margin:0 三件套
    body = ('<div class="full-page" data-bg-img="%s" data-bg-mode="c" '
            'data-bg-pos="cc"><p>x</p></div>' % PNG)
    css_bg, _ = m._native_fullbg(body, 210, 297, 25, 30, 25, 18, "", mirror=True)
    chk("整页背景图：镜像时强制 margin:0 三件套",
        "@page mdefbg1:left{margin:0}" in css_bg
        and "@page mdefbg1:right{margin:0}" in css_bg
        and "@page mdefbg1:first{margin:0}" in css_bg, css_bg[:160])
    css_bg2, _ = m._native_fullbg(body, 210, 297, 25, 30, 25, 18, "", mirror=False)
    chk("整页背景图：非镜像不加三条（字节不变）",
        ":left{margin:0}" not in css_bg2)


def test_pnpage_bytes():
    """非镜像的 <style id="pnpage"> 必须与 v2.39.1 基线逐字节相同。
    基线取打包 staging（发出去的那一版）；缺失则跳过，不算失败。"""
    base_path = os.path.join(HERE, "_setup_staging", "md_server.py")
    if not os.path.exists(base_path):
        print("  SKIP  基线 staging 不存在，跳过逐字节比对")
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("old_md_base", base_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    cfg = {"paper": "A4", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
           "tone": "light", "pn": {"on": "on", "pos": "outer", "size": 9,
                                   "tpl": "{p}/{P}"},
           "toc": {"on": "on", "solo": True, "pos": "top"},
           "truePages": {"P": 60, "regions": {"a": 4}}}
    body = ('<div class="page-region" data-pn="i" data-pr-id="a"><p>x</p>'
            '</div>' + four_page_body())
    h1 = old.build_paged_html(None, body, "", dict(cfg), native=True)
    h2 = m.build_paged_html(None, body, "", dict(cfg), native=True)
    a = re.search(r'<style id="pnpage">(.*?)</style>', h1, re.S)
    b = re.search(r'<style id="pnpage">(.*?)</style>', h2, re.S)
    chk("非镜像 pnpage 与 v2.39.1 逐字节相同",
        bool(a and b) and a.group(1) == b.group(1),
        "len %s vs %s" % (len(a.group(1)) if a else -1,
                          len(b.group(1)) if b else -1))


def main():
    print("== v2.40.0 镜像出片测试 ==")
    test_css()
    if not EDGE or not pypdf:
        print("  SKIP  Edge 或 pypdf 不可用，跳过 PDF 实测（%s / %s）"
              % (bool(EDGE), bool(pypdf)))
    else:
        test_geometry()
        test_first()
        test_toc()
        test_noll()
        test_fullbg()
        test_equal_margins()
    test_pnpage_bytes()
    print("\nPASS %d / FAIL %d" % (len(PASS), len(FAIL)))
    if FAIL:
        for n in FAIL:
            print("  FAILED:", n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
