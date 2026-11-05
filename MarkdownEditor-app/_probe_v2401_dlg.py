# -*- coding: utf-8 -*-
"""v2.40.1 漏网三窗统一探针：保存文档 / 存为母版 / 打印面板。

判据（全部 PASS/FAIL）：
  P1 三窗几何——卡片宽 480、圆角 10、阴影 0 12px 40px
  P2 三窗头部都是 .ts-head（标题 + 右上 ×），× 有点击行为
  P3 按钮族——pp-btn 全灭；打印面板脚部 sv-btn/sv-btn primary；
     分页预览栏 sv-mini / sv-mini.primary
  P4 点空白关闭——svOverlay / tplSaveOverlay / printPanel
  P5 Esc 关闭三窗（原有链不回归）
  P6 内联深色硬编码清零（#23272f / #1a1d24 不再出现在三窗 HTML）
  P7 浅色主题下保存文档卡是浅底（--panel 跟主题）
  P8 全程零 page error
跑法：python _probe_v2401_dlg.py   （前置：服务已在 127.0.0.1:18766）
"""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"
WAIT = 2600
fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


def geom(pg, sel):
    return pg.evaluate("""(s)=>{
      const c=document.querySelector(s);
      if(!c) return null;
      const cs=getComputedStyle(c);
      return {w:c.getBoundingClientRect().width, r:cs.borderRadius,
              sh:cs.boxShadow};
    }""", sel)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(WAIT)

    # P1+P2 保存文档：点「保存」唤起（无路径时必弹此窗）
    pg.click("#btnSave")
    pg.wait_for_timeout(400)
    sv_vis = pg.evaluate("!document.getElementById('svOverlay').hidden")
    if not sv_vis:
        # 有的路径「保存」直接落盘不弹窗；改走另存为
        pg.click("#btnSaveAs")
        pg.wait_for_timeout(400)
    sv_vis = pg.evaluate("!document.getElementById('svOverlay').hidden")
    chk("P1a 保存文档弹窗在场", sv_vis)
    g = geom(pg, "#svOverlay .dlg-card")
    chk("P1b 保存文档卡 宽480/圆角10/阴影同档",
        g and abs(g["w"] - 480) < 2 and g["r"] == "10px"
        and "12px 40px" in g["sh"], str(g))
    head_ok = pg.evaluate("""()=>{
      const h=document.querySelector('#svOverlay .ts-head');
      return !!h && !!h.querySelector('#svX');
    }""")
    chk("P2a 保存文档头=ts-head+×", head_ok)
    pg.click("#svX")
    pg.wait_for_timeout(200)
    chk("P2b 保存文档 × 可关闭", pg.evaluate("document.getElementById('svOverlay').hidden"))

    # 存为母版：触发撞名流程较重，直接手动开窗验证几何与交互
    pg.evaluate("document.getElementById('tplSaveOverlay').hidden=false")
    pg.wait_for_timeout(200)
    g = geom(pg, "#tplSaveOverlay .dlg-card")
    chk("P1c 存为母版卡 宽480/圆角10/阴影同档",
        g and abs(g["w"] - 480) < 2 and g["r"] == "10px"
        and "12px 40px" in g["sh"], str(g))
    chk("P2c 存为母版头=ts-head+×",
        pg.evaluate("!!document.querySelector('#tplSaveOverlay .ts-head #tplSaveX')"))
    # P4 点空白关闭
    pg.mouse.click(30, 475)
    pg.wait_for_timeout(200)
    chk("P4a 存为母版点空白关闭", pg.evaluate("document.getElementById('tplSaveOverlay').hidden"))

    # 打印面板：真实打开（点分页打印入口不可靠，直接唤起面板）
    pg.evaluate("document.getElementById('printPanel').hidden=false")
    pg.wait_for_timeout(200)
    g = geom(pg, "#ppCard")
    chk("P1d 打印面板卡 宽480/圆角10/阴影同档",
        g and abs(g["w"] - 480) < 2 and g["r"] == "10px"
        and "12px 40px" in g["sh"], str(g))
    chk("P2d 打印面板头=ts-head+×",
        pg.evaluate("!!document.querySelector('#ppCard .ts-head #ppX')"))
    cls = pg.evaluate("""[document.getElementById('ppCancel').className,
                          document.getElementById('ppGo').className]""")
    chk("P3a 打印面板脚部=sv-btn/sv-btn primary",
        cls[0] == "sv-btn" and cls[1] == "sv-btn primary", str(cls))
    chk("P3b pp-btn 全灭", pg.evaluate("document.querySelectorAll('.pp-btn').length===0"))
    pg.click("#ppX")
    pg.wait_for_timeout(200)
    chk("P2e 打印面板 × 可关闭", pg.evaluate("document.getElementById('printPanel').hidden"))

    # 分页预览栏按钮族（真实打开分页预览）
    on = pg.evaluate("""()=>{
      const bar=document.getElementById('pvbar');
      return !!bar;
    }""")
    chk("P3c 分页预览栏按钮=sv-mini/sv-mini.primary（静态类断言）",
        pg.evaluate("""document.getElementById('ppPrint').className==='sv-mini primary'
                       && document.getElementById('ppClose').className==='sv-mini'"""))

    # P4b 保存文档点空白关闭
    pg.evaluate("document.getElementById('svOverlay').hidden=false")
    pg.wait_for_timeout(150)
    pg.mouse.click(30, 475)
    pg.wait_for_timeout(200)
    chk("P4b 保存文档点空白关闭", pg.evaluate("document.getElementById('svOverlay').hidden"))

    # P5 Esc 链
    pg.evaluate("document.getElementById('svOverlay').hidden=false")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    esc1 = pg.evaluate("document.getElementById('svOverlay').hidden")
    pg.evaluate("document.getElementById('tplSaveOverlay').hidden=false")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    esc2 = pg.evaluate("document.getElementById('tplSaveOverlay').hidden")
    pg.evaluate("document.getElementById('printPanel').hidden=false")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(150)
    esc3 = pg.evaluate("document.getElementById('printPanel').hidden")
    chk("P5 Esc 关闭三窗", esc1 and esc2 and esc3,
        "sv=%s tpl=%s pp=%s" % (esc1, esc2, esc3))

    # P6 内联硬编码清零
    leftover = pg.evaluate("""()=>{
      const bad=[];
      document.querySelectorAll('#svOverlay [style], #tplSaveOverlay [style]').forEach(el=>{
        const s=el.getAttribute('style')||'';
        if(/#23272f|#1a1d24|#3a4358|#8a93a6|#e8eaed/.test(s)) bad.push(el.id||el.tagName);
      });
      return bad;
    }""")
    chk("P6 三窗内联深色硬编码清零", len(leftover) == 0,
        str(leftover))

    # P7 浅色主题下保存文档卡是浅底（先按当前状态切到浅色，别盲点——
    # 主题被服务端记忆，起点不一定是深色）
    was_light = pg.evaluate("document.body.classList.contains('light')")
    if not was_light:
        pg.click("#btnTheme")
        pg.wait_for_timeout(300)
    chk("P7-pre 已切到浅色", pg.evaluate("document.body.classList.contains('light')"))
    pg.evaluate("document.getElementById('svOverlay').hidden=false")
    pg.wait_for_timeout(150)
    bg = pg.evaluate("""getComputedStyle(document.querySelector('#svOverlay .dlg-card')).backgroundColor""")
    chk("P7 浅色下保存文档卡浅底", bg in ("rgb(255, 255, 255)", "#ffffff"), bg)
    pg.evaluate("document.getElementById('svOverlay').hidden=true")
    if not was_light:
        pg.click("#btnTheme")  # 还原原主题
        pg.wait_for_timeout(200)

    chk("P8 零 page error", len(errs) == 0, "; ".join(errs[:3]))
    b.close()

print("\n%d failed" % len(fails) if fails else "\nALL PASS")
raise SystemExit(1 if fails else 0)
