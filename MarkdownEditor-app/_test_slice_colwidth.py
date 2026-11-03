# -*- coding: utf-8 -*-
"""长图切片判定：分栏栏宽基准回归测试

背景：v2.13.1 修复前，fill-col 内的图片宽度由 CSS 给出（img 标签无 width:N%），
切片判定按满版心宽折算 → 25% 栏里的证书被误判为超高长图切成条带。

用例：
  A 分栏 25% + 证书(1.451 比例) → 不切（修复目标）
  B 满宽 + 同证书            → 切（规则不变）
  C 分栏 25% + 4:1 长图      → 不切（43.5mm × 4 = 174mm < 245mm）
  D 分栏 50% + 4:1 长图      → 切（87mm × 4 = 348mm > 245mm，栏内真长图仍切）
  E 分栏 25% + img 自身 width:50% + 4:1（43.5 × 0.5 × 4 = 87mm）→ 不切
"""
import io
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import md_server as S  # noqa: E402

ICB_W = 174.0
IMG_MAXH = 245.0
DIR = "D:/Users/sm001/onedirve/OneDrive/Desktop/个人工作简历2026.assets/"
CERT = "20261028_170617_7769.jpg"  # 2881x4180 ratio 1.451
TALL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_slice_fixture", "tall.png")

PASS = FAIL = 0


def img_tag(path, pct=None):
    q = urllib.parse.quote(path, safe="")
    st = "" if pct is None else ' style="width:%d%%"' % pct
    return '<img src="/img?path=%s" alt="x"%s>' % (q, st)


def row(cols):
    inner = "".join(
        '<div class="fill-col" style="width:%d%%" data-fill="%d">%s</div>' % (w, w, tag)
        for tag, w in cols)
    return '<div class="fill-row" style="margin-left:0px" data-fill-row="1">' + inner + "</div>"


def check(name, body, should_slice):
    out = S._slice_tall_images(body, ICB_W, IMG_MAXH)
    sliced = "_slice/" in out
    ok = (sliced == should_slice)
    global PASS, FAIL
    if ok:
        PASS += 1
        print("PASS  %-46s 切=%-5s 期望=%-5s" % (name, sliced, should_slice))
    else:
        FAIL += 1
        print("FAIL  %-46s 切=%-5s 期望=%-5s" % (name, sliced, should_slice))
    return ok


cert = img_tag(DIR + CERT)
tall = img_tag(TALL)

# A: 用户现场 —— 25% 四栏证书行
check("A 分栏25%×4 + 证书(1.451)", row([(cert, 25)] * 4), False)
# B: 同证书满宽（不在分栏）→ 174×1.451=252.5mm > 245 仍切
check("B 满宽 + 同证书(1.451)", cert, True)
# C: 分栏 25% + 4:1 长图 → 43.5×4=174mm
check("C 分栏25% + 4:1 长图", row([(tall, 25)]), False)
# D: 分栏 50% + 4:1 长图 → 87×4=348mm
check("D 分栏50% + 4:1 长图", row([(tall, 50)]), True)
# E: 分栏 25% + img 自身 50% + 4:1 → 43.5×0.5×4=87mm
check("E 分栏25%+img50% + 4:1 长图", row([(img_tag(TALL, 50), 25)]), False)
# F: 分栏 80|20（用户简历基本信息行）+ 竖图
check("F 分栏80|20 + 证书", row([(cert, 80), (cert, 20)]), False)
# G: 无分栏无样式的小图 → 不切
check("G 裸小图", img_tag(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "_tmp_slice_fixture", "small.png")), False)

print("\n%d/%d PASS" % (PASS, PASS + FAIL))
sys.exit(0 if FAIL == 0 else 1)
