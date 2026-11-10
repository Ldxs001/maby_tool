# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""版本落点与 CHANGELOG 体例守门。

版本号的唯一事实源是 CHANGELOG.md 首个 `## vX.Y.Z` 标题；其余落点全是派生
（安装器 detect_version、服务端 /api/version 的 app 字段）。本测试把每个派生
落点与源逐字对齐，并对最新版本段做结构与三类禁用词断言——出现即 FAIL。
MD_SERVER_VERSION 独立演进，只打印不参与对齐。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = ["md_server.py"]

fails = []


def ck(name, cond, detail=""):
    print("%-28s %s %s" % (name, "PASS" if cond else "FAIL",
                           detail if (detail and not cond) else ""))
    if not cond:
        fails.append(name)


t = io.open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8").read()
m = re.search(r"^## v(\d+\.\d+\.\d+)", t, re.M)
ck("V1 CHANGELOG 头部版本", m is not None)
if not m:
    print("FAIL 1 / PASS 0")
    sys.exit(1)
ver = m.group(1)

# 最新版本段：本次改动句、固定分组顺序、段分隔符、标题日期
nxt = re.search(r"^## v\d+\.\d+\.\d+", t[m.end():], re.M)
sec = t[m.start():m.end() + nxt.start()] if nxt else t[m.start():]
ck("V2 版本段标题带日期", bool(re.match(r"^## v\d+\.\d+\.\d+（\d{4}-\d{2}-\d{2}）", sec)))
ck("V3 本次改动句在场", bool(re.search(r"^\*\*本次改动：.+?\*\*$", sec, re.M)))
FIXED = ["新增", "修复", "变更", "测试", "说明"]
groups = [g for g in FIXED if "**" + g + "**" in sec]
ck("V4 分组顺序合规", groups == [g for g in FIXED if g in groups],
   "顺序=%s" % groups)
ck("V5 段间分隔符", sec.rstrip().endswith("---"))

# 三类禁用词：人称叙事 / 产品立场论证 / 口语化措辞 + 含糊量词与自评词
BANNED = [
    "主人", "我推荐", "我认为", "我判断", "我踩", "我说",
    "用户说", "用户反馈", "用户纠正", "用户定稿", "用户提出", "用户要求",
    "是要分发出去的", "这个智能体是", "大多数用户唯一", "用户机器上",
    "坑", "顺带", "顺手", "压根", "白跑", "白烧", "白占", "白写", "白干",
    "死档", "这轮", "卧槽", "完美解决", "优雅地", "一些", "大量",
]
hits = [w for w in BANNED if w in sec]
ck("V6 三类禁用词零命中", not hits, "命中=%s" % hits)

# 落点 1：服务端 /api/version 的 app 字段
import md_server  # noqa: E402
ck("V7 _app_version 同源", md_server._app_version() == ver,
   "app=%s changelog=%s" % (md_server._app_version(), ver))
src = io.open(os.path.join(HERE, "md_server.py"), encoding="utf-8").read()
ck("V8 /api/version 两端点带 app", src.count('"app": _app_version()') == 2,
   "count=%d" % src.count('"app": _app_version()'))
ck("V9 MD_SERVER_VERSION 独立", isinstance(md_server.MD_SERVER_VERSION, int),
   "value=%s" % md_server.MD_SERVER_VERSION)

# 落点 2：exe 安装包与 MSIX 共用的 detect_version
sys.path.insert(0, os.path.join(HERE, "installer"))
try:
    import _build_installer  # noqa: E402
    ck("V10 安装包版本同源", _build_installer.detect_version() == ver,
       "detect=%s" % _build_installer.detect_version())
except Exception as e:
    ck("V10 安装包版本同源", False, repr(e))

# 落点 3：MSIX 版本由同一函数派生（静态确认复用，不另存一份）
try:
    msix = io.open(os.path.join(HERE, "installer", "_build_msix.py"),
                   encoding="utf-8").read()
    ck("V11 MSIX 复用 detect_version",
       "_build_installer.detect_version()" in msix and '"%s.0" % ver' in msix)
except OSError as e:
    ck("V11 MSIX 复用 detect_version", False, repr(e))

print("\nPASS %d / FAIL %d" % (11 - len(fails), len(fails)))
sys.exit(1 if fails else 0)
