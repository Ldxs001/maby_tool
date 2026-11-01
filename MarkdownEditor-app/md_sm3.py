# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""md_sm3.py -- 全项目统一的 SM3 国密哈希（GB/T 32905-2016，v2.26.3）

为什么是 SM3 而不是 sha256/md5：

  知识库与写作两个智能体用的就是 SM3（`hashlib.new('sm3', data)`），本项目
  跟随同一套算法，同一份内容在任何项目里算出的指纹可以直接互相比对。国密
  标准，且由 OpenSSL 提供，零依赖、零代码。

为什么不自己写纯 Python 实现：

  Python 的 hashlib 在 OpenSSL 1.1.1+ 上带 SM3，本项目分发的 Python 3.11.9
  （OpenSSL 3.0.13）与开发机上的 3.14.3（OpenSSL 3.0.18）都实测支持。多写
  一份纯 Python 实现就多一个"两套算法各算各的"的来源，宁可没有，不要两套。

为什么要先归一化再算：

  落盘会按目标文件转换换行（md_server._save_text 里的 _target_eol）。同一份
  内容在 Windows 上是 CRLF、在 Linux 上是 LF；不折成 LF，把文件发给别人指纹
  就变了——那是平台差异，不是内容变化，溯源直接失效。BOM 同理，它不是内容。
  除此之外**不做任何清洗**：多一个空格就是内容变了，溯源要忠实。
"""
import hashlib

ALGO = "sm3"
HEX_LEN = 64


def available():
    """当前解释器的 OpenSSL 是否提供 SM3。"""
    try:
        hashlib.new(ALGO, b"")
        return True
    except Exception:
        return False


def hexdigest(data):
    """bytes 或 str → 64 位小写十六进制。str 按 UTF-8 编码。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.new(ALGO, data).hexdigest()


def file_digest(raw):
    """正文指纹：剥 UTF-8 BOM → 换行一律折成 LF → SM3。

    raw 必须是 bytes（落盘的原始字节），不要先 decode：先 decode 再 encode
    会让"解码替换"（errors=replace）的字符偷偷进哈希，那是编辑器的问题，
    不该被记成"内容变了"。
    """
    if not isinstance(raw, bytes):
        raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    if b"\r" in raw:
        raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hexdigest(raw)


def text_digest(text):
    """给已经读成 str 的正文用；口径与 file_digest 完全一致。"""
    if text is None:
        return ""
    if isinstance(text, bytes):
        return file_digest(text)
    return file_digest(str(text).encode("utf-8"))


def short(h, n=8):
    """截短用于显示。校验一律比全长，截短只给人看。"""
    return (h or "")[:n]
