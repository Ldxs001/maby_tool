# -*- coding: utf-8 -*-
"""v2.41.1 前端专项：修上一轮四处偏差 + 公式面板（方案 §7）。

判据（全部 PASS/FAIL）：
  U1 #rmenu 定位——分屏▾/保存▾/配置▾ 的下拉必须贴三角下方（此前漏 CSS
     掉到 body 末尾＝左下角）
  U2 三角样式统一——所有 .tb-caret 都在 .tb-split 里、字号 9px（此前六组
     格式三角裸挂，渲染成正常按钮大小）
  U3 插入链接弹窗——主按钮开窗、文字+地址两栏、插入 [文字](地址)
  U4 公式面板·分数——点 a/b 填两格 → 插入 $\frac{a}{b}$
  U5 公式面板·四角标——左上3 左下4 中心X → ${}^{3}_{4}X$（前置角标拼法）
  U6 槽位递归——分数的下格放四角标 → $\frac{a}{{}^{c}_{d}b}$
  U7 空中心拒绝——只有角标没有主体 → 面板不关、报错、编辑区不动
  U8 大运算符——∑ 变体（中心预填）+ 右侧上下标 → $\sum^{n}_{1}$
  U9 帽线——x̄ 默认 → $\overline{x}$
  U10 容器·矩阵——pmatrix 2×2 → \begin{pmatrix}a & b \\ c & d\end{pmatrix}
  U11 插入物过 KaTeX 闸门后预览区真的渲染出公式
  U12 全程零 page error

跑法：python _test_v2410_ui.py    （需系统 python + playwright；不要用便携 python）
前置：**必须先把服务跑起来**（MarkdownEditor.exe 或 python md_server.py）。
说明：页面初始化约需 2600ms。
"""
import sys
import urllib.request

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"
WAIT = 2600

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


def server_up():
    try:
        urllib.request.urlopen(URL + "api/version", timeout=3).read()
        return True
    except Exception:
        return False


def set_editor(pg, text):
    pg.evaluate("""(t) => { const ed=document.getElementById('editor');
      ed.textContent=t; ed.dispatchEvent(new Event('input',{bubbles:true})); }""", text)


def editor_text(pg):
    return pg.evaluate("() => document.getElementById('editor').textContent")


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

        # ---- U1 rmenu 定位（保存▾：右侧三角，菜单必须贴其下方）----
        pg.evaluate("document.getElementById('btnSaveMore').click()")
        pg.wait_for_timeout(250)
        box = pg.evaluate("""() => { const m=document.getElementById('rmenu');
          const btn=document.getElementById('btnSaveMore');
          if(!m||m.hidden) return null;
          const r=m.getBoundingClientRect(), q=btn.getBoundingClientRect();
          return {pos:getComputedStyle(m).position, left:r.left, top:r.top,
                  right:r.right, bottom:r.bottom, btop:q.bottom, bleft:q.left,
                  vw:innerWidth, vh:innerHeight}; }""")
        ok1 = bool(box) and box["pos"] == "fixed" \
            and box["top"] >= box["btop"] - 2 and box["top"] < box["btop"] + 40 \
            and box["left"] >= 0 and box["right"] <= box["vw"] \
            and box["bottom"] <= box["vh"] - 20
        chk("U1 rmenu 定位贴三角下方", ok1, "%s" % (box and {
            k: (round(v) if isinstance(v, (int, float)) else v)
            for k, v in box.items()},))
        pg.keyboard.press("Escape")
        pg.mouse.click(5, 300)
        pg.wait_for_timeout(200)

        # ---- U2 三角样式统一 ----
        carets = pg.evaluate("""() => Array.from(
          document.querySelectorAll('#toolbar .tb-btn.tb-caret')).map(c => ({
          id: c.id || c.textContent, fs: getComputedStyle(c).fontSize,
          inSplit: !!c.closest('.tb-split'), h: c.getBoundingClientRect().height
        }))""")
        bad = [c for c in carets if not c["inSplit"] or c["fs"] != "9px"]
        chk("U2 三角样式统一（%d 个）" % len(carets),
            len(carets) >= 10 and not bad, "不合规=%s" % bad[:4])

        # ---- U3 插入链接弹窗 ----
        set_editor(pg, "去这里看看")
        pg.evaluate("""() => { const ed=document.getElementById('editor');
          ed.focus();
          const sel=getSelection(); sel.removeAllRanges();
          const r=document.createRange();
          r.selectNodeContents(ed); sel.addRange(r); }""")
        pg.evaluate("""() => { const btns=document.querySelectorAll('#fmtBtns button');
          for(const x of btns){ if(x.textContent==='链接' && !x.classList.contains('tb-caret')){ x.click(); return; } } }""")
        pg.wait_for_timeout(300)
        vis = pg.evaluate("() => !document.getElementById('linkOverlay').hidden")
        chk("U3a 链接主按钮开弹窗", vis)
        pg.fill("#lkUrl", "https://example.dev")
        pg.click("#lkGo")
        pg.wait_for_timeout(300)
        t3 = editor_text(pg)
        chk("U3b 弹窗插入 [文字](地址)",
            t3 == "[去这里看看](https://example.dev)", repr(t3))

        # ---- 公式面板通用步骤 ----
        def eq_reset():
            # 光标收到文末再开面板：上一次 insertPlainText 留下的可能是
            # 展开选区，直接开面板会把选区内容替换掉（U4 首轮实测）
            pg.evaluate("""() => { const ed=document.getElementById('editor');
              ed.focus();
              const sel=getSelection(); sel.removeAllRanges();
              const r=document.createRange();
              r.selectNodeContents(ed); r.collapse(false);
              sel.addRange(r); }""")
            pg.evaluate("document.getElementById('btnMath').click()")
            pg.wait_for_timeout(200)
            pg.evaluate("document.getElementById('eqClear').click()")
            pg.wait_for_timeout(120)

        def eq_tpl(v):
            pg.evaluate(
                "(v) => document.querySelector('#eqTplbar [data-eqv=\"%s\"]').click()" % v, v)
            pg.wait_for_timeout(150)

        def fill_slot(role, text):
            pg.evaluate("""(role) => { const s=document.querySelector(
              '#eqCanvas .eq-slot[data-role="'+role+'"]');
              s.focus();
              const sel=getSelection(); sel.removeAllRanges();
              const r=document.createRange(); r.selectNodeContents(s);
              sel.addRange(r); }""", role)
            pg.keyboard.type(text)   # 有选区：打字即整段替换；空槽：直接落入

        def eq_insert():
            pg.evaluate("document.getElementById('eqInsert').click()")
            pg.wait_for_timeout(250)

        # ---- U4 分数 ----
        eq_reset()
        eq_tpl("frac")
        fill_slot("num", "a")
        fill_slot("den", "b")
        eq_insert()
        t4 = editor_text(pg)
        chk("U4 分数 → $\\frac{a}{b}$", t4.endswith("$\\frac{a}{b}$"), repr(t4[-30:]))

        # ---- U5 四角标（前置角标拼法）----
        eq_reset()
        eq_tpl("script")
        fill_slot("lt", "3")
        fill_slot("lb", "4")
        fill_slot("c", "X")
        eq_insert()
        t5 = editor_text(pg)
        chk("U5 四角标 → ${}^{3}_{4}X$", t5.endswith("${}^{3}_{4}X$"), repr(t5[-30:]))

        # ---- U6 槽位递归：分数下格放四角标 ----
        eq_reset()
        eq_tpl("frac")
        fill_slot("num", "a")
        pg.evaluate("""() => { const s=document.querySelector(
          '#eqCanvas .eq-slot[data-role="den"]'); s.focus();
          const sel=getSelection(); sel.removeAllRanges();
          const r=document.createRange(); r.selectNodeContents(s); r.collapse(false);
          sel.addRange(r); }""")
        eq_tpl("script")
        fill_slot("lt", "c")
        fill_slot("lb", "d")
        fill_slot("c", "b")
        eq_insert()
        t6 = editor_text(pg)
        chk("U6 槽位递归 → $\\frac{a}{{}^{c}_{d}b}$",
            t6.endswith("$\\frac{a}{{}^{c}_{d}b}$"), repr(t6[-34:]))

        # ---- U7 空中心拒绝 ----
        eq_reset()
        eq_tpl("script")
        fill_slot("rt", "2")
        before7 = editor_text(pg)
        eq_insert()
        overlay_open = pg.evaluate("() => !document.getElementById('eqOverlay').hidden")
        msg = pg.evaluate("() => document.getElementById('eqMsg').textContent")
        chk("U7 空中心拒绝（面板不关+报错+编辑区不动）",
            overlay_open and bool(msg) and editor_text(pg) == before7,
            "open=%s msg=%r" % (overlay_open, msg))
        pg.evaluate("document.getElementById('eqX').click()")
        pg.wait_for_timeout(150)

        # ---- U8 大运算符 ∑ ----
        eq_reset()
        pg.evaluate("""() => { const b=document.querySelector(
          '#eqTplbar [data-eqv="script:"]'); b.click(); }""")
        pg.wait_for_timeout(200)
        pg.evaluate("""() => { const items=document.querySelectorAll('#eqMenu button');
          for(const x of items){ if(x.textContent.indexOf('求和')>=0){ x.click(); return; } } }""")
        pg.wait_for_timeout(200)
        fill_slot("rt", "n")
        fill_slot("rb", "1")
        eq_insert()
        t8 = editor_text(pg)
        chk("U8 大运算符 → $\\sum^{n}_{1}$", t8.endswith("$\\sum^{n}_{1}$"), repr(t8[-30:]))

        # ---- U9 帽线 ----
        eq_reset()
        eq_tpl("accent")
        fill_slot("body", "x")
        eq_insert()
        t9 = editor_text(pg)
        chk("U9 帽线 → $\\overline{x}$", t9.endswith("$\\overline{x}$"), repr(t9[-30:]))

        # ---- U10 矩阵 ----
        eq_reset()
        pg.evaluate("() => document.querySelector('#eqTplbar [data-eqv=\"delim:\"]').click()")
        pg.wait_for_timeout(200)
        pg.evaluate("""() => { const items=document.querySelectorAll('#eqMenu button');
          for(const x of items){ if(x.textContent.indexOf('矩阵（圆括号')>=0){ x.click(); return; } } }""")
        pg.wait_for_timeout(200)
        cells = pg.evaluate("""() => Array.from(document.querySelectorAll(
          '#eqCanvas .eq-grid .eq-slot')).map(s=>s.getAttribute('data-role'))""")
        for i, role in enumerate(cells):
            fill_slot(role, "abcd"[i])
        eq_insert()
        t10 = editor_text(pg)
        want10 = "$\\begin{pmatrix}a & b \\\\ c & d\\end{pmatrix}$"
        chk("U10 矩阵 pmatrix", t10.endswith(want10), repr(t10[-46:]))

        # ---- U11 预览区真的渲染出公式 ----
        pg.evaluate("() => { document.getElementById('editor').focus(); }")
        pg.wait_for_timeout(900)
        kat = pg.evaluate("""() => { const pv=document.getElementById('preview');
          return {n: pv.querySelectorAll('.katex').length,
                  frac: pv.innerHTML.indexOf('frac')>=0}; }""")
        chk("U11 预览区 KaTeX 渲染", kat["n"] >= 3, "%s" % kat)

        # ---- U12 零 page error ----
        chk("U12 零 page error", not errs, " | ".join(errs[:3]))

        b.close()

    total = 12 - len(fails)
    print("\n====================================================")
    print("PASS %d / FAIL %d" % (total, len(fails)))
    if fails:
        print("失败项：" + " | ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
