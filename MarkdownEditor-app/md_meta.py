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
   不偷偷解位改写。反过来，锁位在路上会丢（安装包解压不还原属性、`.smd`
   包内条目是 0644、别人拷来的目录、早期版本的老档案），所以 `ensure` /
   `update` / `sync` 遇到「已存在」时会调 `relock()` 把锁补回来——**只改
   属性，内容一个字节不动**，不违反「绝不覆盖创建者快照」。

3. **当前值 = zero.fields 叠加 up 里的全部变更**。zero 存的是"创建时是什么"，
   up 存的是"后来改了什么"，两者合起来才是"现在是什么"。前端要渲染就直接
   用 read() 返回的 fields，不要自己去算——两边算两套必然分叉。

4. **作者是链，不是值**（v2.26.3）。zero.fields.author 是创建者，up 里每条
   `@who` 是那次保存的操作者，按时间序去重拼起来才是「作者」这一行。所以
   没有人会"覆盖"掉创建者——Ldxs 改完之后显示的是 `wUwproject，Ldxs`。
   who 的来源是本机排版设置里的「作者」框：谁的机器写着谁，不冒充。

5. **建档有两种来历**（v2.26.3），由调用方用 created 参数说明：
     created=None    本次会话新建（含另存为）→ 创建时间 = 现在，字段 = 面板值
     created="none"  接手别人已有的内容      → 创建时间 = none，字段只留
                     author=default，并立刻记一条「建档」行，写明是谁开始留痕。
   第二种的意义是"证明现在这位不是创建人"，而不是假装知道它是哪年建的。

纯 IO 模块，无全局状态，供 md_server.py 调用。
"""
import io
import json
import os
import re
import time

import md_sm3

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

DEFAULT_AUTHOR = "default"   # 作者为空时的占位：至少说明"有人，但没报名"
CREATED_UNKNOWN = "none"     # 接手别人的文件时，创建时间就写这个——不猜

# up.md 一行：- 2026-10-30 23:24 @Ldxs · title：`旧` → `新`
# @who 是 v2.26.3 加的，老档案的行没有它，解析成空名，不做迁移。
_UP_RE = re.compile(
    r"^-\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})\s*(?:@(\S+?))?\s*·\s*"
    r"([A-Za-z_][\w\-]*)\s*[：:]\s*(.*?)\s*→\s*(.*)$")
# 无字段行：- 2026-11-01 21:40 @Ldxs · 建档（只说明"此人此刻动过"，没有键值可比）
_UP_NOTE_RE = re.compile(
    r"^-\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})\s*(?:@(\S+?))?\s*·\s*(\S.*)$")
# 内容指纹：v2.26.3 起，保存行尾带 `sm3:<64位十六进制>`。
#   - 2026-11-01 23:10 @Ldxs · 保存 sm3:9f8e7d6c1a2b…
# 老档案的行没有它，解析成空串，**不做迁移**——没有指纹就是没有，不补编一个。
_UP_SM3_RE = re.compile(r"\bsm3:([0-9a-f]{%d})\b" % md_sm3.HEX_LEN)

# Windows 文件属性位（其它平台静默跳过：Linux/macOS 的点开头文件名本身就是隐藏）
_FA_READONLY = 0x1
_FA_HIDDEN = 0x2
_FA_NORMAL = 0x80


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
        # FILE_ATTRIBUTE_NORMAL(0x80) 只在「单独使用」时有效，与任何其它位
        # 组合都是非法值，SetFileAttributesW 会整体失败——那会让补锁静默不生效
        # （_test_zero_perm 的 B 组为同一原因留了注释）。先摘掉再按位加减。
        a = cur & ~_FA_NORMAL
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
    """up.md → [{at, who, key, from, to, note}]。

    两种行都认：带字段的（key 有值）与只记事件的无字段行（key 为 None）。
    不认识的行直接跳过（人手改坏了不影响读）。
    """
    out = []
    for ln in (text or "").split("\n"):
        s = ln.strip()
        if not s.startswith("-"):
            continue
        m = _UP_RE.match(s)
        if m:
            out.append({"at": m.group(1), "who": (m.group(2) or "").strip(),
                        "key": m.group(3),
                        "from": _unbacktick(m.group(4)), "to": _unbacktick(m.group(5)),
                        "note": "", "hash": ""})
            continue
        if "→" in s:
            continue        # 带箭头却合不上格式：宁可当坏行跳过，也不猜成无字段行
        m = _UP_NOTE_RE.match(s)
        if m:
            note = m.group(3).strip()
            h = ""
            mh = _UP_SM3_RE.search(note)
            if mh:
                h = mh.group(1)
                # 去掉指纹后剩下的才是人写的说明；只剩指纹（手写坏了）就当「保存」
                note = (note[:mh.start()] + note[mh.end():]).strip() or "保存"
            out.append({"at": m.group(1), "who": (m.group(2) or "").strip(),
                        "key": None, "from": "", "to": "",
                        "note": note, "hash": h})
    return out


def _fmt_up(entry):
    who = (entry.get("who") or "").strip()
    head = "- %s%s · " % (entry["at"], (" @" + who) if who else "")
    if entry.get("key"):
        return head + "%s：`%s` → `%s`" % (entry["key"], entry.get("from", ""),
                                           entry.get("to", ""))
    body = entry.get("note") or "修改"
    h = (entry.get("hash") or "").strip()
    if h:
        body += " sm3:" + h
    return head + body


def _build_authors(base_author, up):
    """创建者（永远第一）+ up 里出现过的操作者，按时间序去重。

    老档案的履历行没有 @who，但改 author 那条的 `to` 就是当时的作者名，
    拿它兜底——否则老文档的作者链永远只有创建者一个人。
    """
    out = [(base_author or "").strip() or DEFAULT_AUTHOR]
    for e in up:
        w = (e.get("who") or "").strip()
        if not w and e.get("key") == "author":
            w = (e.get("to") or "").strip()
        if w and w not in out:
            out.append(w)
    return out


def _last_hash(up):
    """up 里最后一条带指纹的 hash。

    不能直接取 up[-1]：字段变更行（`title：旧 → 新`）不带指纹，若它恰好是
    最后一条，取它就等于拿空值去比，stale 会永远算不出来。
    """
    for e in reversed(up or ()):
        h = (e.get("hash") or "").strip()
        if h:
            return h
    return ""


def read(assets_dir, content=None):
    """读档案 → {zero, up, fields, authors, created, last, hash, stale}。

    档案不存在返回 None。None 与"存在但字段全空"是两回事：前者根本没建档，
    后者建了档还没填。渲染侧一律按"没数据就不出区域"处理，但面板要区分。

    authors / created / last 三个派生值只在这里算：前端拿到就能直接画，
    不必把 zero+up 的合成规则再实现一遍（两处各算一套必然分叉）。

    content 传入正文原文时顺带算 stale（磁盘正文的指纹是否等于 up 末条）：
      False 一致    True 有未记录的改动    None 无从判断（老档案没有指纹、
      或没传 content）——三者不能合并，None 表示"不知道"，不该报成"正常"。
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
    created = zero.get("created")
    created = str(created).strip() if created is not None else ""
    h_last = _last_hash(up_list)
    stale = None
    if content is not None and h_last:
        try:
            stale = (md_sm3.text_digest(content) != h_last)
        except Exception:
            stale = None
    return {"zero": zero, "up": up_list, "fields": _apply_up(base, up_list),
            "authors": _build_authors(base.get("author", ""), up_list),
            "created": created or CREATED_UNKNOWN,
            "last": (up_list[-1]["at"] if up_list else ""),
            "hash": h_last, "stale": stale}


def relax(assets_dir):
    """清掉档案的只读/隐藏属性（只给「解包目录里的临时副本」和删除路径用）。

    原件应当保持只读；但删临时目录、覆盖解包副本之前必须先解位，否则
    Windows 直接 PermissionError —— 2026-10-31 那次 500 就是这么炸的。
    """
    md = meta_dir(assets_dir)
    _set_attrs(os.path.join(md, ZERO_NAME), hidden=False, readonly=False)
    _set_attrs(md, hidden=False)


def _attrs(path):
    """读 Windows 文件属性位；非 Windows 或读失败返回 None。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        a = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return None if a == 0xFFFFFFFF else a
    except Exception:
        return None


def relock(assets_dir):
    """把**已存在**的档案补上只读 + 隐藏（只改属性，不读不写内容）。

    为什么需要：只读位原本只在 `ensure` 建档那一刻设，而档案会跟着文档与
    安装包到处走，路上会丢：
      - .NET 的 `ZipArchiveEntry.ExtractToFile` 只写字节、**不还原属性**，
        所以安装包里的内置文档档案到用户机上是普通可写文件；
      - `.smd` 包内条目被 `_smd` 强制成 0644（解包后要能直接改，见 E1/E2 契约）；
      - 从别人那里拷来的目录、以及早期版本建的老档案，本来就没锁。
    `ensure` / `update` / `sync` 遇到「已存在」原本直接返回，于是这些档案
    永远补不上锁——「防手滑」这条在用户机上等于没做。这里补一次。

    三条红线：
      1. **只改属性**。不打开内容、不重写 zero，「绝不覆盖创建者快照」这条
         纪律不受影响；内容正确性由 `read()` 负责，与锁位无关。
      2. **只在 lock=True 时调用**。`.smd` 的解包副本建在临时目录，锁上会让
         rmtree 删不干净、下次解包撞只读同名文件 → HTTP 500（2026-10-31 事故）。
         `lock=False` 的分支走 `relax()`，方向相反，两者别混。
      3. **出错静默**。只读盘、网络盘、无权限都只是让这层保护落空，
         不能让一次保存因为设属性失败而报错（`_set_attrs` 内部已吞异常）。

    已经锁好的档案直接返回，不重复写属性：每次保存都写一遍会让同步盘与
    杀软多扫一遍，也没有任何意义。返回是否真的改过属性。
    """
    md = meta_dir(assets_dir)
    zp = os.path.join(md, ZERO_NAME)
    if not os.path.isfile(zp):
        return False
    a = _attrs(zp)
    if a is not None and (a & _FA_READONLY) and (a & _FA_HIDDEN):
        return False                      # 已经锁好，一个字节都不碰
    _set_attrs(md, hidden=True)
    _set_attrs(zp, hidden=True, readonly=True)
    return True


def ensure(assets_dir, fields=None, lock=True, created=None):
    """建档：zero.json + up.md。已存在则原样返回（**绝不覆盖创建者快照**）。

    lock=False 专供 `.smd` 的解包目录：那里的档案只是临时副本，原件在包内。
    副本一旦被设成只读+隐藏，临时目录就删不干净（rmtree 静默留残骸），
    下次解包撞上只读同名文件直接 PermissionError。只读只给磁盘上的真档案。

    created=None 用当前时刻；传字符串则原样写（`none` = 接手别人的文件，
    不知道也不编造创建时间）。author 空就给 DEFAULT_AUTHOR——档案里必须
    有人，哪怕这个人是 default。

    返回 (档案 dict, 是否本次新建)。
    """
    cur = read(assets_dir)
    if cur is not None:
        if not lock:
            relax(assets_dir)            # 老副本可能已被锁过，这里顺带解开
        else:
            relock(assets_dir)           # 已存在但可能没锁（安装包/拷贝/老档案）
        return cur, False
    md = meta_dir(assets_dir)
    os.makedirs(md, exist_ok=True)
    if lock:
        _set_attrs(md, hidden=True)      # 目录隐藏
    f = _clean(fields)
    if not (f.get("author") or "").strip():
        f["author"] = DEFAULT_AUTHOR
    zero = {
        "format": FORMAT,
        "created": (str(created).strip() if created else
                    time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())),
        "creator": {"by": "MDEditor"},
        "fields": f,
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


def _append(assets_dir, entries):
    up = os.path.join(meta_dir(assets_dir), UP_NAME)
    with io.open(up, "a", encoding="utf-8", newline="\n") as f:
        for c in entries:
            f.write(_fmt_up(c) + "\n")


def update(assets_dir, fields, lock=True, who=""):
    """改档案：逐字段 diff，变更追加进 up.md。**永不改 zero.json**。

    who 是本次操作者（本机排版设置里的作者），写进履历行的 `@who`。
    空字符串就省略 @，老行为不变。

    lock 透传给 ensure：`.smd` 的解包副本一律不锁（见 ensure 的说明）。

    返回 (档案 dict, 本次变更条数)。没变就一条都不写（幂等：重复保存不刷履历）。
    """
    cur = read(assets_dir)
    if cur is None:
        cur, _ = ensure(assets_dir, fields, lock)
        return cur, 0
    if lock:
        relock(assets_dir)               # 已存在：补锁（`.smd` 副本 lock=False 不补）
    old = cur.get("fields") or {}
    new = _clean(fields)
    at = _now()
    w = (who or "").strip()
    changes = []
    for k in FIELD_KEYS:
        if k not in new:
            continue
        a = old.get(k, "")
        b = new.get(k, "")
        if a != b:
            changes.append({"at": at, "who": w, "key": k, "from": a, "to": b})
    if not changes:
        return cur, 0
    _append(assets_dir, changes)
    return read(assets_dir), len(changes)


def sync(assets_dir, fields=None, who="", created=None, lock=True, baseline=None,
         touch=False, content=None):
    """保存时的统一入口：该建档就建档，该记履历就记履历（v2.26.3）。

    「应用」只改排版设置，「保存」才落到这篇文档——所有档案写操作都从这里走，
    前端不需要知道 ensure / update 的先后。

    created=None   本次会话新建（含另存为）：
                   zero.fields = baseline（缺省用 fields），创建时间 = 现在
    created="none" 接手别人已有内容的文件：
                   zero 只写 author=default、创建时间 none，并**立刻记一条
                   「建档」行**写明这次是谁开始留痕的——目的是证明现在这位
                   不是创建人，而不是假装知道它是哪年建的

    touch=True     这是一次真正的保存：**字段一个都没变也要留一条痕**
                   （`- 时间 @who · 保存`）。up 是忠实追加的流水账——每 save
                   一行，去重与取最新都是**渲染时**的事（read 的 authors 去重、
                   last 取末条）。以前写不写由 update 的逐字段 diff 决定，结果
                   「改了正文、元数据没动」的保存一个字都不留、修改时间也不动，
                   与「up 记录每一次 save」这条口径相违（2026-11-01 定）。
                   接手建档那次已有「建档」行，不再叠一条同秒的「保存」。

    content        正文原文（落盘后的）。给了就把 SM3 指纹写进履历行，并与上
                   一条指纹比：**一模一样就不追加**——内容没变说明这次保存
                   没产生任何变化，"最近修改"也就不该往前走。忠实追加的是
                   "每一次内容变化"，不是每一个 Ctrl+S（2026-11-01 定）。

    baseline 与 fields 分开是为了第二种来历：那时 fields 只应含「本次会话
    显式改过的字段」，绝不能把本机面板里的标题/标签灌进别人的文档（那是
    污染，不是留痕），所以建档底稿必须另行说明成空。

    返回 (档案 dict, 本次变更条数, 是否本次建档)。
    """
    h = ""
    if content is not None:
        try:
            h = md_sm3.text_digest(content)
        except Exception:
            h = ""      # OpenSSL 不带 SM3 或是极端编码问题：退化成不带指纹的老行为
    cur = read(assets_dir)
    born = False
    if cur is None:
        base = (baseline if baseline is not None else fields) if created is None else {}
        cur, born = ensure(assets_dir, base, lock=lock, created=created)
        if created is not None:
            _append(assets_dir, [{
                "at": _now(), "who": (who or "").strip() or DEFAULT_AUTHOR,
                "key": None, "note": "建档", "from": "", "to": "", "hash": h}])
            cur = read(assets_dir)
    elif lock:
        relock(assets_dir)               # 已存在：补锁（主路径，见 relock 说明）
    changed = 0
    if fields:
        cur, changed = update(assets_dir, fields, lock=lock, who=who)
    if touch and not changed and not (born and created is not None):
        prev = _last_hash(cur.get("up") if cur else None)
        if not (h and prev and h == prev):
            _append(assets_dir, [{
                "at": _now(), "who": (who or "").strip() or DEFAULT_AUTHOR,
                "key": None, "note": "保存", "from": "", "to": "", "hash": h}])
    return read(assets_dir, content), changed, born
