# -*- coding: utf-8 -*-
"""v2.40.0 前端专项：预览栏横栏 / 字段隔离 / 母版排版套用与撤销。

判据（全部 PASS/FAIL，不看"看起来对"）：
  T1 横栏就绪——#pvbar 在场、四框有值、预设 6 项、默认值命中「常规」
  T2 横栏改值立即落盘（change 即写 tsCfg.page.ml）
  T3 面板「应用」不冲掉横栏刚改的边距（字段归属隔离）
  T4 母版排版套用——字体/边距/表格三态生效，横栏同步，状态栏出撤销入口
  T5 撤销还原到套用前快照
  T6 空 typeset（旧母版）返回 None、不改任何值
  T8 打印▾ 菜单定位——贴三角下方、不越出视口（曾经整条漏 CSS，掉到页面最底部）
  T9 全程零 page error

跑法：python _test_v2400_ui.py      （需系统 python + playwright；不要用便携 python）
前置：**必须先把服务跑起来**（`MarkdownEditor.exe`，或 `python md_server.py`）——
      file:// 直开会被页内守卫替换成「请使用正确方式打开」，整页 DOM 不存在，
      看起来就像「横栏没做」。v2.40.0 期间就是这样误判过一次。
说明：页面初始化约需 2600ms——等待过短会把"还没初始化"误判成"按钮失效"。
"""
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"
TS_KEY = "md-editor-typeset-v3"
WAIT = 2600

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


def ls(pg):
    return pg.evaluate("() => JSON.parse(localStorage.getItem('%s')||'{}')" % TS_KEY)


def server_up():
    try:
        urllib.request.urlopen(URL + "api/version", timeout=3).read()
        return True
    except Exception:
        return False


def main():
    if not server_up():
        print("FAIL  服务未启动：先跑 MarkdownEditor.exe 或 python md_server.py")
        return 1
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1360, "height": 860})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(WAIT)

        # ---- 先记下本机现有设置：排版设置落在服务端 runtime/ui-settings.json，
        #      是**全局**的，测试改完必须还原，否则会把主人自己的页边距改掉。
        #      （首轮就是这么把 ml 留在 33 上的，T1 随即因为"默认值不是 25/18"
        #      而 FAIL——那不是功能坏了，是测试污染了自己的前提。）----
        orig = pg.evaluate("""() => ({mt:document.getElementById('pvMt').value,
          mr:document.getElementById('pvMr').value, mb:document.getElementById('pvMb').value,
          ml:document.getElementById('pvMl').value,
          guide:document.getElementById('pvGuide').checked})""")

        # ---- T1 横栏就绪（先切「常规」再断言，不依赖本机当前设置）----
        pg.evaluate("""() => { const s=document.getElementById('pvPreset');
          s.value='regular'; s.dispatchEvent(new Event('change',{bubbles:true})); }""")
        pg.wait_for_timeout(300)
        bar = pg.evaluate("() => { const b=document.getElementById('pvbar'); "
                          "return b ? {w:b.getBoundingClientRect().width, "
                          "disp:getComputedStyle(b).display} : null; }")
        opts = pg.evaluate("() => Array.from(document.getElementById('pvPreset').options)"
                           ".map(o=>o.value)")
        vals = pg.evaluate("() => ['pvMt','pvMr','pvMb','pvMl']"
                           ".map(i=>document.getElementById(i).value)")
        preset = pg.evaluate("() => document.getElementById('pvPreset').value")
        chk("T1 横栏就绪", bool(bar) and bar["disp"] != "none" and bar["w"] > 200
            and len(opts) == 6 and vals == ["25", "18", "25", "18"]
            and preset == "regular",
            "w=%s opts=%s vals=%s preset=%s" % (
                bool(bar) and round(bar["w"]), opts, vals, preset))

        # ---- T2 横栏改值立即落盘 ----
        pg.fill("#pvMl", "33")
        pg.dispatch_event("#pvMl", "change")
        pg.wait_for_timeout(300)
        c = ls(pg)
        chk("T2 横栏改值立即落盘", c.get("page", {}).get("ml") == 33,
            "ml=%s" % c.get("page", {}).get("ml"))

        # ---- T3 面板应用不冲掉横栏边距 ----
        pg.click("#btnTypeset")
        pg.wait_for_timeout(600)
        pg.evaluate("""() => { const s=document.querySelector('select[data-ts="p"]');
          if(s && s.options.length){ s.value=s.options[0].value;
            s.dispatchEvent(new Event('change',{bubbles:true})); } }""")
        pg.click("#tsApply")
        pg.wait_for_timeout(600)
        c = ls(pg)
        chk("T3 面板应用不冲掉横栏边距",
            c.get("page", {}).get("ml") == 33 and c.get("page", {}).get("mt") == 25,
            "ml=%s mt=%s" % (c.get("page", {}).get("ml"), c.get("page", {}).get("mt")))

        # ---- T4 母版排版套用 ----
        before = ls(pg)
        pg.evaluate("""() => { window.__prev = window.__mdeApplyTypeset({v:1,
          page:{mt:40, ml:12}, fonts:{p:{s:'20'}}, table:{three:true}}); }""")
        pg.wait_for_timeout(500)
        mid = ls(pg)
        bar_mt = pg.evaluate("() => document.getElementById('pvMt').value")
        stat = pg.evaluate("() => document.getElementById('statSave').textContent")
        ok4 = (mid.get("page", {}).get("mt") == 40 and mid.get("page", {}).get("ml") == 12
               and mid.get("fonts", {}).get("p", {}).get("s") == "20"
               and mid.get("table", {}).get("three") is True
               and bar_mt == "40" and "撤销" in (stat or ""))
        chk("T4 母版排版套用", ok4,
            "mt=%s ml=%s p.s=%s three=%s 横栏=%s 状态栏=%r" % (
                mid.get("page", {}).get("mt"), mid.get("page", {}).get("ml"),
                mid.get("fonts", {}).get("p", {}).get("s"),
                mid.get("table", {}).get("three"), bar_mt, stat))

        # ---- T5 撤销还原 ----
        pg.click("#statSave")
        pg.wait_for_timeout(500)
        after = ls(pg)
        chk("T5 撤销还原", after == before,
            "mt=%s ml=%s 还原=%s" % (after.get("page", {}).get("mt"),
                                     after.get("page", {}).get("ml"), after == before))

        # ---- T6 旧母版（无 typeset）不改任何值 ----
        b6 = ls(pg)
        r = pg.evaluate("() => window.__mdeApplyTypeset(null)")
        chk("T6 空 typeset 不改值", r is None and ls(pg) == b6, "ret=%r" % (r,))

        # ---- T8 打印▾ 菜单位置 ----
        pg.click("#btnPrintMore")
        pg.wait_for_timeout(250)
        box = pg.evaluate("""() => { const m=document.getElementById('printMenu');
          const b=document.getElementById('btnPrintMore');
          if(!m||!b||m.hidden) return null;
          const r=m.getBoundingClientRect(), q=b.getBoundingClientRect();
          return {left:r.left, top:r.top, right:r.right, bottom:r.bottom,
                  btop:q.bottom, pos:getComputedStyle(m).position,
                  vw:window.innerWidth, vh:window.innerHeight}; }""")
        ok8 = bool(box) and box["pos"] == "fixed" \
            and box["top"] >= box["btop"] - 2 and box["top"] < box["btop"] + 40 \
            and box["left"] >= 0 and box["right"] <= box["vw"] \
            and box["bottom"] <= box["vh"]
        chk("T8 打印▾ 菜单定位", ok8, "%s" % (box and {
            k: (round(v) if isinstance(v, (int, float)) else v) for k, v in box.items()},))
        pg.keyboard.press("Escape")
        pg.mouse.click(5, 5)
        pg.wait_for_timeout(200)

        # ---- T9 零 page error ----
        chk("T9 零 page error", not errs, " | ".join(errs[:3]))

        # ---- T10 还原主人原有设置（排版设置是本机全局，测试不许留痕）----
        pg.evaluate("""(o) => {
          const ids=['pvMt','pvMr','pvMb','pvMl'], keys=['mt','mr','mb','ml'];
          for(let i=0;i<4;i++){ const el=document.getElementById(ids[i]);
            el.value=o[keys[i]]; el.dispatchEvent(new Event('change',{bubbles:true})); }
          const g=document.getElementById('pvGuide');
          if(g.checked!==o.guide){ g.checked=o.guide; g.dispatchEvent(new Event('change',{bubbles:true})); }
        }""", orig)
        pg.wait_for_timeout(400)
        back = pg.evaluate("""() => ({mt:document.getElementById('pvMt').value,
          mr:document.getElementById('pvMr').value, mb:document.getElementById('pvMb').value,
          ml:document.getElementById('pvMl').value,
          guide:document.getElementById('pvGuide').checked})""")
        chk("T10 设置已还原", back == orig, "%s vs %s" % (back, orig))

        b.close()

    total = 9 - len(fails)
    print("\n====================================================")
    print("PASS %d / FAIL %d" % (total, len(fails)))
    if fails:
        print("失败项：" + " | ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
