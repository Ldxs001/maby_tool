# -*- coding: utf-8 -*-
"""v2.33.0 判据（二）：用 DOM 渲染判字体是否命中，避开 canvas 简写解析的歧义。

同一段中英混排文本，宽度由字体的 advance 决定——命中则宽度与兜底不同。
同时用 document.fonts.check 交叉验证。
"""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"

JS = r"""
(cases) => {
  const TXT = '永和九年岁在癸丑AAA111';
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;left:-9999px;top:0;white-space:nowrap;' +
                       'font-size:100px;line-height:1.2;';
  document.body.appendChild(host);
  const span = document.createElement('span');
  span.textContent = TXT;
  host.appendChild(span);
  const w = (ff, fw, fs) => {
    span.style.fontFamily = ff;
    span.style.fontWeight = fw || '400';
    span.style.fontStyle = fs || 'normal';
    void span.offsetWidth;
    return Math.round(span.getBoundingClientRect().width * 100) / 100;
  };
  const out = [];
  for (const c of cases) out.push({ n: c.n, w: w(c.ff, c.fw, c.fs),
                                    chk: document.fonts.check('100px ' + c.ff) });
  out.push({ n: '__serif', w: w('serif') });
  out.push({ n: '__sans', w: w('sans-serif') });
  out.push({ n: '__mono', w: w('monospace') });
  out.push({ n: '__none', w: w('"NoSuchFont_zzz"') });
  host.remove();
  return out;
}
"""

CASES = [
    {"n": "YaHei 400", "ff": '"Microsoft YaHei"', "fw": "400"},
    {"n": "YaHei 300", "ff": '"Microsoft YaHei"', "fw": "300"},
    {"n": "YaHei 700", "ff": '"Microsoft YaHei"', "fw": "700"},
    {"n": "微软雅黑 400", "ff": '"微软雅黑"', "fw": "400"},
    {"n": "微软雅黑 300", "ff": '"微软雅黑"', "fw": "300"},
    {"n": "名:Microsoft YaHei Light", "ff": '"Microsoft YaHei Light"'},
    {"n": "名:微软雅黑 Light", "ff": '"微软雅黑 Light"'},
    {"n": "SimSun 400", "ff": '"SimSun"'},
    {"n": "NSimSun 400", "ff": '"NSimSun"'},
    {"n": "名:Arial Bold", "ff": '"Arial Bold"'},
    {"n": "Arial 400", "ff": '"Arial"'},
    {"n": "Arial 700", "ff": '"Arial"', "fw": "700"},
    {"n": "Segoe UI 300", "ff": '"Segoe UI"', "fw": "300"},
    {"n": "Segoe UI 400", "ff": '"Segoe UI"'},
    {"n": "Segoe UI 600", "ff": '"Segoe UI"', "fw": "600"},
    {"n": "名:Segoe UI Light", "ff": '"Segoe UI Light"'},
]

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1500)
    rows = pg.evaluate(JS, CASES)
    b.close()

ref = {r["n"]: r for r in rows}
none_w = ref["__none"]["w"]
print("各兜底宽：serif=%.2f sans=%.2f mono=%.2f  none=%.2f"
      % (ref["__serif"]["w"], ref["__sans"]["w"], ref["__mono"]["w"], none_w))
print("\n%-26s %9s  %s" % ("用例", "宽度", "chk"))
seen = {}
for r in rows:
    if r["n"].startswith("__"):
        continue
    same_as_none = abs(r["w"] - none_w) < 0.01
    print("%-26s %9.2f  %-5s %s"
          % (r["n"], r["w"], r["chk"], "→ 与不存在字体同宽(MISS)" if same_as_none else ""))
