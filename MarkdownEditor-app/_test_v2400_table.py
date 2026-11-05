# -*- coding: utf-8 -*-
"""v2.40.0 可视化表格弹窗专项测试。

判据（全部 PASS/FAIL）：
  T1 点工具栏「表格」→ 弹窗打开，默认 3 行 × 3 列（首行表头）
  T2 改行数 5 → 就地重建 5 行，已填内容按行列位置保留
  T3 改列数 2 → 2 列，前两列内容保留（第 3 列被裁）
  T4 Enter 同列下移、Tab 右移、行末 Tab 落下一行首、Shift+Tab 回退
  T5 Shift+Enter 不产生换行（格内恒单行，A 方案）
  T6 生成语法：表头行 + `| --- |` 分隔行，格内 `|` 转义成 `\\|`
  T7 插入到光标处：落在光标位置、前后各留一个空行、光标跳到表格之后
  T8 Ctrl+Z 一步撤销：全文回到插入前
  T9 粘贴多行制表符文本：按行列拆开，超尺寸自动扩容
  T10 全程零 page error

跑法：python _test_v2400_table.py   （需系统 python + playwright）
前置：服务已启动（python md_server.py）。
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


SET_TEXT = """(t)=>{
  const ed=document.getElementById('editor');
  ed.textContent=t;
  ed.dispatchEvent(new Event('input',{bubbles:true}));
  return true;
}"""

# 把光标放到逻辑偏移 pos（与 getSel 同一口径：全文文本偏移）
CARET = """(pos)=>{
  const ed=document.getElementById('editor');
  ed.focus();
  const w=document.createTreeWalker(ed,NodeFilter.SHOW_TEXT,null); let n; let acc=0;
  while((n=w.nextNode())){
    const L=n.nodeValue.length;
    if(pos<=acc+L){
      const r=document.createRange();
      r.setStart(n,pos-acc); r.collapse(true);
      const s=getSelection(); s.removeAllRanges(); s.addRange(r);
      return true;
    }
    acc+=L;
  }
  const r=document.createRange(); r.selectNodeContents(ed); r.collapse(false);
  const s=getSelection(); s.removeAllRanges(); s.addRange(r);
  return false;
}"""

OPEN = """()=>{
  const bs=[...document.querySelectorAll('#fmtBtns .tb-btn')];
  const b=bs.find(x=>x.textContent==='表格');
  if(!b) return 'nobtn';
  b.click();
  return document.getElementById('tbOverlay').hidden ? 'hidden' : 'open';
}"""

SHAPE = """()=>{
  const g=document.getElementById('tbGrid');
  const trs=[...g.querySelectorAll('tr')];
  const cells=[...g.querySelectorAll('th,td')];
  return {rows:trs.length, cols:trs[0]?trs[0].children.length:0,
          th:g.querySelectorAll('th').length, td:g.querySelectorAll('td').length,
          cells:cells.map(c=>c.textContent)};
}"""

# 往格子里写内容（直接改 textContent，跳过输入法差异）
FILL = """(vals)=>{
  const g=document.getElementById('tbGrid');
  const cells=[...g.querySelectorAll('th,td')];
  vals.forEach((v,i)=>{ if(cells[i]) cells[i].textContent=v; });
  return true;
}"""

SETNUM = """(o)=>{
  const el=document.getElementById(o.id);
  el.value=String(o.v);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  return true;
}"""

# 聚焦某格并把光标放到格内末尾
FOCUS = """(rc)=>{
  const c=document.querySelector('#tbGrid [data-rc="'+rc+'"]');
  if(!c) return false;
  c.focus();
  const r=document.createRange(); r.selectNodeContents(c); r.collapse(false);
  const s=getSelection(); s.removeAllRanges(); s.addRange(r);
  return true;
}"""
ACTIVE_RC = """()=>{
  const a=document.activeElement;
  return (a&&a.getAttribute)?(a.getAttribute('data-rc')||''):'';
}"""

PASTE = """(o)=>{
  const c=document.querySelector('#tbGrid [data-rc="'+o.rc+'"]');
  if(!c) return false;
  const dt=new DataTransfer();
  dt.setData('text/plain',o.txt);
  c.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
  return true;
}"""

CLICK = """(id)=>{ document.getElementById(id).click(); return true; }"""
TEXT = """()=>document.getElementById('editor').textContent"""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1400, "height": 900})
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(1200)

        # ---------- T1 打开弹窗 ----------
        pg.evaluate(SET_TEXT, "AAA\nBBB")
        pg.evaluate(CARET, 3)
        r = pg.evaluate(OPEN)
        pg.wait_for_timeout(150)
        sh = pg.evaluate(SHAPE)
        chk("T1 弹窗打开且默认 3 行 × 3 列（1 表头行 + 2 数据行）",
            r == "open" and sh["rows"] == 3 and sh["cols"] == 3
            and sh["th"] == 3 and sh["td"] == 6,
            "%s rows=%s cols=%s th=%s td=%s" % (r, sh["rows"], sh["cols"], sh["th"], sh["td"]))

        # ---------- T2 改行数保留内容 ----------
        pg.evaluate(FILL, ["H1", "H2", "H3", "a1", "a2", "a3", "b1", "b2", "b3"])
        pg.evaluate(SETNUM, {"id": "tbRows", "v": 5})
        pg.wait_for_timeout(520)
        sh = pg.evaluate(SHAPE)
        chk("T2 改 5 行 → 5 行 × 3 列，原 9 格内容按位置保留",
            sh["rows"] == 5 and sh["cols"] == 3
            and sh["cells"][:9] == ["H1", "H2", "H3", "a1", "a2", "a3", "b1", "b2", "b3"]
            and len(sh["cells"]) == 15,
            "rows=%s cells=%s" % (sh["rows"], sh["cells"]))

        # ---------- T3 改列数裁列 ----------
        pg.evaluate(SETNUM, {"id": "tbCols", "v": 2})
        pg.wait_for_timeout(520)
        sh = pg.evaluate(SHAPE)
        chk("T3 改 2 列 → 2 列，前两列保留、第 3 列被裁",
            sh["rows"] == 5 and sh["cols"] == 2
            and sh["cells"][:4] == ["H1", "H2", "a1", "a2"],
            "rows=%s cols=%s cells=%s" % (sh["rows"], sh["cols"], sh["cells"]))

        # ---------- T4 键盘移动 ----------
        pg.evaluate(FOCUS, "0,0")
        pg.keyboard.press("Enter")
        k1 = pg.evaluate(ACTIVE_RC)
        pg.keyboard.press("Tab")
        k2 = pg.evaluate(ACTIVE_RC)
        pg.keyboard.press("Shift+Tab")
        k3 = pg.evaluate(ACTIVE_RC)
        pg.evaluate(FOCUS, "2,1")            # 行末格
        pg.keyboard.press("Tab")
        k4 = pg.evaluate(ACTIVE_RC)
        chk("T4 Enter 下移 / Tab 右移 / Shift+Tab 回退 / 行末 Tab 落下一行首",
            k1 == "1,0" and k2 == "1,1" and k3 == "1,0" and k4 == "3,0",
            "Enter→%s Tab→%s Shift+Tab→%s 行末Tab→%s" % (k1, k2, k3, k4))

        # ---------- T5 Shift+Enter 不换行 ----------
        pg.evaluate(FOCUS, "1,0")
        pg.evaluate("""()=>{document.querySelector('#tbGrid [data-rc="1,0"]').textContent='X';}""")
        pg.evaluate(FOCUS, "1,0")
        pg.keyboard.press("Shift+Enter")
        pg.wait_for_timeout(80)
        cell = pg.evaluate("""()=>document.querySelector('#tbGrid [data-rc="1,0"]').textContent""")
        chk("T5 Shift+Enter 不产生换行（格内恒单行）",
            "\n" not in cell and "\r" not in cell and cell == "X",
            repr(cell))

        # ---------- T6+T7 语法与插入位置 ----------
        # 当前：5 行 × 2 列。改成小表便于核对：3 行 × 2 列
        pg.evaluate(SETNUM, {"id": "tbRows", "v": 3})
        pg.wait_for_timeout(520)
        pg.evaluate(FILL, ["甲", "乙", "1|2", "b", "c", ""])
        pg.evaluate(CLICK, "tbInsert")
        pg.wait_for_timeout(400)
        txt = pg.evaluate(TEXT)
        want = ("AAA\n\n"
                "| 甲 | 乙 |\n"
                "| --- | --- |\n"
                "| 1\\|2 | b |\n"
                "| c |  |\n"
                "\nBBB")
        chk("T6 生成语法：表头行 + 分隔行 + 格内 | 转义成 \\|", txt == want, repr(txt))

        hidden = pg.evaluate("""()=>document.getElementById('tbOverlay').hidden""")
        ok7 = (hidden is True
               and txt.count("\n\n") >= 2
               and txt.startswith("AAA\n\n| ")
               and txt.endswith("|\n\nBBB"))
        chk("T7 插入落在光标处、前后各留一个空行、弹窗关闭", ok7,
            "hidden=%s head=%r tail=%r" % (hidden, txt[:12], txt[-12:]))

        # ---------- T8 撤销 ----------
        pg.evaluate(CARET, len(txt))
        pg.keyboard.press("Control+z")
        pg.wait_for_timeout(350)
        txt2 = pg.evaluate(TEXT)
        chk("T8 Ctrl+Z 一步撤销，全文回到插入前", txt2 == "AAA\nBBB", repr(txt2))

        # ---------- T9 粘贴多行 + 自动扩容 ----------
        pg.evaluate(SET_TEXT, "")
        pg.evaluate(OPEN)
        pg.wait_for_timeout(150)
        pg.evaluate(SETNUM, {"id": "tbRows", "v": 2})
        pg.evaluate(SETNUM, {"id": "tbCols", "v": 1})
        pg.wait_for_timeout(520)
        pg.evaluate(PASTE, {"rc": "0,0", "txt": "p1\tq1\np2\tq2\np3\tq3"})
        pg.wait_for_timeout(250)
        sh = pg.evaluate(SHAPE)
        nums = pg.evaluate("""()=>({r:document.getElementById('tbRows').value,
                                    c:document.getElementById('tbCols').value})""")
        chk("T9 粘贴 3 行 × 2 列 → 自动扩到 3 行 × 2 列并逐格填入",
            sh["rows"] == 3 and sh["cols"] == 2
            and sh["cells"] == ["p1", "q1", "p2", "q2", "p3", "q3"]
            and nums["r"] == "3" and nums["c"] == "2",
            "rows=%s cols=%s cells=%s nums=%s" % (sh["rows"], sh["cols"], sh["cells"], nums))

        # ---------- T11 插进去的表真能被渲染成表格 ----------
        pg.evaluate(SET_TEXT, "")
        pg.evaluate(OPEN)
        pg.wait_for_timeout(150)
        pg.evaluate(SETNUM, {"id": "tbRows", "v": 3})
        pg.evaluate(SETNUM, {"id": "tbCols", "v": 2})
        pg.wait_for_timeout(520)
        pg.evaluate(FILL, ["甲", "乙", "丙", "丁", "戊", "己"])
        pg.evaluate(CLICK, "tbInsert")
        pg.wait_for_timeout(900)
        r11 = pg.evaluate("""()=>{
          const t=document.querySelector('#preview table');
          if(!t) return {ok:false};
          const trs=[...t.querySelectorAll('tr')];
          return {ok:true, rows:trs.length,
                  cols:trs[0]?trs[0].children.length:0,
                  th:t.querySelectorAll('th').length,
                  first:t.querySelector('th')?t.querySelector('th').textContent:''};
        }""")
        chk("T11 插入的源码被渲染成真表格（3 行 × 2 列，首行 th）",
            r11.get("ok") and r11.get("rows") == 3 and r11.get("cols") == 2
            and r11.get("th") == 2 and r11.get("first") == "甲",
            str(r11))

        # ---------- T12 复制到真实剪贴板 ----------
        pg.evaluate(OPEN)
        pg.wait_for_timeout(150)
        pg.evaluate(SETNUM, {"id": "tbRows", "v": 2})
        pg.evaluate(SETNUM, {"id": "tbCols", "v": 2})
        pg.wait_for_timeout(520)
        pg.evaluate(FILL, ["A", "B", "C", "D"])
        pg.evaluate(CLICK, "tbCopy")
        pg.wait_for_timeout(350)
        clip = pg.evaluate("""async()=>{ try{ return await navigator.clipboard.readText(); }
                                        catch(e){ return 'ERR:'+e.message; } }""")
        # Windows 剪贴板一律把 LF 规范化成 CRLF（OS 层行为，任何应用都一样），
        # 判据按行尾归一化后比对；我们的源码里写的确实是 \n
        clip_n = (clip or "").replace("\r\n", "\n")
        chk("T12 复制出来的是纯 markdown 表格文本",
            clip_n == "| A | B |\n| --- | --- |\n| C | D |", repr(clip))

        # ---------- T13 英文界面 ----------
        pg.evaluate("()=>{ applyLang('en'); }")
        pg.wait_for_timeout(250)
        r13 = pg.evaluate("""()=>({
          title: document.querySelector('#tbWrap .ts-head > span').textContent,
          ins: document.getElementById('tbInsert').textContent,
          copy: document.getElementById('tbCopy').textContent,
          stat: document.getElementById('tbStat').textContent
        })""")
        pg.evaluate("()=>{ applyLang('zh'); }")
        chk("T13 英文界面下弹窗文字齐备（含动态的尺寸提示）",
            r13["title"] == "Insert table" and r13["ins"] == "Insert at cursor"
            and r13["copy"] == "Copy" and "rows" in r13["stat"],
            str(r13))

        # ---------- T10 ----------
        chk("T10 全程零 page error", len(errs) == 0, "; ".join(errs[:3]))

        b.close()

    print("")
    if fails:
        print("FAIL %d 项：%s" % (len(fails), ", ".join(fails)))
        sys.exit(1)
    print("全部 PASS")


if __name__ == "__main__":
    main()
