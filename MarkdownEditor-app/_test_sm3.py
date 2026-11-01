# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_test_sm3.py -- SM3 归一化与指纹口径验收（v2.26.3）

为什么单独立一个文件：指纹是地基。元数据溯源、资产去重、解包目录命名、
长图切片缓存全都挂在它上面。它一旦漂移，坏的不是某个功能，而是
「同一份内容在不同地方算出不同值」——这种错最难查，因为每个功能单独看
都"正常"，只有把两边结果摆在一起才看得见。

三组：
  A. 标准向量（T01-T03）—— 国标 GB/T 32905-2016 附录的权威值。
     这三个对不上就是实现错了，后面全部不用谈。
  B. 归一化口径（T04-T09）—— 换行折、BOM 剥，**空白不折**。
     折换行是因为落盘会按平台转换（md_server._save_text）；不折空白是
     因为溯源要忠实，"看起来一样"不等于"一样"。
  C. 接口形态（T10-T14）—— 长度、大小写、str/bytes、None、截短。

用法：python _test_sm3.py
"""
import sys

import md_sm3

COUNT = [0]
FAILED = []


def ck(name, ok, detail=""):
    COUNT[0] += 1
    if ok:
        print("PASS  " + name)
    else:
        print("FAIL  " + name + "  [" + str(detail) + "]")
        FAILED.append(name)


# ── A. 标准向量 ──────────────────────────────────────────
# 这三个值来自国标附录与公开测试向量，不是我们自己算出来的。
ck("T01 向量 SM3('abc')",
   md_sm3.text_digest("abc") ==
   "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0",
   md_sm3.text_digest("abc"))

ck("T02 向量 SM3('abcd'*16)",
   md_sm3.text_digest("abcd" * 16) ==
   "debe9ff92275b8a138604889c18e5a4d6fdb70e5387e5765293dcba39c0c5732",
   md_sm3.text_digest("abcd" * 16))

ck("T03 向量 SM3('') 空串",
   md_sm3.text_digest("") ==
   "1ab21d8355cfa17f8e61194831e81a8f22bec8c728fefb747ed035eb5082aa2b",
   md_sm3.text_digest(""))

# ── B. 归一化口径 ─────────────────────────────────────────
ck("T04 CRLF 折成 LF：同一内容两份换行得同一指纹",
   md_sm3.file_digest(b"a\r\nb") == md_sm3.file_digest(b"a\nb"),
   md_sm3.file_digest(b"a\r\nb"))

ck("T05 单独 CR 也折（老 Mac 换行）",
   md_sm3.file_digest(b"a\rb") == md_sm3.file_digest(b"a\nb"),
   md_sm3.file_digest(b"a\rb"))

ck("T06 剥 UTF-8 BOM：带 BOM 与不带 BOM 同指纹",
   md_sm3.file_digest(b"\xef\xbb\xbfabc") == md_sm3.file_digest(b"abc"),
   md_sm3.file_digest(b"\xef\xbb\xbfabc"))

ck("T07 尾部空格**不**折：多一个空格就是内容变了",
   md_sm3.text_digest("a ") != md_sm3.text_digest("a"),
   md_sm3.text_digest("a "))

ck("T08 内部连续空格**不**折叠",
   md_sm3.text_digest("a  b") != md_sm3.text_digest("a b"),
   md_sm3.text_digest("a  b"))

ck("T09 只是换行差异不算改动（真实场景：别人机器上存过一次）",
   md_sm3.text_digest("# 标题\r\n\r\n正文\r\n") ==
   md_sm3.text_digest("# 标题\n\n正文\n"),
   md_sm3.text_digest("# 标题\r\n\r\n正文\r\n"))

# ── C. 接口形态 ──────────────────────────────────────────
_h = md_sm3.text_digest("abc")
ck("T10 输出 64 位小写十六进制",
   len(_h) == 64 and _h == _h.lower() and
   all(c in "0123456789abcdef" for c in _h), _h)

ck("T11 str 与 bytes 入口结果一致",
   md_sm3.hexdigest("中文") == md_sm3.hexdigest("中文".encode("utf-8")),
   md_sm3.hexdigest("中文"))

ck("T12 text_digest(None) 返回空串（调用方据此退化成无指纹）",
   md_sm3.text_digest(None) == "", repr(md_sm3.text_digest(None)))

ck("T13 short() 默认前 8 位且不改变原值",
   md_sm3.short(_h) == _h[:8] and md_sm3.short(_h, 12) == _h[:12] and
   len(md_sm3.short(None)) == 0, md_sm3.short(_h))

ck("T14 当前解释器的 OpenSSL 提供 SM3",
   md_sm3.available() is True, md_sm3.available())

print("-" * 60)
print("合计 %d 条：PASS %d / FAIL %d"
      % (COUNT[0], COUNT[0] - len(FAILED), len(FAILED)))
sys.exit(1 if FAILED else 0)
