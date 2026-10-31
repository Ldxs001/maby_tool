# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""元数据档案只读位与解包缓存（v2.24.1）：PASS/FAIL 二元输出。

事故背景：`.smd` 的档案目录就是解包临时目录，`ensure()` 无差别把 zero.json
锁成只读+隐藏；会话结束 rmtree 删不掉只读文件、`ignore_errors` 静默吞掉，
留下残骸；下次解包往只读同名文件写 -> PermissionError -> 前端看到 HTTP 500。

本文件钉住四条契约：
  1. 解包目录里的副本**永不只读**（只读只给磁盘上的真档案）
  2. 真档案仍然只读+隐藏（防手滑）
  3. 删除一律走 `_force_rmtree`，只读残留也必须清干净
  4. 解包遇到只读同名文件不炸（逐条目写，写前解位）
"""
import os
import sys
import io
import shutil
import zipfile
import ctypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _smd
import md_meta

HERE = os.path.dirname(os.path.abspath(__file__))
TD = os.path.join(HERE, "runtime", "_smd_zero_test")
results = []

RO, HI = 0x01, 0x02


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print("%s  %s%s" % ("PASS" if cond else "FAIL", name, ("  [" + detail + "]") if detail else ""))


def attrs(p):
    return ctypes.windll.kernel32.GetFileAttributesW(str(p))


def is_ro(p):
    a = attrs(p)
    return a != 0xFFFFFFFF and bool(a & RO)


def is_hidden(p):
    a = attrs(p)
    return a != 0xFFFFFFFF and bool(a & HI)


def png_bytes(color, n=512):
    return b"\x89PNG\r\n\x1a\n" + bytes([color]) * n


def mk_smd(path, doc, assets=None):
    stage = os.path.join(TD, "_stage_" + os.path.basename(path))
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(os.path.join(stage, "assets"), exist_ok=True)
    with io.open(os.path.join(stage, "doc.md"), "w", encoding="utf-8", newline="") as f:
        f.write(doc)
    for nm, data in (assets or {}).items():
        with open(os.path.join(stage, "assets", nm), "wb") as f:
            f.write(data)
    _smd.pack_from_dir(path, os.path.join(stage, "doc.md"), os.path.join(stage, "assets"))
    return stage


shutil.rmtree(TD, ignore_errors=True)
os.makedirs(TD, exist_ok=True)

# ---------------------------------------------------------------------------
# A. .smd 副本不锁；真档案仍锁
# ---------------------------------------------------------------------------
smd_a = os.path.join(TD, "a.smd")
mk_smd(smd_a, "# 甲\n\n![p](assets/p.png)\n", {"p.png": png_bytes(1)})
base_a = _smd.base_dir_for(smd_a)
adir_a = os.path.join(base_a, _smd.ASSETS_DIR)
rec, new = md_meta.ensure(adir_a, {"author": "wUwproject"}, lock=False)
zp_a = os.path.join(md_meta.meta_dir(adir_a), md_meta.ZERO_NAME)
check("A1 首次建档成功", new and rec is not None)
check("A2 解包副本不是只读", not is_ro(zp_a), "attr=%s" % hex(attrs(zp_a)))
check("A3 解包副本不是隐藏", not is_hidden(zp_a), "attr=%s" % hex(attrs(zp_a)))
check("A4 副本内容正确", '"author": "wUwproject"' in io.open(zp_a, encoding="utf-8").read())

# .md 的真档案：仍要锁
md_a = os.path.join(TD, "b.md")
adir_b = os.path.join(TD, "b.assets")
os.makedirs(adir_b, exist_ok=True)
md_meta.ensure(adir_b, {"author": "wUwproject"}, lock=True)
zp_b = os.path.join(md_meta.meta_dir(adir_b), md_meta.ZERO_NAME)
check("A5 真档案仍是只读", is_ro(zp_b), "attr=%s" % hex(attrs(zp_b)))
check("A6 真档案仍是隐藏", is_hidden(zp_b), "attr=%s" % hex(attrs(zp_b)))
check("A7 真档案可正常读", md_meta.read(adir_b)["fields"]["author"] == "wUwproject")

# 老副本已被锁过 -> ensure(lock=False) 顺带解开
ctypes.windll.kernel32.SetFileAttributesW(zp_a, attrs(zp_a) | RO | HI)
check("A8 构造只读副本", is_ro(zp_a))
md_meta.ensure(adir_a, {"author": "wUwproject"}, lock=False)
check("A9 再次 ensure 解开老副本", not is_ro(zp_a) and not is_hidden(zp_a),
      "attr=%s" % hex(attrs(zp_a)))

# ---------------------------------------------------------------------------
# B. 删除：只读残留必须清干净
# ---------------------------------------------------------------------------
victim = os.path.join(TD, "_victim")
os.makedirs(os.path.join(victim, "sub"), exist_ok=True)
for nm in ("zero.json", "sub/x.png"):
    fp = os.path.join(victim, nm)
    with open(fp, "w") as f:
        f.write("x")
    # 注意先清掉 FILE_ATTRIBUTE_NORMAL(0x80)：它与任何其它位组合都是非法值，
    # 直接 or 上去会让 SetFileAttributesW 整体失败，阳性对照就假通过了。
    ctypes.windll.kernel32.SetFileAttributesW(fp, (attrs(fp) & ~0x80) | RO | HI)
# 注意：这里不做「裸 rmtree 删不掉只读文件」的阴性对照。实测该行为随 Python
# 版本与目录不同而摇摆（3.11 与部分目录会残留、3.14 与另一些目录能删），拿它
# 当断言只会得到一个环境相关的假阳性。真正要钉住的是「先解位再删」这个动作。
check("B1 真档案起始是只读", bool(attrs(zp_b) & RO), "attr=%s" % hex(attrs(zp_b)))
_smd._clear_attrs(zp_b)
check("B2 _clear_attrs 能解位", not is_ro(zp_b) and not is_hidden(zp_b),
      "attr=%s" % hex(attrs(zp_b)))
ctypes.windll.kernel32.SetFileAttributesW(zp_b, 0x23)    # 还原真档案的锁
check("B3 _force_rmtree 清掉只读残留", _smd._force_rmtree(victim) and not os.path.exists(victim))

# ---------------------------------------------------------------------------
# C. 解包撞只读同名文件不炸
# ---------------------------------------------------------------------------
smd_c = os.path.join(TD, "c.smd")
mk_smd(smd_c, "# 丙\n\n正文\n")
base_c = _smd.base_dir_for(smd_c)
# 人为把解包目录里的 doc.md 锁成只读，并删掉指纹 -> 触发重解包
doc_c = os.path.join(base_c, _smd.DOC_NAME)
ctypes.windll.kernel32.SetFileAttributesW(doc_c, attrs(doc_c) | RO | HI)
os.remove(os.path.join(base_c, ".source.json"))
try:
    base_c2 = _smd.base_dir_for(smd_c)
    ok_c = io.open(os.path.join(base_c2, _smd.DOC_NAME), encoding="utf-8").read().startswith("# 丙")
    err_c = ""
except Exception as e:
    ok_c, err_c = False, "%s: %s" % (type(e).__name__, e)
check("C1 重解包遇到只读文件不抛", ok_c, err_c)

# ---------------------------------------------------------------------------
# D. 端到端：建档 -> 保存 -> 清缓存 -> 再打开
# ---------------------------------------------------------------------------
smd_d = os.path.join(TD, "d.smd")
stage_d = mk_smd(smd_d, "# 丁\n\n正文一\n")
base_d = _smd.base_dir_for(smd_d)
adir_d = os.path.join(base_d, _smd.ASSETS_DIR)
md_meta.ensure(adir_d, {"author": "wUwproject"}, lock=False)
_smd.save_from_dir(smd_d, base_d)
check("D1 档案已进包",
      "assets/.mde/zero.json" in zipfile.ZipFile(smd_d).namelist())
_smd.clear_tmp()
check("D2 clear_tmp 后临时目录真的没了", not os.path.exists(_smd._tmp_root()),
      _smd._tmp_root())
try:
    base_d2 = _smd.base_dir_for(smd_d)
    ok_d = os.path.isfile(os.path.join(base_d2, _smd.DOC_NAME))
    err_d = ""
except Exception as e:
    ok_d, err_d = False, "%s: %s" % (type(e).__name__, e)
check("D3 清缓存后重新打开成功", ok_d, err_d)
check("D4 重开后档案仍读得到",
      (md_meta.read(os.path.join(base_d2, _smd.ASSETS_DIR)) or {}).get("fields", {}).get("author")
      == "wUwproject")

# ---------------------------------------------------------------------------
# E. 包内条目权限位不含只读
# ---------------------------------------------------------------------------
with zipfile.ZipFile(smd_d) as z:
    zi = z.getinfo("assets/.mde/zero.json")
    mode = zi.external_attr >> 16
check("E1 包内档案条目权限不是 0444", not (mode & 0o200) == 0, "mode=%s" % oct(mode))
check("E2 包内档案条目为 0644", mode == 0o644, "mode=%s" % oct(mode))

# 收尾：清干净（含 _force_rmtree 对只读路径的验证）
_smd.clear_tmp()
shutil.rmtree(TD, ignore_errors=True)

ok = sum(1 for _n, c, _d in results if c)
bad = len(results) - ok
print("\n==== %d/%d PASS ====" % (ok, len(results)))
if bad:
    print("FAILED:")
    for n, c, d in results:
        if not c:
            print("  - %s  [%s]" % (n, d))
sys.exit(0 if bad == 0 else 1)
