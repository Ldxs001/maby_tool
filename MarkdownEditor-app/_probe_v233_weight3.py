# -*- coding: utf-8 -*-
"""v2.33.0 判据（三）：双保险字体栈是否两头都命中。

设计：font-family = "原样名","折叠后的 family",sans-serif；同时给 font-weight/style。
  原样名有效（Light 面独立注册）→ 直接命中该面
  原样名无效（Bold 只是同族某面）→ 回落到 family + 数字字重，仍命中该面
"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"

JS = r"""
(cases) => {
  const TXT = '永和九年岁在癸丑AAA111';
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:-9999px;top:0;white-space:nowrap;font-size:100px;';
  document.body.appendChild(host);
  const span = document.createElement('span');
  span.textContent = TXT;
  host.appendChild(span);
  const w = (ff, fw, fs) => {
    span.style.font = '';
    span.style.fontFamily = ff;
    span.style.fontWeight = fw || '400';
    span.style.fontStyle = fs || 'normal';
    void span.offsetWidth;
    return Math.round(span.getBoundingClientRect().width * 100) / 100;
  };
  const out = [];
  for (const c of cases) out.push({ n: c.n, w: w(c.ff, c.fw, c.fs) });
  host.remove();
  return out;
}
"""

# 参考值（上一轮已测）：none/sans=1187.02  YaHei300=1119.20  YaHei700=1210.61
#                     Arial400=1152.11  Arial700=1172.47  Segoe300=1095.61 Segoe400=1155.23
CASES = [
    {"n": "基准 sans-serif", "ff": "sans-serif"},
    {"n": "基准 YaHei 300", "ff": '"Microsoft YaHei"', "fw": "300"},
    {"n": "基准 YaHei 700", "ff": '"Microsoft YaHei"', "fw": "700"},
    {"n": "基准 Arial 700", "ff": '"Arial"', "fw": "700"},
    {"n": "基准 Arial 400", "ff": '"Arial"'},
    {"n": "基准 SegoeUI 300", "ff": '"Segoe UI"', "fw": "300"},
    {"n": "双保险 YaHeiLight", "ff": '"Microsoft YaHei Light","Microsoft YaHei",sans-serif', "fw": "300"},
    {"n": "双保险 ArialBold", "ff": '"Arial Bold","Arial",sans-serif', "fw": "700"},
    {"n": "双保险 SegoeUILight", "ff": '"Segoe UI Light","Segoe UI",sans-serif', "fw": "300"},
    {"n": "双保险 SimSun", "ff": '"SimSun","SimSun",sans-serif'},
    {"n": "单名 ArialBold", "ff": '"Arial Bold"', "fw": "700"},
    {"n": "双保险 但数字冲突", "ff": '"Microsoft YaHei Light","Microsoft YaHei",sans-serif', "fw": "400"},
]

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1500)
    rows = pg.evaluate(JS, CASES)
    b.close()

ref = {r["n"]: r["w"] for r in rows}
print("%-24s %9s   判定" % ("用例", "宽度"))
ok = 0
checks = [
    ("双保险 YaHeiLight", "基准 YaHei 300"),
    ("双保险 ArialBold", "基准 Arial 700"),
    ("双保险 SegoeUILight", "基准 SegoeUI 300"),
    ("双保险 SimSun", "基准 sans-serif"),
]
for r in rows:
    print("%-24s %9.2f" % (r["n"], r["w"]))
print("\n对照：")
for a, bb in checks:
    if a == "双保险 SimSun":
        same = abs(ref[a] - ref[bb]) > 0.01
        note = "≠ sans-serif（命中宋体）" if same else "= sans-serif（未命中）"
    else:
        same = abs(ref[a] - ref[bb]) < 0.01
        note = "一致 ✓" if same else "不一致 ✗"
    print("  %-22s vs %-16s %s" % (a, bb, note))
print("  单名 ArialBold = %.2f（基准 sans %.2f）→ %s"
      % (ref["单名 ArialBold"], ref["基准 sans-serif"],
         "MISS" if abs(ref["单名 ArialBold"] - ref["基准 sans-serif"]) < 0.01 else "HIT"))
print("  数字冲突档 = %.2f（Light=%.2f, 400=%.2f）→ %s"
      % (ref["双保险 但数字冲突"], ref["基准 YaHei 300"], ref["基准 sans-serif"],
         "仍取 Light 面" if abs(ref["双保险 但数字冲突"] - ref["基准 YaHei 300"]) < 0.01 else "数字胜"))
