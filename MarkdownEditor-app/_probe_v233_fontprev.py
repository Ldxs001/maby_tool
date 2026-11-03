# -*- coding: utf-8 -*-
"""v2.33.0 预览侧验收：@@ begin font 的渲染、字重真值、并写、fail-closed。"""
import io, json, os, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18766"

DOC = """# 字体块验收

块外正文，应当是排版默认。

@@ begin font{"Microsoft YaHei Light" 12pt}
## 块内标题

块内正文段落，字体应为 Light、字号 12pt（= 16px）。

- 块内列表项一
- 块内列表项二

`行内代码在块内`
@@ end font

块外正文恢复默认。

@@ begin page{noll} font{楷体 14pt} color{#c0392b}
并写块：page + font + color 三者同时生效。
@@ end color
@@ end font
@@ end page

@@ begin font{不存在的字体 200pt}
参数非法（字号越界），应原样露出这一行，内容照常渲染。
@@ end font
"""

FAIL = []


def chk(name, cond, note=""):
    print("  %s %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  ← " + note) if (note and not cond) else ""))
    if not cond:
        FAIL.append(name)


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2600)
    pg.evaluate("""(t)=>{const e=document.getElementById('editor');
        e.textContent=t;e.dispatchEvent(new Event('input',{bubbles:true}));}""", DOC)
    pg.wait_for_timeout(2200)
    # 保证字体表已就位（@@ begin font 的映射依赖它）
    pg.wait_for_timeout(1500)

    r = pg.evaluate(r"""() => {
      const pv = document.querySelector('#preview');
      const box = pv.querySelector('.mde-font');
      const pOf = (root, txt) => [...root.querySelectorAll('p')]
        .find(e => e.textContent.indexOf(txt) >= 0);
      const cs = e => e ? getComputedStyle(e) : null;
      const inP = box ? pOf(box, '块内正文段落') : null;
      const inH = box ? box.querySelector('h2') : null;
      const inLi = box ? box.querySelector('li') : null;
      const inCode = box ? box.querySelector('code') : null;
      const outP = [...pv.querySelectorAll('p')].find(e => e.textContent.indexOf('块外正文，应当') >= 0);
      const outP2 = [...pv.querySelectorAll('p')].find(e => e.textContent.indexOf('块外正文恢复默认') >= 0);
      const mg = pv.querySelectorAll('.mde-font').length;
      const multi = [...pv.querySelectorAll('.mde-font')]
        .find(e => e.textContent.indexOf('并写块') >= 0);
      const mp = multi ? pOf(multi, '并写块') : null;
      const bad = [...pv.querySelectorAll('p')].find(e => e.textContent.indexOf('参数非法') >= 0);
      return {
        fontBoxes: mg,
        boxStyle: box ? box.getAttribute('style') : '',
        boxAttrs: box ? box.getAttribute('data-ff') + '/' + box.getAttribute('data-fs') : '',
        inP: inP ? {ff: cs(inP).fontFamily, fw: cs(inP).fontWeight, fs: cs(inP).fontSize} : null,
        inH: inH ? {ff: cs(inH).fontFamily, fs: cs(inH).fontSize} : null,
        inLi: inLi ? {ff: cs(inLi).fontFamily, fs: cs(inLi).fontSize} : null,
        inCode: inCode ? {ff: cs(inCode).fontFamily, fs: cs(inCode).fontSize} : null,
        outP: outP ? {ff: cs(outP).fontFamily, fw: cs(outP).fontWeight, fs: cs(outP).fontSize} : null,
        outP2: outP2 ? {ff: cs(outP2).fontFamily, fs: cs(outP2).fontSize} : null,
        multi: mp ? {ff: cs(mp).fontFamily, fw: cs(mp).fontWeight, fs: cs(mp).fontSize,
                     color: cs(mp).color} : null,
        badRaw: [...pv.querySelectorAll('p')]
          .map(e => e.textContent).filter(t => t.indexOf('@@ begin font') >= 0)
          .join(' | ').slice(0, 60),
        badBody: bad ? bad.textContent.slice(0, 20) : null,
      };
    }""")

    print("\n[一] 容器生成")
    chk("生成了 .mde-font 容器", r["fontBoxes"] >= 2, "只有 %d 个" % r["fontBoxes"])
    chk("容器带 data-ff/data-fs", r["boxAttrs"] == "1/1", r["boxAttrs"])

    print("\n[二] 块内生效（Light 真实字重）")
    ip = r["inP"] or {}
    chk("块内 p 字体 = Microsoft YaHei Light",
        "Microsoft YaHei Light" in (ip.get("ff") or ""), ip.get("ff"))
    chk("块内 p 字重 = 290（字体文件真值）", ip.get("fw") == "290", ip.get("fw"))
    chk("块内 p 字号 = 16px（12pt）", ip.get("fs") == "16px", ip.get("fs"))
    ih = r["inH"] or {}
    chk("块内 h2 也被覆盖（字号 16px）", ih.get("fs") == "16px", ih.get("fs"))
    il = r["inLi"] or {}
    chk("块内 li 被覆盖", il.get("fs") == "16px" and "YaHei Light" in (il.get("ff") or ""),
        json.dumps(il, ensure_ascii=False))
    ic = r["inCode"] or {}
    chk("块内 code 被覆盖（与 ts 同集合）", ic.get("fs") == "16px", ic.get("fs"))

    print("\n[三] 块外不受影响")
    op = r["outP"] or {}
    chk("块外 p 字体不是 Light", "YaHei Light" not in (op.get("ff") or ""), op.get("ff"))
    chk("块外 p 字号不是 16px", op.get("fs") != "16px", op.get("fs"))
    op2 = r["outP2"] or {}
    chk("块后正文恢复默认字号", op2.get("fs") != "16px", op2.get("fs"))

    print("\n[四] 并写 page+font+color")
    mp = r["multi"] or {}
    chk("并写块字体 = KaiTi", "KaiTi" in (mp.get("ff") or "") or "楷体" in (mp.get("ff") or ""),
        mp.get("ff"))
    chk("并写块字号 = 14pt/18.666px", mp.get("fs", "").startswith("18.666"), mp.get("fs"))
    chk("并写块颜色 = #c0392b", mp.get("color") == "rgb(192, 57, 43)", mp.get("color"))

    print("\n[五] 非法参数 fail-closed")
    chk("字号越界的标记行原样露出", (r["badRaw"] or "").find("@@ begin font") >= 0, r["badRaw"])
    chk("内容照常渲染", (r["badBody"] or "").find("参数非法") >= 0, r["badBody"])

    chk("无 JS 错误", not errs, "; ".join(errs[:2]))

    pg.screenshot(path=os.path.abspath("Temp/_v233_font_preview.png"), full_page=False)
    b.close()

print("\n" + "=" * 46)
print("FAIL %d 项" % len(FAIL))
if FAIL:
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
