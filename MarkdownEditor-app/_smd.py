# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_smd.py -- .smd 自包含文档格式（v1.3.0）

.smd = ZIP 容器，内部结构：
    doc.md       正文（UTF-8）
    history/NNNNNN.md  历史版本（v1.3.0 新增；序号单调递增，最新一条是上一版正文）
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
    （history/* 走的是"每次追加新名字"的路径，没有比对问题。）
  - 不被正文引用的资产有两类豁免（见 is_protected）：annotations.json 与
    `.mde/*`。二者都靠"正文里搜 assets/<名字>"这个判据永远搜不到，不豁免就
    会在保存时被当孤儿删掉。
  - v1.3.0 起「保留谁」的判据是**并集**：当前正文 + 全部历史版本。
    只被某个历史版本引用的图必须留着，否则回滚到那个版本会破图。
    回收动作只在**打开文档时**做（maintain），保存过程不删任何资产——
    保存时删会与并集判据自相矛盾：历史独占的图第一次保存就没了。
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
HIST_DIR = "history"       # 历史版本目录：history/NNNNNN.md（v1.3.0）

# 历史保留份数（用户可配，2026-10-31 口径：默认 30，允许 1~200）。
# 包内容忍上限按同比例放大 4/3，见 hist_cap()。设成 0 或负数一律按 1 处理。
HIST_KEEP = 30
HIST_KEEP_MIN = 1
HIST_KEEP_MAX = 200
_HIST_KEEP = HIST_KEEP


def set_hist_keep(n):
    """设置进程内的保留份数（md_server 每次入口按 ui-settings 调用）。

    非数字/越界一律夹到合法区间，返回实际生效值——静默吞掉非法值等于让人以为
    设置生效了，实际还是旧值。
    """
    global _HIST_KEEP
    try:
        v = int(n)
    except (TypeError, ValueError):
        return _HIST_KEEP
    v = max(HIST_KEEP_MIN, min(HIST_KEEP_MAX, v))
    _HIST_KEEP = v
    return v


def hist_keep():
    return _HIST_KEEP


def hist_cap(keep=None):
    """包内容忍上限 = round(keep / 0.75)。

    keep=30 → 40，keep=5 → 7，keep=10 → 13（整数四舍五入，用
    (k*4+1)//3 精确复现，不引入浮点误差）。留在包里的份数超过 cap 才触发
    一次整理并裁回 keep——追加式 zip 删不掉单条，只能整包重建，加这点缓冲
    是为了不变成"每次保存都重建"。
    """
    k = hist_keep() if keep is None else max(1, int(keep))
    return max(1, (k * 4 + 1) // 3)


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
    """正文的等价形态集合：原样 + URL 解码后 + 反斜杠归一。

    链接目标里的空格与中文可能被写成 %20 / %E5%9B%BE，纯子串匹配会认不出，
    正在使用的图就被判成孤儿删掉。解码只参与「是否被引用」这一个判断，
    绝不回写正文（回写会改动用户内容）。

    反斜杠归一（v1.3.0）：手写的 Windows 绝对路径 `...\\<stem>.assets\\a.png`
    里没有 "assets/a.png" 这个正斜杠子串，不归一就会在打开时被当孤儿删掉。
    归一只是多加一种形态参与匹配，方向仍然是「宁可多留」。
    """
    raw = doc_text or ""
    try:
        dec = urllib.parse.unquote(raw)
    except Exception:
        dec = raw
    out = [raw]
    if dec != raw:
        out.append(dec)
    for t in list(out):
        if "\\" in t:
            out.append(t.replace("\\", "/"))
    # 去重保序：三种形态常常完全一样
    seen = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return tuple(uniq)


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


def is_asset_used(rel, texts):
    """并集判定：rel 是否被 texts（多份正文的 _ref_texts 拼接）中任意一份引用。

    v1.3.0 的回收口径就是这一条——当前版本 + 全部历史版本，谁提到都算数。
    """
    ref = ASSETS_DIR + "/" + str(rel).replace("\\", "/")
    for t in texts:
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


def _clear_attrs(path):
    """递归清掉只读/隐藏位（Windows）。失败静默——删不掉由调用方断言。

    只读文件删不掉，而 `rmtree(ignore_errors=True)` 把这个失败**静默吞掉**，
    留下半个目录；下次解包撞上同名只读文件就 PermissionError，前端只看到
    「读取文件失败：HTTP 500」。所以删除与覆盖之前必须逐层解位。
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
    except Exception:
        return
    RO, HI = 0x01, 0x02                      # FILE_ATTRIBUTE_READONLY / HIDDEN

    def _one(p):
        try:
            a = k32.GetFileAttributesW(str(p))
            if a == 0xFFFFFFFF:
                return
            if a & (RO | HI):
                k32.SetFileAttributesW(str(p), a & ~(RO | HI))
        except Exception:
            pass

    if not os.path.exists(path):
        return
    _one(path)
    for dp, dns, fns in os.walk(path):
        for nm in fns:
            _one(os.path.join(dp, nm))
        for nm in dns:
            _one(os.path.join(dp, nm))


def _force_rmtree(path, tries=2):
    """删目录：解位 → 删；没删掉再解位重试。返回目录是否真的消失。

    不能只靠 rmtree(ignore_errors=True)：它遇到只读文件静默跳过，调用方
    以为清干净了，实际留残骸——那正是 2026-10-31 那次 500 的成因。
    """
    if not os.path.exists(path):
        return True
    for _ in range(max(1, tries)):
        _clear_attrs(path)
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return True
    return False


def _extract_all(smd_path, dest):
    """逐条目解包，写之前先解位。

    `zipfile.extractall` 碰到目标位置的只读文件直接 PermissionError 且不重试；
    而只读档案是我们自己设的，所以这里绕开 extractall 自己写——顺带保证
    解出来的副本一律普通属性（副本本来就不该是只读）。
    """
    with zipfile.ZipFile(smd_path, "r") as z:
        for info in z.infolist():
            target = os.path.join(dest, info.filename.replace("/", os.sep))
            if info.filename.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            _clear_attrs(target)
            with z.open(info) as src, io.open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


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
        _force_rmtree(d)
    if os.path.exists(d):
        # 上一次没删干净（残留只读文件 / 被占用）：再解位清一次。
        # 仍清不掉也不阻断 —— 下面的逐条目解包会先给目标解位再写。
        _force_rmtree(d)
    os.makedirs(d, exist_ok=True)
    _check_all_entries(smd_path)
    _extract_all(smd_path, d)
    if not os.path.isfile(doc):
        _force_rmtree(d)
        raise ValueError("not a valid .smd (missing %s): %s" % (DOC_NAME, smd_path))
    _write_sig(smd_path, sig_file)
    return d


def _write_sig(smd_path, sig_file):
    try:
        with io.open(sig_file, "w", encoding="utf-8") as f:
            json.dump(_sig(smd_path), f)
    except Exception:
        pass


def _put_file(z, fp, arcname):
    """把磁盘文件写入包，条目权限固定 0644，**不继承源文件的只读位**。

    z.write 会把源文件的 st_mode 一起写进 external_attr；元数据档案是 0444，
    于是包里也记成只读，任何解包工具解出来都是只读副本 —— 副本只读正是
    「临时目录删不干净 -> 重开 500」的源头，所以这里一律压平。
    """
    st = os.stat(fp)
    zi = zipfile.ZipInfo(arcname, time.localtime(st.st_mtime)[:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    with z.open(zi, "w") as dst, open(fp, "rb") as src:
        shutil.copyfileobj(src, dst)


def _pack_from_dir(smd_path, doc_src, assets_src=None, hist_dir=None):
    """全量打包（新建/另存为/整理/回滚用）。临时文件 + os.replace 原子替换。

    资产过滤（v1.3.0 改为并集）：doc_src 正文 **以及 hist_dir 里每一份历史正文**
    都没提到的文件不入包。方向仍是「宁可多留」——只被某个旧版本引用的图必须
    留着，否则回滚过去就是破图；谁都不提到的才是真孤儿，正好借这次重建出包。

    hist_dir：解包目录下的 history/。历史条目的时间戳从**现有包**里取回
    （extractall 不还原 mtime，只用磁盘 mtime 会让每次整理都把历史时间刷成
    整理那一刻），包里没有的才用当前时间。
    """
    tmp = "%s.tmp%d" % (smd_path, int(time.time() * 1000))
    try:
        times = {s: dt for s, dt in _hist_times(smd_path).items()}
    except Exception:
        times = {}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        # newline=""：按原始字节读，不做 CRLF→LF 翻译（否则“整理”会顺手改正文）
        with io.open(doc_src, "r", encoding="utf-8", newline="") as f:
            doc_text = f.read()
        texts = list(_ref_texts(doc_text))
        z.writestr(DOC_NAME, doc_text)
        for seq, fp in _hist_files(hist_dir):
            try:
                with io.open(fp, "r", encoding="utf-8", newline="") as f:
                    t = f.read()
            except Exception:
                continue
            texts.extend(_ref_texts(t))
            nm = "%s/%06d.md" % (HIST_DIR, seq)
            dt = times.get(seq) or tuple(time.localtime()[:6])
            zi = zipfile.ZipInfo(nm, dt)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, t)
        for rel, fp in _scan_assets(assets_src):
            if is_protected(rel):
                _put_file(z, fp, ASSETS_DIR + "/" + rel)
                continue
            if not is_asset_used(rel, texts):
                continue
            _put_file(z, fp, ASSETS_DIR + "/" + rel)
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


# ---------------------------------------------------------------------------
# 历史版本：history/NNNNNN.md
#
# 追加式结构下历史条目只能"新增"不能"删除"，所以序号单调递增、永不回退、
# 永不重排；裁剪靠整包重建（compact），重建后序号保持原值，不重新编号。
# ---------------------------------------------------------------------------

def hist_dir_of(base_dir):
    return os.path.join(base_dir, HIST_DIR)


def _hist_seq(name):
    """entry 名 → 序号；不是历史条目返回 None（history/x.md 之外一律不算）。"""
    n = str(name).replace("\\", "/")
    if not n.startswith(HIST_DIR + "/"):
        return None
    base = n[len(HIST_DIR) + 1:]
    if "/" in base or not base.lower().endswith(".md"):
        return None
    num = base[:-3]
    if not num.isdigit():
        return None
    return int(num)


def _hist_files(hist_dir):
    """解包目录里的历史文件 → [(序号, 磁盘路径)]，按序号升序。"""
    out = []
    if not hist_dir or not os.path.isdir(hist_dir):
        return out
    try:
        names = os.listdir(hist_dir)
    except OSError:
        return out
    for fn in names:
        seq = _hist_seq(HIST_DIR + "/" + fn)
        if seq is None:
            continue
        fp = os.path.join(hist_dir, fn)
        if os.path.isfile(fp):
            out.append((seq, fp))
    out.sort()
    return out


def _hist_infos(smd_path):
    """包内历史条目 → {序号: ZipInfo}（同名多条以后者为准）。"""
    ent = {}
    with zipfile.ZipFile(smd_path, "r") as z:
        for info in z.infolist():
            seq = _hist_seq(info.filename)
            if seq is not None:
                ent[seq] = info
    return ent


def _hist_times(smd_path):
    """包内历史条目 → {序号: date_time 六元组}，重建时用来保住原始时间。"""
    return {s: i.date_time for s, i in _hist_infos(smd_path).items()}


def _next_hist_seq(smd_path):
    try:
        seqs = list(_hist_infos(smd_path).keys())
    except Exception:
        seqs = []
    return (max(seqs) + 1) if seqs else 1


def _package_doc_text(smd_path):
    """包内当前正文（末条 doc.md）；包不存在/损坏返回 None。"""
    try:
        with zipfile.ZipFile(smd_path, "r") as z:
            return z.read(DOC_NAME).decode("utf-8")
    except Exception:
        return None


def _write_text(path, text):
    """通用原子写（tmp → fsync → replace），供历史文件使用。"""
    tmp = "%s.tmp%d" % (path, next(_DOC_SEQ))
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    _replace_retry(tmp, path)


def _first_line(text):
    """历史列表用的标题：首个非空行，去掉前导 # 与空白，截 60 字。"""
    for ln in (text or "").splitlines():
        s = ln.strip().lstrip("#").strip()
        if s:
            return s[:60]
    return ""


def _trim_hist_dir(hist_dir, keep=None):
    """按保留份数裁掉最老的条目，返回删除条数（只在目录里删，包里靠重建）。"""
    k = hist_keep() if keep is None else max(1, int(keep))
    files = _hist_files(hist_dir)
    n = 0
    for _seq, fp in files[:max(0, len(files) - k)]:
        try:
            os.remove(fp)
            n += 1
        except OSError:
            pass
    return n


def _prune_empty_dirs(root):
    """删掉资产目录里被清空的子目录（不碰 root 本身）。"""
    if not root or not os.path.isdir(root):
        return
    for dp, dns, fns in os.walk(root, topdown=False):
        if os.path.normpath(dp) == os.path.normpath(root):
            continue
        try:
            if not os.listdir(dp):
                os.rmdir(dp)
        except OSError:
            pass


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

    v1.3.0 追加两条闸门（历史版本）：
      · 历史条目数 > hist_cap()（= round(keep/0.75)）→ 必须重建，重建时裁回 keep。
        追加式 zip 删不掉单条，只能整包重建，所以留这个缓冲把重建摊成
        「每 cap-keep 次保存一次」，而不是从第 keep 次起每次保存都重建。
      · 历史条目**不计入死空间**以外的判断——它们本来就是有效数据。
    """
    try:
        total = os.path.getsize(smd_path)
        with zipfile.ZipFile(smd_path, "r") as _z:
            infos = _z.infolist()
        live = {i.filename: (i.file_size, i.CRC & 0xFFFFFFFF, i.compress_size)
                for i in infos}
        hist_seqs = set()
        doc_copies = 0
        for i in infos:
            if i.filename == DOC_NAME:
                doc_copies += 1
            seq = _hist_seq(i.filename)
            if seq is not None:
                hist_seqs.add(seq)
        if len(hist_seqs) > hist_cap():
            return True                        # 历史超缓冲，重建并裁剪
        if total < COMPACT_MIN_BYTES:
            # 小包（纯文本文档）的死空间占比永远到不了 30%，5MB 闸门等于永
            # 不整理——可 doc.md 每次保存都追加一份，实测 20 次保存积了 21 份
            # 副本、包从 403 字节涨到 3693。小包重建成本可以忽略，所以给一条
            # 副本数闸门：超过 COMPACT_MAX_DOC_COPIES 份就重建。
            # 注意不能数 live：那是 dict，同名 entry 已被合并成一条，恒为 1。
            return doc_copies > COMPACT_MAX_DOC_COPIES
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
                _put_file(z, fp, nm)
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
    2. 在副本上追加变化 entry（doc.md 与 history/新条目；assets 与包内按
       (字节数, CRC32) diff，只比大小会漏掉"换了图但字节数没变"）；
    3. fsync 后 os.replace 原子替换 —— 任意时刻断电：replace 前原包完好，
       replace 后新包完好，不存在半写状态。

    历史（v1.3.0）：保存前把**包里当前那一版正文**写成 history/<新序号>.md，
    即"被替换掉的那一版"。正文与包内一字不差则整次保存什么都不写——包括不
    追加 doc.md，避免无改动保存也刷版本。

    **保存不删任何资产**：保留判据是"当前 + 全部历史"的并集，保存时按当前
    单版删，历史独占的图第一次保存就没了。回收只在打开文档时做（maintain）。

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
    to_add = []
    prev = _package_doc_text(smd_path)
    if prev is None or prev != doc_text:
        if prev is not None:
            hd = hist_dir_of(base_dir)
            try:
                os.makedirs(hd, exist_ok=True)
                seq = _next_hist_seq(smd_path)
                hp = os.path.join(hd, "%06d.md" % seq)
                _write_text(hp, prev)
                to_add.append((HIST_DIR + "/%06d.md" % seq, hp))
            except OSError:
                pass                      # 历史写不进去不该挡住正文保存
        to_add.append((DOC_NAME, doc))
    adir = os.path.join(base_dir, ASSETS_DIR)
    for rel, fp in _scan_assets(adir):
        nm = ASSETS_DIR + "/" + rel
        if nm not in live or _file_sig(fp) != live[nm]:
            to_add.append((nm, fp))
    if not to_add:
        return 0, False
    if needs_compact(smd_path, base_dir):
        # 重建按解包目录现状出包：本次的新正文与新历史已在目录里，一并进包，
        # 顺带把历史裁回保留份数
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


def compact(smd_path, base_dir, keep=None):
    """整理：按解包目录现状重建全量包，原子替换，天然清掉死空间与已删除资源。

    v1.3.0：重建前先把历史裁到保留份数（目录里删最老的那几条，包里随之消失）。
    裁剪只在这里做——追加式结构下这是唯一能真正删掉条目的时机。
    """
    _trim_hist_dir(hist_dir_of(base_dir), keep)
    pack_from_dir(smd_path,
                  os.path.join(base_dir, DOC_NAME),
                  os.path.join(base_dir, ASSETS_DIR),
                  hist_dir_of(base_dir))
    sig_file = os.path.join(base_dir, ".source.json")
    _write_sig(smd_path, sig_file)
    _purge_stale_tmps(smd_path)


def _maintain(smd_path, base_dir, keep=None):
    """打开文档时的整理：回收没人引用的资产 + 按保留份数裁剪历史，一次重建。

    资产判据是**并集**：当前正文 + 目录里每一份历史正文，谁提到都留着。
    只被已裁掉的那版引用的图，本来就该跟着版本一起消失——这正是"30 份里
    没人引用就删"的口径。

    顺序必须是「先裁历史、再按剩下的算并集、最后删资产」：反过来的话，已被
    裁掉的那版还参与判据，它独占的图会多活一轮，要等下次打开才删——同一次
    打开里看不出来，测试也测不出来。

    返回 {cleaned, bytes, trimmed}；什么都没做就返回全 0，且不写盘。
    """
    doc = os.path.join(base_dir, DOC_NAME)
    if not os.path.isfile(doc):
        raise ValueError("doc.md missing in unpacked dir: %s" % base_dir)
    hd = hist_dir_of(base_dir)
    trimmed = _trim_hist_dir(hd, keep)
    texts = []
    with io.open(doc, "r", encoding="utf-8", newline="") as f:
        texts.extend(_ref_texts(f.read()))
    for _seq, fp in _hist_files(hd):
        try:
            with io.open(fp, "r", encoding="utf-8", newline="") as f:
                texts.extend(_ref_texts(f.read()))
        except Exception:
            continue                      # 读不出来就少一份判据，方向仍偏保守
    adir = os.path.join(base_dir, ASSETS_DIR)
    cleaned = 0
    freed = 0
    for rel, fp in _scan_assets(adir):
        if is_protected(rel):
            continue
        if is_asset_used(rel, texts):
            continue
        try:
            sz = os.path.getsize(fp)
            os.remove(fp)
            cleaned += 1
            freed += sz
        except OSError:
            pass
    if cleaned:
        _prune_empty_dirs(adir)
    if cleaned or trimmed:
        compact(smd_path, base_dir, keep)
    return {"cleaned": cleaned, "bytes": freed, "trimmed": trimmed}


def _list_history(smd_path, keep=None):
    """历史版本列表，最新在前，最多 keep 条（界面可见上限 = 保留份数）。

    标题与字数从正文现算（不额外存清单：清单会跟正文不同步）。
    """
    k = hist_keep() if keep is None else max(1, int(keep))
    out = []
    with zipfile.ZipFile(smd_path, "r") as z:
        infos = {}
        for info in z.infolist():
            s = _hist_seq(info.filename)
            if s is not None:
                infos[s] = info          # 同名多条以后者为准
        for seq in sorted(infos)[-k:]:
            info = infos[seq]
            try:
                t = z.read(info).decode("utf-8", "replace")
            except Exception:
                t = ""
            out.append({
                "seq": seq,
                "time": "%04d-%02d-%02d %02d:%02d" % tuple(info.date_time[:5]),
                "words": len(t),
                "title": _first_line(t),
            })
    out.reverse()
    return out


def _read_history(smd_path, seq):
    """取某一历史版本的正文。"""
    n = int(seq)
    with zipfile.ZipFile(smd_path, "r") as z:
        infos = _hist_infos(smd_path)
        info = infos.get(n)
        if info is None:
            raise ValueError("history version not found: %s" % seq)
        return z.read(info).decode("utf-8", "replace")


def _restore_history(smd_path, base_dir, seq):
    """回滚到某一历史版本（确定性、原子）。

    语义（用户定稿）：选中的历史变成当前，当前变成最新一条历史，该历史条目
    从列表移除；总数不变。
    """
    n = int(seq)
    cur = _package_doc_text(smd_path)
    if cur is None:
        raise ValueError("not a valid .smd (missing %s): %s" % (DOC_NAME, smd_path))
    with zipfile.ZipFile(smd_path, "r") as z:
        infos = _hist_infos(smd_path)
        if n not in infos:
            raise ValueError("history version not found: %s" % seq)
        entries = []
        for s in sorted(infos):
            entries.append((s, z.read(infos[s]).decode("utf-8", "replace")))
    target = dict(entries)[n]
    rest = [(s, t) for s, t in entries if s != n]
    newseq = (max([s for s, _ in entries] + [0])) + 1
    rest.append((newseq, cur))
    keep = hist_keep()
    rest = rest[-keep:]
    hd = hist_dir_of(base_dir)
    os.makedirs(hd, exist_ok=True)
    for fn in os.listdir(hd):
        if _hist_seq(HIST_DIR + "/" + fn) is not None:
            try:
                os.remove(os.path.join(hd, fn))
            except OSError:
                pass
    for s, t in rest:
        _write_text(os.path.join(hd, "%06d.md" % s), t)
    write_doc(base_dir, target)
    compact(smd_path, base_dir)
    return {"content": target, "seq": newseq, "removed": n, "kept": len(rest)}


def clear_tmp():
    """服务启动/退出时清理解包缓存目录（会话级数据，正文与资源以 .smd 为准）。

    必须解位再删：只读档案（zero.json）会让 rmtree 静默失败，留下残骸 ->
    下次解包撞只读文件 PermissionError -> 文档打不开。
    """
    _force_rmtree(_tmp_root())


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


def pack_from_dir(smd_path, doc_src, assets_src=None, hist_dir=None):
    """全量打包（新建/另存为/整理用），原子替换。"""
    with locked(smd_path):
        _pack_from_dir(smd_path, doc_src, assets_src, hist_dir)


def save_from_dir(smd_path, base_dir):
    """增量保存（两阶段提交），返回 (追加 entry 数, 是否发生整理)。"""
    with locked(smd_path):
        return _save_from_dir(smd_path, base_dir)


def maintain(smd_path, base_dir, keep=None):
    """打开文档时整理：回收未引用资产 + 裁剪历史。返回 {cleaned, bytes, trimmed}。"""
    with locked(smd_path):
        return _maintain(smd_path, base_dir, keep)


def list_history(smd_path, keep=None):
    """历史版本列表（最新在前，最多 keep 条）。"""
    with locked(smd_path):
        return _list_history(smd_path, keep)


def read_history(smd_path, seq):
    """取某一历史版本的正文。"""
    with locked(smd_path):
        return _read_history(smd_path, seq)


def restore_history(smd_path, base_dir, seq):
    """回滚到某一历史版本，返回 {content, seq, removed, kept}。"""
    with locked(smd_path):
        return _restore_history(smd_path, base_dir, seq)
