# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_extract_parser.py -- 从 markdown-editor.html 重抽独立解释器 md-parser.js

流程（与 md-parser.js 首次抽取完全一致）：
  1. 按标记行定位 core 段（/*PARSER_START*/ .. /*PARSER_END*/，含标记行）；
  2. 应用两处抽取版增强：
     a. `function parseMarkdown(src){` → `function parseMarkdown(src, opts){`
     b. IPX 行加 `(opts&&opts.indents)||` 兜底；
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
 * 相对原文件的两处增强（仅本抽取版，原文件未动）：
 *   1. 外包 UMD：浏览器全局(MDParser) / CommonJS(require) / ESM(import) 通用；
 *   2. parseMarkdown(src, opts) 增加可选第二参 opts.indents = {p, quote, li}
 *      （容器级缩进档，px）——不传时与原文 100% 一致（默认 {p:0,quote:0,li:0}）。
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

    # 两处抽取版增强（锚点计数断言）
    anchors = [
        ("function parseMarkdown(src){", "function parseMarkdown(src, opts){"),
        ("var IPX=(typeof window!=='undefined'&&window.__IND_PX__)||{p:0,quote:0,li:0};",
         "var IPX=(opts&&opts.indents)||(typeof window!=='undefined'&&window.__IND_PX__)||{p:0,quote:0,li:0};"),
    ]
    for old, new in anchors:
        if core.count(old) != 1:
            raise SystemExit("FAIL 增强锚点出现 %d 次（应为 1）: %r" % (core.count(old), old[:50]))
        core = core.replace(old, new)

    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(HEADER + core + FOOTER)
    print("EXTRACT OK: %s (%d bytes)" % (OUT, len(HEADER + core + FOOTER)))


if __name__ == "__main__":
    main()
