# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_test_metadata.py -- v2.23.0 元数据通道验收

分五组：
  A. front matter 四判据（T01-T06）
  B. @@ meta 自有模式（T07-T12）
  C. 诊断码（T13-T14）
  D. 回归：无元数据文档渲染逐字节不变（T15）——阳性对照用改前的 md-parser.js
  E. 导出剔除（T16-T19）——交给 _test_export_strip.cjs 跑，本文件汇总

D 组是本文件的核心：存量 1287 份文档一份都不能变。做法是把改前备份的解析器
（Temp/_bak_meta_20261030/md-parser.js）和改后的解析器分别渲染同一批真实文档，
逐字节比对。构造样本也一并比对——它们覆盖了文首 ---／正文中 --- 这些最容易
被新前置逻辑误伤的形态。

E 组验证元数据区不会漏进导出产物：docx/paged 整块删除，HTML 导出把兼容模式的
front matter 还原成原文放回文件头（不渲染）。该函数只依赖少量 DOM API，用最小
桩驱动，函数体从 markdown-editor.html 现场抽取——测的是真代码，不是副本。

用法：python _test_metadata.py
"""
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARSER_NEW = os.path.join(HERE, "md-parser.js")
PARSER_OLD = os.path.join(HERE, "Temp", "_bak_meta_20261030", "md-parser.js")

RUNNER = r"""
const path=process.argv[process.argv.length-1];
const {parseMarkdown}=require(path);
let buf="";
process.stdin.setEncoding("utf8");
process.stdin.on("data",d=>buf+=d);
process.stdin.on("end",()=>{
  let cases=[];
  try{ cases=JSON.parse(buf); }catch(e){ process.stdout.write("__BADJSON__"); return; }
  const out=[];
  for(const c of cases){
    global.window=c.window||{};
    let html="",diag=[];
    try{
      if(c.diag) html=parseMarkdown(c.src,0,{diag:diag});
      else html=parseMarkdown(c.src);
    }catch(e){ html="__ERR__"+e.message; }
    out.push({html:html,diag:diag});
  }
  process.stdout.write(JSON.stringify(out));
});
"""


def run(parser, cases):
    p = subprocess.run(["node", "-e", RUNNER, parser],
                       input=json.dumps(cases, ensure_ascii=False).encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("node 失败：%s" % p.stderr.decode("utf-8", "replace")[:800])
    txt = p.stdout.decode("utf-8")
    if txt == "__BADJSON__":
        raise RuntimeError("用例 JSON 传输失败")
    return json.loads(txt)


FAILED = []
COUNT = [0]   # 已执行条数（E 组条数由子进程决定，不能写死总表）


def ck(name, cond, detail=""):
    COUNT[0] += 1
    if cond:
        print("PASS  " + name)
    else:
        print("FAIL  " + name + (("  ← " + detail) if detail else ""))
        FAILED.append(name)


def has(s, *parts):
    return all(p in s for p in parts)


def none(s, *parts):
    return all(p not in s for p in parts)


# ---------------------------------------------------------------------------
# A 组 · front matter 四判据
# ---------------------------------------------------------------------------
FM_OK = "---\ntitle: 我写故我播\nauthor: \"wUwproject\"\n---\n\n正文第一段"
FM_BLANK = "---\ntitle: x\n\nauthor: y\n---\n正文"
FM_NOKV = "---\n第一章\n---\n正文"
FM_NOTOP = "\n---\ntitle: x\n---\n正文"
FM_RAW = "---\ntitle: x\n# 这是注释行\n---\n正文"
FM_QUOTE = "---\ntitle: '单引号值'\n---\n正文"

A = [
    {"src": FM_OK},
    {"src": FM_BLANK, "diag": 1},
    {"src": FM_NOKV, "diag": 1},
    {"src": FM_NOTOP},
    {"src": FM_RAW},
    {"src": FM_QUOTE},
]

# ---------------------------------------------------------------------------
# B 组 · @@ meta 自有模式
# ---------------------------------------------------------------------------
META_ON = {"__MDE_META__": {"zero": {"fields": {"title": "我写故我播", "author": "wUwproject"}},
                            "up": [{"at": "2026-10-30 23:24", "key": "title"}]}}
META_EMPTY = {"__MDE_META__": {"zero": {"fields": {"title": "   ", "author": ""}}, "up": []}}

B = [
    {"src": "@@ meta\n\n正文"},                                    # 无数据 → 不占位
    {"src": "@@ meta\n\n正文", "window": META_ON},                 # 有数据 → 出区
    {"src": "@@ meta\n\n正文", "window": dict(META_ON, __MDE_META_ON__=False)},   # 总开关关
    {"src": "---\ntitle: a\n---\n@@ meta\n正文", "window": META_ON},              # 冲突
    {"src": "@@ meta\n@@ meta\n正文", "window": META_ON, "diag": 1},               # 重复
    {"src": "@@ meta 说明\n正文", "diag": 1},                       # 带参 → 原文露出
    {"src": "@@ meta\n", "window": META_EMPTY},                    # 全空字段 → 不出区
]


def main():
    if not os.path.isfile(PARSER_NEW):
        raise SystemExit("FAIL 缺少 md-parser.js")
    ra = run(PARSER_NEW, A)
    rb = run(PARSER_NEW, B)

    # ---- A 组 ----
    h = ra[0]["html"]
    ck("T01 front matter 正常渲染成元数据区",
       has(h, 'data-mde-zone="a"', "<span class=\"mde-fm-k\">title</span>", "我写故我播")
       and "---" not in h, h[:200])
    ck("T02 值两侧引号被剥离",
       has(ra[0]["html"], ">wUwproject</span>") and '"wUwproject' not in ra[0]["html"],
       ra[0]["html"][:200])
    ck("T03 内含空行 → 整段不认，一字不吞",
       none(ra[1]["html"], "mde-fm") and has(ra[1]["html"], "<hr>", "title: x", "author: y"),
       ra[1]["html"][:200])
    ck("T03b 内含空行 → D501",
       any(d["code"] == "D501" for d in ra[1]["diag"]), str(ra[1]["diag"]))
    ck("T04 无 key:value（装饰横线组）→ 整段不认",
       none(ra[2]["html"], "mde-fm") and has(ra[2]["html"], "第一章"),
       ra[2]["html"][:200])
    ck("T04b 无 key:value → D501",
       any(d["code"] == "D501" for d in ra[2]["diag"]), str(ra[2]["diag"]))
    ck("T05 不在首行 → 不算元数据",
       none(ra[3]["html"], "mde-fm") and has(ra[3]["html"], "<hr>"), ra[3]["html"][:200])
    ck("T06 不合键值的行按原文露出（零吞字）",
       has(ra[4]["html"], "mde-fm-raw", "# 这是注释行"), ra[4]["html"][:300])
    ck("T06b 单引号值剥离",
       has(ra[5]["html"], ">单引号值</span>") and "'单引号值'" not in ra[5]["html"],
       ra[5]["html"][:200])

    # ---- B 组 ----
    ck("T07 @@ meta 无数据 → 不占位、不报错",
       none(rb[0]["html"], "mde-fm") and has(rb[0]["html"], "<p>正文</p>"), rb[0]["html"][:200])
    ck("T08 @@ meta 有数据 → 出区（zone=b）+ 最近修改",
       has(rb[1]["html"], 'data-mde-zone="b"', ">代称</span>", "我写故我播", "最近修改", "2026-10-30 23:24"),
       rb[1]["html"][:300])
    ck("T09 总开关关闭 → 两条通道都不出区",
       none(rb[2]["html"], "mde-fm") and has(rb[2]["html"], "<p>正文</p>"), rb[2]["html"][:200])
    ck("T10 冲突 → 都不渲染，只出提示条",
       has(rb[3]["html"], "mde-fm-conflict", "元数据冲突")
       and none(rb[3]["html"], 'data-mde-zone="a"', 'data-mde-zone="b"'),
       rb[3]["html"][:300])
    ck("T10b 冲突时 front matter 的字段值也不渲染",
       "title" not in rb[3]["html"], rb[3]["html"][:300])
    ck("T11 重复 @@ meta → 只第一处生效 + D502",
       rb[4]["html"].count('data-mde-zone="b"') == 1
       and any(d["code"] == "D502" for d in rb[4]["diag"]), str(rb[4]["diag"]))
    ck("T12 @@ meta 带参 → 按原文露出 + D406",
       has(rb[5]["html"], "@@ meta 说明")
       and any(d["code"] == "D406" for d in rb[5]["diag"]), str(rb[5]["diag"]))
    ck("T12b 字段全空 → 仍出区，至少给作者 default + 创建（v2.26.3）",
       has(rb[6]["html"], 'data-mde-zone="b"', ">作者</span>", "default", ">创建</span>")
       and none(rb[6]["html"], ">代称</span>"), rb[6]["html"][:300])

    # ---- C 组 · 指令边界（家族惯例：@@ 与指令名之间的空白可有可无） ----
    rc = run(PARSER_NEW, [
        {"src": "@@meta\n\n正文", "window": META_ON},
        {"src": "@@ metax\n正文", "diag": 1},
        {"src": "@@meta说明\n正文", "diag": 1},
    ])
    ck("T13 @@meta（无空格）与 @@ meta 等价",
       has(rc[0]["html"], 'data-mde-zone="b"'), rc[0]["html"][:200])
    ck("T14 @@ metax 不被误认（词边界），按原文露出",
       has(rc[1]["html"], "@@ metax") and none(rc[1]["html"], "mde-fm"), rc[1]["html"][:200])
    ck("T14b @@meta说明（带尾巴）不被认，报 D406",
       none(rc[2]["html"], "mde-fm")
       and any(d["code"] == "D406" for d in rc[2]["diag"]), str(rc[2]["diag"]))

    # ---- F 组 · v2.26.3 作者链 / 创建 / 最近修改（渲染层） ----
    META_FULL = {"__MDE_META__": {
        "zero": {"created": "2026-10-31T01:47:36+0800",
                 "fields": {"author": "wUwproject", "title": "我写故我播",
                            "date": "2026-10-31"}},
        "up": [{"at": "2026-11-01 20:33", "who": "Ldxs", "key": "title",
                "from": "a", "to": "b"}],
        "fields": {"author": "Ldxs", "title": "b", "date": "2026-10-31"},
        "authors": ["wUwproject", "Ldxs"],
        "created": "2026-10-31T01:47:36+0800",
        "last": "2026-11-01 20:33"}}
    META_NONE = {"__MDE_META__": {
        "zero": {"created": "none", "fields": {"author": "default"}},
        "up": [{"at": "2026-11-01 21:40", "who": "Ldxs", "key": None,
                "from": "", "to": "", "note": "建档"}],
        "fields": {"author": "default"},
        "authors": ["default", "Ldxs"], "created": "none",
        "last": "2026-11-01 21:40"}}
    # 老结构：后端还没升级时前端必须自己兜底（authors/created/last 全缺）
    META_OLD = {"__MDE_META__": {
        "zero": {"created": "2026-10-31T01:47:36+0800",
                 "fields": {"author": "wUwproject", "title": "旧文档"}},
        "up": [{"at": "2026-10-30 23:24", "key": "title"}],
        "fields": {"author": "wUwproject", "title": "旧文档"}}}

    rf = run(PARSER_NEW, [
        {"src": "@@ meta\n\n正文", "window": META_FULL},
        {"src": "@@ meta\n\n正文", "window": META_NONE},
        {"src": "@@ meta\n\n正文", "window": META_OLD},
    ])
    hf, hn, ho = rf[0]["html"], rf[1]["html"], rf[2]["html"]
    ck("F01 作者链 = 创建者 + 修改者，全角逗号分隔",
       has(hf, '>作者</span><span class="mde-fm-v">wUwproject，Ldxs</span>'), hf[:400])
    ck("F02 创建时间 ISO → YYYY-MM-DD HH:MM",
       has(hf, '>创建</span><span class="mde-fm-v">2026-10-31 01:47</span>'), hf[:400])
    ck("F03 最近修改只给时间，不带字段名",
       has(hf, '>最近修改</span><span class="mde-fm-v">2026-11-01 20:33</span>')
       and " · " not in hf, hf[:400])
    ck("F04 作者只出一行（fields.author 不在字段行里重复）",
       hf.count(">作者</span>") == 1 and ">Ldxs</span>" not in hf, hf[:400])
    ck("F05 date 只读不写：老档案的值照常显示",
       has(hf, '>日期</span><span class="mde-fm-v">2026-10-31</span>'), hf[:400])
    ck("F06 接手别人的文件：创建显示 none，作者链含 default",
       has(hn, '>创建</span><span class="mde-fm-v">none</span>',
           '>作者</span><span class="mde-fm-v">default，Ldxs</span>'), hn[:400])
    ck("F07 老结构（无 authors/created/last）前端兜底不炸",
       has(ho, '>作者</span><span class="mde-fm-v">wUwproject</span>',
           '>创建</span><span class="mde-fm-v">2026-10-31 01:47</span>',
           '>最近修改</span><span class="mde-fm-v">2026-10-30 23:24</span>'), ho[:400])

    # ---- G 组 · v2.26.3 建档语义（md_meta 纯 Python，不碰文档） ----
    import shutil
    import tempfile
    sys.path.insert(0, HERE)
    import md_meta as MM

    def _adir():
        d = tempfile.mkdtemp(prefix="mde_meta_")
        return d, os.path.join(d, "doc.assets")

    u = MM.parse_up("# 记录\n\n"
                    "- 2026-11-01 20:33 @Ldxs · title：`a` → `b`\n"
                    "- 2026-11-01 21:40 @Ldxs · 建档\n"
                    "- 2026-10-30 23:24 · author：`x` → `y`\n")
    ck("G01 带字段行解析出 @who",
       len(u) == 3 and u[0]["who"] == "Ldxs" and u[0]["key"] == "title", str(u))
    ck("G02 无字段行（建档）解析成 key=None + note",
       u[1]["key"] is None and u[1]["note"] == "建档" and u[1]["who"] == "Ldxs", str(u[1]))
    ck("G03 老格式无 @ → who 为空，不报错",
       u[2]["who"] == "" and u[2]["key"] == "author", str(u[2]))
    ck("G04 无字段行不被当成字段变更（_apply_up 只认白名单键）",
       MM._apply_up({"author": "z"}, u)["author"] == "y", "合成结果应只受 author 行影响")

    _d, _a = _adir()
    r1, c1, b1 = MM.sync(_a, {"title": "T", "author": "wUwproject"},
                         who="wUwproject", created=None)
    ck("G05 本次新建：created 写现在、作者取面板、up 不刷",
       b1 is True and c1 == 0 and r1["authors"] == ["wUwproject"]
       and r1["created"] != "none" and r1["last"] == "", str(r1))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    r2, c2, b2 = MM.sync(_a, {"author": "Ldxs"}, who="Ldxs", created="none")
    ck("G06 接手别人的文件：created=none，作者链 default+Ldxs",
       b2 is True and r2["created"] == "none"
       and r2["authors"] == ["default", "Ldxs"], str(r2))
    ck("G07 接手时 up 第一条就是「建档」，写明是谁开始留痕",
       r2["up"] and r2["up"][0]["note"] == "建档" and r2["up"][0]["who"] == "Ldxs",
       str(r2["up"]))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    r3, c3, _b3 = MM.sync(_a, {}, who="Ldxs", created="none",
                          baseline={"title": "本机的标题", "tags": "本机的标签"})
    ck("G08 接手时不拿本机面板值污染别人文档（baseline 被忽略）",
       r3["fields"].get("title") is None and r3["fields"].get("tags") is None,
       str(r3["fields"]))
    ck("G09 接手且什么都没填：作者链 = default（创建者）+ 本人，档案照样建",
       r3["authors"] == ["default", "Ldxs"] and r3["created"] == "none", str(r3))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    MM.sync(_a, {"author": "wUwproject"}, who="wUwproject", created=None)
    r4, c4, b4 = MM.sync(_a, {"author": "wUwproject"}, who="wUwproject")
    r5, c5, _b5 = MM.sync(_a, {"title": "改个标题"}, who="Ldxs")
    ck("G10 重复保存不刷履历（幂等）",
       c4 == 0 and r4["last"] == "" and b4 is False, str(r4))
    ck("G11 换人改字段 → 作者链追加，履历带 @who",
       c5 == 1 and r5["authors"] == ["wUwproject", "Ldxs"]
       and "@Ldxs" in MM._fmt_up(r5["up"][-1]), str(r5["up"][-1]))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    os.makedirs(MM.meta_dir(_a))
    io.open(os.path.join(MM.meta_dir(_a), "zero.json"), "w", encoding="utf-8").write(
        '{"format":1,"created":"2026-10-31T01:47:36+0800","creator":{"by":"MDEditor"},'
        '"fields":{"author":"wUwproject","date":"2026-10-31"}}')
    r6 = MM.read(_a)
    ck("G12 老档案 date 仍可读（白名单不删，面板不提供输入而已）",
       r6["fields"].get("date") == "2026-10-31", str(r6["fields"]))
    shutil.rmtree(_d, ignore_errors=True)

    # ---- H 组 · up 是忠实追加的流水账：每次 save 一行（v2.26.3 定）----
    # 主人原话：「up 就是记录每一次 save 时候的元信息和时间的，不管是不是相同。
    # 去重排序那是渲染时候的事情！」所以写不写由 touch 决定，不由 diff 决定。
    _d, _a = _adir()
    MM.sync(_a, {"author": "wUwproject"}, who="wUwproject", created=None)
    n0 = len(MM.read(_a)["up"])
    r7, c7, _b7 = MM.sync(_a, {"author": "wUwproject"}, who="wUwproject", touch=True)
    ck("H01 touch=True：字段没变也记一条「保存」，字段变更数仍是 0",
       c7 == 0 and len(r7["up"]) == n0 + 1
       and r7["up"][-1]["note"] == "保存" and r7["up"][-1]["who"] == "wUwproject",
       str(r7["up"]))
    ck("H02 记了「保存」→ 最近修改不再为空（改正文也会走动）", r7["last"] != "", str(r7))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    r8, c8, b8 = MM.sync(_a, {"author": "Ldxs"}, who="Ldxs", created=None, touch=True)
    ck("H03 touch 且本次建档：照样留一条「保存」，last 与建档同一时刻",
       b8 is True and c8 == 0 and len(r8["up"]) == 1
       and r8["up"][0]["note"] == "保存" and r8["last"] != "",
       str([r8["up"], r8["last"], r8["created"]]))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    r9, _c9, _b9 = MM.sync(_a, {}, who="Ldxs", created="none", touch=True)
    ck("H04 touch 且接手建档：只有「建档」一条，不叠同秒的「保存」",
       [e["note"] for e in r9["up"]] == ["建档"], str(r9["up"]))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    MM.sync(_a, {"author": "wUwproject"}, who="wUwproject", created=None)
    r10, c10, _b10 = MM.sync(_a, {"title": "新标题"}, who="Ldxs", touch=True)
    ck("H05 touch 且有字段变更：只记字段行（from→to），不重复记「保存」",
       c10 == 1 and len(r10["up"]) == 1 and r10["up"][0]["key"] == "title",
       str(r10["up"]))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    MM.sync(_a, {"author": "Ldxs"}, who="Ldxs", created=None)
    for _ in range(2):
        MM.sync(_a, {"author": "Ldxs"}, who="Ldxs", touch=True)
    r11 = MM.read(_a)
    ck("H06 同一人连存两次：up 两条忠实追加，作者链仍只有一个（去重在渲染）",
       len(r11["up"]) == 2 and r11["authors"] == ["Ldxs"],
       str([r11["up"], r11["authors"]]))
    shutil.rmtree(_d, ignore_errors=True)

    _d, _a = _adir()
    MM.sync(_a, {"author": "wUwproject"}, who="wUwproject", created=None)
    r12, _c12, _b12 = MM.sync(_a, {"author": "wUwproject"}, who="wUwproject")
    ck("H07 touch 缺省（老的 update 语义）：没变就一条不写，旧调用方不受影响",
       len(r12["up"]) == 0 and r12["last"] == "", str(r12["up"]))
    shutil.rmtree(_d, ignore_errors=True)

    # ---- I 组 · 内容指纹（v2.26.3，溯源主角）---------------------
    # up 不只是"谁改了什么字段"，更是"这个时间点内容长这个样子"。
    # 指纹一变说明内容真变了；没变说明这次保存没产生任何变化。
    _d, _a = _adir()
    body1 = "# 标题\n\n第一版正文\n"
    body2 = "# 标题\n\n第二版正文\n"
    r13, _c13, _b13 = MM.sync(_a, {"author": "Ldxs"}, who="Ldxs",
                              created=None, touch=True, content=body1)
    h1 = MM._last_hash(r13["up"])
    ck("I01 首次保存：履历行带 64 位 SM3 指纹", len(h1) == 64, h1)
    ck("I02 read 返回的 hash 与 up 末条一致", r13["hash"] == h1, r13["hash"])
    ck("I03 指纹写进 up.md 原文（不是只在内存里）",
       ("sm3:" + h1) in io.open(os.path.join(_a, ".mde", "up.md"),
                                encoding="utf-8").read(), h1[:16])

    n_before = len(r13["up"])
    r14 = MM.read(_a, content=body1)
    MM.sync(_a, {"author": "Ldxs"}, who="Ldxs", touch=True, content=body1)
    r15 = MM.read(_a, content=body1)
    ck("I04 同内容再存一次：up 不追加（内容没变，最近修改不该往前走）",
       len(r15["up"]) == n_before, "%d → %d" % (n_before, len(r15["up"])))
    ck("I05 同内容保存后 stale 仍为 False（本来就没差）",
       r14["stale"] is False and r15["stale"] is False,
       (r14["stale"], r15["stale"]))

    MM.sync(_a, {"author": "Ldxs"}, who="Ldxs", touch=True, content=body2)
    r16 = MM.read(_a, content=body2)
    ck("I06 内容变了：up 追加一条，指纹换新",
       len(r16["up"]) == n_before + 1 and r16["hash"] != h1,
       (len(r16["up"]), r16["hash"][:8]))
    ck("I07 改完内容后 stale=False（盘上与末条一致）", r16["stale"] is False,
       r16["stale"])

    r17 = MM.read(_a, content=body1)      # 假装文件被外部改回了第一版
    ck("I08 盘上内容与末条不符：stale=True（这就是『未记录改动』）",
       r17["stale"] is True, r17["stale"])

    r18 = MM.read(_a)                      # 没传 content：无从判断
    ck("I09 不传正文时 stale=None，不冒充『正常』", r18["stale"] is None,
       r18["stale"])

    # 字段变、内容没变：只记字段行，不再叠一条「保存」
    _n = len(MM.read(_a)["up"])
    MM.sync(_a, {"author": "Ldxs", "note": "只改备注"}, who="Ldxs",
            touch=True, content=body2)
    _u = MM.read(_a)["up"]
    ck("I10 字段变更 + 内容未变：只多一条字段行，不重复记「保存」",
       len(_u) == _n + 1 and _u[-1]["key"] == "note", str(_u[-1]))

    # 老档案（没有指纹行）：解析成空串，stale 恒为 None，绝不误报
    _d2, _a2 = _adir()
    MM.ensure(_a2, {"author": "old"})
    with io.open(os.path.join(_a2, ".mde", "up.md"), "a",
                 encoding="utf-8", newline="\n") as _f:
        _f.write("- 2026-10-30 23:24 @old · 保存\n")
    r19 = MM.read(_a2, content="随便什么内容")
    ck("I11 老档案无指纹：hash 空、stale=None（不误报未记录改动）",
       r19["hash"] == "" and r19["stale"] is None,
       (r19["hash"], r19["stale"]))

    # 接手别人文件建档：那条「建档」也要带指纹，链从第一笔就完整
    _d3, _a3 = _adir()
    r20, _c20, b20 = MM.sync(_a3, {}, who="Ldxs", created="none",
                             touch=True, content=body1)
    ck("I12 接手建档：「建档」行带指纹，链从第一笔就完整",
       b20 is True and len(r20["hash"]) == 64 and
       "建档 sm3:" in io.open(os.path.join(_a3, ".mde", "up.md"),
                              encoding="utf-8").read(),
       r20["hash"][:16])

    for _x in (_d, _d2, _d3):
        shutil.rmtree(_x, ignore_errors=True)

    # ---- D 组 · 回归：逐字节不变 ----
    reg = []
    for fn in ("README.md", "CHANGELOG.md", "PLAN-v2.13.0.md", "PLAN-v2.17.0-页区页码.md",
               "PLAN-v2.18.0-begin并写.md", "COPYRIGHT"):
        fp = os.path.join(HERE, fn)
        if os.path.isfile(fp):
            with io.open(fp, "r", encoding="utf-8", errors="replace") as f:
                reg.append({"src": f.read(), "window": META_ON, "name": fn})
    # 构造样本：专攻"文首/正文中的 ---"
    reg += [
        {"src": "---\n\n正文\n\n---\n\n结尾"},
        {"src": "---"},
        {"src": "---\n---"},
        {"src": "---\ntitle: x"},
        {"src": "正文\n\n---\n\ntitle: x\n\n---\n\n结尾"},
        {"src": "  ---  \ntitle: x\n  ---  \n正文"},
    {"src": "#### 标题\n\n---\n\n列表：\n\n- a\n- b"},
    {"src": "@@ blank{1}\n\n正文"},
    {"src": "@@ begin color red\n文字\n@@ end color"},
    {"src": "@@ caption{l} 表 1　标题\n| a | b |\n|---|---|\n| 1 | 2 |"},
    ]
    for _k, _o in enumerate(reg):
        _o.setdefault("name", "构造%02d" % _k)
    if os.path.isfile(PARSER_OLD):
        old = run(PARSER_OLD, reg)
        new = run(PARSER_NEW, reg)
        diff = [i for i in range(len(reg)) if old[i]["html"] != new[i]["html"]]
        # v2.25.0 反引号「整串读 + 按长度配对」：含 ` ``` `（单反引号包三反引号）
        # 或 `\``（转义反引号）的文档渲染必然改变，且方向是修复——旧版把三个
        # 反引号拆成 `` + ` 去抢后面的反引号，产出错位 <code> 与漏出的 @@C 占位。
        # 这不是"存量文档不能变"要保护的对象，但必须逐条点名，不许沉默放行。
        ALLOW = {"README.md", "CHANGELOG.md"}
        unexpected = [reg[i]["name"] for i in diff if reg[i]["name"] not in ALLOW]
        ck("T15 无元数据文档：除已声明的反引号升级样本外渲染逐字节相同（%d 份）" % len(reg),
           not unexpected, "未声明差异 %s" % unexpected)
        leak = [reg[i]["name"] for i in diff if re.search(r"@@C\d+@@", new[i]["html"])]
        ck("T15b 反引号升级样本不得残留 @@C 占位（修复的硬证据）", not leak, "残留 %s" % leak)
    else:
        ck("T15 阳性对照可用（备份解析器存在）", False, PARSER_OLD)

    # ---- E 组 · 导出剔除（子进程跑 node 断言，逐行并入本文件的判定） ----
    strip_test = os.path.join(HERE, "_test_export_strip.cjs")
    if os.path.isfile(strip_test):
        p = subprocess.run(["node", strip_test], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        out = p.stdout.decode("utf-8", "replace")
        lines = [ln for ln in out.splitlines() if ln.startswith(("PASS  ", "FAIL  "))]
        if not lines:
            ck("E 组导出剔除测试可执行", False,
               p.stderr.decode("utf-8", "replace")[:400])
        for ln in lines:
            ck(ln[6:].strip(), ln.startswith("PASS"))
    else:
        ck("E 组导出剔除测试存在", False, strip_test)

    print("-" * 60)
    print("合计 %d 条：PASS %d / FAIL %d"
          % (COUNT[0], COUNT[0] - len(FAILED), len(FAILED)))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
