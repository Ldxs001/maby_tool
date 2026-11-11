# -*- coding: utf-8 -*-
"""发版前置门禁：索引白名单 + 打包输入一致性。

判据来源：refs/03「代码管理」（过程材料不入库）、refs/13 §0.6（打包输入不可信）、
refs/14 坑 14 / 坑 17（题注被测试清空、规划文件只污染索引不污染安装包）。

用法：
    python installer/_preflight.py                  # 从本文件向上找 .git
    python installer/_preflight.py --repo ../maby_tool

查三件：
  A. 仓库索引里不许有开发过程材料（PLAN / 任务地图 / 方案 / 草案 / 计划 / plans 目录）。
     「过程材料」只看顶层散装文件与专用目录；docs/ 下的产品文档（含「…契约-方案.md」）不算。
  B. 打包输入不许被测试写坏：docs/**/.assets/annotations.json 必须与 git HEAD 逐字节一致。
  C. 构建产物里不许带 PLAN（_setup_staging 存在时顺带查）。

退出码：0 = 全过；1 = 有 FAIL。
"""
import argparse
import os
import re
import subprocess
import sys

# 顶层散装文件：命中即视为过程材料
TOP_BAD = [
    (re.compile(r"^PLAN-.*\.md$", re.I), "版本规划"),
    (re.compile(r"^.*任务地图.*$"), "任务地图"),
    (re.compile(r"^.*方案.*\.md$"), "方案"),
    (re.compile(r"^.*草案.*$"), "草案"),
    (re.compile(r"^.*计划.*\.md$"), "计划"),
    (re.compile(r"^.*\.plan\.md$", re.I), "计划"),
]

# 任意层级的专用目录
DIR_BAD = ("/plans/", "/_plan/", "/.workbuddy/", "/_notes/")

FAILS = []
CHECKS = [0]


def check(name, ok, detail=""):
    CHECKS[0] += 1
    print(("PASS" if ok else "FAIL") + " | " + name + ((" | " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def find_repo(start):
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def top_level_rel(path, repo):
    """把仓库内路径剥成「相对产品根」的形式，并标出是否顶层散装。

    仓库结构是 <repo>/MarkdownEditor-app/<file>；取 products 顶层那一层的相对路径。
    顶层散装 = 相对路径里没有 '/'（如 PLAN-x.md），任何层级的专用目录单独判。
    """
    p = path.replace("\\", "/")
    parts = p.split("/")
    # 去掉仓库顶层目录（如 MarkdownEditor-app/）
    rel = "/".join(parts[1:]) if len(parts) > 1 else p
    return p, rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="仓库根（默认从本文件向上找 .git）")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.abspath(args.repo) if args.repo else find_repo(here)
    if not repo:
        print("FAIL | 找不到 git 仓库；用 --repo 指定")
        return 1
    print("repo: %s" % repo)
    print("--- A. 索引白名单（过程材料不入库）---")

    r = git(repo, "-c", "core.quotepath=false", "ls-files", "-z")
    if r.returncode != 0:
        print("FAIL | git ls-files 失败：%s" % r.stderr.strip()[:200])
        return 1
    files = [x for x in r.stdout.split("\0") if x]

    bad = []
    for f in files:
        full, rel = top_level_rel(f, repo)
        lowered = "/" + full.lower().replace("\\", "/")
        if any(d in lowered for d in DIR_BAD):
            bad.append((f, "专用目录"))
            continue
        if "/" in rel:          # 只在顶层散装文件里判，docx/ 等产品文档不误伤
            continue
        for rx, why in TOP_BAD:
            if rx.match(rel):
                bad.append((f, why))
                break

    check("A1 索引里无过程材料（PLAN/任务地图/方案/草案/计划）", not bad,
          "命中 %d 项：%s" % (len(bad), [b[0] for b in bad[:8]]))
    if bad:
        for f, why in bad[:20]:
            print("       · [%s] %s" % (why, f))
        print("       处置：git rm --cached <上面的路径>（保留本地文件）→ 提交")

    print("--- B. 打包输入一致性（题注 json 与 HEAD 一致）---")
    ann = [f for f in files if f.endswith("/.assets/annotations.json")
           or f.endswith(".assets/annotations.json")]
    if not ann:
        check("B0 找到题注文件", False, "一个都没找到，路径规则需复核")
    for f in ann:
        d = git(repo, "-c", "core.quotepath=false", "diff", "--name-only", "HEAD", "--", f)
        changed = bool(d.stdout.strip())
        check("B1 与 HEAD 一致：%s" % f.split("/")[-2].replace(".assets", ""), not changed,
              "工作区/索引与 HEAD 不同；用 git show HEAD:<路径> 拷回（以 HEAD 为准）")

    print("--- C. 构建产物里无 PLAN ---")
    stage = os.path.join(os.path.dirname(here), "_setup_staging")
    if os.path.isdir(stage):
        hits = []
        for root, dirs, names in os.walk(stage):
            for n in names:
                if "PLAN" in n.upper():
                    hits.append(os.path.join(root, n))
        check("C1 staging 内无 PLAN", not hits, str(hits[:5]))
    else:
        print("SKIP | C1 尚无 _setup_staging（未构建）")

    print("--- D. 未跟踪文件（提示，不判失败）---")
    st = git(repo, "-c", "core.quotepath=false", "status", "--porcelain")
    untracked = [l[3:] for l in st.stdout.splitlines() if l.startswith("??")]
    for u in untracked[:15]:
        print("       ? %s" % u)
    if len(untracked) > 15:
        print("       … 共 %d 项" % len(untracked))
    if not untracked:
        print("       （无）")

    print("PREFLIGHT %s（%d 项，FAIL %d）"
          % ("PASS" if not FAILS else "FAIL", CHECKS[0], len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
