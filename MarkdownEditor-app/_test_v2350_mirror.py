# -*- coding: utf-8 -*-
"""v2.35.0 静态纪律测试：打印断页规则必须 1:1 镜像到多列测量盒

为什么单列一条测试：测量盒靠**多列**复刻打印的**分页**。打印里每加一条
`break-*:page`，测量盒就得有一条对应的 `break-*:column`；漏一条不会报错，
只会让量出来的页数偏少、目录页码整体前移。2026-11-04 就是这样漏了
`.page-region` 的 `break-after`：真值 7 页量出 5 页，逐个标题错 1~2 页，
而所有字符串断言全绿。这类错误只能靠静态比对挡。

跑法：python _test_v2350_mirror.py
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
        "" if not detail else "   [" + str(detail)[:160] + "]"))


def print_css():
    cfg = {"paper": "A4", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
           "tone": "light",
           "pn": {"on": "on", "pos": "outer", "size": 9, "tpl": "{p}"},
           "toc": {"on": "on", "solo": True, "pos": "top"}}
    html = m.build_paged_html(None, "<p>x</p>", "", cfg, native=True)
    mm = re.search(r'<style id="pnpage">(.*?)</style>', html, re.S)
    return mm.group(1) if mm else ""


def meas_css():
    """把 _PN_FILL_JS 里 MEAS_CSS 的字面量拼起来（CH/CW 换成占位）。"""
    src = m._PN_FILL_JS
    i = src.find("var MEAS_CSS")
    j = src.find(";\n", i)
    seg = src[i:j]
    seg = re.sub(r"'\s*\+\s*CH\s*\+\s*'", "CH", seg)
    seg = re.sub(r"'\s*\+\s*CW\s*\+\s*'", "CW", seg)
    lits = re.findall(r"'([^']*)'", seg)
    return "".join(lits)


def rules(css, prop):
    """返回 [(selector_list, value)]，只取该属性。"""
    out = []
    for mm in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel, body = mm.group(1).strip(), mm.group(2)
        v = re.search(re.escape(prop) + r"\s*:\s*([a-z\-]+)", body)
        if v:
            out.append((sel, v.group(1)))
    return out


def norm(sel):
    """把选择器归一成"测量盒里的写法"：#paged-content 前缀与 > 去掉，空白压平。"""
    s = re.sub(r"#paged-content\s*>?\s*", "", sel)
    return re.sub(r"\s+", " ", s).strip()


def bare(sel):
    """测量盒选择器去掉 #pnmeas 作用域前缀，好和打印侧同一条比较。"""
    return re.sub(r"^#pnmeas\s+", "", norm(sel))


def main():
    pcss, mcss = print_css(), meas_css()
    print("\n[一] 取到两套 CSS")
    chk("打印 CSS 非空", len(pcss) > 200, len(pcss))
    chk("测量 CSS 非空", len(mcss) > 100, len(mcss))

    mbefore, mafter = set(), set()
    for prop, pool in (("break-before", mbefore), ("break-after", mafter)):
        for sel, _v in rules(mcss, prop):
            for one in sel.split(","):
                pool.add(bare(one))

    print("\n[二] 打印里每条 break-*:page 都有 column 镜像")
    miss = []
    seen = 0
    for prop in ("break-before", "break-after"):
        for sel, val in rules(pcss, prop):
            if val != "page":
                continue                       # auto / avoid / 其它不催页
            for one in sel.split(","):
                tail = norm(one)
                if not tail:
                    continue
                seen += 1
                pool = mbefore if prop == "break-before" else mafter
                if tail not in pool:
                    miss.append(prop + " " + tail)
    chk("命中的打印断页选择器数 > 0", seen > 0, seen)
    chk("无遗漏镜像", not miss, miss)

    print("\n[三] 测量盒不许偷偷改版面")
    chk("测量盒自身不产生页脚", "@bottom" not in mcss)
    chk("测量盒不写纸张尺寸", "size:A4" not in mcss and "@page" not in mcss)

    print("\n" + "=" * 52)
    print("PASS %d / FAIL %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：" + " | ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
