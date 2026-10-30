# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_extract_parser.py -- 从 markdown-editor.html 重抽独立解释器 md-parser.js

流程（v2.22.0 起）：
  1. 按标记行定位 core 段（/*PARSER_START*/ .. /*PARSER_END*/，含标记行）；
  2. **逐字抽取，不再应用增强**——v2.22.0 起 html core 已自带最终形态
     （parseMarkdown(src,_lv,opts,_base) 签名与 IPX 的 opts.indents 兜底），
     html core 与 md-parser.js core 逐字节同文，同步校验零归一化；
  3. 外包 UMD 壳（浏览器 MDParser / CommonJS / ESM 通用），写 md-parser.js。

用法（在 MarkdownEditor-app 目录下）：
  python _extract_parser.py              # 原地重抽 markdown-editor.html → md-parser.js
  python _extract_parser.py <src> <dst>  # 指定源/目标

改完必跑：python _test_parser_sync.py（PASS 后再跑 node md-parser.test.cjs 回归）。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "markdown-editor.html")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "md-parser.js")

START_MARK = "/*PARSER_START*/"
END_MARK = "/*PARSER_END*/"

HEADER = '''/*! md-parser.js — MDEditor 自研 Markdown 方言解释器（独立抽取版）
 * 来源：MarkdownEditor-app/markdown-editor.html
 *       标记 PARSER_START … PARSER_END 之间（逐字抽取，行号以标记定位）
 * 抽取脚本：_extract_parser.py（重抽后必跑 _test_parser_sync.py 校验）
 * 许可：同项目根 LICENSE（见 MarkdownEditor-app/LICENSE）
 *
 * 用法：
 *   // 浏览器：<script src="md-parser.js"></script> 后
 *   MDParser.parseMarkdown("# 标题\\n\\n正文");
 *   // Node / CommonJS
 *   const { parseMarkdown } = require('./md-parser.js');
 *   parseMarkdown(src);
 *   // ESM
 *   import { parseMarkdown } from './md-parser.js';
 *
 * 相对原文件：仅外包 UMD 壳，core 段逐字复制未改动（v2.22.0 起 html core
 *   已含 parseMarkdown(src,_lv,opts,_base) 签名、opts.indents 兜底与语法
 *   诊断埋点；opts.diag 传数组即可收集 {line,code,msg,sev} 诊断）。
 * 其余解析逻辑逐字复制，未改动。改 html 解析器段后必须重新抽取本文件。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else if (typeof define === 'function' && define.amd) define(factory);
  else { root.MDParser = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  /* ===== 以下自 markdown-editor.html PARSER_START … PARSER_END 原样抽取 ===== */

'''

FOOTER = '''
  /* ===== 抽取结束 ===== */
  return {
    parseMarkdown: parseMarkdown,
    parseInline: parseInline,
    parseList: parseList,
    parseTable: parseTable,
    parseFenceLang: parseFenceLang,
    splitRow: splitRow,
    escapeHtml: escapeHtml,
    escAttr: escAttr,
    sanitizeUrl: sanitizeUrl
  };
}));
'''


def main():
    with io.open(SRC, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.strip() == START_MARK]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == END_MARK]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise SystemExit("FAIL 标记异常 START=%s END=%s" % (starts, ends))
    core = "\n".join(lines[starts[0]:ends[0] + 1])

    # v2.22.0 起 core 为最终形态，逐字抽取、无增强锚点（列表保留空结构，
    # 未来若再出现抽取版差异可在此追加 (old, new) 锚点）
    anchors = []
    for old, new in anchors:
        if core.count(old) != 1:
            raise SystemExit("FAIL 增强锚点出现 %d 次（应为 1）: %r" % (core.count(old), old[:50]))
        core = core.replace(old, new)

    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(HEADER + core + FOOTER)
    print("EXTRACT OK: %s (%d bytes)" % (OUT, len(HEADER + core + FOOTER)))


if __name__ == "__main__":
    main()
