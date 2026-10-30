# -*- coding: utf-8 -*-
"""_test_meta_api.py -- /api/meta 端到端（真服务）

覆盖建档、字段合并、只读与隐藏属性、.smd 行李往返。
**前置条件**：本机已有 md_server 在跑（python md_server.py，默认 18766 端口；脚本自动探测 18766 / 18799）。
用法：python _test_meta_api.py
"""
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

# 端口自探测：服务端默认 18766，历史脚本用过 18799，哪个通就用哪个。
BASE = None
for _port in (18766, 18799):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/" % _port, timeout=2).read(64)
        BASE = "http://127.0.0.1:%d" % _port
        break
    except Exception:
        pass
if BASE is None:
    print("FAIL  18766 / 18799 都没有 md_server 在跑（先 python md_server.py）")
    sys.exit(1)
HERE = os.path.dirname(os.path.abspath(__file__))
APPDIR = HERE
sys.path.insert(0, APPDIR)
import _smd

TD = os.path.join(APPDIR, "Temp", "_e2e_meta")
shutil.rmtree(TD, ignore_errors=True)
os.makedirs(TD, exist_ok=True)
fails = []


def post(path, obj):
    req = urllib.request.Request(BASE + path, method="POST",
                                 data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def ck(name, cond, detail=""):
    print(("%s  %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  [" + str(detail) + "]") if detail else "")))
    if not cond:
        fails.append(name)


# ---------- A. 普通 .md ----------
md = os.path.join(TD, "t.md")
with io.open(md, "w", encoding="utf-8") as f:
    f.write("@@ meta\n\n正文第一段\n")

j = post("/api/meta", {"path": md, "action": "ensure",
                       "fields": {"title": "我写故我播", "author": "wUwproject"}})
ck("A1 ensure 建档成功", j.get("ok") and j.get("meta"), j)
adir = os.path.join(TD, "t.assets")
ck("A2 档案目录建出来了", os.path.isdir(os.path.join(adir, ".mde")))
ck("A3 zero.json 存在", os.path.isfile(os.path.join(adir, ".mde", "zero.json")))
ck("A4 up.md 存在", os.path.isfile(os.path.join(adir, ".mde", "up.md")))

j2 = post("/api/meta", {"path": md, "action": "read"})
ck("A5 read 返回合并后的字段", j2.get("meta", {}).get("fields", {}).get("title") == "我写故我播", j2)

j3 = post("/api/meta", {"path": md, "action": "update", "fields": {"title": "改过了"}})
ck("A6 update 记了 1 条变更", j3.get("changed") == 1, j3.get("changed"))
ck("A7 合并后取新值", j3.get("meta", {}).get("fields", {}).get("title") == "改过了",
   j3.get("meta", {}).get("fields"))
ck("A8 zero 仍存创建值", j3.get("meta", {}).get("zero", {}).get("fields", {}).get("title") == "我写故我播")

j4 = post("/api/meta", {"path": md, "action": "update", "fields": {"title": "改过了"}})
ck("A9 重复提交同样的值 → 0 条变更（不刷履历）", j4.get("changed") == 0, j4.get("changed"))

j5 = post("/api/meta", {"path": md, "action": "ensure", "fields": {"title": "不该生效"}})
ck("A10 再次 ensure 不覆盖创建者快照",
   j5.get("meta", {}).get("zero", {}).get("fields", {}).get("title") == "我写故我播")

js = post("/api/file", {"path": md, "content": "@@ meta\n\n正文第一段\n"})
ck("A11 保存响应带回 meta", js.get("ok") and js.get("meta"), list(js.keys()))
ck("A12 保存后字段仍在", js.get("meta", {}).get("fields", {}).get("title") == "改过了")

if os.name == "nt":
    import ctypes
    k32 = ctypes.windll.kernel32
    zp = os.path.join(adir, ".mde", "zero.json")
    a = k32.GetFileAttributesW(zp)
    ck("A13 zero.json 带只读位", bool(a & 0x1) and a != 0xFFFFFFFF, hex(a))
    ck("A14 zero.json 带隐藏位", bool(a & 0x2), hex(a))
    d = k32.GetFileAttributesW(os.path.join(adir, ".mde"))
    ck("A15 .mde 目录隐藏", bool(d & 0x2), hex(d))

# ---------- B. .smd 包内 ----------
stage = os.path.join(TD, "_stage")
os.makedirs(os.path.join(stage, "assets"), exist_ok=True)
with io.open(os.path.join(stage, "doc.md"), "w", encoding="utf-8") as f:
    f.write("@@ meta\n\n包内正文\n")
smd = os.path.join(TD, "t.smd")
_smd.pack_from_dir(smd, os.path.join(stage, "doc.md"), os.path.join(stage, "assets"))

j6 = post("/api/meta", {"path": smd, "action": "ensure", "fields": {"title": "包内元数据"}})
ck("B1 .smd ensure 成功", j6.get("ok") and j6.get("meta"), j6)
with zipfile.ZipFile(smd) as z:
    names = z.namelist()
ck("B2 档案立即进包（不等下次保存）",
   "assets/.mde/zero.json" in names, ",".join(names))

j7 = post("/api/meta", {"path": smd, "action": "update", "fields": {"author": "包内作者"}})
with zipfile.ZipFile(smd) as z:
    up = z.read("assets/.mde/up.md").decode("utf-8")
ck("B3 up 追加内容也进包", "包内作者" in up, up.replace("\n", " | ")[:120])

j8 = post("/api/meta", {"path": smd, "action": "read"})
ck("B4 从包里读回合并字段",
   j8.get("meta", {}).get("fields", {}).get("author") == "包内作者", j8.get("meta", {}).get("fields"))

# 保存正文一次，确认档案没被孤儿清理干掉
js2 = post("/api/file", {"path": smd, "content": "@@ meta\n\n包内正文\n"})
with zipfile.ZipFile(smd) as z:
    names = z.namelist()
ck("B5 保存正文后档案仍在包内",
   "assets/.mde/zero.json" in names and "assets/.mde/up.md" in names, ",".join(names))
ck("B6 保存响应带回 meta", bool(js2.get("meta")), list(js2.keys()))

print("\n===== %d 项，FAIL %d =====" % (23, len(fails)))
sys.exit(1 if fails else 0)
