# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""反引号整串配对回归测试（v2.25.0）。

口径（v2.25.0 起，唯一一条规则）：
  连续反引号先整串读出来、记长度 N，再决定身份——
    N=1   行内代码定界，找下一个 N=1 收尾
    N=2   自闭合（一个开、一个闭，内容为空），不需要搭档
    N≧3   定界，找下一个「长度恰好等于 N」的串收尾；找不到则整串按字面
  行首独占一行且 N≧3 时是块级围栏，收尾行的个数必须 ≧ 开头的个数。

在此之前是「看见下一个反引号就抓」，于是行内的 ``` 被拆成 `` + `，
第三个反引号跑去抢后面 $…$ 的开引号，公式被当 LaTeX 渲染成空。

用法：python _test_tick_pair.py
输出只有 PASS / FAIL；exit 0 = 全过。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "md-parser.js")
RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, ok))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                       (" | " + extra) if extra else ""))


HARNESS = r"""
const P = require(process.argv[1]);
const B = "`";
const C = B.repeat(3), C4 = B.repeat(4), C5 = B.repeat(5);
const CASES = [
  // ---- 行内：整串读，三个不再拆成 `` + ` ----
  ["裸写三个（行中）不构成任何语法", "想表达 " + C + " 这段是围栏",
   "<p>想表达 ``` 这段是围栏</p>"],
  ["单反引号包三个：进代码", "想表达 " + B + " " + C + " " + B + " 这段是围栏",
   "<p>想表达 <code> ``` </code> 这段是围栏</p>"],
  ["单反引号包「三+文字+三」", "想表达 " + B + " xxx " + C + " zzz " + B + " 这段",
   "<p>想表达 <code> xxx ``` zzz </code> 这段</p>"],
  ["三个包一个（3 配 3，中间 1 是内容）", "写 " + C + " " + B + " " + C + " 结束",
   "<p>写 <code> ` </code> 结束</p>"],
  ["四个包三个（行内）", "写 " + C4 + " " + C + " " + C4 + " 结束",
   "<p>写 <code> ``` </code> 结束</p>"],
  ["五个未配对：整串字面", "写 " + C5 + " 结束",
   "<p>写 ````` 结束</p>"],
  // ---- 行内：N=2 自闭合 ----
  ["两个相邻=一个空代码", "写 " + B + B + " 结束",
   "<p>写 <code></code> 结束</p>"],
  ["两个包字=空代码+字+空代码", "写 " + B + B + "x" + B + B + " 结束",
   "<p>写 <code></code>x<code></code> 结束</p>"],
  // ---- 行内：常规不受影响 ----
  ["单反引号常规用法", "命令 " + B + "npm i" + B + " 就行",
   "<p>命令 <code>npm i</code> 就行</p>"],
  ["多个单反引号并列", "甲 " + B + "a" + B + " 乙 " + B + "b" + B + " 丙",
   "<p>甲 <code>a</code> 乙 <code>b</code> 丙</p>"],
  ["转义反引号不参与配对（CHANGELOG 实况）",
   "一行 " + B + "- 键：\\" + B + "旧\\" + B + " → \\" + B + "新\\" + B + B + "）。",
   "<p>一行 <code>- 键：`旧` → `新`</code>）。</p>"],
  // ---- 块级围栏：最外围不限个数（≥3 即成围栏）；开 N 收 N；严格相等才收口 ----
  ["围栏 3 开 3 收", C + "\nabc\n" + C,
   "<pre><code>abc</code></pre>"],
  ["围栏 4 开 4 收", C4 + "\nabc\n" + C4,
   "<pre><code>abc</code></pre>"],
  ["围栏 4 包 3：代码块里展示三个反引号", C4 + "\n" + C + "\n" + C4,
   "<pre><code>```</code></pre>"],
  ["围栏 5 包 4 包 3：内层少也能嵌（外层多内层少）", C5 + "\n" + C4 + "\n" + C + "\nx\n" + C + "\n" + C4 + "\n" + C5,
   "<pre><code>````\n```\nx\n```\n````</code></pre>"],
  ["围栏 3 包 4：代码块内嵌代码块（外层少内层多）", C + "md\n" + C4 + "bash\nls\n" + C4 + "\n" + C,
   "<pre><code class=\"lang-md\">````bash\nls\n````</code></pre>"],
  ["围栏 3 包 5 包 4：内层更大的都只是内容", C + "\n" + C5 + "\n" + C4 + "\nx\n" + C4 + "\n" + C5 + "\n" + C,
   "<pre><code>`````\n````\nx\n````\n`````</code></pre>"],
  ["围栏 3 开 4 收：4 不是收口，未闭合吃到文末", C + "\nabc\n" + C4,
   "<pre><code>abc\n````</code></pre>"],
  ["围栏 4 开 3 收：3 不是收口，未闭合吃到文末", C4 + "\nabc\n" + C,
   "<pre><code>abc\n```</code></pre>"],
  ["围栏 3 开未闭合：吃到文末（标准行为）", C + "\nabc",
   "<pre><code>abc</code></pre>"],
];

let fail = 0;
for (const [name, src, want] of CASES) {
  let got = "";
  try { got = P.parseMarkdown(src).trim(); } catch (e) { got = "__ERR__" + e.message; }
  const ok = got === want;
  if (!ok) fail++;
  console.log((ok ? "PASS  " : "FAIL  ") + name + (ok ? "" : "\n      want: " + want + "\n      got : " + got));
}
// 围栏未闭合必须报 D103（不能静默）
try {
  const dg = [];
  P.parseMarkdown(C + "\nabc", 0, { diag: dg });
  const ok = dg.some(d => d.code === "D103");
  if (!ok) fail++;
  console.log((ok ? "PASS  " : "FAIL  ") + "围栏未闭合报 D103");
} catch (e) {
  fail++;
  console.log("FAIL  围栏未闭合报 D103 | " + e.message);
}
console.log("__SUMMARY__" + CASES.length + "|" + fail);
"""


MATH_HARNESS = r"""
/* 公式提取层：extractMath 在 markdown-editor.html 内联作用域，这里现场抽函数体跑，
   测的是真代码。它依赖同作用域的 _tickScan，一并抽出来。 */
const fs = require("fs");
const html = fs.readFileSync(process.argv[1], "utf8");
function seg(a, b) {
  const i = html.indexOf(a);
  if (i < 0) throw new Error("缺少标记 " + a);
  const j = html.indexOf(b, i + 1);
  if (j < 0) throw new Error("缺少结束标记 " + b);
  return html.slice(i, j);
}
const src = seg("function _tickScan(text){", "function parseInline(text,noMde){")
          + seg("var mathStore=[];", "function restoreMath(root){");
const api = new Function("return (function(){\n" + src +
  "\nreturn {extractMath:extractMath, store:function(){return mathStore;}};\n})();")();
const B = "`", C = B.repeat(3), C4 = B.repeat(4);
const CASES = [
  ["行内代码里的 $ 不当公式", "命令 " + B + "echo $HOME$" + B + " 结束", true],
  ["真实公式照抽", "值 $x^2$ 与块 $$y=1$$", false, 2],
  ["11 个反引号那行：全部落进代码、零公式",
   "ATX 标题、``` 围栏、表格（含 `:` 与 `\\|`）、`$…$` 与 `$$…$$` 公式。", true],
  ["裸写三个后跟公式：公式仍识别", "想表达 " + C + " 然后 $a+b$ 是公式", false, 1],
  ["单引号包三个后跟公式：公式仍识别", "写 " + B + " " + C + " " + B + " 然后 $a+b$ 是公式", false, 1],
  ["3 包 4 围栏里的公式不抽", [C, C4, "$x$", C4, C].join(String.fromCharCode(10)), true],
];
let fail = 0;
for (const [name, src1, noMath, wantN] of CASES) {
  let store = [];
  try {
    api.extractMath(src1);
    store = api.store();
  } catch (e) {
    fail++;
    console.log("FAIL  " + name + " | " + e.message);
    continue;
  }
  const ok = noMath ? store.length === 0 : store.length === (wantN || 1);
  if (!ok) fail++;
  console.log((ok ? "PASS  " : "FAIL  ") + name +
    (ok ? "" : " | store=" + JSON.stringify(store)));
}
console.log("__SUMMARY__" + CASES.length + "|" + fail);
"""


def run_harness(harness, arg, label):
    p = subprocess.run(["node", "-e", harness, arg],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    for line in out.splitlines():
        if line.startswith("__SUMMARY__"):
            total, fail = line[len("__SUMMARY__"):].split("|")
            total, fail = int(total) + 1, int(fail)
            check("%s 合计 %d 条" % (label, total), fail == 0,
                  "%d 条不符" % fail if fail else "")
            continue
        if line.startswith("PASS  "):
            check(line[6:], True)
        elif line.startswith("FAIL  "):
            parts = line[6:].split("\n", 1)
            check(parts[0], False, parts[1].strip() if len(parts) > 1 else "")
        elif line.strip():
            print("  " + line)
    if err.strip():
        print("STDERR: " + err.strip()[:500])


def main():
    if not os.path.isfile(JS):
        print("FAIL md-parser.js 不存在")
        sys.exit(1)
    run_harness(HARNESS, JS, "解析器")
    run_harness(MATH_HARNESS, os.path.join(HERE, "markdown-editor.html"), "公式层")
    bad = [n for n, ok in RESULTS if not ok]
    print("\n===== %d/%d PASS =====" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
