# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_test_parser_sync.py -- md-parser.js 与 markdown-editor.html 解析器段一致性校验

背景：md-parser.js 是从 markdown-editor.html 的 /*PARSER_START*/../*PARSER_END*/
段逐字抽取的独立发行版（UMD 包壳 + 可选 opts.indents 增强）。两者构成双源，
本脚本把"漂移"变成显式检查点：core 段字节级不一致即 FAIL。

口径：
  1. 两个文件均按标记行定位 core 段（不硬编码行号，行号可漂、标记不可丢）；
  2. v2.22.0 起 core 为最终形态，**逐字节全等比对、零归一化**（原两处抽取
     增强——签名与 IPX 兜底——已直接写进 html core，增强列表清空）；
  3. 任何在 html 解析器段或 md-parser.js core 段的改动，若未同步另一方，
     本测试 FAIL。改动流程：改 html 解析器段 → 重新抽取 md-parser.js → 本测试 PASS。

用法：
  python _test_parser_sync.py            # 校验默认 md-parser.js
  python _test_parser_sync.py <js路径>   # 校验指定副本（负向自检用）

输出只有 PASS / FAIL；exit 0 = PASS，exit 1 = FAIL。
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "markdown-editor.html")
JS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "md-parser.js")

START_MARK = "/*PARSER_START*/"
END_MARK = "/*PARSER_END*/"

# v2.22.0 起 core 为最终形态，逐字抽取、零归一化（历史增强锚点已清空）
ENHANCE = []


def extract_core(path):
    """按标记行提取 core 段（含标记行），返回行列表。标记缺失/多处即报错。"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.strip() == START_MARK]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == END_MARK]
    if len(starts) != 1 or len(ends) != 1:
        raise AssertionError(
            "%s: 标记异常 START=%d END=%d（必须各恰一处）" % (path, len(starts), len(ends)))
    s, e = starts[0], ends[0]
    if e <= s:
        raise AssertionError("%s: END 在 START 之前" % path)
    return lines[s:e + 1]


def main():
    try:
        html_core = extract_core(HTML)
        js_core = extract_core(JS)
    except AssertionError as ex:
        print("FAIL  %s" % ex)
        return 1

    # html core → 归一化（应用两处已知增强）→ 应与 js core 字节级全等
    norm = "\n".join(html_core)
    for old, new in ENHANCE:
        cnt = norm.count(old)
        if cnt != 1:
            print("FAIL  html core 中增强锚点出现 %d 次（应为 1）：%r" % (cnt, old[:60]))
            return 1
        norm = norm.replace(old, new)

    js_text = "\n".join(js_core)
    if norm == js_text:
        print("PASS  md-parser.js core 与 markdown-editor.html 解析器段一致"
              "（%d 行，逐字节全等）" % len(js_core))
        return 0

    # 差异定位：逐行找第一处分歧，给出可行动信息
    nl, jl = norm.split("\n"), js_text.split("\n")
    for k in range(max(len(nl), len(jl))):
        a = nl[k] if k < len(nl) else "<缺行>"
        b = jl[k] if k < len(jl) else "<缺行>"
        if a != b:
            print("FAIL  core 段漂移！第一处分歧在 core 第 %d 行：" % (k + 1))
            print("  html(归一) : %s" % a[:120])
            print("  md-parser  : %s" % b[:120])
            print("  处置：改了 html 解析器段后必须重新抽取 md-parser.js；"
                  "反之改 md-parser.js 必须回写 html。改完重跑本测试。")
            return 1
    print("FAIL  未定位到差异行（不应发生）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
