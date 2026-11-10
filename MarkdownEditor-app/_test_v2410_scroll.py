# -*- coding: utf-8 -*-
"""v2.41.0 验收后专项：开窗插入的滚动守恒 + 列表▾ 缩进两项已删除。

判据（全部 PASS/FAIL，12 项）：
  S1  表格弹窗插入：编辑区 / 预览栏滚动守恒，落点与光标正确
  S2  表格弹窗取消：滚动守恒
  S3  链接弹窗插入：滚动守恒 + `[文字](地址)` 落在原光标处
  S4  链接弹窗取消：滚动守恒
  S5  公式面板插入：滚动守恒 + `$\\frac{a}{b}$` 落在原光标处（execCommand 路径）
  S6  公式面板取消：滚动守恒
  S7  不开窗插入（B▾ 填空线）：原本就正常，不被修复带坏
  S8  列表▾ 只剩两项、无「缩进」字样
  S9  源码守门：唯一插入入口收编完整、setSel 未被塞滚动恢复
  S10 插入后手动滚动不被 rAF 兜底拉回
  S11 格式按钮四条分支收编后行为不变（wrap / 行前缀 / 标题级 / 无选区插入）
  S12 全程零 page error

跑法：python _test_v2410_scroll.py    （自起 18767 服务，跑完即关，零残留）
"""
import io
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = ["md_server.py"]
import md_server  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 18767
URL = "http://127.0.0.1:%d/" % PORT
TOL = 2

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


HELPERS = r"""() => {
  const ed=document.getElementById('editor');
  const pv=document.getElementById('previewPane');
  window.__ed=ed; window.__pv=pv;
  window.__caret=function(){
    const s=getSelection();
    if(!s||!s.rangeCount) return -1;
    const r=s.getRangeAt(0);
    if(r.startContainer!==ed&&!ed.contains(r.startContainer)) return -2;
    const p=document.createRange(); p.setStart(ed,0);
    p.setEnd(r.startContainer,r.startOffset);
    return p.toString().length;
  };
  window.__setCaret=function(pos){
    let acc=0,node=null,off=0;
    const w=document.createTreeWalker(ed,NodeFilter.SHOW_TEXT); let n;
    while((n=w.nextNode())){ if(pos<=acc+n.nodeValue.length){node=n;off=pos-acc;break;} acc+=n.nodeValue.length; }
    if(!node){node=ed;off=0;}
    const r=document.createRange(); r.setStart(node,off); r.setEnd(node,off);
    ed.focus(); const s=getSelection(); s.removeAllRanges(); s.addRange(r);
  };
  window.__setDoc=function(t){
    ed.textContent=t; ed.dispatchEvent(new Event('input',{bubbles:true}));
  };
  window.__state=function(){
    return {caret:window.__caret(), edTop:ed.scrollTop, pvTop:pv.scrollTop,
            len:ed.textContent.length};
  };
  window.__btn=function(label){
    return [...document.querySelectorAll('#fmtBtns .tb-split .tb-btn')]
      .find(b=>b.textContent===label && !b.classList.contains('tb-caret'));
  };
  window.__caretBtn=function(label){
    const sp=[...document.querySelectorAll('#fmtBtns .tb-split')]
      .find(x=>{const b=x.querySelector('.tb-btn'); return b && b.textContent===label;});
    return sp && sp.querySelector('.tb-caret');
  };
}"""

DOC = "\n".join(["第 %03d 行正文内容，用于把文档撑到需要滚动的高度。" % i
                 for i in range(1, 121)])
MARK = "第 080 行正文内容，用于把文档撑到需要滚动的高度。"
POS = DOC.index(MARK) + 12


def state(pg):
    return pg.evaluate("() => window.__state()")


def reset(pg):
    pg.evaluate("(t)=>window.__setDoc(t)", DOC)
    pg.wait_for_timeout(750)
    pg.evaluate("(p)=>window.__setCaret(p)", POS)   # 先 focus
    pg.evaluate("""() => { window.__ed.scrollTop=1400; window.__pv.scrollTop=700; }""")
    pg.wait_for_timeout(220)
    return state(pg)


def held(before, after):
    return (abs(before["edTop"] - after["edTop"]) <= TOL
            and abs(before["pvTop"] - after["pvTop"]) <= TOL)


def fill_slot(pg, role, text):
    pg.evaluate("""(role) => { const s=document.querySelector(
      '#eqCanvas .eq-slot[data-role="'+role+'"]');
      s.focus();
      const sel=getSelection(); sel.removeAllRanges();
      const r=document.createRange(); r.selectNodeContents(s);
      sel.addRange(r); }""", role)
    pg.keyboard.type(text)


def main():
    httpd = md_server.ReuseTCPServer(("127.0.0.1", PORT), md_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1360, "height": 860})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(URL)
            pg.wait_for_timeout(2600)
            pg.evaluate(HELPERS)

            # ---- S1 表格弹窗插入 ----
            before = reset(pg)
            pg.evaluate("() => window.__btn('表格').click()")
            pg.wait_for_timeout(250)
            pg.evaluate("() => document.getElementById('tbInsert').click()")
            pg.wait_for_timeout(950)
            after = state(pg)
            txt = pg.evaluate("() => document.getElementById('editor').textContent")
            pipe = txt.find("|")
            chk("S1 表格插入滚动守恒 + 落点/光标正确",
                held(before, after) and abs(pipe - POS) < 120 and after["caret"] > POS,
                "before=%s after=%s pipe=%d pos=%d" % (before, after, pipe, POS))

            # ---- S2 表格弹窗取消 ----
            before = reset(pg)
            pg.evaluate("() => window.__btn('表格').click()")
            pg.wait_for_timeout(250)
            pg.evaluate("() => document.getElementById('tbCancel').click()")
            pg.wait_for_timeout(700)
            after = state(pg)
            chk("S2 表格取消滚动守恒", held(before, after),
                "before=%s after=%s" % (before, after))

            # ---- S3 链接弹窗插入 ----
            before = reset(pg)
            pg.evaluate("() => window.__btn('链接').click()")
            pg.wait_for_timeout(250)
            pg.fill("#lkText", "示例链接")
            pg.fill("#lkUrl", "https://example.dev")
            pg.evaluate("() => document.getElementById('lkGo').click()")
            pg.wait_for_timeout(900)
            after = state(pg)
            txt = pg.evaluate("() => document.getElementById('editor').textContent")
            at = txt.find("[示例链接](https://example.dev)")
            chk("S3 链接插入滚动守恒 + 内容正确",
                held(before, after) and abs(at - POS) < 8,
                "before=%s after=%s at=%d pos=%d" % (before, after, at, POS))

            # ---- S4 链接弹窗取消 ----
            before = reset(pg)
            pg.evaluate("() => window.__btn('链接').click()")
            pg.wait_for_timeout(250)
            pg.evaluate("() => document.getElementById('lkCancel').click()")
            pg.wait_for_timeout(700)
            after = state(pg)
            chk("S4 链接取消滚动守恒", held(before, after),
                "before=%s after=%s" % (before, after))

            # ---- S5 公式面板插入（execCommand 路径）----
            before = reset(pg)
            pg.evaluate("() => document.getElementById('btnMath').click()")
            pg.wait_for_timeout(250)
            pg.evaluate("() => document.getElementById('eqClear').click()")
            pg.wait_for_timeout(120)
            pg.evaluate("""() => document.querySelector(
              '#eqTplbar [data-eqv="frac"]').click()""")
            pg.wait_for_timeout(150)
            fill_slot(pg, "num", "a")
            fill_slot(pg, "den", "b")
            pg.evaluate("() => document.getElementById('eqInsert').click()")
            pg.wait_for_timeout(900)
            after = state(pg)
            txt = pg.evaluate("() => document.getElementById('editor').textContent")
            at = txt.find("$\\frac{a}{b}$")
            chk("S5 公式插入滚动守恒 + 落点正确",
                held(before, after) and at > 0 and abs(at - POS) < 80,
                "before=%s after=%s at=%d pos=%d" % (before, after, at, POS))

            # ---- S6 公式面板取消 ----
            before = reset(pg)
            pg.evaluate("() => document.getElementById('btnMath').click()")
            pg.wait_for_timeout(250)
            pg.evaluate("() => document.getElementById('eqX').click()")
            pg.wait_for_timeout(700)
            after = state(pg)
            chk("S6 公式取消滚动守恒", held(before, after),
                "before=%s after=%s" % (before, after))

            # ---- S7 不开窗插入（B▾ 填空线）----
            before = reset(pg)
            pg.evaluate("() => window.__caretBtn('B').click()")
            pg.wait_for_timeout(180)
            pg.evaluate("""() => { const bs=[...document.querySelectorAll('#fmtMenu button')];
              const x=bs.find(b=>b.textContent.indexOf('填空线')>=0); x.click(); }""")
            pg.wait_for_timeout(850)
            after = state(pg)
            txt = pg.evaluate("() => document.getElementById('editor').textContent")
            chk("S7 不开窗插入滚动守恒 + 内容正确",
                held(before, after) and "++{0 x 9}++" in txt,
                "before=%s after=%s" % (before, after))

            # ---- S8 列表▾ 只剩两项 ----
            items = pg.evaluate("""() => { window.__caretBtn('列表').click();
              return [...document.querySelectorAll('#fmtMenu button')]
                .map(b=>b.textContent); }""")
            pg.keyboard.press("Escape")
            pg.mouse.click(5, 300)
            pg.wait_for_timeout(150)
            chk("S8 列表▾ 无缩进两项且其余完好",
                len(items) == 2 and not any("缩进" in x for x in items)
                and any("有序" in x for x in items)
                and any("任务" in x for x in items),
                repr(items))

            # ---- S9 源码守门 ----
            src = io.open(os.path.join(HERE, "markdown-editor.html"),
                          encoding="utf-8").read()
            body = src.split("function setSel(s,e){", 1)[1].split(
                "function insertPlainText", 1)[0]
            # v2.41.0 V2（方案 §11）新增三处合法入口，计数随收编同步、不是放宽：
            #   图片弹窗网络插入 +1 replaceAtCaret；
            #   两条唯一落盘函数各 +1 insertNativeAtCaret（共 +2）；
            #   图片弹窗关闭 +1 focusKeepScroll。
            chk("S9 唯一入口收编完整 + setSel 未改",
                src.count("fmtIndentLines") == 0
                and src.count("replaceAtCaret(") == 10
                and src.count("insertNativeAtCaret(") == 4
                and src.count("focusKeepScroll(") == 5
                and src.count("_insRestore(sc);") == 3
                and "scrollTop" not in body and "_insRestore" not in body,
                "replace=%d native=%d focus=%d restore=%d"
                % (src.count("replaceAtCaret("), src.count("insertNativeAtCaret("),
                   src.count("focusKeepScroll("), src.count("_insRestore(sc);")))

            # ---- S10 插入后手动滚动不被兜底拉回 ----
            pg.evaluate("() => { window.__ed.scrollTop=320; }")
            pg.wait_for_timeout(300)
            chk("S10 插入后手动滚动保持",
                abs(state(pg)["edTop"] - 320) <= TOL,
                "edTop=%s" % state(pg)["edTop"])

            # ---- S11 格式按钮四条分支：收编只换写入口，行为逐字不变 ----
            def short_sel():
                pg.evaluate("(t)=>window.__setDoc(t)", "ABC\nDEF")
                pg.wait_for_timeout(320)
                pg.evaluate("""() => { const ed=window.__ed; ed.focus();
                  const s=getSelection(); s.removeAllRanges();
                  const r=document.createRange(); r.selectNodeContents(ed);
                  s.addRange(r); }""")

            short_sel()
            pg.evaluate("() => window.__btn('B').click()")
            pg.wait_for_timeout(320)
            t_wrap = pg.evaluate("() => window.__ed.textContent")

            short_sel()
            pg.evaluate("() => window.__btn('列表').click()")
            pg.wait_for_timeout(320)
            t_pre = pg.evaluate("() => window.__ed.textContent")

            short_sel()
            pg.evaluate("() => window.__caretBtn('H1').click()")
            pg.wait_for_timeout(160)
            pg.evaluate("""() => { const bs=[...document.querySelectorAll('#fmtMenu button')];
              bs.find(b=>b.textContent.indexOf('H2')>=0).click(); }""")
            pg.wait_for_timeout(320)
            t_head = pg.evaluate("() => window.__ed.textContent")

            pg.evaluate("(t)=>window.__setDoc(t)", "ABC\nDEF")
            pg.wait_for_timeout(320)
            pg.evaluate("(p)=>window.__setCaret(p)", 7)
            pg.evaluate("() => window.__caretBtn('表格').click()")
            pg.wait_for_timeout(160)
            pg.evaluate("""() => { const bs=[...document.querySelectorAll('#fmtMenu button')];
              bs.find(b=>b.textContent.indexOf('题注')>=0).click(); }""")
            pg.wait_for_timeout(320)
            t_ins = pg.evaluate("() => window.__ed.textContent")

            chk("S11 格式按钮四分支行为不变",
                t_wrap.startswith("**") and t_wrap.endswith("**")
                and t_pre.startswith("- ABC\nDEF")
                and t_head.startswith("## ABC\nDEF")
                and t_ins == "ABC\nDEF@@ caption{表题}\n",
                "wrap=%r pre=%r head=%r ins=%r"
                % (t_wrap, t_pre, t_head, t_ins))

            # ---- S12 零 page error ----
            chk("S12 零 page error", not errs, repr(errs[:3]))
            b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    print("\nPASS %d / FAIL %d" % (12 - len(fails), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
