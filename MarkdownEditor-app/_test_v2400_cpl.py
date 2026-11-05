# -*- coding: utf-8 -*-
"""v2.40.0 每行字数（均等割）专项测试。

判据（全部 PASS/FAIL）：
  T1 设 28 字后每行**恰好 28 个汉字**（末行除外），且首行宽 = 版心宽
  T2 版心宽与页边距**一个像素都没动**（段宽与基线逐像素相等）
  T3 字号换算：H1（24pt）同一个 em 字距下每行字数按比例缩到 13 字量级
  T4 勾「所有#标题」→ H1 零字距、正文仍 28 字
  T5 勾「表格」→ 单元格零字距、正文仍 28 字
  T6 字数归 0 → 字距消失、回到自然密度（43 字/行）
  T7 改正文字号 → 输入框旁的上限随之变化（读控件，不等「应用」）
  T8 全程零 page error

跑法：python _test_v2400_cpl.py   （需系统 python + playwright）
前置：服务已启动（python md_server.py）。
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"
TS_KEY = "md-editor-typeset-v3"

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


LONG = ("天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏闰余成岁律吕调阳"
        "云腾致雨露结为霜金生丽水玉出昆冈剑号巨阙珠称夜光果珍李柰菜重芥姜"
        "海咸河淡鳞潜羽翔龙师火帝鸟官人皇始制文字乃服衣裳推位让国有虞陶唐")

TXT = "\n\n".join([
    "# " + LONG * 2,
    LONG * 2, LONG * 2, LONG * 2,
    "\n\n| 甲 | 乙 |\n|---|---|\n| " + LONG[:60] + " | " + LONG[:60] + " |\n",
])

MEASURE = """(opt) => {
  const pv = document.getElementById('preview');
  function rowsOf(el){
    const rows=[]; let cur=null;
    const w=document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    let t;
    while((t=w.nextNode())){
      const s=t.nodeValue||'';
      for(let i=0;i<s.length;i++){
        const ch=s.charAt(i);
        if(/\\s/.test(ch)) continue;
        const rg=document.createRange();
        rg.setStart(t,i); rg.setEnd(t,i+1);
        const rc=rg.getBoundingClientRect();
        if(!rc.height) continue;
        if(!cur||Math.abs(rc.top-cur.top)>2){
          cur={top:rc.top,n:0,left:rc.left,right:rc.right};
          rows.push(cur);
        }
        cur.n++; cur.right=Math.max(cur.right,rc.right);
      }
    }
    return rows;
  }
  const longP = Array.from(pv.querySelectorAll('p'))
    .filter(e=>e.textContent.replace(/\\s/g,'').length>150);
  const p = longP[0] || null;
  const h1 = pv.querySelector('h1');
  const td = pv.querySelector('td');
  const out = {p:null,h1:null,td:null,lsw:null,lsh:null,lst:null};
  if(p){
    const cs=getComputedStyle(p);
    const rows=rowsOf(p);
    out.p={ls:cs.letterSpacing,fs:cs.fontSize,w:+p.getBoundingClientRect().width.toFixed(2),
           rows:rows.map(r=>r.n),
           lineW:rows.length?+(rows[0].right-rows[0].left).toFixed(2):0};
  }
  if(h1){
    const cs=getComputedStyle(h1);
    out.h1={ls:cs.letterSpacing,fs:cs.fontSize,rows:rowsOf(h1).map(r=>r.n)};
  }
  if(td){
    out.td={ls:getComputedStyle(td).letterSpacing};
  }
  return out;
}"""


def rows_hist(rows):
    h = {}
    for n in rows or []:
        h[n] = h.get(n, 0) + 1
    return dict(sorted(h.items()))


def open_ts(pg):
    """「应用」会关面板（#tsOverlay hidden），下一次改控件前必须重开。"""
    if pg.evaluate("() => !!document.getElementById('tsOverlay').hidden"):
        pg.click("#btnTypeset")
        pg.wait_for_timeout(450)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(2800)

        # 归零本机残留，边距切「常规」，保证前提确定
        # 排版设置是**本机全局**的，上一轮测试会把 cpl 留在 28 上——不归零
        # 就会把「基线」当成 28 字量，T6 必然假红。先记原值、结尾还原。
        orig = pg.evaluate(
            "() => { const c=JSON.parse(localStorage.getItem('%s')||'{}');"
            " return (c.page||{}).cpl||0; }" % TS_KEY)
        pg.evaluate("""() => { const s=document.getElementById('pvPreset');
            s.value='regular'; s.dispatchEvent(new Event('change',{bubbles:true})); }""")
        pg.wait_for_timeout(300)
        # 编辑器是 contenteditable，正文读取走 textContent（setText 同源）：
        # pg.fill 会把多行折成一段、丢换行，整篇变成一个 h1——必须直接写
        # textContent 再冒 input，才是产品自己的注入路径。
        pg.evaluate("""(t) => {
            const ed = document.getElementById('editor');
            ed.textContent = t;
            ed.dispatchEvent(new Event('input', {bubbles:true}));
        }""", TXT)
        pg.wait_for_timeout(1800)
        # 基线必须是 cpl=0（自然密度），不能沿用本机残留值
        open_ts(pg)
        pg.fill("#tsCpl", "0")
        pg.click("#tsApply")
        pg.wait_for_timeout(900)
        base = pg.evaluate(MEASURE)
        if not base.get("p"):
            print("FAIL  正文未渲染，无法测量")
            b.close()
            return 1

        open_ts(pg)
        pg.fill("#tsCpl", "28")
        pg.click("#tsApply")
        pg.wait_for_timeout(1000)
        r = pg.evaluate(MEASURE)

        # ---- T1 每行恰好 28 字 ----
        cnt = rows_hist(r["p"]["rows"])
        full = [n for n in (r["p"]["rows"] or [])[:-1]]
        ok1 = bool(full) and all(n == 28 for n in full) and cnt.get(28, 0) >= 2
        chk("T1 每行恰好 28 字", ok1, "行字数=%s" % cnt)

        # ---- T2 版心宽不变 ----
        d = abs(r["p"]["w"] - base["p"]["w"])
        ok2 = d < 0.6 and abs(r["p"]["lineW"] - r["p"]["w"]) < 1.5
        chk("T2 版心宽与边距未动", ok2,
            "基线 %.2f → %.2f (Δ%.2f) 首行宽 %.2f"
            % (base["p"]["w"], r["p"]["w"], d, r["p"]["lineW"]))

        # ---- T3 字号换算：H1 同 em 字距下按比例缩字 ----
        h1 = r.get("h1") or {}
        n1 = (h1.get("rows") or [None])[0]
        fs_p = float(r["p"]["fs"].replace("px", ""))
        fs_h = float(str(h1.get("fs") or "0").replace("px", "")) or 0
        want = int(28 * fs_p / fs_h) if fs_h else 0
        # 字距在两边是**同一个 em 比例**（继承会被解析成绝对 px，所以 h1 上
        # 的 px 值必然更大）；比较 em，不能比较 px。
        try:
            em_p = float(str(r["p"]["ls"]).replace("px", "")) / fs_p
            em_h = float(str(h1.get("ls")).replace("px", "")) / fs_h
        except Exception:
            em_p, em_h = -1, -2
        ok3 = bool(n1) and want > 0 and abs(n1 - want) <= 1 and abs(em_p - em_h) < 0.01
        chk("T3 H1 按字号换算", ok3,
            "H1 %s 每行 %s 字（按 28 字/%.0fpx 折算应为 %d）em 字距 %.4f vs %.4f"
            % (h1.get("fs"), n1, fs_p, want, em_h, em_p))

        # ---- T4 标题豁免 ----
        open_ts(pg)
        pg.check("#tsCjAll")
        pg.wait_for_timeout(200)
        dis = pg.evaluate("() => ['tsCj1','tsCj2','tsCj3']"
                          ".map(i=>document.getElementById(i).disabled)")
        pg.click("#tsApply")
        pg.wait_for_timeout(900)
        r4 = pg.evaluate(MEASURE)
        h1_ls = (r4.get("h1") or {}).get("ls")
        cnt4 = rows_hist(r4["p"]["rows"])
        ok4 = h1_ls == "normal" and all(n == 28 for n in (r4["p"]["rows"] or [])[:-1]) \
            and all(dis)
        chk("T4 标题豁免", ok4,
            "h1 ls=%s 子项置灰=%s 正文行=%s" % (h1_ls, dis, cnt4))

        # ---- T5 表格豁免 ----
        open_ts(pg)
        pg.uncheck("#tsCjAll")
        pg.check("#tsCjTbl")
        pg.wait_for_timeout(200)
        pg.click("#tsApply")
        pg.wait_for_timeout(900)
        r5 = pg.evaluate(MEASURE)
        ok5 = (r5.get("td") or {}).get("ls") == "normal" \
            and all(n == 28 for n in (r5["p"]["rows"] or [])[:-1])
        chk("T5 表格豁免", ok5,
            "td ls=%s 正文行=%s" % ((r5.get("td") or {}).get("ls"),
                                 rows_hist(r5["p"]["rows"])))

        # ---- T6 归零复原 ----
        open_ts(pg)
        pg.uncheck("#tsCjTbl")
        pg.fill("#tsCpl", "0")
        pg.click("#tsApply")
        pg.wait_for_timeout(900)
        r6 = pg.evaluate(MEASURE)
        back = r6["p"]["rows"][0] if r6["p"]["rows"] else 0
        ok6 = r6["p"]["ls"] == "normal" and back == base["p"]["rows"][0] \
            and abs(r6["p"]["w"] - base["p"]["w"]) < 0.6
        chk("T6 归零复原", ok6,
            "ls=%s 首行=%s（基线 %s）段宽 %.2f"
            % (r6["p"]["ls"], back, base["p"]["rows"][0], r6["p"]["w"]))

        # ---- T7 改正文字号 → 上限随之变化（提示读控件，不等「应用」）----
        open_ts(pg)
        pg.fill("#tsCpl", "28")
        pg.wait_for_timeout(200)
        hint0 = pg.inner_text("#tsCplHint")
        fs_el = pg.query_selector('input[data-tssz="p"]')
        orig_fs = fs_el.input_value() if fs_el else ""
        pg.fill('input[data-tssz="p"]', "48")
        pg.wait_for_timeout(250)
        hint1 = pg.inner_text("#tsCplHint")
        ok7 = ("上限" in hint0) and ("上限" in hint1) and hint0 != hint1
        chk("T7 改字号上限随之变化", ok7, "%s → %s" % (hint0, hint1))
        pg.fill('input[data-tssz="p"]', orig_fs)      # 不点应用，仅回填控件
        pg.wait_for_timeout(200)

        # 还原本机设置
        open_ts(pg)
        pg.fill("#tsCpl", str(orig))
        pg.click("#tsApply")
        pg.wait_for_timeout(700)

        chk("T8 零 page error", not errs, " | ".join(errs[:2]))
        b.close()

    print("\nPASS %d / FAIL %d" % (8 - len(fails), len(fails)))
    return 1 if fails else 0


sys.exit(main())
