# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_smd.py -- .smd 自包含文档格式（v1.2.0）

.smd = ZIP 容器，内部结构：
    doc.md       正文（UTF-8）
    assets/...   图片资源（对应普通文档的 <stem>.assets/）
    assets/.mde/ 元数据档案：zero.json（创建者快照）、up.md（修改履历）
    meta.json    {"format": 1}

设计要点：
  - 读取以"最后一次出现的同名 entry"为准（zipfile.NameToInfo 后者覆盖前者），
    因此保存走 ZIP 追加模式：只追加变化的 entry，不重写整包。
  - 断电安全：entry 数据先写、central directory 由 zipfile 在 close() 时最后写，
    中途崩溃只丢本次保存，旧包完整可读。
  - 垃圾积累用阈值整理（compact）：死空间 >30% 且文件 >5MB 时全量重建，原子替换。
  - 安全：解包前校验全部 entry 名，拒绝绝对路径/盘符/.. 穿越。
  - 保存时参与比对的 entry 只有两类：doc.md（恒追加）与 assets/*（按
    (字节数, CRC32) 判变化，`.mde/*` 同属这一类，一并按内容 diff）。
    meta.json 是常量，按设计不比；**将来新增第三类 entry 必须同时进比对逻辑**，
    否则会跟 meta.json 一样被静默冻住——文件在包里，值停在打包那天，且不报错。
  - 不被正文引用的资产有两类豁免（见 is_protected）：annotations.json 与
    `.mde/*`。二者都靠"正文里搜 assets/<名字>"这个判据永远搜不到，不豁免就
    会在保存时被当孤儿删掉。
"""
import os
import io
import json
import time
import hashlib
import zipfile
import shutil
import warnings
import zlib
import itertools
import threading
import urllib.parse

FORMAT_VERSION = 1
DOC_NAME = "doc.md"
ASSETS_DIR = "assets"
META_NAME = "meta.json"
META_DIR = ".mde"          # 元数据档案目录（assets/.mde/zero.json、up.md）


def is_protected(rel):
    """资产目录里不参与"孤儿回收"的条目判定。

    · annotations.json：编辑器批注，doc.md 不引用它，但必须随包走。
    · .mde/*：元数据档案（zero.json 创建者快照、up.md 修改履历），正文同样
      不引用它。**这一类必须在这里豁免**——保存时的孤儿清理会 os.remove 掉它、
      整包重建会跳过它，档案就这么没了，而且一句错都不报。
    """
    r = str(rel).replace("\\", "/")
    return r == "annotations.json" or r.split("/")[0] == META_DIR

# 包内资产引用（格式契约：包内引用恒为 assets/<文件名>，打包/另存为时已改写）
#
# 判定只有这一个入口：按真实文件名去正文里找 "assets/<文件名>"。
# 不再用正则从正文里"猜"文件名——文件名允许空格（Windows 截图默认名即带空格：
# 「屏幕截图 2026-10-30 205849.png」），任何以空白/标点为终止符的猜测都会截断，
# 把正在使用的图判成孤儿并删掉。宁可多留（多留只是占空间），绝不多删。

def _ref_texts(doc_text):
    """正文的等价形态集合：原样 + URL 解码后。

    链接目标里的空格与中文可能被写成 %20 / %E5%9B%BE，纯子串匹配会认不出，
    正在使用的图就被判成孤儿删掉。解码只参与「是否被引用」这一个判断，
    绝不回写正文（回写会改动用户内容）。
    """
    raw = doc_text or ""
    try:
        dec = urllib.parse.unquote(raw)
    except Exception:
        dec = raw
    return (raw,) if dec == raw else (raw, dec)


def is_asset_referenced(doc_text, filename, texts=None):
    """filename 是否被正文引用 —— 精确判定。

    判据：正文里存在 "assets/<filename>" 这个完整子串。含空格、含标点、含中文
    都不影响。方向刻意选「宁可多留」：子串误命中时只是多留一个没用的文件，
    而误判成孤儿会把图从工作目录和包里一起删掉，不可逆。

    texts：调用方批量判定时传入 _ref_texts(doc_text) 的结果，省掉重复解码。
    """
    ref = ASSETS_DIR + "/" + str(filename).replace("\\", "/")
    for t in (texts if texts is not None else _ref_texts(doc_text)):
        if ref in t:
            return True
    return False

# 阈值整理触发条件：死空间占比与文件大小双门槛
COMPACT_DEAD_RATIO = 0.3
COMPACT_MIN_BYTES = 5 * 1024 * 1024
# 小包另走副本数闸门：doc.md 每次保存都追加一份，纯文本包远不到 5MB 就能积
# 十几份历史副本。12 份 ≈ 每 11 次成功保存重建一次，重建小包是毫秒级。
COMPACT_MAX_DOC_COPIES = 12

# 同一 .smd 的保存必须串行。服务端是多线程的（Reentrant），Ctrl+S 与自动落盘
# 可以同时到达；两个线程同时进 save_from_dir 会各拷一份包、各自追加、各自
# os.replace，最后落盘的是「最后完成的那个」而不是「最新的那个」——旧快照覆盖
# 新快照。更糟的是正文写入不是原子操作，另一个线程能读到截断到一半的 doc.md
# 并把它打进包，正文就真丢了（包本身是好的，所以没有任何报错）。
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_DOC_SEQ = itertools.count()


def locked(smd_path):
    """按包路径取互斥锁（可重入）。同一路径的不同写法归一化到同一把锁。"""
    key = os.path.normcase(os.path.abspath(str(smd_path)))
    with _LOCKS_GUARD:
        lk = _LOCKS.get(key)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[key] = lk
        return lk


def _replace_retry(src, dst, tries=6):
    """os.replace 重试：Windows 上目标被杀毒/索引/并发替换瞬时占用时报
    WinError 5。退避重试，全部失败再抛原始异常（不吞错）。"""
    last = None
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except OSError as e:
            last = e
            time.sleep(0.02 * (i + 1))
    raise last


def write_doc(base_dir, text):
    """把正文原子写进工作目录（tmp → fsync → replace）。

    非原子写（open(...,"w") 先截成 0 字节再写）会让并发读者读到半截正文；
    这里改成写临时文件再替换，任何时刻读到的都是完整的一版。
    """
    doc = os.path.join(base_dir, DOC_NAME)
    tmp = "%s.tmp%d" % (doc, next(_DOC_SEQ))
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    _replace_retry(tmp, doc)


def is_smd(path):
    return str(path).lower().endswith(".smd")


def _safe_entry(name):
    """entry 名安全校验：拒绝绝对路径、盘符、.. 穿越。合法原样返回。"""
    n = str(name).replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        raise ValueError("unsafe zip entry (absolute): %r" % name)
    if any(part == ".." for part in n.split("/")):
        raise ValueError("unsafe zip entry (traversal): %r" % name)
    return n


def _check_all_entries(smd_path):
    with zipfile.ZipFile(smd_path, "r") as z:
        for info in z.infolist():
            _safe_entry(info.filename)


def _sig(smd_path):
    """文件指纹（mtime+size），用于解包目录失效判断。"""
    st = os.stat(smd_path)
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size}


def _dir_writable(d):
    """写探针：目录可创建且可写入（与 md_server 的 _dir_writable 同哲学，不猜 ACL）。"""
    try:
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, ".smd_wtest")
        with io.open(p, "w") as f:
            f.write("1")
        os.remove(p)
        return True
    except Exception:
        return False


def _tmp_root():
    # 探针缓存：同一进程只判一次
    global _TMP_RESOLVED
    if _TMP_RESOLVED:
        return _TMP_RESOLVED
    legacy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "runtime", "tmp")
    if _dir_writable(legacy):
        _TMP_RESOLVED = legacy
        return _TMP_RESOLVED
    # 安装位只读（MSIX 商城包的 WindowsApps / Program Files）：解包工作目录
    # 回退用户可写区，与 md_server 的 RUNTIME_DIR 回退同一落点
    la = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")
    _TMP_RESOLVED = os.path.join(la, "MDEditor", "runtime", "tmp")
    return _TMP_RESOLVED


_TMP_RESOLVED = None


def _base_dir_for(smd_path):
    """返回该 .smd 的解包工作目录；未解包或包已变化（外部修改）则重新解包。

    目录名 = md5(绝对路径小写)，跨会话稳定；目录内 .source.json 记录
    打开时的包指纹，保存/贴图后同步更新，外部改动会触发重解包。
    """
    abspath = os.path.abspath(smd_path)
    d = os.path.join(_tmp_root(), hashlib.md5(abspath.lower().encode("utf-8")).hexdigest()[:16])
    doc = os.path.join(d, DOC_NAME)
    sig_file = os.path.join(d, ".source.json")
    if os.path.isfile(doc) and os.path.isfile(sig_file):
        try:
            with io.open(sig_file, "r", encoding="utf-8") as f:
                rec = json.load(f)
            cur = _sig(smd_path)
            if rec.get("mtime_ns") == cur["mtime_ns"] and rec.get("size") == cur["size"]:
                return d                      # 命中：目录有效且包未变化
        except Exception:
            pass
        # 包被外部修改：丢弃旧目录重解
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    _check_all_entries(smd_path)
    with zipfile.ZipFile(smd_path, "r") as z:
        z.extractall(d)
    if not os.path.isfile(doc):
        shutil.rmtree(d, ignore_errors=True)
        raise ValueError("not a valid .smd (missing %s): %s" % (DOC_NAME, smd_path))
    _write_sig(smd_path, sig_file)
    return d


def _write_sig(smd_path, sig_file):
    try:
        with io.open(sig_file, "w", encoding="utf-8") as f:
            json.dump(_sig(smd_path), f)
    except Exception:
        pass


def _pack_from_dir(smd_path, doc_src, assets_src=None):
    """全量打包（新建/另存为/整理用）。临时文件 + os.replace 原子替换。

    打包过滤：assets_src 中未被 doc.md 引用的文件不入包（保存清理纪律——
    包内资产与引用严格对齐；历史旧包的孤儿资产借此在全量重建时移除）。
    """
    tmp = "%s.tmp%d" % (smd_path, int(time.time() * 1000))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        # newline=""：按原始字节读，不做 CRLF→LF 翻译（否则“整理”会顺手改正文）
        with io.open(doc_src, "r", encoding="utf-8", newline="") as f:
            doc_text = f.read()
        texts = _ref_texts(doc_text)
        z.writestr(DOC_NAME, doc_text)
        for rel, fp in _scan_assets(assets_src):
            if not is_protected(rel) and not is_asset_referenced(doc_text, rel, texts):
                continue
            z.write(fp, ASSETS_DIR + "/" + rel)
        z.writestr(META_NAME, json.dumps({"format": FORMAT_VERSION}, ensure_ascii=False))
    _replace_retry(tmp, smd_path)


def _scan_assets(assets_src):
    """遍历资产目录 → [(包内相对名, 磁盘路径)]，按包内名排序。

    子目录必须一并遍历：引用形如 "assets/<相对路径>"，只扫顶层会让
    assets/sub/x.png 在打包/整理时被静默丢掉——包内没有这个文件，正文却
    还引用它，重开后破图，而保存过程一句错都不报。
    """
    out = []
    if not assets_src or not os.path.isdir(assets_src):
        return out
    for dp, dns, fns in os.walk(assets_src):
        dns.sort()
        fns.sort()
        for fn in fns:
            fp = os.path.join(dp, fn)
            if not os.path.isfile(fp):
                continue
            out.append((os.path.relpath(fp, assets_src).replace("\\", "/"), fp))
    out.sort()
    return out


def _file_sig(fp):
    """工作目录文件的指纹：(字节数, CRC32)。

    CRC 取自内容而非元数据，同尺寸不同内容也能分辨。代价是读一遍文件，与保存
    时整包 copyfile 同量级；换来的是「改了没进包」这种静默回滚不再发生——
    那种错当场看不出来（预览读的是工作目录），重启才发作。
    """
    crc = 0
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            crc = zlib.crc32(chunk, crc)
    return (os.path.getsize(fp), crc & 0xFFFFFFFF)


def _live_entries(smd_path):
    """名字 -> 该名下最后 entry 的 (字节数, CRC32, 压缩后字节数)。

    CRC 直接读 entry 头里已有的值，不需要额外存清单；追加式结构保证同名 entry
    后写覆盖先写，zipfile 的 NameToInfo 亦以后者为准。
    压缩后字节数是给死空间统计用的：包文件大小是压缩后的量，两边必须同单位。
    """
    with zipfile.ZipFile(smd_path, "r") as z:
        live = {}
        for info in z.infolist():
            live[info.filename] = (info.file_size, info.CRC & 0xFFFFFFFF,
                                   info.compress_size)
        return live


def _live_sigs(smd_path):
    """名字 -> (字节数, CRC32)（保存 diff 用，不含压缩尺寸）。"""
    return {k: (v[0], v[1]) for k, v in _live_entries(smd_path).items()}


def needs_compact(smd_path, base_dir):
    """死空间 >30% 且文件 >5MB 时需要整理。

    死空间 = 包文件大小 − 仍然有效的那批 entry 的**压缩后**字节数。
    有效以解包目录现状为准（同名同 CRC）；凡是对不上的（被替换的旧图、
    doc.md 的历史副本、已删除资源）都算死空间。

    单位必须统一：包大小是压缩后的量。旧实现减的却是未压缩大小，又按未压缩
    大小把「内容已变」的 entry 补回死空间——三个不同单位的量混在一个式子
    里，结果既可能虚高也可能为负。实测后果是双向的：内容改一次就误判成
    大面积死空间、每次保存全量重建；内容没改时重复副本又永远不被回收。
    异常时返回 False（保守不整理）。
    """
    try:
        total = os.path.getsize(smd_path)
        live = _live_entries(smd_path)
        if total < COMPACT_MIN_BYTES:
            # 小包（纯文本文档）的死空间占比永远到不了 30%，5MB 闸门等于永
            # 不整理——可 doc.md 每次保存都追加一份，实测 20 次保存积了 21 份
            # 副本、包从 403 字节涨到 3693。小包重建成本可以忽略，所以给一条
            # 副本数闸门：超过 COMPACT_MAX_DOC_COPIES 份就重建。
            # 注意不能数 live：那是 dict，同名 entry 已被合并成一条，恒为 1。
            try:
                with zipfile.ZipFile(smd_path) as _z:
                    _doc = sum(1 for _n in _z.namelist() if _n == DOC_NAME)
            except Exception:
                return False
            return _doc > COMPACT_MAX_DOC_COPIES
        valid = {}
        for nm in (DOC_NAME, META_NAME):
            fp = os.path.join(base_dir, nm)
            if os.path.isfile(fp):
                valid[nm] = _file_sig(fp)      # 含 meta.json：不再按 0 字节算
        for rel, fp in _scan_assets(os.path.join(base_dir, ASSETS_DIR)):
            valid[ASSETS_DIR + "/" + rel] = _file_sig(fp)
        alive = 0
        for nm, ent in live.items():
            if valid.get(nm) == (ent[0], ent[1]):
                alive += ent[2]                # 压缩后字节，与 total 同单位
        return (total - alive) > total * COMPACT_DEAD_RATIO
    except Exception:
        return False


def _append_entries(pkg_path, entries):
    """在包上追加 (名字, 源文件) 列表。重名 entry 为设计依赖（读取以后写为准），
    压掉 zipfile 的 Duplicate name 告警。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(pkg_path, "a", zipfile.ZIP_DEFLATED) as z:
            for nm, fp in entries:
                z.write(fp, nm)
    _fsync_file(pkg_path)


def _fsync_file(path):
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save_from_dir(smd_path, base_dir):
    """增量保存（两阶段提交）：

    1. 顺序拷贝当前包到临时副本（字节级复制，旧 entry 不重新压缩，
       成本为顺序 IO，远低于全量重新 deflate）；
    2. 在副本上追加变化 entry（doc.md 恒追加；assets 与包内按 (字节数, CRC32) diff，
       只比大小会漏掉"换了图但字节数没变"）；
    3. fsync 后 os.replace 原子替换 —— 任意时刻断电：replace 前原包完好，
       replace 后新包完好，不存在半写状态。

    达到整理阈值则改为全量重建。返回 (追加 entry 数, 是否发生整理)。
    """
    doc = os.path.join(base_dir, DOC_NAME)
    if not os.path.isfile(doc):
        raise ValueError("doc.md missing in unpacked dir: %s" % base_dir)
    try:
        live = _live_sigs(smd_path)
    except Exception:
        live = {}
    with io.open(doc, "r", encoding="utf-8", newline="") as f:
        doc_text = f.read()
    texts = _ref_texts(doc_text)
    to_add = [(DOC_NAME, doc)]
    orphans = 0
    adir = os.path.join(base_dir, ASSETS_DIR)
    for rel, fp in _scan_assets(adir):
        if not is_protected(rel) and not is_asset_referenced(doc_text, rel, texts):
            # 保存清理纪律：doc.md 未引用的资产从解包目录删除；
            # 删除失败保守留存（不阻断保存）
            try:
                os.remove(fp)
                orphans += 1
            except OSError:
                pass
            continue
        nm = ASSETS_DIR + "/" + rel
        if nm not in live or _file_sig(fp) != live[nm]:
            to_add.append((nm, fp))
    if orphans:
        # 包内旧 entry 是追加式的，增量保存清不掉——孤儿已出目录，
        # 全量重建才能把它们从包内移除
        compact(smd_path, base_dir)
        return len(to_add), True
    if needs_compact(smd_path, base_dir):
        compact(smd_path, base_dir)
        return len(to_add), True
    tmp = "%s.tmp%d" % (smd_path, int(time.time() * 1000))
    # 失败时保留 tmp：会话结束工作目录会被 clear_tmp 清掉，它是本次内容
    # 跨会话的唯一幸存副本（恢复入口 = 打开文档时检测同名 .tmp<时间戳>）。
    # 成功替换后 tmp 已被 os.replace 消费，天然无残留，无需任何清理。
    shutil.copyfile(smd_path, tmp)
    _append_entries(tmp, to_add)
    _replace_retry(tmp, smd_path)
    sig_file = os.path.join(base_dir, ".source.json")
    _write_sig(smd_path, sig_file)          # 保存后刷新指纹，本会话继续复用该目录
    _purge_stale_tmps(smd_path)             # 新包已落位，旧的失败备份过期
    return len(to_add), False


def _purge_stale_tmps(smd_path):
    """保存成功后清掉同名的旧 .tmp<时间戳> 备份。

    tmp 的唯一用途是「这次保存失败了，本次内容还在这儿」。一旦新包已经原子
    落位，旧 tmp 就是过期副本：留着的话每失败一次积一个，而且打开文档时那条
    「发现未完成的保存备份」永远弹（它只挑最新一个，旧的没人管）。清理只放在
    **成功路径**——失败路径一律不动，那是恢复入口。
    """
    d = os.path.dirname(smd_path) or "."
    base = os.path.basename(smd_path)
    pref = base + ".tmp"
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    n = 0
    for fn in names:
        if not fn.startswith(pref):
            continue
        if not fn[len(pref):].isdigit():
            continue
        try:
            os.remove(os.path.join(d, fn))
            n += 1
        except OSError:
            pass
    return n


def compact(smd_path, base_dir):
    """整理：按解包目录现状重建全量包，原子替换，天然清掉死空间与已删除资源。"""
    pack_from_dir(smd_path,
                  os.path.join(base_dir, DOC_NAME),
                  os.path.join(base_dir, ASSETS_DIR))
    sig_file = os.path.join(base_dir, ".source.json")
    _write_sig(smd_path, sig_file)
    _purge_stale_tmps(smd_path)


def clear_tmp():
    """服务启动/退出时清理解包缓存目录（会话级数据，正文与资源以 .smd 为准）。"""
    shutil.rmtree(_tmp_root(), ignore_errors=True)


# ---------------------------------------------------------------------------
# 对外 API：先取包级锁，再调内部实现。
# 锁只在这里取一次——内部实现会互相调用（save → compact → pack），
# 每层各加一把只会造出「漏加一层就静默失效」的结构，而漏掉的那层
# 平时看不出来：单线程手动保存永远正常，只有并发时才丢数据。
# ---------------------------------------------------------------------------

def base_dir_for(smd_path):
    """返回该 .smd 的解包工作目录；未解包或包已变化（外部修改）则重新解包。

    目录名 = md5(绝对路径小写)，跨会话稳定；目录内 .source.json 记录
    打开时的包指纹，保存/贴图后同步更新，外部改动会触发重解包。
    """
    with locked(smd_path):
        return _base_dir_for(smd_path)


def pack_from_dir(smd_path, doc_src, assets_src=None):
    """全量打包（新建/另存为/整理用），原子替换。"""
    with locked(smd_path):
        _pack_from_dir(smd_path, doc_src, assets_src)


def save_from_dir(smd_path, base_dir):
    """增量保存（两阶段提交），返回 (追加 entry 数, 是否发生整理)。"""
    with locked(smd_path):
        return _save_from_dir(smd_path, base_dir)
