# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""md_meta.py -- 元数据档案读写（v2.23.0）

档案位置：资产目录下的 .mde/ 子目录，随文档一起迁移。

    <stem>.assets/.mde/zero.json   创建者快照 · Hidden + ReadOnly · 建档写一次后永不改
    <stem>.assets/.mde/up.md       修改履历   · 不设属性 · 追加式
    .smd 包内：assets/.mde/zero.json、assets/.mde/up.md

三条设计纪律：

1. **值不进正文**。自有模式（@@ meta）的唯一真源就是这两个文件；正文里只有
   一行 @@ meta 当位置锚点。所以读写都以后端为准，前端不缓存可写副本。

2. **"只读"保护的是手滑与外部工具，不是安全边界**。程序只在建档那一刻写
   zero.json，之后任何保存路径都不碰它，因此只读位不影响日常存盘。唯一需要
   解位的场景是 up 在而 zero 丢失时的重建——那种情况由人手动处理，本模块
   不偷偷解位改写。

3. **当前值 = zero.fields 叠加 up 里的全部变更**。zero 存的是"创建时是什么"，
   up 存的是"后来改了什么"，两者合起来才是"现在是什么"。前端要渲染就直接
   用 read() 返回的 fields，不要自己去算——两边算两套必然分叉。

纯 IO 模块，无全局状态，供 md_server.py 调用。
"""
import io
import json
import os
import re
import time

META_DIR = ".mde"
ZERO_NAME = "zero.json"
UP_NAME = "up.md"
FORMAT = 1

# 字段白名单：(键, 中文标签)。键同时是 front matter 的键名，两边必须一致，
# 否则面板里填的标题在兼容模式下找不到落点。
FIELDS = (("title", "标题"), ("author", "作者"), ("date", "日期"),
          ("tags", "标签"), ("note", "备注"))
FIELD_KEYS = tuple(k for k, _ in FIELDS)

MAX_VAL = 500          # 单字段上限，防止把整篇文章塞进元数据

# up.md 一行：- 2026-10-30 23:24 · title：`` → `我写故我播`
_UP_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})\s*·\s*([A-Za-z_][\w\-]*)\s*[：:]\s*(.*?)\s*→\s*(.*)$")

# Windows 文件属性位（其它平台静默跳过：Linux/macOS 的点开头文件名本身就是隐藏）
_FA_READONLY = 0x1
_FA_HIDDEN = 0x2


def assets_dir_for(doc_path):
    """文档对应的资产目录。

    .md  → <同目录>/<stem>.assets
    .smd → 由调用方传入已解包的 base（见 assets_dir_in），本函数不处理
    """
    d = os.path.dirname(os.path.abspath(doc_path))
    stem = os.path.splitext(os.path.basename(doc_path))[0]
    return os.path.join(d, stem + ".assets")


def assets_dir_in(base_dir):
    """.smd 解包目录 → 资产目录（包内契约恒为 assets/）。"""
    return os.path.join(base_dir, "assets")


def meta_dir(assets_dir):
    return os.path.join(assets_dir, META_DIR)


def _set_attrs(path, hidden=None, readonly=None):
    """设置/清除 Windows 文件属性。失败静默——属性只是防手滑，不是功能前提。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        cur = k32.GetFileAttributesW(str(path))
        if cur == 0xFFFFFFFF:
            return
        a = cur
        if hidden is not None:
            a = (a | _FA_HIDDEN) if hidden else (a & ~_FA_HIDDEN)
        if readonly is not None:
            a = (a | _FA_READONLY) if readonly else (a & ~_FA_READONLY)
        k32.SetFileAttributesW(str(path), a)
    except Exception:
        pass


def _clear_readonly(path):
    """写之前先清只读位（Windows 上只读文件 open('w') 会 PermissionError）。"""
    _set_attrs(path, readonly=False)


def _now():
    return time.strftime("%Y-%m-%d %H:%M", time.localtime())


def _clean(fields):
    """只留白名单键，值转字符串、去换行、截断。非 dict 一律当空。"""
    out = {}
    if not isinstance(fields, dict):
        return out
    for k in FIELD_KEYS:
        if k not in fields:
            continue
        v = fields.get(k)
        if v is None:
            v = ""
        v = str(v).replace("\r", " ").replace("\n", " ").strip()
        out[k] = v[:MAX_VAL]
    return out


def _apply_up(base, up):
    """zero.fields 叠加 up 里的变更 → 当前值。"""
    cur = dict(base or {})
    for e in up:
        k = e.get("key")
        if k in FIELD_KEYS:
            cur[k] = e.get("to", "")
    return cur


def _unbacktick(s):
    """剥掉履历行里给人看的反引号包裹（`旧` → `新`）。只剥一轮成对的，
    值本身含反引号时原样保留。"""
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == "`" and s[-1] == "`":
        s = s[1:-1]
    return s


def parse_up(text):
    """up.md → [{at, key, from, to}]。不认识的行直接跳过（人手改坏了不影响读）。"""
    out = []
    for ln in (text or "").split("\n"):
        m = _UP_RE.match(ln.strip())
        if not m:
            continue
        out.append({"at": m.group(1), "key": m.group(2),
                    "from": _unbacktick(m.group(3)), "to": _unbacktick(m.group(4))})
    return out


def _fmt_up(entry):
    return "- %s · %s：`%s` → `%s`" % (entry["at"], entry["key"],
                                       entry.get("from", ""), entry.get("to", ""))


def read(assets_dir):
    """读档案 → {zero, up, fields} 。档案不存在返回 None（不是空对象）。

    None 与"存在但字段全空"是两回事：前者根本没建档，后者建了档还没填。
    渲染侧一律按"没数据就不出区域"处理，但面板要区分（前者显示未建档）。
    """
    md = meta_dir(assets_dir)
    zp = os.path.join(md, ZERO_NAME)
    up = os.path.join(md, UP_NAME)
    if not os.path.isfile(zp):
        return None
    zero = None
    try:
        with io.open(zp, "r", encoding="utf-8") as f:
            zero = json.load(f)
    except Exception:
        zero = None
    if not isinstance(zero, dict):
        # zero 坏了就当没建档——不能拿半截数据冒充创建者快照
        return None
    up_list = []
    if os.path.isfile(up):
        try:
            with io.open(up, "r", encoding="utf-8") as f:
                up_list = parse_up(f.read())
        except Exception:
            up_list = []
    base = _clean(zero.get("fields"))
    return {"zero": zero, "up": up_list, "fields": _apply_up(base, up_list)}


def relax(assets_dir):
    """清掉档案的只读/隐藏属性（只给「解包目录里的临时副本」和删除路径用）。

    原件应当保持只读；但删临时目录、覆盖解包副本之前必须先解位，否则
    Windows 直接 PermissionError —— 2026-10-31 那次 500 就是这么炸的。
    """
    md = meta_dir(assets_dir)
    _set_attrs(os.path.join(md, ZERO_NAME), hidden=False, readonly=False)
    _set_attrs(md, hidden=False)


def ensure(assets_dir, fields=None, lock=True):
    """建档：zero.json + up.md。已存在则原样返回（**绝不覆盖创建者快照**）。

    lock=False 专供 `.smd` 的解包目录：那里的档案只是临时副本，原件在包内。
    副本一旦被设成只读+隐藏，临时目录就删不干净（rmtree 静默留残骸），
    下次解包撞上只读同名文件直接 PermissionError。只读只给磁盘上的真档案。

    返回 (档案 dict, 是否本次新建)。
    """
    cur = read(assets_dir)
    if cur is not None:
        if not lock:
            relax(assets_dir)            # 老副本可能已被锁过，这里顺带解开
        return cur, False
    md = meta_dir(assets_dir)
    os.makedirs(md, exist_ok=True)
    if lock:
        _set_attrs(md, hidden=True)      # 目录隐藏
    zero = {
        "format": FORMAT,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "creator": {"by": "MDEditor"},
        "fields": _clean(fields),
    }
    zp = os.path.join(md, ZERO_NAME)
    _clear_readonly(zp)
    with io.open(zp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(zero, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if lock:
        _set_attrs(zp, hidden=True, readonly=True)   # 建完即锁：隐藏 + 只读
    up = os.path.join(md, UP_NAME)
    if not os.path.isfile(up):
        with io.open(up, "w", encoding="utf-8", newline="\n") as f:
            f.write("# 元数据修改记录\n\n")
    return read(assets_dir) or {"zero": zero, "up": [], "fields": _clean(fields)}, True


def update(assets_dir, fields, lock=True):
    """改档案：逐字段 diff，变更追加进 up.md。**永不改 zero.json**。

    lock 透传给 ensure：`.smd` 的解包副本一律不锁（见 ensure 的说明）。

    返回 (档案 dict, 本次变更条数)。没变就一条都不写（幂等：重复点应用不刷履历）。
    """
    cur = read(assets_dir)
    if cur is None:
        cur, _ = ensure(assets_dir, fields, lock)
        return cur, 0
    old = cur.get("fields") or {}
    new = _clean(fields)
    changes = []
    for k in FIELD_KEYS:
        if k not in new:
            continue
        a = old.get(k, "")
        b = new.get(k, "")
        if a != b:
            changes.append({"at": _now(), "key": k, "from": a, "to": b})
    if not changes:
        return cur, 0
    up = os.path.join(meta_dir(assets_dir), UP_NAME)
    with io.open(up, "a", encoding="utf-8", newline="\n") as f:
        for c in changes:
            f.write(_fmt_up(c) + "\n")
    return read(assets_dir), len(changes)
