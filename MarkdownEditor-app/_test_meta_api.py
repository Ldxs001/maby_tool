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

# ---------- C. sync：v2.26.3 保存时的统一入口 ----------
# 「应用」只改设置，「保存」才落档案；档案写操作全走 sync，前端不需要知道
# ensure / update 的先后。两种建档来历必须能区分。
md2 = os.path.join(TD, "someone_else.md")
with io.open(md2, "w", encoding="utf-8") as f:
    f.write("# 别人的文章\n\n接手时已经有内容\n")

# C1-C3 接手别人的文件：创建时间写 none（不猜），只补 default 与「谁开始留痕」
j9 = post("/api/meta", {"path": md2, "action": "sync", "created": "none",
                        "baseline": {}, "fields": {}, "who": "Ldxs"})
m9 = j9.get("meta") or {}
ck("C1 接手别人的文件 created=none", j9.get("ok") and m9.get("created") == "none",
   m9.get("created"))
ck("C2 补作者 default 并记下当前留痕人", m9.get("authors") == ["default", "Ldxs"],
   m9.get("authors"))
ck("C3 不把本机面板的标题/标签灌进别人的文档",
   not (m9.get("fields") or {}).get("tags") and not (m9.get("fields") or {}).get("title"),
   m9.get("fields"))

# C4-C6 本次会话新建：创建时间就是现在，面板值是创建者快照
md3 = os.path.join(TD, "mine.md")
with io.open(md3, "w", encoding="utf-8") as f:
    f.write("@@ meta\n\n我写的新文章\n")
j10 = post("/api/meta", {"path": md3, "action": "sync", "who": "Ldxs",
                         "baseline": {"title": "我的新文章", "author": "Ldxs"},
                         "fields": {}})
m10 = j10.get("meta") or {}
ck("C4 本次新建 created 写真实时间", (m10.get("created") or "")[:4] == "2026",
   m10.get("created"))
ck("C5 面板值成为创建者快照", (m10.get("fields") or {}).get("title") == "我的新文章",
   m10.get("fields"))

# C6 幂等：没有改动就一条都不写，zero 也不动
j11 = post("/api/meta", {"path": md3, "action": "sync", "who": "Ldxs", "fields": {}})
ck("C6 无改动不刷履历", j11.get("changed") == 0 and
   (j11.get("meta") or {}).get("created") == m10.get("created"),
   j11.get("changed"))

# C7 有改动才进 up，作者链按时间序累积
j12 = post("/api/meta", {"path": md3, "action": "sync", "who": "张三",
                         "fields": {"title": "改过的标题"}})
m12 = j12.get("meta") or {}
ck("C7 改动记 1 条并累积作者链",
   j12.get("changed") == 1 and m12.get("authors") == ["Ldxs", "张三"] and
   (m12.get("fields") or {}).get("title") == "改过的标题",
   (j12.get("changed"), m12.get("authors"), m12.get("fields")))

# C8 touch=true：字段没变也留一条「保存」——up 是忠实追加的流水账，
#    写不写由 touch 决定、不由 diff 决定（2026-11-01 定）
j13 = post("/api/meta", {"path": md3, "action": "sync", "who": "张三",
                         "fields": {"title": "改过的标题"}, "touch": True})
m13 = j13.get("meta") or {}
ck("C8 touch=true：字段没变也追加一条「保存」，changed 仍为 0",
   j13.get("ok") and j13.get("changed") == 0 and
   (m13.get("up") or [{}])[-1].get("note") == "保存" and bool(m13.get("last")),
   (j13.get("changed"), (m13.get("up") or [])[-1:]))

# C9 touch 缺省：老调用方语义不变，无改动一条都不写
j14 = post("/api/meta", {"path": md3, "action": "sync", "who": "张三",
                         "fields": {"title": "改过的标题"}})
m14 = j14.get("meta") or {}
ck("C9 touch 缺省：无改动一条不写（老语义，不破坏既存调用）",
   j14.get("changed") == 0 and
   len(m14.get("up") or []) == len(m13.get("up") or []),
   (len(m14.get("up") or []), len(m13.get("up") or [])))

# C10-C13 SM3 内容指纹（v2.26.3）：服务端从磁盘算，前端不参与
with io.open(md3, "r", encoding="utf-8") as _f:
    _body = _f.read()
_up_md = os.path.join(TD, "mine.assets", ".mde", "up.md")
j15 = post("/api/meta", {"path": md3, "action": "sync", "who": "张三",
                         "touch": True, "content": _body})
m15 = j15.get("meta") or {}
ck("C10 sync 带正文：返回 64 位指纹且写进 up.md 原文",
   len(m15.get("hash") or "") == 64 and
   ("sm3:" + m15["hash"]) in io.open(_up_md, encoding="utf-8").read(),
   (m15.get("hash") or "")[:16])

_n = len(m15.get("up") or [])
j16 = post("/api/meta", {"path": md3, "action": "sync", "who": "张三",
                         "touch": True, "content": _body})
m16 = j16.get("meta") or {}
ck("C11 同内容重复保存不追加（内容没变，最近修改不该往前走）",
   len(m16.get("up") or []) == _n,
   (len(m16.get("up") or []), _n))

_body2 = _body + "\n新增一段\n"
with io.open(md3, "w", encoding="utf-8") as f:
    f.write(_body2)
j17 = post("/api/meta", {"path": md3, "action": "sync", "who": "张三",
                         "touch": True, "content": _body2})
m17 = j17.get("meta") or {}
ck("C12 内容变了：追加一条且指纹换新",
   len(m17.get("up") or []) == _n + 1 and m17.get("hash") != m15.get("hash"),
   (len(m17.get("up") or []), _n + 1))

j18 = post("/api/meta", {"path": md3, "action": "read"})
m18 = j18.get("meta") or {}
ck("C12b read 带回 stale 且盘上一致时为 False",
   m18.get("stale") is False, m18.get("stale"))

with io.open(md3, "w", encoding="utf-8") as f:
    f.write(_body)                      # 模拟被外部改回旧版
j19 = post("/api/meta", {"path": md3, "action": "read"})
ck("C13 盘上正文与末条指纹不符：stale=True（未记录改动可见）",
   (j19.get("meta") or {}).get("stale") is True,
   (j19.get("meta") or {}).get("stale"))

print("\n===== %d 项，FAIL %d =====" % (35, len(fails)))
sys.exit(1 if fails else 0)
