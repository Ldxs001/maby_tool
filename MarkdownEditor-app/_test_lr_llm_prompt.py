# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""v2.6.8：系统提示词"规格化"测试。

A 段 解析单测：`_lr_parse_llm_output` 六种模型输出形态。
B 段 提示词内容断言：数据契约四通道 / 六种数据点形式（含显示与产出）/
    两种执行点（普通 + global）/ 形状消费规则 / 硬禁 / 输出两段。
    **不得**再出现"按场景选形式"的清单（那是场景穷举的病根）。
D 段 规格 ↔ 实现对照：把提示词里声称的"产出什么"，拿前端真实解析器
    （mdeParseBody / mdeParseTable）跑一遍，逐条比对——提示词写错即 FAIL。
E 段 两个语法标本源码真跑。
C 段 前端 UI：拦 /api/run-llm 返回固定 payload，验证用法说明框出现、
    多行存取、新建清空。
端口 18766 有服务则复用（html 每请求读盘，必为新版）；无则进程内起。
"""
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(name, cond, detail=""):
    print("%-56s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


# ---------- A 解析单测 ----------
def full_reply():
    return (
        "```python\n"
        "# run-name: sumcalc\n"
        "# 依据：形式4 键值对向量\n"
        "def run(data):\n"
        "    return 'ok'\n"
        "```\n"
        "```text\n"
        "数据点写法：@@ MDE_甲{A == 3, B == 4, C == 5}\n"
        "执行点写法：@@ MDE import sumcalc is 甲\n"
        "返回值：和 12\n"
        "注意：值须可转数字\n"
        "```\n")


def parse_tests():
    import md_server as M

    code, name, usage = M._lr_parse_llm_output(full_reply())
    check("A1 两围栏：code 取到函数体", "def run(data):" in code)
    check("A2 两围栏：name = sumcalc", name == "sumcalc", name)
    check("A3 两围栏：usage 四行齐",
          all(k in usage for k in ("数据点写法", "执行点写法", "返回值", "注意")))
    check("A4 usage 不含代码", "def run" not in usage)

    # 无 python 围栏（旧行为：整段当代码）
    code, name, usage = M._lr_parse_llm_output("def run(data):\n    return 'x'")
    check("A5 无围栏：整段当代码", code.startswith("def run"), repr(code[:16]))
    check("A6 无围栏：usage 空", usage == "")

    # 只有 python 围栏
    code, name, usage = M._lr_parse_llm_output("```python\n# run-name: a\ndef run(d):\n    return '1'\n```")
    check("A7 仅代码块：usage 空", usage == "" and name == "a", name)

    # 无 text 围栏但尾巴带「数据点写法」
    code, _, usage = M._lr_parse_llm_output(
        "```python\ndef run(d):\n    return '1'\n```\n"
        "数据点写法：@@ MDE_甲{1,2}\n执行点写法：@@ MDE import x is 甲\n")
    check("A8 尾巴兜底：usage 取到", "数据点写法" in usage)

    # 中文冒号
    _, name, _ = M._lr_parse_llm_output("```python\n# run-name：求和\ndef run(d):\n    return ''\n```")
    check("A9 run-name 中文冒号", name == "求和", name)

    # 空串
    code, name, usage = M._lr_parse_llm_output("")
    check("A10 空输入不炸", (code, name, usage) == ("", "", ""))


# ---------- B 提示词内容（规格完整性） ----------
def prompt_tests():
    import md_server as M
    p = M._LR_LLM_SYS

    # 数据契约
    check("B1 四通道齐（kv/vals/raw/marks）",
          all(k in p for k in ("data['kv']", "data['vals']", "data['raw']", "data['marks']")))
    check("B2 vals 四种形状齐",
          all(k in p for k in ("str                     一段文字",
                               "list[str]               一串值",
                               "list[list[str]]         二维",
                               "list[list[list[str]]]   三维")))
    check("B3 raw 明确不是正文/全文/标记",
          ("不是正文" in p) and ("不是全文" in p) and ("不含任何标记" in p))

    # 六种数据点形式：编号 + 四列（写法/显示/产出）
    check("B4 六种形式编号齐",
          all(("%d " % i) in p for i in range(1, 7)) and "没有第七种" in p)
    check("B5 形式1 显示与产出齐",
          "@@ MDE_甲{今天买了苹果}" in p and "vals += \"今天买了苹果\"（str）" in p)
    check("B6 形式2 显示与产出齐",
          "@@ MDE_甲{苹果 == 3}" in p and 'kv["苹果"] = "3"' in p)
    check("B7 形式3 产出 list[str]",
          '@@ MDE_甲{3,4,5}' in p and 'vals += ["3","4","5"]（list[str]）' in p)
    check("B8 形式4 合并 kv",
          "@@ MDE_甲{A == 3, B == 4}" in p and 'kv 合并 {"A":"3","B":"4"}' in p)
    check("B9 形式5 行文抽取（值 + 键值两版）",
          "((8%))" in p and "((A == 8%))" in p and 'vals += ["8%","1.5%"]（list[str]）' in p)
    check("B10 形式6 表格二维/三维",
          ":2(2x2)" in p and ":3()" in p and 'vals += [["tony","59"],["lily","18"]]' in p)
    check("B11 半角逗号规则", "半角逗号 , 是向量分隔符" in p)
    check("B12 fail-closed 静默失效已写明",
          ("整个数据点按普通文字显示，不产生任何数据" in p) and ("静默" in p))
    check("B13 跨行 body 归形式1", "body 跨行时一律当整段文字" in p)
    check("B14 池名三种规则", all(k in p for k in ("@@ MDE_甲 只喂 is 甲", "@@ MDE__甲 是隐性的", "@@ MDE_ 是公共池")))
    check("B15 同池多行自动合并", "同一池名可以写多行数据点，自动合并" in p)

    # 两种执行点
    check("B16 执行点两种形式",
          ("a) 普通" in p) and ("b) 全局 global" in p) and "（全部）" in p)
    check("B17 普通执行点返回 str 即最终文本",
          ("按形状渲染、不做猜测" in p) and ("单行 str → 行内文本" in p))
    check("B42b 图片落点与文件引用口径（v2.8）",
          ("当前目录＝文档资产目录" in p) and ("open(值,'rb')" in p)
          and ('![](x.png)' in p))
    check("B18 global 语法带 {global 标记名}",
          "{global 标记名}" in p and "'''标记名" in p)
    check("B19 global 的 marks 结构与等长契约",
          ("每项 {'mark': '标记名', 'ctx':" in p)
          and ("长度等于 len(data['marks'])" in p)
          and ("第 i 项替换第 i 个标记" in p))
    check("B20 global 长度不符即失败、标记保原文",
          "按执行失败处理，标记保持原文" in p)
    check("B21 global 只展开一轮（不递归）",
          "替换只做一轮" in p and "不会被再次展开" in p)
    check("B22 未声明 global 时标记是普通文字",
          "只有被 {global} 接管时才替换" in p)

    # 消费规则与推导
    check("B23 形状→分支消费表齐",
          all(k in p for k in ("一段文字 → vals 里的 str 元素",
                               "一串值   → vals 里的 list 元素",
                               "名字→值  → data['kv']",
                               "表格     → vals 里的嵌套 list",
                               "全文标记 → data['marks']")))
    check("B24 禁止假设 vals[0] 类型",
          "不能假设 vals[0] 一定是数字" in p)
    check("B24b vals 是容器不是一串值（禁整体 join/sum）",
          ("装着不同形状的容器" in p) and ("禁止把整个 vals 直接 join / sum" in p))
    check("B24c 每处 data 读取都要对得上数据点",
          ("都必须在用法说明里对得上一行数据点" in p)
          and ("没有任何一行数据点写" in p))
    check("B25 推导只有两问（执行点种类 / 数据点形状）",
          ("1) 执行点用哪种" in p) and ("2) 数据点写几行" in p)
          and ("选择的唯一依据是那样东西的**形状**" in p))
    check("B26 global 不需要数据点（除非 is 池并存）",
          "global 执行点不需要数据点" in p)

    # 硬禁
    check("B27 禁 input / stdin / print",
          all(k in p for k in ("禁 input()、sys.stdin", "禁 print")))
    check("B28 缺数据返回说明而非提问",
          ("返回一句说明文字" in p) and ("不提问" in p) and ("不用 0 或空串冒充结果" in p))
    check("B29 只许六种、禁自造",
          ("只许用二的六种写法" in p) and ("一行数据点兼两种形状" in p))
    check("B30 禁猜键名 + 自约定例外",
          ("禁止猜用户的键名" in p) and ("自己在用法说明里约定的键名可以按名取" in p))
    check("B31 一操作一顶层 def", "一个操作一个顶层 def" in p and "禁止加参数开关" in p)
    check("B32 中文不分词", "不要 split()" in p)

    # 输出格式
    check("B33 输出严格两段",
          ("输出格式（严格两段" in p) and ("数据点写法：" in p) and ("执行点写法：" in p))
    check("B34 run-name 与「依据」第二行",
          ("# run-name: 短名" in p) and ("第二行 # 依据：" in p))
    check("B35 global 用法说明写「数据点写法：无」",
          "数据点写法：无" in p)
    check("B35b 数据点必须用用户实际内容（禁搬语法示例）",
          ("内容必须取自**用户文档里的实际内容" in p)
          and ("禁止把二的语法说明行原样搬过来充数" in p))
    check("B36 除两段外不得输出其他内容",
          "除这两个代码块外，不得输出任何解释、前言、后语" in p)
    check("B36b 含输出前四条自检",
          all(k in p for k in ("输出前自检一遍", "都能在上面某一行数据点里找到来源",
                               "没有把整个 vals 当 list[str] 直接拼接",
                               "就有几行数据点")))

    # 场景穷举必须消失（v2.6.8 的方法论纠偏）
    check("B37 旧「场景→形式」清单已删",
          all(k not in p for k in ("我标出的／圈出的／文中这几处", "用于：需求要处理的",
                                   "正例是标本", "【正例1】", "【反例1】")))
    check("B38 prompt 体积回归（规格化后应 < 6000 字）", len(p) < 6000, "len=%d" % len(p))
    # v2.6.9：标本 B 不再示范花括号形态（模型会照抄成 ^{[1]} 并踩 .format 的坑）
    check("B39 标本 B 代码不示范花括号形态",
          "^{[" not in _specimen(1) and "#%d" in _specimen(1))
    check("B40 明写标本形态只是占位",
          ("只是占位，不是格式规范" in p) and ("不要自行加 {} " in p))
    check("B41 明写字面花括号须双写",
          ("必须双写" in p) and ("'int' object is not subscriptable" in p))
    check("B42 明写输出形态逐字照办",
          "逐字照办" in p and "必须与代码实际输出逐字一致" in p)


# ---------- D 规格 ↔ 真实解析器对照 ----------
def _extract_js(func_name):
    s = io.open(os.path.join(HERE, "markdown-editor.html"), encoding="utf-8").read()
    i = s.find("function " + func_name + "(")
    assert i > 0, func_name
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i:j + 1]
        j += 1
    raise AssertionError("unbalanced " + func_name)


def _node(js_code):
    tmp = os.path.join(tempfile.gettempdir(), "_spec_probe.js")
    io.open(tmp, "w", encoding="utf-8").write(js_code)
    cp = subprocess.run(["node", tmp], capture_output=True)
    out = cp.stdout.decode("utf-8", "replace").strip()
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace")[:400])
    return out


def _parse_rows(cases):
    """cases: [[写法, 期望 ch, 期望 val]]，返回实际 [(ch, val)]（含 kvSingle 归一，
    与 mdeDpSpan 写进 data-dp-val 的逻辑一致）。"""
    js = (_extract_js("mdeParseBody") + "\n" + _extract_js("mdeParseTable") + "\n"
          "var cs=%s;\n" % json.dumps([c[0] for c in cases], ensure_ascii=False)
          + "cs.forEach(function(b){var r=mdeParseBody(b);"
            "if(!r.ok){console.log(JSON.stringify({ok:false}));return;}"
            "var v=r.kvSingle?(function(){var o={};o[r.singleKey]=r.singleVal;return o;}()):r.val;"
            "console.log(JSON.stringify({ok:true,ch:r.ch,val:v}));});\n")
    lines = [x for x in _node(js).split("\n") if x.strip()]
    return [json.loads(x) for x in lines]


def spec_vs_parser():
    """提示词声称的"产出什么"，必须与前端真实解析器的产出逐条一致。"""
    cases = [
        ("今天买了苹果", "vals", "今天买了苹果"),
        ("苹果 == 3", "kv", {"苹果": "3"}),
        ("3,4,5", "vals", ["3", "4", "5"]),
        ("A == 3, B == 4", "kv", {"A": "3", "B": "4"}),
        ("2025年，我国GDP上涨((8%))，同比上涨((1.5%))", "vals", ["8%", "1.5%"]),
        ("2025年，我国GDP上涨((A == 8%))", "kv", {"A": "8%"}),
    ]
    rows = _parse_rows(cases)
    names = ["形式1 单值文本", "形式2 单键值对", "形式3 纯值向量",
             "形式4 键值对向量", "形式5 行文抽取(值)", "形式5 行文抽取(键值)"]
    for nm, (body, want_ch, want_val), got in zip(names, cases, rows):
        ok = got.get("ok") and got.get("ch") == want_ch and got.get("val") == want_val
        check("D %s 真实产出 = 提示词声称" % nm, ok, repr(got))

    # 表格 :2(2x2)：提示词声称 [["tony","59"],["lily","18"]]
    body = "|职务|名称|年龄|\n|:-|:-|:-|\n|总经理|tony|59|\n|秘书|lily|18|"
    js = (_extract_js("mdeParseTable") + "\nconsole.log(JSON.stringify(mdeParseTable('2','(2x2)',%s)));\n"
          % json.dumps(body, ensure_ascii=False))
    got = json.loads(_node(js))
    check("D 形式6 二维表真实产出 = 提示词声称",
          got.get("ok") and got.get("val") == [["tony", "59"], ["lily", "18"]], repr(got)[:120])

    # fail-closed：混用/未闭合 → 整块按普通文字（提示词说明的静默失效）
    bad = _parse_rows([("x, ((b))", None, None),
                       ("2025年上涨((8%))，同比((1.5%))", None, None)])
    check("D fail-closed：语法违规不产数据", bad[0]["ok"] is False, repr(bad[0]))
    check("D fail-closed：合法行文抽取仍通过", bad[1]["ok"] is True, repr(bad[1]))


# ---------- E 两个语法标本真跑 ----------
def _specimen(index):
    import md_server as M
    blocks = re.findall(r"```python\n([\s\S]*?)```", M._LR_LLM_SYS)
    return blocks[index] if index < len(blocks) else ""


def specimen_runs():
    src_a = _specimen(0)
    check("E1 标本A 可提取", "def run(data):" in src_a and "# run-name: flat" in src_a)
    check("E2 标本A 无交互/打印",
          ("input(" not in src_a) and ("print(" not in src_a))
    ns = {}
    try:
        exec(compile(src_a, "<specA>", "exec"), ns)
        ok = True
    except Exception as e:  # noqa: BLE001
        ok = False
        check("E3 标本A 可编译", False, repr(e))
    check("E3 标本A 可编译", ok)
    if ok:
        got = ns["run"]({"kv": {"A": "3", "B": "4"}, "vals": [], "raw": []})
        check("E4 标本A 吃 kv（字典序）", got == "3 / 4", got)
        got = ns["run"]({"kv": {}, "vals": [["3", "4", "5"]], "raw": []})
        check("E5 标本A 吃 list[str]", got == "3 / 4 / 5", got)
        got = ns["run"]({"kv": {}, "vals": [["tony", "59"], ["lily", "18"]], "raw": []})
        check("E6 标本A 吃二维表", got == "tony / 59 / lily / 18", got)
        got = ns["run"]({"kv": {}, "vals": ["一段文字"], "raw": []})
        check("E7 标本A 吃 str", got == "一段文字", got)
        got = ns["run"]({"kv": {}, "vals": [], "raw": []})
        check("E8 标本A 空数据返回说明", "没有收到数据" in got, got)

    src_b = _specimen(1)
    check("E9 标本B 可提取", "def run(data):" in src_b and "# run-name: indexes" in src_b)
    ns2 = {}
    try:
        exec(compile(src_b, "<specB>", "exec"), ns2)
        okb = True
    except Exception as e:  # noqa: BLE001
        okb = False
        check("E10 标本B 可编译", False, repr(e))
    check("E10 标本B 可编译", okb)
    if okb:
        got = ns2["run"]({"kv": {}, "vals": [], "raw": [],
                          "marks": [{"mark": "p", "ctx": "a"}, {"mark": "p", "ctx": "b"}]})
        check("E11 标本B 返回等长 list", got == ["#1", "#2"], repr(got))
        got = ns2["run"]({"kv": {}, "vals": [], "raw": [], "marks": []})
        check("E12 标本B 无标记返回空 list", got == [], repr(got))
        got = ns2["run"]({"kv": {}, "vals": [], "raw": []})
        check("E13 标本B 无 marks 键也不炸", got == [], repr(got))


# ---------- C 前端 UI ----------
def port_in_use():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", 18766)) == 0
    finally:
        s.close()


USAGE = ("数据点写法：@@ MDE_甲{A == 3, B == 4}（产生 kv，一组名字→值）\n"
         "执行点写法：@@ MDE import sumcalc is 甲\n"
         "返回值：和 7\n"
         "注意：值须可转数字")
CODE = ("# run-name: sumcalc\n"
        "# 依据：形式4 键值对向量\n"
        "def run(data):\n"
        "    return 'ok'")


def ui_tests():
    httpd = None
    if not port_in_use():
        sys.argv = ["md_server.py"]
        import md_server
        httpd = md_server.ReuseTCPServer(("127.0.0.1", 18766), md_server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        time.sleep(0.4)

    from playwright.sync_api import sync_playwright

    tmpdoc = os.path.join(os.environ.get("TEMP", "."), "mda_llm_usage_test.md")
    io.open(tmpdoc, "w", encoding="utf-8").write("# 测试\n\n@@ MDE_甲{A == 3, B == 4}\n")
    import urllib.parse
    url = "http://127.0.0.1:18766/?file=" + urllib.parse.quote(tmpdoc)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        stub = {"code": CODE, "name": "sumcalc", "usage": USAGE, "ok": True}
        pg.route("**/api/run-llm", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(stub, ensure_ascii=False)))
        pg.goto(url)
        pg.wait_for_timeout(1500)
        pg.click("#btnRun")
        pg.wait_for_timeout(300)
        check("C1 面板打开", pg.is_visible("#lrPanel"))
        check("C2 用法框初始隐藏", not pg.is_visible("#lrUsage"))

        pg.fill("#lrPrompt", "求数据点所有数字之和")
        pg.click("#lrGen")
        pg.wait_for_timeout(800)
        check("C3 生成后用法框可见", pg.is_visible("#lrUsage"))
        txt = pg.inner_text("#lrUsage") if pg.is_visible("#lrUsage") else ""
        check("C4 用法框四行齐",
              all(k in txt for k in ("数据点写法", "执行点写法", "返回值", "注意")))
        check("C5 代码已填入", "def run(data)" in pg.input_value("#lrCode"))
        check("C6 名称已带出", pg.input_value("#lrName") == "sumcalc",
              pg.input_value("#lrName"))

        # 第二轮：返回空 usage → 必须清空并隐藏（不得残留上一轮）
        stub2 = {"ok": True, "code": "def run(d):\n    return '2'", "name": "b", "usage": ""}
        pg.unroute("**/api/run-llm")
        pg.route("**/api/run-llm", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(stub2, ensure_ascii=False)))
        pg.fill("#lrPrompt", "第二个需求")
        pg.click("#lrGen")
        pg.wait_for_timeout(800)
        check("C7 无用法时清空并隐藏",
              (not pg.is_visible("#lrUsage")) and pg.inner_text("#lrUsage").strip() == "")
        # 第三轮：新建必须清掉上一轮用法说明（v2.6.4 回归点）
        pg.route("**/api/run-llm", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(stub, ensure_ascii=False)))
        pg.fill("#lrPrompt", "第三个需求")
        pg.click("#lrGen")
        pg.wait_for_timeout(800)
        shown = pg.is_visible("#lrUsage") and "数据点写法" in pg.inner_text("#lrUsage")
        check("C8 生成后用法框再次出现（前置）", shown)
        pg.click("#lrNew")
        pg.wait_for_timeout(400)
        check("C9 新建后用法框清空并隐藏",
              (not pg.is_visible("#lrUsage")) and pg.inner_text("#lrUsage").strip() == "")
        check("C10 新建后代码框同时清空", pg.input_value("#lrCode").strip() == "")

        # ── v2.6.5：用法说明随 run 持久化（保存写入 .py 注释、载入解析回来）──
        TESTRUN = "__uittest_usage"
        pg.fill("#lrPrompt", "持久化用例")
        pg.click("#lrGen")
        pg.wait_for_timeout(800)
        check("C11 生成后用法框可见（保存前置）", pg.is_visible("#lrUsage"))
        pg.fill("#lrName", TESTRUN)
        pg.click("#lrSave")
        pg.wait_for_timeout(1000)
        saved = pg.evaluate(
            """async (nm) => {
                 const r = await fetch('/api/runs?name=' + encodeURIComponent(nm));
                 const j = await r.json();
                 return (j && j.ok) ? j.code : ('ERR ' + JSON.stringify(j));
               }""", TESTRUN)
        check("C12 .py 里写入用法注释",
              ("# 数据点写法：" in saved) and ("# 执行点写法：" in saved),
              repr(saved[:80]))
        # 重复保存幂等（不得越存越多）
        pg.click("#lrSave")
        pg.wait_for_timeout(800)
        saved2 = pg.evaluate(
            """async (nm) => {
                 const r = await fetch('/api/runs?name=' + encodeURIComponent(nm));
                 const j = await r.json();
                 return (j && j.ok) ? j.code : '';
               }""", TESTRUN)
        check("C13 重复保存幂等（用法注释不叠加）",
              saved2.count("# 数据点写法：") == 1, "count=%d" % saved2.count("# 数据点写法："))
        # 新建清空 → 从列表载入 → 用法恢复
        pg.click("#lrNew")
        pg.wait_for_timeout(400)
        check("C14 新建后用法框隐藏（载入前置）", not pg.is_visible("#lrUsage"))
        pg.click("div.lr-item:has-text('%s') .lr-nm" % TESTRUN)
        pg.wait_for_timeout(900)
        restored = pg.inner_text("#lrUsage") if pg.is_visible("#lrUsage") else ""
        check("C15 载入已保存 run 后用法说明恢复",
              ("数据点写法" in restored) and ("执行点写法" in restored), repr(restored[:40]))
        check("C16 载入后 code 不含重复用法行",
              pg.input_value("#lrCode").count("# 数据点写法：") == 1)

        # ── v2.6.6：多行「数据点写法」，存取不丢 ──
        TESTRUN2 = "__uittest_multi"
        USAGE2 = ("数据点写法：@@ MDE_甲{今天遇到…中国话。}（产生 str）\n"
                  "数据点写法：@@ MDE_甲{你好,中国话}（产生 list[str]）\n"
                  "执行点写法：@@ MDE from wordcount import count is 甲\n"
                  "返回值：你好 出现 2 次；中国话 出现 1 次\n"
                  "注意：两行同一个池名，自动合并")
        CODE2 = ("# run-name: wordcount\n"
                 "# 依据：形式1 + 形式3\n"
                 "def count(data):\n"
                 "    return 'x'")
        pg.unroute("**/api/run-llm")
        pg.route("**/api/run-llm", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "code": CODE2, "name": "wordcount",
                             "usage": USAGE2}, ensure_ascii=False)))
        pg.click("#lrNew")
        pg.wait_for_timeout(300)
        pg.fill("#lrPrompt", "统计正文里若干关键词")
        pg.click("#lrGen")
        pg.wait_for_timeout(800)
        u2 = pg.inner_text("#lrUsage") if pg.is_visible("#lrUsage") else ""
        check("C17 多行用法说明全部显示", u2.count("数据点写法") == 2, repr(u2[:60]))
        pg.fill("#lrName", TESTRUN2)
        pg.click("#lrSave")
        pg.wait_for_timeout(1000)
        saved3 = pg.evaluate(
            """async (nm) => {
                 const r = await fetch('/api/runs?name=' + encodeURIComponent(nm));
                 const j = await r.json();
                 return (j && j.ok) ? j.code : ('ERR ' + JSON.stringify(j));
               }""", TESTRUN2)
        check("C18 .py 里两行数据点写法都在",
              saved3.count("# 数据点写法：") == 2,
              "count=%d" % saved3.count("# 数据点写法："))
        pg.click("#lrNew")
        pg.wait_for_timeout(300)
        pg.click("div.lr-item:has-text('%s') .lr-nm" % TESTRUN2)
        pg.wait_for_timeout(900)
        rest2 = pg.inner_text("#lrUsage") if pg.is_visible("#lrUsage") else ""
        check("C19 载入后多行用法完整恢复", rest2.count("数据点写法") == 2, repr(rest2[:60]))
        pg.evaluate(
            """async (nm) => { await fetch('/api/runs?name=' + encodeURIComponent(nm),
                 {method:'DELETE'}); }""", TESTRUN2)
        # 清理测试条目
        pg.evaluate(
            """async (nm) => { await fetch('/api/runs?name=' + encodeURIComponent(nm),
                 {method:'DELETE'}); }""", TESTRUN)
        b.close()

    if httpd is not None:
        httpd.shutdown()


# ---------- F 上下标渲染（v2.6.10） ----------
def _ensure_server():
    if port_in_use():
        return None
    sys.argv = ["md_server.py"]
    import md_server
    httpd = md_server.ReuseTCPServer(("127.0.0.1", 18766), md_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    return httpd


def markup_tests():
    """^{...} → <sup>、_{...} → <sub>：LaTeX 写法不加 $ 直接进正文。"""
    httpd = _ensure_server()
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page()
            pg.goto("http://127.0.0.1:18766/")
            pg.wait_for_timeout(1200)
            got = pg.evaluate("t => parseInline(t)", "A^{[1]}B^{世界之光}C_{2}D")
            check("F1 ^{} 渲染上标（编号/数字/中文）",
                  ("<sup>[1]</sup>" in got) and ("<sup>世界之光</sup>" in got), got)
            check("F2 _{} 渲染下标", "<sub>2</sub>" in got, got)
            got = pg.evaluate("t => parseInline(t)", "x_{a} 与 y_{b}")
            check("F3 多个 _{} 不被 _.._ 斜体吃掉", got.count("<sub>") == 2, got)
            got = pg.evaluate("t => parseInline(t)", r"\^{1}")
            check("F4 反斜杠转义保留字面", ("<sup>" not in got) and ("^{1}" in got), got)
            got = pg.evaluate("t => parseInline(t)", "^{未闭合")
            check("F5 缺右花括号原样", "<sup>" not in got, got)
            b.close()
    finally:
        if httpd:
            httpd.shutdown()


def docx_markup_tests():
    """docx 导出：<sup>/<sub> → Word 上下标位。
    用便携解释器跑：系统 Python 与内置 lxml 4.9.2 的扩展 ABI 不兼容。"""
    app = os.path.dirname(os.path.abspath(__file__))
    script = (
        "import io, os, sys, zipfile\n"
        "APP = r'%s'\n"
        "sys.path.insert(0, APP)\n"
        "sys.path.insert(0, os.path.join(APP, 'docxdeps'))\n"
        "import docx_export\n"
        "h = '<div class=\"markdown-body\"><p>正文<sup>[1]</sup>与<sub>2</sub>结束</p></div>'\n"
        "d = docx_export.build_docx(None, h, '', None)\n"
        "p = os.path.join(os.environ.get('TEMP', '.'), '_mda_sup_test.docx')\n"
        "io.open(p, 'wb').write(d)\n"
        "with zipfile.ZipFile(p) as z:\n"
        "    xml = z.read('word/document.xml').decode('utf-8')\n"
        "os.remove(p)\n"
        "print(int('w:val=\"superscript\"' in xml),\n"
        "      int('w:val=\"subscript\"' in xml),\n"
        "      int(all(t in xml for t in ('正文', '[1]', '结束'))))\n"
    ) % app
    py = os.path.join(app, "python", "python.exe")
    r = subprocess.run([py, "-X", "utf8", "-c", script], capture_output=True)
    out = r.stdout.decode("utf-8", "replace").strip().split()
    detail = (r.stdout[-160:] + r.stderr[-200:]).decode("utf-8", "replace") if not out else str(out)
    check("F6 docx 上标位（superscript）", out[:1] == ["1"], detail)
    check("F7 docx 下标位（subscript）", out[1:2] == ["1"], detail)
    check("F8 docx 文本不丢", out[2:3] == ["1"], detail)


RUN_MODE_BTN = {"instant": "#lrModeInstant", "manual": "#lrModeManual"}


def _read_run_mode():
    """运行模式的权威值：编辑器目录 runtime/ui-settings.json 的 md-editor-run-mode。"""
    app = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(app, "runtime", "ui-settings.json")
    try:
        raw = json.load(io.open(cfg, encoding="utf-8")).get("md-editor-run-mode") or "{}"
        return (json.loads(raw) if isinstance(raw, str) else raw).get("mode") or "instant"
    except Exception:
        return "instant"


def _set_run_mode(pg, mode):
    """通过 run 面板按钮切模式（与用户操作同一条路，会写回 ui-settings.json）。"""
    sel = RUN_MODE_BTN.get(mode)
    if not sel:
        return
    pg.evaluate("document.getElementById('lrOverlay').hidden=false")
    pg.click(sel)
    pg.wait_for_timeout(400)


def replay_tests():
    """手动模式：改别处不许把运行结果吃掉；数据真变了才回落待运行。
    块级重建是 div.innerHTML=parseMarkdown(...)，节点状态全丢，靠 runCache 重放兜。"""
    app = os.path.dirname(os.path.abspath(__file__))
    runs = os.path.join(app, "runtime", "runs")
    lib = os.path.join(runs, "_selftest_replay.py")
    doc1 = ("# 标题\n\n@@ MDE_甲{A == 3, B == 4}\n\n"
            "@@ MDE import _selftest_replay is 甲\n\n另一个块的内容。\n")
    doc2 = doc1.replace("A == 3", "A == 5")
    # 唯一文件名：编辑器会自动保存回原文件，固定名会让上一次的 doc2 污染下一次的 doc1
    tmp = os.path.join(os.environ.get("TEMP", "."),
                       "mda_replay_%s.md" % uuid.uuid4().hex[:8])
    httpd = _ensure_server()
    from playwright.sync_api import sync_playwright
    try:
        io.open(lib, "w", encoding="utf-8").write(
            "# run-name: _selftest_replay\n"
            "def run(data):\n"
            "    return '结果:' + ','.join(str(v) for v in data['kv'].values())\n")
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(doc1)
        import urllib.parse
        url = ("http://127.0.0.1:18766/?file=" + urllib.parse.quote(tmp)
               + "&t=" + uuid.uuid4().hex[:6])
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(url)
            pg.wait_for_timeout(1200)
            old_mode = _read_run_mode()
            try:
                # 模式走 UI 按钮切换（服务端 ui-settings.json 才是权威来源，
                # 只写 localStorage 会被它盖掉），测完按原值点回去
                _set_run_mode(pg, "manual")
                pg.reload()
                pg.wait_for_timeout(1500)
                if "A == 3" not in pg.inner_text("#editor"):
                    # 上一轮自动保存可能抢在删除后回写，重写一次再载入
                    with io.open(tmp, "w", encoding="utf-8") as f:
                        f.write(doc1)
                    pg.reload()
                    pg.wait_for_timeout(1500)
                pg.locator(".mde-run .mde-run-btn").first.click()
                pg.wait_for_timeout(1500)
                base = pg.locator(".mde-run").first.inner_text().strip()
                check("F9 手动运行出结果", "结果:3,4" in base, base)
                # 改执行点所在块（块要重建）→ 必须重放，不许变待运行
                pg.click("#editor")
                pg.keyboard.press("Control+Home")
                for _ in range(4):
                    pg.keyboard.press("ArrowDown")
                pg.keyboard.press("End")
                pg.keyboard.type(" ")
                pg.wait_for_timeout(2000)
                got = pg.locator(".mde-run").first.inner_text().strip()
                check("F10 改执行点所在块结果保留", got == base, got)
                # 数据真变（A:3→5）→ 必须回落待运行，不许拿旧结果冒充
                pg.click("#editor")
                pg.keyboard.press("Control+a")
                pg.keyboard.type(doc2)
                pg.wait_for_timeout(2000)
                got2 = pg.locator(".mde-run").first.inner_text()
                check("F11 数据变了回落待运行", "待运行" in got2, got2)
                check("F12 无页面报错", not errs, str(errs[:3]))
            finally:
                try:
                    _set_run_mode(pg, old_mode or "instant")
                except Exception:
                    pass
            b.close()
    finally:
        for f in (lib, tmp):
            try:
                os.remove(f)
            except OSError:
                pass
        if httpd:
            httpd.shutdown()


parse_tests()
prompt_tests()
spec_vs_parser()
specimen_runs()
ui_tests()
markup_tests()
docx_markup_tests()
replay_tests()

print("")
print("RESULT:", "PASS" if not fails else ("FAIL " + str(fails)))
sys.exit(0 if not fails else 1)
