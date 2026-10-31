# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_smd 历史版本与打开时资产回收（v2.24.0）：PASS/FAIL 二元输出。

覆盖：历史条目生成、无改动不刷版本、可配置保留份数与裁剪、回滚语义、
时间戳跨重建保持、并集回收（当前 + 历史）、保存不删资产、反斜杠引用、
`.mde/*` 豁免、无孤儿时零写入。
"""
import os
import sys
import io
import shutil
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _smd

HERE = os.path.dirname(os.path.abspath(__file__))
TD = os.path.join(HERE, "runtime", "_smd_hist_test")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print("%s  %s%s" % ("PASS" if cond else "FAIL", name, ("  [" + detail + "]") if detail else ""))


def png_bytes(color, n=1024):
    return b"\x89PNG\r\n\x1a\n" + bytes([color]) * n


def fresh(name):
    """建一个干净的解包目录 + 目标包路径。"""
    stage = os.path.join(_smd._tmp_root(), "test_hist_" + name)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(os.path.join(stage, "assets"), exist_ok=True)
    return os.path.join(TD, name + ".smd"), stage


def write_doc(stage, text):
    _smd.write_doc(stage, text)


def put_asset(stage, rel, data=None):
    fp = os.path.join(stage, "assets", rel)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "wb") as f:
        f.write(data if data is not None else png_bytes(1))
    return fp


def pkg_names(path):
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def pkg_doc(path):
    with zipfile.ZipFile(path) as z:
        return z.read(_smd.DOC_NAME).decode("utf-8")


shutil.rmtree(TD, ignore_errors=True)
os.makedirs(TD, exist_ok=True)
_smd.set_hist_keep(30)

# --- A 历史生成 ---
smd, stage = fresh("a")
write_doc(stage, "A0")
put_asset(stage, "a.png")
_smd.pack_from_dir(smd, os.path.join(stage, _smd.DOC_NAME),
                   os.path.join(stage, "assets"))
check("A1 新建包无历史", _smd.list_history(smd) == [])

for i in (1, 2, 3):
    write_doc(stage, "A%d\n\n![a](assets/a.png)\n" % i)
    _smd.save_from_dir(smd, stage)
h = _smd.list_history(smd)
check("A2 三次保存三条历史", len(h) == 3, "%d" % len(h))
check("A3 序号与顺序（最新在前）", [x["seq"] for x in h] == [3, 2, 1],
      ",".join(str(x["seq"]) for x in h))
check("A4 最新一条 = 上一版正文", _smd.read_history(smd, 3).startswith("A2"),
      _smd.read_history(smd, 3)[:8])
check("A5 最早一条 = 初版", _smd.read_history(smd, 1) == "A0")
check("A6 标题与字数现算", h[0]["title"] == "A2" and h[0]["words"] > 3,
      "%s/%d" % (h[0]["title"], h[0]["words"]))

# --- B 无改动保存不刷版本 ---
n, compacted = _smd.save_from_dir(smd, stage)
check("B1 无改动保存零追加", (n, compacted) == (0, False), "%r" % ((n, compacted),))
check("B2 历史条数不变", len(_smd.list_history(smd)) == 3)

# --- C 可配置保留份数 + 裁剪 ---
_smd.set_hist_keep(5)
check("C1 上限按 4/3 同比例", (_smd.hist_keep(), _smd.hist_cap()) == (5, 7),
      "%d/%d" % (_smd.hist_keep(), _smd.hist_cap()))
smd_c, stage_c = fresh("c")
write_doc(stage_c, "B0")
_smd.pack_from_dir(smd_c, os.path.join(stage_c, _smd.DOC_NAME),
                   os.path.join(stage_c, "assets"))
for i in range(1, 10):
    write_doc(stage_c, "B%d" % i)
    _smd.save_from_dir(smd_c, stage_c)
hc = _smd.list_history(smd_c)
check("C2 裁到保留份数", len(hc) == 5, "%d" % len(hc))
check("C3 留的是最新 5 条", [x["seq"] for x in hc] == [9, 8, 7, 6, 5],
      ",".join(str(x["seq"]) for x in hc))
check("C4 包内条目数与列表一致",
      len([n for n in pkg_names(smd_c) if n.startswith("history/")]) == 5)
check("C5 最新历史内容正确", _smd.read_history(smd_c, 9) == "B8")

_smd.set_hist_keep(30)

# --- D 回滚语义 ---
cur_before = pkg_doc(smd)
target_text = _smd.read_history(smd, 2)
r = _smd.restore_history(smd, stage, 2)
check("D1 内容回到选中版本", r["content"] == target_text and pkg_doc(smd) == target_text,
      r["content"][:8])
with open(os.path.join(stage, _smd.DOC_NAME), encoding="utf-8") as f:
    check("D2 工作目录正文同步", f.read() == target_text)
hd = _smd.list_history(smd)
check("D3 选中条目移出、总数不变", [x["seq"] for x in hd] == [4, 3, 1],
      ",".join(str(x["seq"]) for x in hd))
check("D4 原当前内容成为最新历史", _smd.read_history(smd, 4) == cur_before,
      _smd.read_history(smd, 4)[:8])
write_doc(stage, "A9")
check("D5 回滚后可继续保存", _smd.save_from_dir(smd, stage)[0] >= 1)

# --- E 并集回收 ---
smd_e, stage_e = fresh("e")
write_doc(stage_e, "E1 a b c\n\n![a](assets/a.png) ![b](assets/b.png) ![c](assets/c.png)\n")
for nm in ("a.png", "b.png", "c.png"):
    put_asset(stage_e, nm, png_bytes(ord(nm[0])))
_smd.pack_from_dir(smd_e, os.path.join(stage_e, _smd.DOC_NAME),
                   os.path.join(stage_e, "assets"))
write_doc(stage_e, "E2 a only\n\n![a](assets/a.png)\n")
_smd.save_from_dir(smd_e, stage_e)            # history/0001 = E1（引用 b、c）
m1 = _smd.maintain(smd_e, stage_e)
check("E1 历史仍引用的图不删", m1["cleaned"] == 0 and m1["trimmed"] == 0, str(m1))
check("E2 三张图都在包里",
      all(("assets/" + n) in pkg_names(smd_e) for n in ("a.png", "b.png", "c.png")))
write_doc(stage_e, "E3 a only\n\n![a](assets/a.png)\n")
_smd.save_from_dir(smd_e, stage_e)            # history/0002 = E2（只引用 a）
_smd.set_hist_keep(1)
m2 = _smd.maintain(smd_e, stage_e)
check("E3 裁掉旧版后其独占图被回收", (m2["trimmed"], m2["cleaned"]) == (1, 2), str(m2))
names_e = pkg_names(smd_e)
check("E4 包里只剩被引用的图",
      "assets/a.png" in names_e and "assets/b.png" not in names_e
      and "assets/c.png" not in names_e)
check("E5 目录里也删干净",
      os.path.isfile(os.path.join(stage_e, "assets", "a.png"))
      and not os.path.exists(os.path.join(stage_e, "assets", "b.png")))
_smd.set_hist_keep(30)

# --- F 保存不删资产 ---
smd_f, stage_f = fresh("f")
write_doc(stage_f, "F1\n\n![a](assets/a.png)\n")
put_asset(stage_f, "a.png")
stray = put_asset(stage_f, "stray.png", png_bytes(9, 4096))
_smd.pack_from_dir(smd_f, os.path.join(stage_f, _smd.DOC_NAME),
                   os.path.join(stage_f, "assets"))
_smd._append_entries(smd_f, [("assets/stray.png", stray)])   # 旧包里的孤儿 entry
write_doc(stage_f, "F2\n\n![a](assets/a.png)\n")
_smd.save_from_dir(smd_f, stage_f)
check("F1 保存不删未引用资产", os.path.isfile(stray))
check("F2 保存不把孤儿打出包", "assets/stray.png" in pkg_names(smd_f))
m3 = _smd.maintain(smd_f, stage_f)
check("F3 打开时才回收", m3["cleaned"] == 1 and not os.path.exists(stray), str(m3))
check("F4 回收后包内条目消失", "assets/stray.png" not in pkg_names(smd_f))

# --- G 反斜杠绝对路径引用不误删 ---
smd_g, stage_g = fresh("g")
put_asset(stage_g, "p.png", png_bytes(7, 2048))
write_doc(stage_g, "G1\n\n见 C:\\Users\\me\\doc.assets\\p.png\n")
_smd.pack_from_dir(smd_g, os.path.join(stage_g, _smd.DOC_NAME),
                   os.path.join(stage_g, "assets"))
check("G1 打包按反斜杠形态也认引用", "assets/p.png" in pkg_names(smd_g))
m4 = _smd.maintain(smd_g, stage_g)
check("G2 打开时不误删", m4["cleaned"] == 0
      and os.path.isfile(os.path.join(stage_g, "assets", "p.png")), str(m4))

# --- H 元数据档案豁免 ---
smd_h, stage_h = fresh("h")
write_doc(stage_h, "H1\n")
mde = os.path.join(stage_h, "assets", ".mde")
os.makedirs(mde, exist_ok=True)
with io.open(os.path.join(mde, "zero.json"), "w", encoding="utf-8") as f:
    f.write('{"fields": {"author": "wUwproject"}}')
_smd.pack_from_dir(smd_h, os.path.join(stage_h, _smd.DOC_NAME),
                   os.path.join(stage_h, "assets"))
m5 = _smd.maintain(smd_h, stage_h)
check("H1 .mde 不被当孤儿", m5["cleaned"] == 0
      and os.path.isfile(os.path.join(mde, "zero.json")), str(m5))

# --- I 无孤儿零写入 ---
before = os.stat(smd_h).st_mtime_ns
m6 = _smd.maintain(smd_h, stage_h)
check("I1 无孤儿不重写包", m6 == {"cleaned": 0, "bytes": 0, "trimmed": 0}
      and os.stat(smd_h).st_mtime_ns == before, str(m6))

# --- J 时间戳跨重建保持 ---
smd_j, stage_j = fresh("j")
write_doc(stage_j, "J0\n")
_smd.pack_from_dir(smd_j, os.path.join(stage_j, _smd.DOC_NAME),
                   os.path.join(stage_j, "assets"))
write_doc(stage_j, "J1\n")
_smd.save_from_dir(smd_j, stage_j)
t_before = _smd._hist_times(smd_j)
_smd.compact(smd_j, stage_j)
check("J1 重建不改历史时间", _smd._hist_times(smd_j) == t_before,
      "%r -> %r" % (t_before, _smd._hist_times(smd_j)))

# --- 汇总 ---
ok = sum(1 for _n, c, _d in results if c)
bad = len(results) - ok
print("\n==== %d/%d PASS ====" % (ok, len(results)))
if bad:
    print("FAILED:")
    for n, c, d in results:
        if not c:
            print("  - %s  [%s]" % (n, d))
sys.exit(0 if bad == 0 else 1)
