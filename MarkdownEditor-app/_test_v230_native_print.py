# -*- coding: utf-8 -*-
"""v2.30.0 原生分页（CSS Paged Media）契约测试

判定口径：每条 PASS/FAIL，无"大致可用"。
覆盖 2026-11-03 双路对照实测暴露过的全部事故点：
  - 产物含脚本 / 依赖 Paged.js         -> 分页不可预测且会丢内容
  - 无 @page 页码                     -> 纸面没页码
  - 缺 thead table-header-group        -> 跨页表无表头
  - 首块 full-page 的 break-before     -> 封面后多一张空白页
  - body 默认 margin 8px               -> 整篇下移、独占页溢出
  - body 宽度未钉死版心                -> 表格/代码块右侧出纸被裁
  - 缺 print-color-adjust:exact        -> 深色纸印成白纸
用法：python _test_v230_native_print.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import md_server as m

PASS, FAIL = [], []


def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (
        "" if not detail else "   [" + str(detail)[:120] + "]"))


BODY = (
    '<div class="pblk"><div class="full-page" data-full-pos="m" '
    'style="background-image:url(\'/img?path=x.png\');background-size:cover">'
    '<h1 id="md-h-1">封面标题</h1></div>'
    '<p>封面后的第一段。</p></div>'
    '<div class="pblk"><h2 id="md-h-2">第一章</h2>'
    '<p>正文段落。</p>'
    '<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>'
    + "".join("<tr><td>行%d</td><td>值</td></tr>" % i for i in range(40))
    + "</tbody></table></div>"
    '<div class="pblk"><h2 id="md-h-3">第二章</h2><p>再来一段。</p></div>'
)

CFG = {
    "paper": "A4", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
    "tone": "dark",
    "pn": {"on": "on", "pos": "outer", "size": 9,
           "tpl": "第 {p} 页 / 共 {P} 页"},
    "toc": {"on": "off"},
}


def main():
    html = m.build_paged_html(None, BODY, "", CFG, native=True)

    print("\n[一] 产物形态")
    chk("产物不含任何 <script>", "<script" not in html.lower(),
        html.lower().count("<script"))
    chk("产物不引用 Paged.js 运行时",
        "PagedPolyfill" not in html and "paged.polyfill" not in html)

    print("\n[二] 页码（@page margin box）")
    chk("@page 声明存在", bool(re.search(r"@page\s*\{", html)))
    chk("页码用 counter(page)", "counter(page)" in html)
    chk("总页数用 counter(pages)", "counter(pages)" in html)
    chk("外侧页码分奇偶页",
        "@page:right" in html and "@page:left" in html)
    chk("页码模板文字被保留", '"第 "' in html and "页 / 共 " in html)
    chk("页码在 bottom margin box",
        "@bottom-right" in html or "@bottom-center" in html)

    print("\n[三] 分页规则（对齐 typesetting PRINT_CSS）")
    chk("h1 独立起页", re.search(r"h1\{break-before:page;?\}", html) is not None)
    chk("标题不落页末 h2/h3/h4 avoid",
        re.search(r"h2,h3,h4\{break-after:avoid;?\}", html) is not None)
    chk("段落孤行 2/2", "orphans:2" in html and "widows:2" in html)
    chk("列表项孤行 1/1", "li{orphans:1" in html)
    chk("跨页表头重复 thead", "table-header-group" in html)
    chk("表格行不腰斩 tr avoid", re.search(r"tr\{break-inside:avoid;?\}", html) is not None)
    chk("表格允许行间拆页", "table{break-inside:auto" in html
        or "table{width:100% !important" in html)

    print("\n[四] 三处实测事故的防回归")
    chk("首块 full-page 不催空白页",
        "first-child > .full-page{break-before:auto}" in html
        or "first-child.full-page" in html,
        "封面后整页空白事故")
    # v2.31.0：清零边距拆成 html / body 两条（纸色改由 body 兜底后，两条规则
    # 不再合并）。断言只管规则存在，不做位置匹配。
    chk("打印态清零 body 默认边距",
        re.search(r"@media print\{html\{margin:0 !important", html) is not None
        and re.search(r"body\{margin:0 !important;padding:0 !important;", html) is not None,
        "body margin 8px 致独占页溢出")
    # v2.30.1：打印态 body 的宽度仍钉死版心（不依赖它在 @media print 里
    # 的字符距离——中间会陆续插入纸色/透明度规则，位置断言会误报）
    chk("打印态钉死版心宽",
        re.search(r"body\{[^}]*width:174(\.0)?mm !important", html) is not None,
        "超宽表/代码块出纸被裁")
    # v2.31.0 换了口径：html 必须透明（它的底色会盖在 @page 之上），body 则
    # 保留纸色当兜底（@page 失效时至少版心是深的，同色时接缝不可见）。
    chk("打印态 html 透明、body 兜底纸色",
        re.search(r"@media print\{html\{background-color:transparent !important", html) is not None
        and re.search(r"md-tone-light\{background-color:#1a1a1c !important", html) is not None,
        "html 底色会盖住整页图；body 无兜底则 @page 一失效就全白")
    chk("纸色写在 @page 上",
        re.search(r"@page\{size:[^}]*background:#1a1a1c", html) is not None,
        "body 背景只到版心，页边距会是白纸")
    chk("背景强制打印 print-color-adjust",
        "print-color-adjust:exact" in html, "深色纸印成白纸")

    print("\n[五] 屏幕纸面（预览不是裸流）")
    chk("屏幕态有纸张阴影", "@media screen" in html and "box-shadow" in html)
    chk("屏幕纸宽 = 纸宽（含页边距）",
        re.search(r"@media screen\{[\s\S]{0,400}?width:210", html) is not None)

    print("\n[六] 内容零丢失")
    chk("h2 全在", html.count("<h2") == BODY.count("<h2"),
        "%d/%d" % (html.count("<h2"), BODY.count("<h2")))
    chk("table 全在", html.count("<table") == BODY.count("<table"),
        "%d/%d" % (html.count("<table"), BODY.count("<table")))
    chk("表格 40 行全在", html.count("行") >= 40,
        html.count("行"))

    print("\n[七] 回退开关仍在")
    old = m.build_paged_html(None, BODY, "", CFG, native=False)
    chk("native=False 仍产出 Paged.js 版本",
        "PagedPolyfill" in old and "<script" in old.lower())

    # ── v2.31.0 full 整页背景：命名页 + 真实 <img> ─────────────────────
    # 判例：@page 的 background-image 在「背景图形」不勾时整条消失（P1 全白），
    # 而 <img> 是内容，两档输出字节相同。以下断言锁死这条口径。
    print("\n[八] full 整页背景（命名页 + <img>）")

    def _full(mode, pos="cc"):
        body = ('<div class="full-page" data-full-pos="m"'
                ' data-bg-img="/img?path=a.png" data-bg-mode="%s"'
                ' data-bg-pos="%s" style="background-image:url(\'/img?path=a.png\')">'
                '<h1>封面</h1></div><h2>正文</h2><p>x</p>' % (mode, pos))
        return m.build_paged_html(None, body, "", CFG, native=True)

    h_c = _full("c")
    chk("命名页 margin 归零（该页=整张纸）",
        re.search(r"@page mdefbg1\{margin:0;", h_c) is not None,
        "不归零则元素量不到纸宽/纸高")
    chk("full 块写死纸宽纸高",
        re.search(r'\.full-page\[data-mde-pg="mdefbg1"\]\{page:mdefbg1;'
                  r'width:210(\.0)?mm !important;height:297(\.0)?mm !important', h_c)
        is not None, "尺寸不写死就铺不满整张纸")
    chk("插入真实 <img> 且用原始 URL",
        '<img class="mde-pgimg" src="/img?path=a.png"' in h_c,
        "背景图必须走 <img>，不能靠 @page background")
    chk("产物不含 base64 data URI",
        "data:image" not in h_c, "大图 base64 会撑爆产物且非必要")
    chk("打印态元素自身不再画背景",
        re.search(r'@media print\{\.full-page\[data-mde-pg="mdefbg1"\]'
                  r'\{background-image:none !important', h_c) is not None,
        "否则版心内会叠一层、边缘硬切")
    chk("c -> object-fit:cover",
        "object-fit:cover" in h_c, "撑满裁切")
    chk("f -> object-fit:fill",
        "object-fit:fill" in _full("f"), "填充拉伸")
    chk("o -> object-fit:none",
        "object-fit:none" in _full("o"), "原始尺寸")
    chk("九宫定位落到 object-position",
        "object-position:right bottom" in _full("c", "rb"),
        "九宫必须一一对应")

    print("\n" + "=" * 52)
    print("PASS %d / FAIL %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：" + " | ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
