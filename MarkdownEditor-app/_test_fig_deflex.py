# -*- coding: utf-8 -*-
"""v2.26.4 切片 figure 防翻面回归测试

背景（判例 2026-11-02 食品检验检测机构现状分析.smd）：side="t"（题注在上）的
figure 用 flex column-reverse 实现题注翻面——单图没问题；长图切片后 figure 里
是整串条带 img，column-reverse 把条带视觉顺序整串倒过来，且 flex 在 Paged.js
里不可跨页分裂（大空白 + 跨页叠印）。

修复：_deflex_sliced_figures 把含 ≥2 条条带且 side="t" 的 figure 改写为
side="ts"（CSS display:block;break-inside:auto）并把 figcaption 移到首条
条带之前。本测试钉死改写规则与 CSS 配对。
"""
import io
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import md_server as S  # noqa: E402

ICB_W = 174.0
IMG_MAXH = 245.0
TALL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "_tmp_slice_fixture", "tall.png")

PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS  %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s  %s" % (name, detail))


def strips(n, digest="abc123"):
    return "".join('<img src="/static/_slice/%s/strip-%02d.png" alt="x">'
                   % (digest, i) for i in range(1, n + 1))


def fig(side, inner, with_cap=True):
    cap = "<figcaption>行业分析点</figcaption>" if with_cap else ""
    return ('<figure class="mde-fig" data-fig-side="%s" data-fig-gap="0.5" '
            'style="--figgap:0.5">%s%s</figure>' % (side, inner, cap))


# ---------- A组：_deflex_sliced_figures 直测 ----------

# A1 多条带 + side=t → ts + 题注前置
out = S._deflex_sliced_figures(fig("t", strips(3)))
ok("A1 多条带 side=t → side=ts", 'data-fig-side="ts"' in out, out[:120])
ok("A2 题注移到首条条带之前",
   out.index("<figcaption>") < out.index("strip-01.png"), out[:200])
ok("A3 题注不再留在尾部", out.rstrip().endswith("</figure>")
   and "</figcaption></figure>" not in out, out[-80:])

# A4 side=t + 2 条条带（临界条数）→ 也改写
out = S._deflex_sliced_figures(fig("t", strips(2)))
ok("A4 两条带也改写 ts", 'data-fig-side="ts"' in out, out[:120])

# A5 单条带 + side=t → 不动（flex 单图行为零变化）
out = S._deflex_sliced_figures(fig("t", strips(1)))
ok("A5 单条带 side=t 不动", 'data-fig-side="t"' in out
   and "</figcaption></figure>" in out, out[:160])

# A6 多条带 + side=b → 不动（本就是块级流）
out = S._deflex_sliced_figures(fig("b", strips(3)))
ok("A6 side=b 不动", 'data-fig-side="b"' in out
   and "</figcaption></figure>" in out, out[:160])

# A7 多条带 + 无题注 → 只改 side，不崩
out = S._deflex_sliced_figures(fig("t", strips(3), with_cap=False))
ok("A7 无题注只改 side", 'data-fig-side="ts"' in out
   and "<figcaption" not in out, out[:160])

# A8 已是 ts → 幂等（题注不二次搬动）
out2 = S._deflex_sliced_figures(out.replace('data-fig-side="t"',
                                            'data-fig-side="ts"', 1)
                                if 'data-fig-side="ts"' not in out else out)
src = fig("ts", strips(3)).replace("%s%s</figure>",
                                   "").replace('>%s%s</figure>', "")
src = ('<figure class="mde-fig" data-fig-side="ts" data-fig-gap="0.5" '
       'style="--figgap:0.5"><figcaption>行业分析点</figcaption>%s</figure>'
       % strips(3))
out = S._deflex_sliced_figures(src)
ok("A8 已是 ts 幂等", out == src, out[:160])

# A9 普通单图 figure（无切片）→ 不动
plain = ('<figure class="mde-fig" data-fig-side="t" data-fig-gap="0.3">'
         '<img src="/img?path=x.png" alt=""><figcaption>题</figcaption></figure>')
out = S._deflex_sliced_figures(plain)
ok("A9 普通单图不动", out == plain, out[:160])

# A10 两个 figure 混排：只有多条带的那个被改写
two = fig("t", strips(2)) + plain
out = S._deflex_sliced_figures(two)
ok("A10 混排只改切片 figure", 'data-fig-side="ts"' in out
   and out.count("strip-01.png") == 1 and 'data-fig-side="t"' in out,
   out[:300])

# ---------- B组：端到端——超高图在 side=t figure 里切片后自动防翻面 ----------

def img_tag(path):
    q = urllib.parse.quote(path, safe="")
    return '<img src="/img?path=%s" alt="行业分析点">' % q


body = ('<p>前文。</p>' + fig("t", img_tag(TALL)) + '<p>后文。</p>')
out = S._slice_tall_images(body, ICB_W, IMG_MAXH)
n_strips = out.count("/static/_slice/")
ok("B1 端到端切出多条带", n_strips >= 2, "条带数=%d" % n_strips)
ok("B2 端到端 side 改写 ts", 'data-fig-side="ts"' in out, out[:200])
ok("B3 端到端题注前置",
   out.index("<figcaption>") < out.index("strip-01.png")
   if n_strips >= 2 else False, out[:300])

# B4 单条带边界：side=t figure 里的图不超高 → 原样返回（flex 保留）
small = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "_tmp_slice_fixture", "small.png")
body2 = fig("t", img_tag(small))
out2 = S._slice_tall_images(body2, ICB_W, IMG_MAXH)
ok("B4 不切图保持 side=t", 'data-fig-side="t"' in out2
   and "/static/_slice/" not in out2, out2[:200])

# ---------- C组：CSS 配对 ----------

css = S.FIGCAP_BASE_CSS
ok("C1 ts 块级流规则在位",
   'figure.mde-fig[data-fig-side="ts"]{display:block;break-inside:auto;}' in css)
ok("C2 ts 题注间距规则在位",
   'figure.mde-fig[data-fig-side="ts"]>figcaption{margin-bottom:' in css)
ok("C3 t 的 flex 规则原样保留",
   'figure.mde-fig[data-fig-side="t"]{display:flex;'
   'flex-direction:column-reverse;align-items:flex-start;}' in css)

print("\n%d/%d PASS" % (PASS, PASS + FAIL))
sys.exit(0 if FAIL == 0 else 1)
