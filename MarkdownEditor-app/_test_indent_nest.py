# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""<<< 分层配对回归测试（v2.26.0）。

口径（与 ``` 围栏同一套，唯一一条规则）：
  最外围只认 3 个；进了块只能写更大的个数（3 里 4、4 里 5…，跳级也认）；
  严格相等才收口——个数不对等一律不收，配不上的开符按文本露出（不兜底）。

取代旧版「开闭同符号、状态翻转、不支持嵌套」：那条规矩下叠层深只能靠
并列紧邻自动累加（curInd），只进不退，回到父级就错版。个数显式写出后，
进哪层、回哪层都由符号自己说清楚。

起点仍是 curInd（继承上一段的容器级缩进，空行打断归零），块内递归渲染。

用法：python _test_indent_nest.py
输出只有 PASS / FAIL；exit 0 = 全过。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "md-parser.js")

HARNESS = r"""
const P = require(process.argv[1]);
const O = { indents: { p: 0, quote: 0, li: 30 } };
function run(src) {
  const dg = [];
  const h = P.parseMarkdown(src, 0, Object.assign({}, O, { diag: dg }), 0);
  return { h: h, dg: dg };
}
function mls(h) {
  return (h.match(/margin-left:(\d+)px/g) || []).map(s => parseInt(s.match(/\d+/)[0], 10));
}
function nblk(h) { return (h.match(/class="ind-blk"/g) || []).length; }
function codes(dg) { return dg.map(d => d.code); }
function has(h, s) { return h.indexOf(s) >= 0; }

const L3 = "<<<", L4 = "<<<<", L5 = "<<<<<", L6 = "<<<<<<";

const CASES = [
  ["3 包 4：两级，外层 30、内层再 30",
   [L3, "- 甲1", L4, "+ 甲1a", L4, "- 甲2", L3].join("\n"),
   (r) => nblk(r.h) === 2 && mls(r.h).length === 2
       && mls(r.h)[0] === 0 && mls(r.h)[1] === 30
       && has(r.h, 'u-hollow">甲1') && has(r.h, 'u-solid">甲1a')
       && has(r.h, 'u-hollow">甲2')],

  ["3 包 4 包 5：三级都独立成块",
   [L3, L4, L5, "x", L5, L4, L3].join("\n"),
   (r) => nblk(r.h) === 3 && r.dg.length === 0],

  ["并列两块：不递进，各自从同一基准起",
   [L3, "xxx", L3, L3, "xxx", L3].join("\n"),
   (r) => nblk(r.h) === 2 && mls(r.h).join(",") === "0,0"],

  ["无空行继承：块内有列表，下一块 +30",
   [L3, "+ a", L3, L3, "+ b", L3].join("\n"),
   (r) => mls(r.h).join(",") === "0,30"],

  ["空行打断：继承链清零，回到 0",
   [L3, "+ a", L3, "", L3, "+ b", L3].join("\n"),
   (r) => mls(r.h).join(",") === "0,0"],

  ["最外层 4 个：不认识，D104 + 文本露出",
   [L4, "内容", L4].join("\n"),
   (r) => codes(r.dg).filter(c => c === "D104").length === 2
       && nblk(r.h) === 0 && has(r.h, "&lt;&lt;&lt;&lt;")],

  ["最外层 10 个：同样不认识",
   "<".repeat(10) + "\n内容\n" + "<".repeat(10),
   (r) => codes(r.dg).filter(c => c === "D104").length === 2 && nblk(r.h) === 0],

  ["3 开 4 收：4 不是收口，3 未闭合 → D101",
   [L3, "xxx", L4].join("\n"),
   (r) => codes(r.dg).indexOf("D101") >= 0 && nblk(r.h) === 0],

  ["3 里 6 里 4：4 比 6 小，6 未闭合当文本，3 仍正常闭合",
   [L3, L6, "xxx", L4, "xxx", L3].join("\n"),
   (r) => nblk(r.h) === 1
       && has(r.h, "&lt;&lt;&lt;&lt;&lt;&lt;") && has(r.h, "&lt;&lt;&lt;&lt;")
       && codes(r.dg).filter(c => c === "D101").length === 0],

  ["3 里 4 里 3：那个 3 是外层收口，4 未闭合当文本",
   [L3, L4, "xxx", L3].join("\n"),
   (r) => nblk(r.h) === 1 && has(r.h, "&lt;&lt;&lt;&lt;")
       && codes(r.dg).length === 0],

  ["行尾带内容：D102，按普通文本",
   L3 + " yyyy " + L3,
   (r) => codes(r.dg).indexOf("D102") >= 0 && has(r.h, "&lt;&lt;&lt; yyyy")],

  ["块内普通行不受影响：标题、列表、引用照旧",
   [L3, "# 标题", "+ 项", "> 引", L3].join("\n"),
   (r) => nblk(r.h) === 1 && has(r.h, "<h1>") && has(r.h, "<blockquote>")],

  ["块内引用里的 4 个：层级透传，不当最外层",
   [L3, "> 引", L4, "x", L4, L3].join("\n"),
   (r) => nblk(r.h) === 2 && codes(r.dg).length === 0],
];

let fail = 0;
for (const [name, src, fn] of CASES) {
  let ok = false, detail = "";
  try {
    const r = run(src);
    ok = !!fn(r);
    if (!ok) detail = JSON.stringify({ ml: mls(r.h), blk: nblk(r.h),
                                       dg: codes(r.dg), h: r.h.slice(0, 160) });
  } catch (e) {
    detail = "EXC " + e.message;
  }
  if (!ok) fail++;
  console.log((ok ? "PASS  " : "FAIL  ") + name + (ok ? "" : " | " + detail));
}
console.log("__SUMMARY__" + CASES.length + "|" + fail);
"""


def main():
    r = subprocess.run(["node", "-e", HARNESS, JS],
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or "") + (r.stderr or "")
    total = fail = 0
    for line in out.splitlines():
        if line.startswith("__SUMMARY__"):
            total, fail = [int(x) for x in line[len("__SUMMARY__"):].split("|")]
        elif line.startswith(("PASS", "FAIL")):
            print(line)
    if total == 0:
        print(out)
        print("NO RESULT")
        return 1
    print("\n===== %d/%d PASS =====" % (total - fail, total))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
