# -*- coding: utf-8 -*-
"""参考线开关几何实证 v2：量真实文字元素 + 现场还原。

关键修正：
  - 量 #preview 下所有带直接文本的元素（前 8 个）的 tag/fontSize/clientWidth
  - 开始前记录 tsCfg.page 的 guide 与四边距，结束原样还原（不污染机器配置）
"""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"
WAIT = 2600

SNAP = """()=>{
  const pv=document.getElementById('preview');
  const pane=document.getElementById('previewPane');
  const out=[];
  const walk=(n)=>{
    for(const c of n.childNodes){
      if(c.nodeType===3 && c.textContent.trim().length>3){
        const r=c.parentElement.getBoundingClientRect();
        const cs=getComputedStyle(c.parentElement);
        out.push({tag:c.parentElement.tagName, fs:cs.fontSize, w:Math.round(r.width*10)/10,
                  x:Math.round(r.left)});
      } else if(c.nodeType===1 && out.length<8){
        walk(c);
      }
      if(out.length>=8) return;
    }
  };
  walk(pv);
  return {items:out, pvW:pv.clientWidth, pvPad:getComputedStyle(pv).padding};
}"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1360, "height": 860})
    pg.goto(URL)
    pg.wait_for_timeout(WAIT)

    # 现场存档
    orig = pg.evaluate("""()=>{
      const g=document.getElementById('pvGuide');
      const v=['pvMt','pvMr','pvMb','pvMl'].map(i=>document.getElementById(i).value);
      return {guide:g.checked, m:v};
    }""")
    print("现场：guide=%s 边距=%s" % (orig["guide"], orig["m"]))
    # 统一切到关闭态做基线
    if orig["guide"]:
        pg.uncheck("#pvGuide")
        pg.wait_for_timeout(300)

    off = pg.evaluate(SNAP)
    print("\n=== 参考线关 ===")
    print("  #preview 宽=%s padding=%s" % (off["pvW"], off["pvPad"]))
    for it in off["items"]:
        print("  %-4s 字号=%s 宽=%s 左=%s" % (it["tag"], it["fs"], it["w"], it["x"]))

    pg.check("#pvGuide")
    pg.wait_for_timeout(400)
    on = pg.evaluate(SNAP)
    print("\n=== 参考线开 ===")
    print("  #preview 宽=%s padding=%s" % (on["pvW"], on["pvPad"]))
    for it in on["items"]:
        print("  %-4s 字号=%s 宽=%s 左=%s" % (it["tag"], it["fs"], it["w"], it["x"]))

    diff = []
    for a, c in zip(off["items"], on["items"]):
        if a["fs"] != c["fs"]:
            diff.append("%s 字号 %s→%s" % (a["tag"], a["fs"], c["fs"]))
        if a["w"] != c["w"]:
            diff.append("%s 宽 %s→%s" % (a["tag"], a["w"], c["w"]))
    print("\n判定：" + ("全部文字元素字号与宽度逐项相等（内容没放大）" if not diff else "差异！ " + "; ".join(diff)))

    # 还原现场
    pg.uncheck("#pvGuide")
    ids = ['pvMt', 'pvMr', 'pvMb', 'pvMl']
    for i, v in enumerate(orig["m"]):
        pg.fill("#" + ids[i], v)
        pg.evaluate("""(id)=>document.getElementById(id).dispatchEvent(new Event('change'))""", ids[i])
    if orig["guide"]:
        pg.check("#pvGuide")
    pg.wait_for_timeout(300)
    now = pg.evaluate("""()=>({guide:document.getElementById('pvGuide').checked,
        m:['pvMt','pvMr','pvMb','pvMl'].map(i=>document.getElementById(i).value)})""")
    print("\n还原：guide=%s 边距=%s  %s" % (now["guide"], now["m"],
          "OK" if now["m"] == orig["m"] and now["guide"] == orig["guide"] else "不一致!"))
    b.close()
