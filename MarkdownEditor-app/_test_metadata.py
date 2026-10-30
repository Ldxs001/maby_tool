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
       has(rb[1]["html"], 'data-mde-zone="b"', ">标题</span>", "我写故我播", "最近修改", "2026-10-30 23:24"),
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
    ck("T12b 字段全空 → 不出区",
       none(rb[6]["html"], "mde-fm"), rb[6]["html"][:200])

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

    # ---- D 组 · 回归：逐字节不变 ----
    reg = []
    for fn in ("README.md", "CHANGELOG.md", "PLAN-v2.13.0.md", "PLAN-v2.17.0-页区页码.md",
               "PLAN-v2.18.0-begin并写.md", "COPYRIGHT"):
        fp = os.path.join(HERE, fn)
        if os.path.isfile(fp):
            with io.open(fp, "r", encoding="utf-8", errors="replace") as f:
                reg.append({"src": f.read(), "window": META_ON})
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
    if os.path.isfile(PARSER_OLD):
        old = run(PARSER_OLD, reg)
        new = run(PARSER_NEW, reg)
        diff = [i for i in range(len(reg)) if old[i]["html"] != new[i]["html"]]
        ck("T15 无元数据文档：改前改后渲染逐字节相同（%d 份样本）" % len(reg),
           not diff, "差异索引 %s" % diff)
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
