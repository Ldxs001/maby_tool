# -*- coding: utf-8 -*-
"""v2.33 设计验证：@@ begin font 的两个硬约束。

Q1 字体名映射：注册表枚举出来的名字，直接写进 font-family 能不能命中？
   /api/fonts 的名单来自注册表 value 名（按 & 拆分、去 (TrueType)），
   里面混着「字面样式名」（Arial Bold / Microsoft YaHei Light）。
   判定法：measureText 宽度对比——候选链后面挂一个宽度明显不同的兜底，
   命中则宽度不同于兜底，不命中则等于兜底。
Q2 !important 归属：ts-style 生成的 `#preview p{font-size:Xpt !important}`，
   与块级容器的内联 style 谁赢？（决定 @@ begin font 必须走哪条路）
"""
import json
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"
FONTS = json.load(urllib.request.urlopen(BASE + "/api/fonts"))["fonts"]

CAND = [
    ("Arial", "真 family 名"),
    ("Arial Bold", "字面样式名（注册表口径）"),
    ("Microsoft YaHei", "真 family 名"),
    ("Microsoft YaHei Bold", "字面样式名"),
    ("Microsoft YaHei UI", "真 family 名"),
    ("SimSun", "真 family 名"),
    ("KaiTi", "真 family 名"),
    ("楷体", "中文名"),
    ("华文楷体", "中文 family 名"),
    ("仿宋_GB2312", "中文 family 名"),
    ("NoSuchFont_zzz", "不存在的名（对照）"),
]

JS_MEASURE = r"""
(names) => {
  const cv = document.createElement('canvas').getContext('2d');
  const TXT = '永和九年岁在癸丑ABCabc0123';
  const out = {};
  // 兜底链：把不可能命中的名字放前面，monospace 垫底 → 该宽度即「未命中」
  cv.font = '100px NoSuchFont_qqq, monospace';
  const base = cv.measureText(TXT).width;
  out.__base = base;
  for (const n of names) {
    cv.font = '100px "NoSuchFont_qqq", "' + n + '", monospace';
    const w = cv.measureText(TXT).width;
    out[n] = { w: Math.round(w * 100) / 100, hit: Math.abs(w - base) > 0.5 };
  }
  return out;
}
"""

JS_IMPORTANT = r"""
() => {
  const box = document.createElement('div');
  box.id = 'pfBox';
  // ts-style 口径：选择器 #preview p + !important
  const st = document.createElement('style');
  st.textContent = '#preview #pfBox p{font-size:20pt !important;font-family:Arial !important;}';
  document.head.appendChild(st);
  document.getElementById('preview').innerHTML =
    '<div id="pfBox">' +
    '<p id="pfA">继承档：只给容器写变量</p>' +
    '<p id="pfB" style="font-size:9pt !important">内联带 !important</p>' +
    '</div>';
  const A = document.getElementById('pfA'), B = document.getElementById('pfB');
  const r = {};
  r['A 继承（无内联）'] = getComputedStyle(A).fontSize;
  r['B 内联 !important'] = getComputedStyle(B).fontSize;
  // 容器上的 font-size 会不会被 #preview p 的 !important 盖掉
  document.getElementById('pfBox').style.fontSize = '9pt';
  r['容器 9pt 后 A'] = getComputedStyle(A).fontSize;
  return r;
}
"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2000)

    print("=" * 62)
    print("Q1 字体名能否直接命中（宽度对比，base=%.2f）" % 0)
    names = [c[0] for c in CAND]
    res = pg.evaluate(JS_MEASURE, names)
    print("  未命中基准宽 = %.2f" % res.pop("__base"))
    for n, why in CAND:
        d = res[n]
        print("  %-22s %-24s w=%-8.2f %s" % (n, why, d["w"], "HIT" if d["hit"] else "MISS"))

    print("\n" + "=" * 62)
    print("Q2 !important 归属")
    imp = pg.evaluate(JS_IMPORTANT)
    for k, v in imp.items():
        print("  %-22s %s" % (k, v))

    b.close()
