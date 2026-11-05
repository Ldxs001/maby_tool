# -*- coding: utf-8 -*-
"""v2.40.0 每行字数 · 出片侧（打印 / HTML / docx）专项测试。

判据（全部 PASS/FAIL）：
  E1 打印产物每行 28 字，行宽 = 版心
  E2 打印产物与预览字距同源（同一 em 比例）
  E3 勾「西文」→ 预览与打印产物都带 .mde-lat 且零字距
  E4 docx 正文 w:spacing = ls_em × 字号pt × 20
  E5 docx 标题按自身字号换算（比正文大），勾总项后消失
  E6 docx 表格豁免
  E7 关闭字距时 docx 一条 spacing 都不写

跑法：python _test_v2400_cpl_export.py   （系统 python；需服务与 playwright）
"""
import io
import json
import re
import sys
import types
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/"
TS_KEY = "md-editor-typeset-v3"
LONG = ("天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏闰余成岁律吕调阳"
        "云腾致雨露结为霜金生丽水玉出昆冈剑号巨阙珠称夜光果珍李柰菜重芥姜"
        "海咸河淡鳞潜羽翔龙师火帝鸟官人皇始制文字乃服衣裳推位让国有虞陶唐")
EN = " The quick brown fox jumps over the lazy dog while measuring advances. "
TXT = "\n\n".join([LONG * 2, LONG[:80] + EN + LONG[80:] * 2, LONG * 2])

if "latex2mathml" not in sys.modules:
    _pkg = types.ModuleType("latex2mathml")
    _conv = types.ModuleType("latex2mathml.converter")
    _conv.convert = lambda tex: ""
    _pkg.converter = _conv
    sys.modules["latex2mathml"] = _pkg
    sys.modules["latex2mathml.converter"] = _conv

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


ROWS = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const rows = []; let cur = null;
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
  let t;
  while ((t = w.nextNode())) {
    const s = t.nodeValue || '';
    for (let i = 0; i < s.length; i++) {
      if (/\\s/.test(s.charAt(i))) continue;
      const rg = document.createRange();
      rg.setStart(t, i); rg.setEnd(t, i + 1);
      const rc = rg.getBoundingClientRect();
      if (!rc.height) continue;
      if (!cur || Math.abs(rc.top - cur.top) > 2) { cur = {top: rc.top, n: 0}; rows.push(cur); }
      cur.n++;
    }
  }
  const cs = getComputedStyle(el);
  return {rows: rows.map(r => r.n), ls: cs.letterSpacing, fs: cs.fontSize,
          w: +el.getBoundingClientRect().width.toFixed(2)};
}"""


def scan_docx(data):
    from lxml import etree
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml")
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = etree.fromstring(xml)
    out = []
    for p in root.iter(W + "p"):
        ps = p.find(W + "pPr/" + W + "pStyle")
        out.append({
            "style": ps.get(W + "val") if ps is not None else None,
            "tbl": any(a.tag == W + "tbl" for a in p.iterancestors()),
            "spacing": [e.get(W + "val") for e in p.iter(W + "spacing")],
            "sz": [e.get(W + "val") for e in p.iter(W + "sz")],
        })
    return out


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(2800)

        def open_ts():
            if pg.evaluate("() => !!document.getElementById('tsOverlay').hidden"):
                pg.click("#btnTypeset")
                pg.wait_for_timeout(450)

        pg.evaluate("""(t) => { const ed=document.getElementById('editor');
            ed.textContent=t; ed.dispatchEvent(new Event('input',{bubbles:true})); }""", TXT)
        pg.wait_for_timeout(1600)
        orig = pg.evaluate("() => { const c=JSON.parse(localStorage.getItem('%s')||'{}');"
                           " return (c.page||{}).cpl||0; }" % TS_KEY)
        orig_ex = pg.evaluate("() => { const c=JSON.parse(localStorage.getItem('%s')||'{}');"
                              " return (c.page||{}).cjEx||{}; }" % TS_KEY)

        open_ts()
        pg.fill("#tsCpl", "28")
        pg.check("#tsCjLat")
        pg.click("#tsApply")
        pg.wait_for_timeout(1200)

        pv = pg.evaluate(ROWS, "#preview p")
        lat_n = pg.evaluate("() => document.querySelectorAll('#preview .mde-lat').length")
        payload = pg.evaluate("""() => {
            const c=JSON.parse(localStorage.getItem('%s')||'{}');
            return {bodyHtml:document.getElementById('preview').innerHTML,
                    tsCss:(document.getElementById('ts-style')||{textContent:''}).textContent,
                    cfg:c.page||{}, mode:'native'}; }""" % TS_KEY)
        req = urllib.request.Request(URL + "api/export-paged",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=180).read().decode("utf-8"))
        if not r.get("ok"):
            chk("E1 打印产物每行 28 字", False, "出片失败 %s" % r)
            b.close()
            return 1

        pg.goto(URL + r["url"].lstrip("/"))
        pg.wait_for_timeout(1600)
        pr = pg.evaluate(ROWS, ".markdown-body p, p")
        lat_pr = pg.evaluate("() => document.querySelectorAll('.mde-lat').length")

        body = [n for n in (pr["rows"] or [])[:-1]]
        ok1 = bool(body) and all(n == 28 for n in body) \
            and abs(pr["w"] - pv["w"]) < 1.5
        chk("E1 打印产物每行 28 字", ok1,
            "行=%s 宽 %.2f vs 预览 %.2f" % (pr["rows"], pr["w"], pv["w"]))

        em_pv = float(str(pv["ls"]).replace("px", "")) / float(pv["fs"].replace("px", ""))
        em_pr = float(str(pr["ls"]).replace("px", "")) / float(pr["fs"].replace("px", ""))
        chk("E2 打印与预览字距同源", abs(em_pv - em_pr) < 0.002,
            "%.4fem vs %.4fem" % (em_pv, em_pr))

        ok3 = lat_n > 0 and lat_pr > 0
        chk("E3 西文 span 进产物", ok3, "预览 %d / 产物 %d" % (lat_n, lat_pr))
        b.close()

    # ---- docx ----
    sys.path.insert(0, ".")
    import docx_export

    ls_em = round(em_pv, 6)
    ts = ":root{--mde-ls:%sem;}\n#preview p, .markdown-body p{font-size:11.25pt;}\n" % ls_em
    html = ('<div class="markdown-body"><h1>标题一</h1><p>%s</p>'
            '<table><tr><th>甲</th></tr><tr><td>乙</td></tr></table></div>' % LONG)

    rows = scan_docx(docx_export.build_docx(None, html, ts, {"paper": "A4", "cjEx": {}}))
    body_sp = [r["spacing"] for r in rows if r["style"] is None and not r["tbl"]]
    head_sp = [r["spacing"] for r in rows if (r["style"] or "").startswith("Heading")]
    want = int(round(ls_em * 11.25 * 20))
    chk("E4 docx 正文 w:spacing", body_sp and body_sp[0] == [str(want)],
        "期望 %d 实际 %s" % (want, body_sp[:1]))

    ok5 = bool(head_sp and head_sp[0]) and int(head_sp[0][0]) > want
    chk("E5 docx 标题按自身字号", ok5,
        "标题 %s vs 正文 %d（标题字号更大 → 间距更大）" % (head_sp[:1], want))

    rows = scan_docx(docx_export.build_docx(
        None, html, ts, {"paper": "A4", "cjEx": {"hall": True, "tbl": True}}))
    tail = [r["spacing"] for r in rows if (r["style"] or "").startswith("Heading")]
    tbl = [r["spacing"] for r in rows if r["tbl"]]
    chk("E6 docx 标题与表格豁免", not tail[0] and not any(tbl),
        "标题=%s 表格=%s" % (tail[:1], tbl))

    rows = scan_docx(docx_export.build_docx(
        None, html, ts.replace(":root{--mde-ls:%sem;}\n" % ls_em, ""),
        {"paper": "A4"}))
    chk("E7 关闭态不写 spacing", all(not r["spacing"] for r in rows))

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(URL)
        pg.wait_for_timeout(2600)
        def open_ts2():
            if pg.evaluate("() => !!document.getElementById('tsOverlay').hidden"):
                pg.click("#btnTypeset")
                pg.wait_for_timeout(450)
        open_ts2()
        pg.fill("#tsCpl", str(orig))
        # 六个勾选全部按测试前的值还原，别把本机设置留在测试状态
        for key, eid in (("h1", "tsCj1"), ("h2", "tsCj2"), ("h3", "tsCj3"),
                         ("hall", "tsCjAll"), ("tbl", "tsCjTbl"), ("lat", "tsCjLat")):
            el = pg.locator("#" + eid)
            if orig_ex.get(key):
                el.check()
            else:
                el.uncheck()
        pg.click("#tsApply")
        pg.wait_for_timeout(600)
        chk("E8 零 page error", not errs, " | ".join(errs[:2]))
        b.close()

    print("\nPASS %d / FAIL %d" % (8 - len(fails), len(fails)))
    return 1 if fails else 0


sys.exit(main())
