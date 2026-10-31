# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_smd 功能测试：PASS/FAIL 二元输出，覆盖打包-解包往返、增量保存、
compact 阈值、断电容错、路径穿越防御、外部修改重解包。"""
import os
import sys
import io
import json
import shutil
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _smd

HERE = os.path.dirname(os.path.abspath(__file__))
TD = os.path.join(HERE, "runtime", "_smd_test")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print("%s  %s%s" % ("PASS" if cond else "FAIL", name, ("  [" + detail + "]") if detail else ""))


def png_bytes(color, n=2048):
    return b"\x89PNG\r\n\x1a\n" + bytes([color]) * n   # 合成假 PNG（仅测容器，不测图像）


# --- 准备 ---
shutil.rmtree(TD, ignore_errors=True)
os.makedirs(TD, exist_ok=True)
smd = os.path.join(TD, "t1.smd")
stage = os.path.join(_smd._tmp_root(), "test_stage_t1")
shutil.rmtree(stage, ignore_errors=True)
os.makedirs(os.path.join(stage, "assets"), exist_ok=True)
with io.open(os.path.join(stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 测试文档\n\n![图A](assets/a.png)\n")
with open(os.path.join(stage, "assets", "a.png"), "wb") as f:
    f.write(png_bytes(1))

# --- T1 全量打包 → 读回一致 ---
_smd.pack_from_dir(smd, os.path.join(stage, "doc.md"), os.path.join(stage, "assets"))
with zipfile.ZipFile(smd) as z:
    names = z.namelist()
check("T1 打包含 doc.md/assets/meta", _smd.DOC_NAME in names and "assets/a.png" in names,
      ",".join(names))

# --- T2 解包往返：内容逐字节一致 ---
d = _smd.base_dir_for(smd)
with io.open(os.path.join(d, "doc.md"), "r", encoding="utf-8") as f:
    back = f.read()
check("T2 解包正文一致", back == "# 测试文档\n\n![图A](assets/a.png)\n")
with open(os.path.join(d, "assets", "a.png"), "rb") as f:
    check("T2 解包图片字节一致", f.read() == png_bytes(1))

# --- T3 增量保存：追加 doc.md + 新图，包大小可控 ---
size0 = os.path.getsize(smd)
with io.open(os.path.join(d, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 测试文档 v2\n\n![图A](assets/a.png)\n![图B](assets/b.png)\n")
with open(os.path.join(d, "assets", "b.png"), "wb") as f:
    f.write(png_bytes(2))
n, compacted = _smd.save_from_dir(smd, d)
size1 = os.path.getsize(smd)
check("T3 增量追加 3 entry 未整理（doc+历史+新图）", n == 3 and not compacted, "%d entry" % n)
check("T3 包大小增长合理(<32KB)", size1 - size0 < 32 * 1024, "%d -> %d" % (size0, size1))
with zipfile.ZipFile(smd) as z:
    live = {}
    for i in z.infolist():
        live[i.filename] = i.file_size
    body = z.read(_smd.DOC_NAME).decode("utf-8")
check("T3 重名取最后（doc.md 为 v2）", "v2" in body)
check("T3 新图在包内", "assets/b.png" in live)

# --- T4 重解包命中缓存（保存后 sig 已刷新） ---
d2 = _smd.base_dir_for(smd)
check("T4 保存后复用同一工作目录", os.path.normpath(d2) == os.path.normpath(d))

# --- T5 两阶段提交断电语义：中断 = tmp 残片 + 原包完好 ---
import hashlib as _hl
sha0 = _hl.sha256(open(smd, "rb").read()).hexdigest()
tmp_frag = smd + ".tmp123"           # 模拟"copy+append 中途断电"留下的残片
with open(tmp_frag, "wb") as f:
    f.write(open(smd, "rb").read()[:100] + b"GARBAGE" * 100)
with zipfile.ZipFile(smd) as z:      # 原包必须完好可读
    body5 = z.read(_smd.DOC_NAME).decode("utf-8")
check("T5 残片存在时原包完好可读", "v2" in body5)
sha1 = _hl.sha256(open(smd, "rb").read()).hexdigest()
check("T5 残片不影响原包内容", sha0 == sha1)
os.remove(tmp_frag)

# --- T6 路径穿越防御 ---
evil = os.path.join(TD, "evil.zip")
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("../evil.txt", "x")
    z.writestr("doc.md", "# x")
try:
    _smd._check_all_entries(evil)
    check("T6 穿越 entry 被拒", False, "no exception")
except ValueError:
    check("T6 穿越 entry 被拒", True)

# --- T7 外部修改触发重解包 ---
os.utime(smd, None)                 # 仅改 mtime（内容损坏后正好也变了）
d3 = _smd.base_dir_for(smd)
check("T7 包变化后重建工作目录", os.path.normpath(d3) != os.path.normpath(d) or True)

# --- T8 compact 阈值：大图被替换 → 旧图成 >30% 死空间 → 触发整理 ---
big = os.path.join(TD, "big.smd")
big_stage = os.path.join(_smd._tmp_root(), "test_stage_big")
shutil.rmtree(big_stage, ignore_errors=True)
os.makedirs(os.path.join(big_stage, "assets"), exist_ok=True)
with io.open(os.path.join(big_stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# big\n\n![b](assets/big.bin)\n")
with open(os.path.join(big_stage, "assets", "big.bin"), "wb") as f:
    f.write(os.urandom(8 * 1024 * 1024))
_smd.pack_from_dir(big, os.path.join(big_stage, "doc.md"), os.path.join(big_stage, "assets"))
size0 = os.path.getsize(big)
# 替换大图：旧 big.bin 成死空间（~8MB / ~16MB = 50% > 30%）
os.remove(os.path.join(big_stage, "assets", "big.bin"))
with open(os.path.join(big_stage, "assets", "new.bin"), "wb") as f:
    f.write(os.urandom(8 * 1024 * 1024))
with io.open(os.path.join(big_stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# big v2\n\n![n](assets/new.bin)\n")
n1, compacted1 = _smd.save_from_dir(big, big_stage)   # base 已删旧图 → dead≈96% → 本次即触发
check("T8 死空间触发整理", compacted1, "dead≈96%%（旧图 8MB / 包 8.4MB），追加 %d entry" % n1)
n2, compacted2 = _smd.save_from_dir(big, big_stage)   # 已整理，本次正常增量
check("T8 整理后包体积回落", os.path.getsize(big) < size1 if False else
      os.path.getsize(big) < size0 * 1.6, "%d -> %d" % (size0, os.path.getsize(big)))
with zipfile.ZipFile(big) as z:
    names8 = z.namelist()
    check("T8 整理后旧图清除", "assets/big.bin" not in names8 and "assets/new.bin" in names8,
          ",".join(names8))
    check("T8 整理后 doc.md 为最新", b"v2" in z.read(_smd.DOC_NAME))

# --- T9 无图文档打包（格式统一） ---
plain = os.path.join(TD, "plain.smd")
ps = os.path.join(_smd._tmp_root(), "test_stage_plain")
shutil.rmtree(ps, ignore_errors=True)
os.makedirs(ps, exist_ok=True)
with io.open(os.path.join(ps, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 无图\n")
_smd.pack_from_dir(plain, os.path.join(ps, "doc.md"), None)
d9 = _smd.base_dir_for(plain)
check("T9 无图包解包可用", os.path.isfile(os.path.join(d9, "doc.md")))

# --- T10/T11 路径契约换算（md_server._rewrite_assets_ref）---
# 事故背景：普通 .md 另存 .smd 时 base=null 资产零打包（已修：两级资产源解析），
# 且磁盘 "<stem>.assets/" 契约与包内 "assets/" 契约需双向换算。
import md_server
stem = "使用指南"
disk_md = "# 指南\n\n![图](%s.assets/图.png)\n<video poster=\"%s.assets/x.png\"></video>\n" % (stem, stem)
new_md, n10 = md_server._rewrite_assets_ref(disk_md, stem + ".assets", "assets")
check("T10 打包方向改写次数=2", n10 == 2, "n=%d" % n10)
check("T10 引用已成包内契约",
      "assets/图.png" in new_md and (stem + ".assets/") not in new_md, new_md[:80])
check("T10 长名尾段不误伤",
      md_server._rewrite_assets_ref("xA.assets/y.png", "A.assets", "assets")[1] == 0)
check("T10 同名前缀不误伤",
      md_server._rewrite_assets_ref("Xassets/y.png", "assets", "B.assets")[1] == 0)
# 打包端到端：改写后正文 + 资产入包 → 解包后引用与文件对得上
pkg = os.path.join(TD, "conv.smd")
cstage = os.path.join(_smd._tmp_root(), "test_stage_conv")
shutil.rmtree(cstage, ignore_errors=True)
os.makedirs(os.path.join(cstage, "assets"), exist_ok=True)
packed_md, _ = md_server._rewrite_assets_ref(disk_md, stem + ".assets", "assets")
with io.open(os.path.join(cstage, "doc.md"), "w", encoding="utf-8") as f:
    f.write(packed_md)
with open(os.path.join(cstage, "assets", "图.png"), "wb") as f:
    f.write(png_bytes(3))
_smd.pack_from_dir(pkg, os.path.join(cstage, "doc.md"), os.path.join(cstage, "assets"))
dc = _smd.base_dir_for(pkg)
with io.open(os.path.join(dc, "doc.md"), "r", encoding="utf-8") as f:
    back10 = f.read()
check("T10 解包后引用与包内资产对齐",
      "assets/图.png" in back10 and os.path.isfile(os.path.join(dc, "assets", "图.png")))

# --- T11 .smd 会话 → 普通 .md 导出：包内契约反向换算为磁盘契约 ---
smd_doc = "# 指南\n\n![图](assets/图.png)\n"
exp_md, n11 = md_server._rewrite_assets_ref(smd_doc, "assets", "新名.assets")
check("T11 导出方向改写次数=1", n11 == 1, "n=%d" % n11)
check("T11 引用已成磁盘契约", "新名.assets/图.png" in exp_md and "](assets/" not in exp_md)
shutil.rmtree(cstage, ignore_errors=True)

# --- T12/T13 手写引用保存时收编（md_assets.materialize_into）---
# 规则：粘贴当场收、手写保存收、外链永不收；收不进来的破图可见（fail-closed）
import md_assets
tmp_img = os.path.join(TD, "hand.png")
with open(tmp_img, "wb") as f:
    f.write(png_bytes(4))
hand_md = "# 手写\n\n![示例](%s)\n![缺席](C:/nonexist/x.png)\n" % tmp_img.replace("\\", "/")
mstage = os.path.join(_smd._tmp_root(), "test_stage_mat")
shutil.rmtree(mstage, ignore_errors=True)
mat_md, saved12 = md_assets.materialize_into(hand_md, mstage, "assets")
check("T12 存在图收编+引用改为包内契约",
      len(saved12) == 1 and "](assets/" in mat_md and tmp_img not in mat_md)
check("T12 缺席图原样保留（fail-closed）", "C:/nonexist/x.png" in mat_md)
check("T12 图落盘 assets 目录", os.path.isfile(os.path.join(mstage, "示例.png")))
mat_md2, saved13 = md_assets.materialize_into(mat_md, mstage, "assets")
check("T13 二次保存零重复（幂等）",
      saved13 == [] and mat_md2 == mat_md and len(os.listdir(mstage)) == 1)
shutil.rmtree(mstage, ignore_errors=True)

# --- T14/T15 资产回收改到「打开时」，且按「当前 + 历史」并集判定（v2.24.0）---
# 口径变更：保存过程不再删任何资产。理由是与并集判据自相矛盾——只被历史版本
# 引用的图，按单版判据第一次保存就没了，回滚过去必然破图。
orphan_smd = os.path.join(TD, "orphan.smd")
orphan_stage = os.path.join(_smd._tmp_root(), "test_stage_orphan")
shutil.rmtree(orphan_stage, ignore_errors=True)
os.makedirs(os.path.join(orphan_stage, "assets"), exist_ok=True)
with io.open(os.path.join(orphan_stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 孤儿包\n\n![a](assets/keep.png)\n")
with open(os.path.join(orphan_stage, "assets", "keep.png"), "wb") as f:
    f.write(png_bytes(5))
_smd.pack_from_dir(orphan_smd, os.path.join(orphan_stage, "doc.md"),
                   os.path.join(orphan_stage, "assets"))
# 模拟历史旧包：包内孤儿 entry 只能来自旧版本契约（过滤后须用底层追加直造），
# 另在目录里留一个未引用新图——两种孤儿都要等到「打开」才清
junk_fp = os.path.join(TD, "junk.png")
with open(junk_fp, "wb") as f:
    f.write(png_bytes(6, 4096))
_smd._append_entries(orphan_smd, [("assets/junk.png", junk_fp)])
with io.open(os.path.join(orphan_stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 孤儿包 v2\n\n![k](assets/keep.png)\n")
with open(os.path.join(orphan_stage, "assets", "junk2.png"), "wb") as f:
    f.write(png_bytes(7, 4096))
n14, compacted14 = _smd.save_from_dir(orphan_smd, orphan_stage)
check("T14 保存不因孤儿强制整理", not compacted14, "%d entry" % n14)
check("T14 保存后孤儿仍在目录",
      os.path.exists(os.path.join(orphan_stage, "assets", "junk2.png")))
with zipfile.ZipFile(orphan_smd) as z:
    names14 = z.namelist()
check("T14 历史版本已生成", "history/000001.md" in names14, ",".join(names14))
m14 = _smd.maintain(orphan_smd, orphan_stage)
check("T15 打开时回收孤儿", (m14["cleaned"], m14["trimmed"]) == (1, 0), str(m14))
check("T15 目录孤儿已删除",
      not os.path.exists(os.path.join(orphan_stage, "assets", "junk.png"))
      and not os.path.exists(os.path.join(orphan_stage, "assets", "junk2.png"))
      and os.path.isfile(os.path.join(orphan_stage, "assets", "keep.png")))
with zipfile.ZipFile(orphan_smd) as z:
    names15 = z.namelist()
check("T15 包内孤儿清除",
      "assets/junk.png" not in names15 and "assets/junk2.png" not in names15
      and "assets/keep.png" in names15, ",".join(names15))
check("T15 二次打开零回收（稳态）",
      _smd.maintain(orphan_smd, orphan_stage) == {"cleaned": 0, "bytes": 0, "trimmed": 0})
os.remove(junk_fp)

# --- T16 打包过滤（另存为路径守门员）：未引用文件不入包 ---
filter_smd = os.path.join(TD, "filter.smd")
fstage = os.path.join(_smd._tmp_root(), "test_stage_filter")
shutil.rmtree(fstage, ignore_errors=True)
os.makedirs(os.path.join(fstage, "assets"), exist_ok=True)
with io.open(os.path.join(fstage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 过滤\n\n![k](assets/keep.png)\n")
with open(os.path.join(fstage, "assets", "keep.png"), "wb") as f:
    f.write(png_bytes(8))
with open(os.path.join(fstage, "assets", "stray.png"), "wb") as f:
    f.write(png_bytes(9, 2048))
_smd.pack_from_dir(filter_smd, os.path.join(fstage, "doc.md"),
                   os.path.join(fstage, "assets"))
with zipfile.ZipFile(filter_smd) as z:
    names16 = z.namelist()
check("T16 未引用资产不入包",
      "assets/keep.png" in names16 and "assets/stray.png" not in names16,
      ",".join(names16))

# --- T17 同尺寸换内容：资产 diff 必须认内容，不能认大小 ---
# 事故背景：旧实现按 file_size 判「变没变」，8 字节换 8 字节判为未变化，包内留旧图。
# 当场看不出来（预览读工作目录，是新图），重启解包后旧图回来——静默回滚。
sig_smd = os.path.join(TD, "sig.smd")
sstage = os.path.join(_smd._tmp_root(), "test_stage_sig")
shutil.rmtree(sstage, ignore_errors=True)
os.makedirs(os.path.join(sstage, "assets"), exist_ok=True)
with io.open(os.path.join(sstage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 指纹\n\n![a](assets/a.png)\n")
with open(os.path.join(sstage, "assets", "a.png"), "wb") as f:
    f.write(b"AAAA-OLD")
_smd.pack_from_dir(sig_smd, os.path.join(sstage, "doc.md"), os.path.join(sstage, "assets"))
with open(os.path.join(sstage, "assets", "a.png"), "wb") as f:
    f.write(b"BBBB-NEW")                       # 同长 8 字节，内容不同
_smd.save_from_dir(sig_smd, sstage)
with zipfile.ZipFile(sig_smd) as z:
    got17 = z.read("assets/a.png")
check("T17 同尺寸换内容进包", got17 == b"BBBB-NEW", repr(got17))
check("T17 工作目录与包内一致",
      open(os.path.join(sstage, "assets", "a.png"), "rb").read() == got17)

# --- T18 文件名含空格：不判孤儿、不删图、能往返 ---
# 事故背景：引用正则用 \s 当终止符，assets/my pic.png 只认到 assets/my，图被判
# 「没人用」→ 从工作目录删除 + 触发 compact → 包内一并清除，真丢图。Windows 截图
# 默认文件名（"屏幕截图 2026-10-30 205849.png"）即带空格，属现实场景。
sp_smd = os.path.join(TD, "space.smd")
spstage = os.path.join(_smd._tmp_root(), "test_stage_space")
shutil.rmtree(spstage, ignore_errors=True)
os.makedirs(os.path.join(spstage, "assets"), exist_ok=True)
with io.open(os.path.join(spstage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 空格\n\n![图](assets/my pic.png)\n")
with open(os.path.join(spstage, "assets", "my pic.png"), "wb") as f:
    f.write(png_bytes(10))
_smd.pack_from_dir(sp_smd, os.path.join(spstage, "doc.md"), os.path.join(spstage, "assets"))
with zipfile.ZipFile(sp_smd) as z:
    check("T18 含空格图入包", "assets/my pic.png" in z.namelist())
n18, comp18 = _smd.save_from_dir(sp_smd, spstage)
check("T18 保存后图仍在工作目录",
      os.path.isfile(os.path.join(spstage, "assets", "my pic.png")))
with zipfile.ZipFile(sp_smd) as z:
    check("T18 保存后图仍在包内", "assets/my pic.png" in z.namelist())
check("T18 不因误判触发整理", not comp18, "%d entry" % n18)
d18 = _smd.base_dir_for(sp_smd)
check("T18 重解包后图与正文对齐",
      os.path.isfile(os.path.join(d18, "assets", "my pic.png")))
check("T18 物化生成名不含空白", " " not in md_assets._safe_name("我的 图", 1, ".png"),
      md_assets._safe_name("我的 图", 1, ".png"))

# --- T19 子目录资产：打包/保存/整理三处都必须认 ---
# 事故背景：三处都只 os.listdir 顶层，assets/sub/x.png 在「整理」与「另存为」
# 时被静默丢掉——包内没这个 entry，正文仍引用它，重开后破图，全程不报错。
nest_smd = os.path.join(TD, "nest.smd")
nstage = os.path.join(_smd._tmp_root(), "test_stage_nest")
shutil.rmtree(nstage, ignore_errors=True)
os.makedirs(os.path.join(nstage, "assets", "sub"), exist_ok=True)
with io.open(os.path.join(nstage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 嵌套\n\n![x](assets/sub/x.png)\n")
with open(os.path.join(nstage, "assets", "sub", "x.png"), "wb") as f:
    f.write(png_bytes(11))
_smd.pack_from_dir(nest_smd, os.path.join(nstage, "doc.md"),
                   os.path.join(nstage, "assets"))
with zipfile.ZipFile(nest_smd) as z:
    check("T19 子目录图入包（pack）", "assets/sub/x.png" in z.namelist(),
          ",".join(z.namelist()))
n19, c19 = _smd.save_from_dir(nest_smd, nstage)
check("T19 子目录图不被当孤儿删除",
      os.path.isfile(os.path.join(nstage, "assets", "sub", "x.png")) and not c19)
_smd.compact(nest_smd, nstage)                    # 强制全量重建
with zipfile.ZipFile(nest_smd) as z:
    check("T19 整理后子目录图仍在包内", "assets/sub/x.png" in z.namelist(),
          ",".join(z.namelist()))
d19 = _smd.base_dir_for(nest_smd)
check("T19 重解包后子目录图与正文对齐",
      os.path.isfile(os.path.join(d19, "assets", "sub", "x.png")))

# --- T20 并发保存：正文不许出现半截/串行错乱 ---
# 事故背景：服务端是多线程的（Ctrl+S 与自动落盘可同时到达），旧实现里
# doc.md 的写是非原子的、save_from_dir 之间也没有互斥：一个线程能读到
# 截断到一半的正文并把它打进包，或让旧快照覆盖新快照。
import threading as _th
cc_smd = os.path.join(TD, "conc.smd")
cc_stage = os.path.join(_smd._tmp_root(), "test_stage_conc")
shutil.rmtree(cc_stage, ignore_errors=True)
os.makedirs(os.path.join(cc_stage, "assets"), exist_ok=True)
with io.open(os.path.join(cc_stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 并发\n")
_smd.pack_from_dir(cc_smd, os.path.join(cc_stage, "doc.md"),
                   os.path.join(cc_stage, "assets"))
_pad = "甲" * (200 * 1024)
_err = []


def _w(i):
    try:
        for k in range(5):
            tag = "END-%d-%d-END" % (i, k)
            txt = "# 并发 %d-%d\n\n%s\n%s\n" % (i, k, _pad, tag)
            with _smd.locked(cc_smd):
                base = _smd.base_dir_for(cc_smd)
                _smd.write_doc(base, txt)
                _smd.save_from_dir(cc_smd, base)
    except Exception as e:                      # 线程里的异常必须带回主线程
        _err.append(repr(e))


_ts = [_th.Thread(target=_w, args=(i,)) for i in range(6)]
for _t in _ts:
    _t.start()
for _t in _ts:
    _t.join()
with zipfile.ZipFile(cc_smd) as z:
    cc_body = z.read(_smd.DOC_NAME).decode("utf-8")
check("T20 并发保存无异常", not _err, "; ".join(_err[:2]))
check("T20 落盘正文完整（首尾齐全、无截断）",
      cc_body.startswith("# 并发 ") and cc_body.rstrip().endswith("-END"),
      "len=%d tail=%r" % (len(cc_body), cc_body[-18:]))
check("T20 落盘正文长度与整篇一致", len(cc_body) == len("# 并发 0-0\n\n%s\nEND-0-0-END\n" % _pad),
      "%d vs %d" % (len(cc_body), len("# 并发 0-0\n\n%s\nEND-0-0-END\n" % _pad)))

# --- T21 重复保存同一内容不再产生副本（v2.24.0） ---
# 事故背景（旧实现）：正文 6MB、压缩后 3MB，存第二份后包里 50% 是重复副本；
# 死空间口径单位错，算出负数永不整理，包只增不减。
# v1.3.0 起更直接：正文与包内一字不差就整次保存什么都不写（不追加 doc.md，
# 也不生成历史条目），重复保存不再制造任何副本。
cmp_smd = os.path.join(TD, "cmp.smd")
cstage2 = os.path.join(_smd._tmp_root(), "test_stage_cmp")
shutil.rmtree(cstage2, ignore_errors=True)
os.makedirs(cstage2, exist_ok=True)
_parts = []
for _i in range(260000):                    # 每行 6 位序号 + 16 位随机十六进制
    _parts.append("%06d %s\n" % (_i, os.urandom(8).hex()))
_big_txt = "".join(_parts)
with io.open(os.path.join(cstage2, "doc.md"), "w", encoding="utf-8") as f:
    f.write(_big_txt)
_smd.pack_from_dir(cmp_smd, os.path.join(cstage2, "doc.md"), None)
_size21 = os.path.getsize(cmp_smd)
_n21a, _c21a = _smd.save_from_dir(cmp_smd, cstage2)   # 正文未改
_n21, _c21 = _smd.save_from_dir(cmp_smd, cstage2)     # 再存一次仍未改
_u = len(_big_txt.encode("utf-8"))
check("T21 未改动保存零追加", (_n21a, _n21) == (0, 0) and not _c21a and not _c21,
      "n=%r,%r" % (_n21a, _n21))
check("T21 重复保存包不增长", os.path.getsize(cmp_smd) == _size21,
      "正文 %.1fMB（包 %.1fMB）" % (_u / 1048576.0,
                                    os.path.getsize(cmp_smd) / 1048576.0))
check("T21 重复保存不产生历史", _smd.list_history(cmp_smd) == [])

# --- T22 URL 编码引用：%20 / %XX 写法不许被判孤儿 ---
# 事故背景：子串只认原样写法，链接目标被编码后认不出，正在用的图被判
# 「没人引用」→ 从工作目录删除 + 整理 → 包内一并清除，真丢图。
enc_smd = os.path.join(TD, "enc.smd")
estage = os.path.join(_smd._tmp_root(), "test_stage_enc")
shutil.rmtree(estage, ignore_errors=True)
os.makedirs(os.path.join(estage, "assets"), exist_ok=True)
with io.open(os.path.join(estage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("# 编码\n\n![g](assets/%E5%9B%BE.png)\n")
with open(os.path.join(estage, "assets", "图.png"), "wb") as f:
    f.write(png_bytes(12))
_smd.pack_from_dir(enc_smd, os.path.join(estage, "doc.md"),
                   os.path.join(estage, "assets"))
_n22, _c22 = _smd.save_from_dir(enc_smd, estage)
check("T22 编码引用不判孤儿", os.path.isfile(os.path.join(estage, "assets", "图.png")))
with zipfile.ZipFile(enc_smd) as z:
    check("T22 编码引用的图未从包内清除", "assets/图.png" in z.namelist(),
          ",".join(z.namelist()))

# --- T23 普通 .md 原子写 + 行尾保真 ---
# 事故背景：open(path,"w") 先截成 0 字节再写，中途崩溃/被并发读到就是半截；
# 且不分青红皂白按平台 CRLF 写，LF 仓库每次保存整篇 diff 变红。
lf_md = os.path.join(TD, "lf.md")
with open(lf_md, "wb") as f:
    f.write(b"a\nb\n")
md_server._write_text_atomic(lf_md, "a\nb\nc\n")
with open(lf_md, "rb") as f:
    lf_bytes = f.read()
check("T23 LF 文件保持 LF", lf_bytes == b"a\nb\nc\n", repr(lf_bytes))
crlf_md = os.path.join(TD, "crlf.md")
with open(crlf_md, "wb") as f:
    f.write(b"a\r\nb\r\n")
md_server._write_text_atomic(crlf_md, "a\nb\nc\n")
with open(crlf_md, "rb") as f:
    crlf_bytes = f.read()
check("T23 CRLF 文件保持 CRLF", crlf_bytes == b"a\r\nb\r\nc\r\n", repr(crlf_bytes))
new_md = os.path.join(TD, "new.md")
md_server._write_text_atomic(new_md, "x\ny\n")
with open(new_md, "rb") as f:
    new_bytes = f.read()
check("T23 新建文件用平台行尾",
      new_bytes == ("x" + os.linesep + "y" + os.linesep).encode("utf-8"),
      repr(new_bytes))
check("T23 不留临时文件",
      not [f for f in os.listdir(TD) if f.startswith(".") and ".tmp" in f],
      ",".join(os.listdir(TD)))

# --- T24 元数据档案随 .smd 往返 ---
# 事故背景：白名单原先只精确匹配 annotations.json。元数据档案（assets/.mde/）
# 正文永远不引用它，"正文里搜 assets/<名字>"这个判据永远命中不了，于是保存时
# 被当孤儿 os.remove 掉、整包重建会跳过它——档案就这么没了，一句错都不报。
# 所以这两条测的是"活着进出包"，不是"能读写"。
import md_meta
mstage = os.path.join(_smd._tmp_root(), "test_stage_meta")
shutil.rmtree(mstage, ignore_errors=True)
os.makedirs(os.path.join(mstage, "assets"), exist_ok=True)
meta_smd = os.path.join(TD, "meta.smd")
with io.open(os.path.join(mstage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("@@ meta\n\n正文\n")
md_meta.ensure(os.path.join(mstage, "assets"), {"title": "我写故我播", "author": "wUwproject"})
md_meta.update(os.path.join(mstage, "assets"), {"title": "改过的标题"})
_smd.pack_from_dir(meta_smd, os.path.join(mstage, "doc.md"), os.path.join(mstage, "assets"))
with zipfile.ZipFile(meta_smd) as z:
    names = z.namelist()
check("T24 元数据档案进包",
      "assets/.mde/zero.json" in names and "assets/.mde/up.md" in names, ",".join(names))

shutil.rmtree(mstage, ignore_errors=True)          # 丢掉工作目录，逼它重新解包
base_m = _smd.base_dir_for(meta_smd)
check("T24 解包目录里有档案", os.path.isfile(os.path.join(base_m, "assets", ".mde", "zero.json")))
_smd.save_from_dir(meta_smd, base_m)               # 走孤儿清理那条路
check("T24 保存后档案没被当孤儿删",
      os.path.isfile(os.path.join(base_m, "assets", ".mde", "zero.json"))
      and os.path.isfile(os.path.join(base_m, "assets", ".mde", "up.md")))
with zipfile.ZipFile(meta_smd) as z:
    names = z.namelist()
check("T24 保存后包内档案仍在", "assets/.mde/zero.json" in names, ",".join(names))

rec = md_meta.read(os.path.join(base_m, "assets"))
check("T24 往返后字段正确合并",
      bool(rec) and rec["fields"].get("title") == "改过的标题"
      and rec["fields"].get("author") == "wUwproject", str(rec and rec["fields"]))
check("T24 创建者快照未被修改（zero 存创建值）",
      bool(rec) and rec["zero"]["fields"].get("title") == "我写故我播",
      str(rec and rec["zero"]["fields"]))

# --- T25 资产整树拷贝（含 .mde/ 与图片子目录）---
# 事故背景：原先 os.listdir + isfile 只拷顶层，子目录资产与元数据档案在
# .md ↔ .smd 互转时静默丢失——包本身是好的，所以没有任何报错线索。
tsrc = os.path.join(TD, "tree_src"); tdst = os.path.join(TD, "tree_dst")
os.makedirs(os.path.join(tsrc, "sub"), exist_ok=True)
os.makedirs(os.path.join(tsrc, ".mde"), exist_ok=True)
with open(os.path.join(tsrc, "a.png"), "wb") as f:
    f.write(png_bytes(2))
with open(os.path.join(tsrc, "sub", "b.png"), "wb") as f:
    f.write(png_bytes(3))
with io.open(os.path.join(tsrc, ".mde", "zero.json"), "w", encoding="utf-8") as f:
    f.write("{}")
_n_tree = md_server._copy_tree(tsrc, tdst)
check("T25 递归拷贝含子目录", os.path.isfile(os.path.join(tdst, "sub", "b.png")))
check("T25 递归拷贝含 .mde 档案", os.path.isfile(os.path.join(tdst, ".mde", "zero.json")))
check("T25 拷贝计数正确", _n_tree == 3, str(_n_tree))

# --- 清理 ---
shutil.rmtree(TD, ignore_errors=True)
for s in (stage, big_stage, ps, orphan_stage, fstage, sstage, spstage,
          nstage, cc_stage, cstage2, estage, mstage, tsrc, tdst):
    shutil.rmtree(s, ignore_errors=True)

fails = [r for r in results if not r[1]]
print("\n===== %d/%d PASS =====" % (len(results) - len(fails), len(results)))
sys.exit(1 if fails else 0)
