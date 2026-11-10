# -*- coding: utf-8 -*-
"""一次性探针：对照 KaTeX（预览）与 latex2mathml（Word 导出）对同一批公式的接受度。
只读，不参与打包。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "docxdeps"))
import latex2mathml.converter as conv

cases = [
    ("右上", "x^{2}"),
    ("右下", "x_{i}"),
    ("四角标手工", "{}^{a}_{b}X^{c}_{d}"),
    ("left/right 隔开", "{}_{b}^{a}X"),
    ("根号", "\\sqrt[3]{x+1}"),
    ("分数", "\\frac{a}{b}"),
    ("方框", "\\boxed{x^2}"),
    ("overset", "\\overset{\\triangle}{AB}"),
    ("underset", "\\underset{n}{\\max}"),
    ("underbrace", "\\underbrace{a+b}_{n}"),
    ("行列式", "\\begin{vmatrix}a&b\\\\c&d\\end{vmatrix}"),
    ("分段", "\\begin{cases}x&x>0\\\\0&x\\le0\\end{cases}"),
    ("上划线", "\\overline{AB}"),
    ("向量", "\\vec{a}"),
    ("度数", "90^{\\circ}"),
    ("极限", "\\lim_{x\\to0}\\frac{\\sin x}{x}"),
    ("积分", "\\int_{0}^{1}f(x)\\,dx"),
    ("求和", "\\sum_{i=1}^{n}i^2"),
    ("中文 text", "\\text{当}x>0"),
    ("着色", "\\color{red}{x}"),
    ("phantom", "\\phantom{xx}"),
    ("underline", "\\underline{x}"),
    ("aligned", "\\begin{aligned}a&=b\\\\c&=d\\end{aligned}"),
    ("mathbb", "\\mathbb{E}[X]"),
    ("偏导", "\\frac{\\partial f}{\\partial x}"),
    ("空心方框", "\\square\\,\\blacksquare\\,\\Box"),
    ("填空横线", "\\underline{\\hspace{2em}}"),
    ("花体", "\\mathcal{F}"),
]
p = f = 0
for name, tex in cases:
    try:
        m = conv.convert(tex)
        ok = bool(m) and len(m) > 40
        err = ""
    except Exception as e:
        ok, err = False, str(e).split("\n")[0][:80]
    if ok:
        p += 1
        print("PASS  %-14s | %s" % (name, tex))
    else:
        f += 1
        print("FAIL  %-14s | %s  -> %s" % (name, tex, err))
print("\nTOTAL %d / PASS %d / FAIL %d" % (p + f, p, f))
