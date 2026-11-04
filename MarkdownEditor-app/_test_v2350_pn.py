# -*- coding: utf-8 -*-
"""v2.35.0 页码体系回归（真引擎 : Edge 156，与 WebView2 运行时同版本号）

判据只有 PASS/FAIL，不做"大致可用"。每条都是**印出来的 PDF**里读到的，不是字符串断言：
  1. 目录页没有页脚，且不占页号（正文首页印 1）
  2. 目录条目有页码，且与页脚同源（标题落在哪页，目录就写那页的号）
  3. {P} = 可编号页数（物理页数 − 目录/封面等前件），{N} = 本区页数
  4. noll 页区照旧不印号；页码位置 outer/bottom 两种都对

跑法：python _test_v2350_pn.py          （无 Edge 时 SKIP，不算通过）
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import md_server as m

EDGE_CANDS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
EDGE = next((p for p in EDGE_CANDS if os.path.exists(p)), None)

PASS, FAIL, SKIP = [], [], []
MK = '<span class="mkm">M%04d</span>'
PARA = "<p>%s</p>" % ("正文填充文字，用来把版面撑开。" * 16)
MARK_CSS = ".mkm{font-size:1px;color:transparent;line-height:0;}"


def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (
        "" if not detail else "   [" + str(detail)[:110] + "]"))


def body_with_marks():
    """带隐形标记的正文：标记 → 标题在 PDF 第几页，作为真值。"""
    n = [0]

    def H(lvl, txt):
        n[0] += 1
        return "<h%d>%s%s</h%d>" % (lvl, MK % n[0], txt, lvl)

    return (
        '<div class="page-region" data-pn="noll" data-pr-id="r0">'
        + H(1, "封面") + "<p>副标题</p></div>"
        + H(1, "第一章 起") + PARA * 2
        + H(2, "第一节 甲") + PARA * 3
        + H(1, "第二章 承") + PARA * 2
        + H(2, "第二节 甲") + PARA * 2
        + '<div class="page-region" data-pn="1" data-pr-id="r1">'
        + H(2, "附录 甲") + PARA * 2 + "</div>"
        + H(1, "第三章 转") + PARA
    ), n[0]


def build(cfg, body):
    html = m.build_paged_html(None, body, "", cfg, native=True)
    return html.replace("</style>", MARK_CSS + "</style>", 1)


def render(html, tag):
    hp = os.path.join(HERE, "Temp", "_t2350_%s.html" % tag)
    pdf = os.path.join(HERE, "Temp", "_t2350_%s.pdf" % tag)
    io.open(hp, "w", encoding="utf-8").write(html)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=EDGE)
        pg = b.new_page(viewport={"width": 1200, "height": 900})
        pg.goto("file:///" + hp.replace("\\", "/"), wait_until="load")
        pg.wait_for_function("() => window.__pnReady === 1", timeout=20000)
        fail = pg.evaluate("() => window.__pnFail || ''")
        toc = pg.evaluate(
            "() => Array.from(document.querySelectorAll('.md-toc a'))"
            ".map(a => ({t:(a.textContent||'').trim(),"
            " n:(a.querySelector('.md-toc-pg')||{}).textContent||''}))")
        pg.pdf(path=pdf, prefer_css_page_size=True, print_background=True)
        b.close()
    return pdf, fail, toc


def read_pdf(pdf):
    import pypdf
    rd = pypdf.PdfReader(pdf)
    pages, mkmap, toc_pages = [], {}, 0
    for i, pg in enumerate(rd.pages):
        t = " ".join((pg.extract_text() or "").split())
        flat = t.replace(" ", "")
        foot = re.search(r"p(\d+)/P(\d+)/N(\d+)", flat)
        pages.append({"foot": foot.groups() if foot else None, "text": t})
        if ("目 录" in t) or ("⽬ 录" in t):
            toc_pages += 1
            continue
        for mm in re.finditer(r"M(\d{4})", t):
            mkmap.setdefault(int(mm.group(1)), i + 1)
    return pages, mkmap, toc_pages


def case(tag, cfg, want_toc=True, want_pn=True):
    print("\n[%s]" % tag)
    body, nh = body_with_marks()
    pdf, fail, toc = render(build(cfg, body), tag)
    pages, mkmap, toc_pages = read_pdf(pdf)
    chk(tag + " 脚本零报错", not fail, fail)
    foots = [p["foot"] for p in pages]
    numbered = [(i, f) for i, f in enumerate(foots) if f]
    # 1. 目录页无页脚
    if want_toc:
        chk(tag + " 目录页无页脚", all(foots[i] is None for i in range(toc_pages)),
            [foots[i] for i in range(toc_pages)])
    if want_pn:
        # 2. 正文首页 = 1
        chk(tag + " 正文首页印 1", numbered and numbered[0][1][0] == "1",
            numbered[0][1] if numbered else "无页码")
        # 3. 页号契约（v2.35.0 修订）：区外连续递增、**跳过页区页**；区内
        #    从 1 重编。旧断言「全篇页号连续递增」写死在「区重编未生效」的
        #    旧世界——2026-11-04 修好区重编后它必然失效（实测序列
        #    [1,2,3,1,4]：附录区第 1 页印 1，区外续到 4），故改为按契约判。
        #    区分区页/区外页靠 {N}：N=1 是区外页，N>1 是页区页（{N}=本区页数）。
        seq = [int(f[0]) for _i, f in numbered]
        Ns = [int(f[2]) for _i, f in numbered]
        out_seq = [s for s, n in zip(seq, Ns) if n == 1]
        reg_seq = [s for s, n in zip(seq, Ns) if n > 1]
        chk(tag + " 区外页号连续递增",
            out_seq == list(range(1, len(out_seq) + 1)), out_seq[:12])
        segs = []
        for s in reg_seq:
            if not segs or segs[-1][-1] + 1 != s:
                segs.append([s])
            else:
                segs[-1].append(s)
        chk(tag + " 区页号从 1 重编",
            bool(segs) and all(g[0] == 1 for g in segs), segs[:4])
        # 4. {P} = 可编号页数
        tot = {f[1] for _i, f in numbered}
        chk(tag + " {P}=可编号页数", tot == {str(len(seq))}, (sorted(tot), len(seq)))
    # 5. 目录页码与页脚同源
    if want_toc and toc:
        bad = []
        for item in toc:
            k = int(re.search(r"M(\d{4})", item["t"]).group(1))
            phys = mkmap.get(k)
            if phys is None:
                bad.append((item["t"][:8], "未落页"))
                continue
            want = None
            if want_pn:
                f = foots[phys - 1]
                want = f[0] if f else None
            got = item["n"]
            if want is not None and got != want:
                bad.append((item["t"][:10], "目录%s/页脚%s" % (got, want)))
            if want is None and not got:
                bad.append((item["t"][:10], "缺页码"))
        chk(tag + " 目录页码与页脚一致", not bad, bad[:3])
    return pages, toc


def main():
    if not EDGE:
        print("SKIP：未找到 Edge，无法用真引擎验证")
        return 0
    base = {"paper": "A4", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
            "tone": "light"}
    tpl = "p{p}/P{P}/N{N}"

    pages, toc = case("A_toc_outer", dict(
        base, pn={"on": "on", "pos": "outer", "size": 9, "tpl": tpl},
        toc={"on": "on", "solo": True, "pos": "top"}))

    case("B_toc_bottom", dict(
        base, pn={"on": "on", "pos": "bc", "size": 11, "tpl": tpl},
        toc={"on": "on", "solo": True, "pos": "top"}))

    case("C_pn_only", dict(
        base, pn={"on": "on", "pos": "br", "size": 9, "tpl": tpl},
        toc={"on": "off"}), want_toc=False)

    case("D_toc_only", dict(
        base, pn={"on": "off"},
        toc={"on": "on", "solo": True, "pos": "top"}), want_pn=False)

    # 6. noll 页区照旧不印号（A 样本的封底页）
    print("\n[E_noll]")
    body = ('<div class="page-region" data-pn="noll" data-pr-id="r9">'
            '<h1>封底</h1></div><h1>末尾章</h1>' + PARA)
    pdf, fail, _toc = render(build(dict(
        base, pn={"on": "on", "pos": "bc", "size": 9, "tpl": tpl},
        toc={"on": "off"}), body), "E_noll")
    pages, _mk, _t = read_pdf(pdf)
    foots = [p["foot"] for p in pages]
    chk("E_noll 封底页无页脚", foots[0] is None, foots[0])
    chk("E_noll 其后仍按连续号", foots[1] and foots[1][0] == "1", foots[1])

    # 7. 只开目录、页码关：页区循环不许凭空造页脚（v2.35.0 实测漏洞）
    print("\n[F_toc_nopn]")
    body, _nh = body_with_marks()
    pdf, fail, toc = render(build(dict(
        base, pn={"on": "off"},
        toc={"on": "on", "solo": True, "pos": "top"}), body), "F_toc_nopn")
    pages, _mk, _t = read_pdf(pdf)
    chk("F_toc_nopn 脚本零报错", not fail, fail)
    chk("F_toc_nopn 全文无页脚", all(p["foot"] is None for p in pages),
        [i for i, p in enumerate(pages) if p["foot"]])
    chk("F_toc_nopn 目录仍有页码", bool(toc) and all(
        re.search(r"\d+$", t["t"] or "") for t in toc),
        [t["t"][:12] for t in toc[:3]])

    # 8. 跨页长表样本（2026-11-04 补的盲区样本）
    #    为什么必须有：表头跨页重复是 Chromium 打印引擎的行为，而多列测量盒
    #    不重复表头 → 表格之后的所有内容在测量里整体偏早，目录号与 {P} 跟着
    #    偏。旧样本（6 个 + e2e）**一个表格都没有**，这个漂移源从未被触发，
    #    所以「实测完全一致」的结论当时只在无表格内容上成立。
    print("\n[G_long_table]")
    rows = "".join("<tr><td>第%d行</td><td>数据%d</td></tr>" % (i, i)
                    for i in range(1, 61))
    body = ("<h1>%s表前章</h1>"
            "<table><thead><tr><th>序号</th><th>内容</th></tr></thead>"
            "<tbody>" + rows + "</tbody></table>"
            "<h1>%s表后章</h1>" + PARA) % (MK % 10, MK % 11)
    pdf, fail, toc = render(build(dict(
        base, pn={"on": "on", "pos": "bc", "size": 9, "tpl": tpl},
        toc={"on": "on", "solo": True, "pos": "top"}), body), "G_long_table")
    pages, mkmap, toc_pages = read_pdf(pdf)
    chk("G_long_table 脚本零报错", not fail, fail)
    foots = [p["foot"] for p in pages]
    # 8.1 表确实跨页了（否则这个样本测不到漂移源）
    span = (mkmap.get(11) or 0) - (mkmap.get(10) or 0)
    chk("G_long_table 表格确实跨页", span >= 1, "表前P%s 表后P%s" % (mkmap.get(10), mkmap.get(11)))
    # 8.2 打印侧表头确实在续页重复（Chromium paged-media 行为，漂移源本体）
    rep = sum(1 for p in pages if "序号" in (p["text"] or "").replace(" ", ""))
    chk("G_long_table 续页重复表头", rep >= 2, "含表头页数=%d" % rep)
    # 8.3 表格前后标题的目录号 == 打印真值落页的页脚号（漂移会打破这条）
    bad = []
    for item in toc:
        mm = re.search(r"M(\d{4})", item["t"])
        if not mm:
            continue
        k = int(mm.group(1))
        phys = mkmap.get(k)
        if phys is None:
            bad.append((item["t"][:10], "未落页"))
            continue
        f = foots[phys - 1]
        want = f[0] if f else None
        if (want is None) != (not item["n"]) or (want is not None and item["n"] != want):
            bad.append((item["t"][:12], "目录%s/页脚%s" % (item["n"], want)))
    chk("G_long_table 目录号与打印真值一致", not bad, bad[:3])
    # 8.4 {P} = 参与编号页数
    numbered = [(i, f) for i, f in enumerate(foots) if f]
    tot = {f[1] for _i, f in numbered}
    chk("G_long_table {P}=参与编号页数", tot == {str(len(numbered))},
        (sorted(tot), len(numbered)))

    print("\n" + "=" * 52)
    print("PASS %d / FAIL %d / SKIP %d" % (len(PASS), len(FAIL), len(SKIP)))
    if FAIL:
        print("失败项：" + " | ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
