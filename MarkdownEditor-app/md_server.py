# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""
MD 编辑器本地后端 + 系统托盘（纯标准库，零第三方依赖）
- 标准库 http.server 提供页面 / 读文件 / 写文件路由
- 仅在 127.0.0.1 监听，单实例（由 md_launch.pyw 负责端口占用检测）
- 托盘用 ctypes 直接调用 Shell_NotifyIcon，无 pystray；失败则降级无托盘常驻
- LLM 客户端（润色/注解）为纯标准库 urllib 实现，见 llm_client.py
本文件与 markdown-editor.html 一同分发，配合内置 python/ 即可在任意 Windows 运行。
"""
import http.server
import hashlib
import io
import base64
import time
import subprocess
import tempfile
import socketserver
import socket
import shutil
import threading
import os
import sys
import json
import re
import atexit
import zipfile
import urllib.parse
import urllib.request
import webbrowser
import html as html_module

try:
    if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import llm_client as _llm
except Exception as _e:
    _llm = None
    try:
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime"), exist_ok=True)
        with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "runtime", "_llm.err"), "w", encoding="utf-8") as _f:
            _f.write(repr(_e))
    except Exception:
        pass

try:
    if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rag_client as _ragc
    import web_search as _ws_mod
except Exception as _e:
    _ragc = None
    _ws_mod = None
    try:
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime"), exist_ok=True)
        with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "runtime", "_ragc.err"), "w", encoding="utf-8") as _f:
            _f.write(repr(_e))
    except Exception:
        pass

PORT = 18766
HERE = os.path.dirname(os.path.abspath(__file__))
EDITOR_HTML = os.path.join(HERE, "markdown-editor.html")
MD_SERVER_VERSION = 99  # 每次服务端路由/能力变更时 +1；md_launch 依此自愈换代
SETTINGS_PATH = os.path.join(HERE, "runtime", "settings.json")

# ---------- low runner（v2.4）：文档内参数值的自动化计算 ----------
# run 库（编辑器级统一管理，所有文档共用；分发 = 拷 runs 目录）。
# 三方包：pip --target runtime/pylibs 安装，执行时挂 PYTHONPATH——
# 编辑器只管通道不管装包（集成边界）。run 代码 cwd=run_cache（作图落此处）。
RUNS_DIR = os.path.join(HERE, "runtime", "runs")
PYLIBS_DIR = os.path.join(HERE, "runtime", "pylibs")
RUN_CACHE_DIR = os.path.join(HERE, "runtime", "run_cache")
PORTABLE_PY = os.path.join(HERE, "python", "python.exe")

# 子进程一律不带控制台（v2.9.0 修）：本服务跑在 pythonw.exe 里（GUI 子系统、
# 无控制台），被拉起的 python.exe 是控制台程序——不指定 CREATE_NO_WINDOW 时
# Windows 必须为每个子进程新建一个 conhost.exe。实测（pythonw 当父进程，8 次
# run 一组）：无 flags 均 0.386s、净增 2 个 conhost；带 flags 均 0.058s、净增 0。
# 更要紧的是控制台初始化失败会弹「应用程序无法正常启动(0xc0000142)」，进程挂在
# 对话框上不退出，父进程等 stdout EOF 等满 10s 才 kill，前端误报"执行超时"。
# 非 Windows 上该常量为 0，等价于不传。
_NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
for _d in (RUNS_DIR, RUN_CACHE_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception:
        pass

# UI 状态服务端持久化（v2.0.x）：WebView2 内嵌窗口下 localStorage 只活在内存
# （关窗进程终止，异步刷盘从未发生——实测 userdata leveldb 自安装日起零增长）。
# 排版/主题/视图/跟随/最近文件/草稿等 UI 状态单一来源 = 本文件；前端启动时
# 同步拉取回放进 localStorage（后续代码照旧读 LS，零侵入），写入经 lsSet
# 节流后 POST 增量合并到此。原子写（tmp+replace）+ 线程锁防多窗口并发竞态。
UI_SETTINGS_PATH = os.path.join(HERE, "runtime", "ui-settings.json")
_UI_LOCK = threading.Lock()


def _ui_settings_read():
    try:
        with io.open(UI_SETTINGS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ui_settings_write(d):
    try:
        os.makedirs(os.path.dirname(UI_SETTINGS_PATH), exist_ok=True)
        tmp = UI_SETTINGS_PATH + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, UI_SETTINGS_PATH)
    except Exception:
        pass

# .smd 自包含文档格式（v1.2.0）；导入失败落错误日志，相关路由返回明确错误而非静默
try:
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import _smd
except Exception as _e:  # embedded Python 下兜底，与 md_assets 同模式
    _smd = None
    try:
        os.makedirs(os.path.join(HERE, "runtime"), exist_ok=True)
        with io.open(os.path.join(HERE, "runtime", "_smd.err"), "w", encoding="utf-8") as _f:
            _f.write(repr(_e))
    except Exception:
        pass


def _rewrite_assets_ref(text, old, new):
    """把文档内 "old/..." 资源引用改写为 "new/..."（.smd 打包/导出的路径契约换算）。

    old/new 均为不含尾斜杠的目录引用，如 "我的文档.assets"（磁盘契约）或
    "assets"（.smd 包内契约）。左边界断言 (?<![\\w\\-.]) 防止误伤更长名字的
    尾段（如 "xA.assets" 不会被 "A.assets" 命中，"Xassets/" 不会被 "assets" 命中）。
    返回 (新文本, 替换次数)。
    """
    if not text or not old or old == new:
        return text, 0
    pat = re.compile(r"(?<![\w\-.])" + re.escape(old) + r"/")
    out, n = pat.subn(new + "/", text)
    return out, n


# ---------------------------------------------------------------------------
# 批注与 LLM 配置持久化
#   .md  → 同目录 <文档名>.assets/annotations.json
#   .smd → 解包目录 assets/annotations.json（随包分发，_smd.PROTECTED 豁免清理）
# ---------------------------------------------------------------------------
ANNOT_NAME = "annotations.json"
LLM_DEFAULTS = {"backend": "lmstudio", "base_url": "", "model": "", "api_key": "",
                "timeout": 180, "max_tokens": 2048, "temperature": 0.7,
                "web_search": None}   # web_search 由 _norm_web_search_config 填充
WS_DEFAULTS = {"enabled": False, "backend": "duckduckgo", "api_key": "",
               "google_key": "", "google_cx": "", "bing_key": "",
               "custom_url": "", "max_results": 3}
_WS_BACKENDS = ("duckduckgo", "tavily", "google", "bing", "custom")


def _load_json(path, default):
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _annotations_path(doc_path):
    if _smd is not None and _smd.is_smd(doc_path):
        return os.path.join(_smd.base_dir_for(doc_path), _smd.ASSETS_DIR, ANNOT_NAME)
    stem = os.path.splitext(os.path.basename(doc_path))[0]
    return os.path.join(os.path.dirname(doc_path), stem + ".assets", ANNOT_NAME)


def _smd_tmp_backups(smd_path):
    """列出某文档未完成的保存备份（<文档名>.tmp<毫秒时间戳>），按时间升序。

    保存失败时 tmp 故意保留：会话结束解包工作目录会被 clear_tmp 清掉，
    它是本次内容跨会话的唯一幸存副本（打开文档时提供恢复入口）。
    """
    d = os.path.dirname(smd_path)
    base = os.path.basename(smd_path)
    if not d or not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        m = re.match(re.escape(base) + r"\.tmp(\d+)$", fn)
        if m and os.path.isfile(os.path.join(d, fn)):
            out.append((int(m.group(1)), os.path.join(d, fn)))
    out.sort()
    return [fp for _, fp in out]


def _friendly_save_error(e, path):
    """保存失败 → 说人话。只读目标是高频根因（OneDrive/手工设置 R 属性）。"""
    if not isinstance(e, OSError):
        return str(e)
    ro = False
    try:
        if os.path.exists(path):
            ro = not (os.stat(path).st_mode & 0o222)
    except OSError:
        pass
    if ro:
        kept = ""
        try:
            tmps = _smd_tmp_backups(path)
            if tmps:
                kept = "\n本次内容已保留在 %s（重新打开本文档时可恢复）" % tmps[-1]
        except OSError:
            pass
        return ("目标文件为只读（可能被 OneDrive 或手工设置了只读属性），"
                "请解除只读后重新保存。%s" % kept)
    return str(e)


def _norm_llm_config(cfg):
    """LLM 配置归一：backend 白名单、数值限幅，防手写 settings.json 脏数据打崩客户端。"""
    cfg = cfg if isinstance(cfg, dict) else {}
    out = dict(LLM_DEFAULTS)
    backend = str(cfg.get("backend") or "").lower()
    if backend in ("lmstudio", "ollama", "openai"):
        out["backend"] = backend
    for k in ("base_url", "model", "api_key"):
        v = cfg.get(k)
        out[k] = v.strip() if isinstance(v, str) else ""
    for k, lo, hi in (("timeout", 5, 600), ("max_tokens", 64, 32768)):
        try:
            out[k] = max(lo, min(hi, int(cfg.get(k, out[k]))))
        except Exception:
            pass
    try:
        out["temperature"] = max(0.0, min(2.0, float(cfg.get("temperature", out["temperature"]))))
    except Exception:
        pass
    out["web_search"] = _norm_web_search_config(cfg.get("web_search"))
    return out


def _norm_web_search_config(cfg):
    """联网查询子配置归一：backend 白名单、布尔/数值限幅（模式同 rag-assistant）。"""
    cfg = cfg if isinstance(cfg, dict) else {}
    out = dict(WS_DEFAULTS)
    out["enabled"] = bool(cfg.get("enabled"))
    backend = str(cfg.get("backend") or "").lower()
    if backend in _WS_BACKENDS:
        out["backend"] = backend
    for k in ("api_key", "google_key", "google_cx", "bing_key", "custom_url"):
        v = cfg.get(k)
        out[k] = v.strip() if isinstance(v, str) else ""
    try:
        out["max_results"] = max(1, min(10, int(cfg.get("max_results", out["max_results"]))))
    except Exception:
        pass
    return out


def _llm_saved_config():
    settings = _load_json(SETTINGS_PATH, {})
    cfg = settings.get("llm") if isinstance(settings, dict) else None
    return _norm_llm_config(cfg if isinstance(cfg, dict) else {})


def _llm_config_from_request(obj):
    """按请求携带的 config（未保存的表单值）归一配置；未携带则用已存配置。"""
    cfg = obj.get("config") if isinstance(obj, dict) else None
    return _norm_llm_config(cfg) if isinstance(cfg, dict) else _llm_saved_config()


def _llm_from_request(obj):
    """按请求携带的 config（未保存的表单值）构造 LLMClient；未携带则用已存配置。"""
    if _llm is None:
        raise _LLM_ERR("llm_client.py 加载失败，详见 runtime/_llm.err")
    return _llm.LLMClient(_llm_config_from_request(obj))


_LLM_ERR = _llm.LLMError if _llm is not None else RuntimeError


# ---------------------------------------------------------------------------
# low runner 执行器（v2.4）
# ---------------------------------------------------------------------------
# LLM 生成 run 的系统提示词（v2.4.2→v2.6 演进）。
# v2.6 全面重写（用户三要求：明确规范 / 举例 / 正反例并指出错在哪）：
# 数据契约 = 前端传入的固定类型集（六形式 → kv/vals/raw/marks 四通道，
# 全 Python 原生类型），LLM 按契约生成不会错位；三方包转换路径明牌。
# 历史纪律保留的：A 幻觉函数（product 非内置）/ B 顶层函数可导入 /
# 中文无空格分词；D 类角色映射纪律由结构化通道取代（框架已给结构）。
# 原则（v2.4.3 用户纠偏，不变）：三方库正规不劝退；场景中性；
# run 库是源头不从文档反推。
_LR_LLM_SYS = """你是 MDEditor low runner 的代码生成器。产物固定两段：① 一段 Python 代码（存进 run 库）；② 一份用法说明（用户照抄就能跑）。用法说明里写的每一行数据点、每一行执行点，都是用户要原样粘进文档的可执行 MDE 语法。

═══ 一、代码能拿到什么：data 只有四个键 ═══
data['kv']    dict，键与值都是 str（数字也是字符串）
data['vals']  list，元素只有四种形状，按用户的写法决定（见二）：
              1) str                     一段文字
              2) list[str]               一串值
              3) list[list[str]]         二维（行 × 列，单元格全 str）
              4) list[list[list[str]]]   三维（多张二维表）
              元素按文档里出现的顺序排列；不同形状可以混在同一个 list 里。
data['raw']   list[str]，数据点的原文（含 == 与 (( )) 等语法字符）。它是原文备份，不是正文、不是全文、不含任何标记。
data['marks'] 只有 global 执行点才有，见三-b。

═══ 二、用户能写的数据点：六种形式（全部，没有第七种） ═══
格式：编号｜用户写法｜屏幕上显示什么｜data 里产生什么
1 单值文本｜@@ MDE_甲{今天买了苹果}｜原文｜vals += "今天买了苹果"（str）
2 单键值对｜@@ MDE_甲{苹果 == 3}｜3｜kv["苹果"] = "3"
3 纯值向量｜@@ MDE_甲{3,4,5}｜原文｜vals += ["3","4","5"]（list[str]）
4 键值对向量｜@@ MDE_甲{A == 3, B == 4}｜3、4｜kv 合并 {"A":"3","B":"4"}
5 行文抽取｜@@ MDE_甲{…上涨((8%))，同比上涨((1.5%))}｜去掉 (()) 的句子｜vals += ["8%","1.5%"]（list[str]）
  键值版：((A == 8%))｜显示 8%｜kv["A"] = "8%"
6 二维表｜@@ MDE_甲:2(2x2){ 表格行 }｜渲染成真表格（整张原表）｜vals += [["tony","59"],["lily","18"]]
  三维表｜@@ MDE_甲:3(){ 多张二维表，空行分隔 }｜渲染成多张真表格｜vals += [[[...],[...]],[[...]]]

这六种形式被解释时必须知道的规则（决定 data 的真实形状）：
- 半角逗号 , 是向量分隔符；全角 ， 与顿号 、 是普通字。
- 表格行按 Markdown 写（每行以 | 起止）；:2 是二维、:3 是三维；坐标 (rxc) 为 1-based 起点，() 表示全表；表头下面的 |:-|:-| 是结构行，不计入坐标也不进数据。
- 一个数据点的 body 只有一行时按上面语法解析；body 跨行时一律当整段文字（形式1）。
- 语法不合规（直写与 (()) 混用、(( 未闭合、坐标越界、键值段缺 ==、:2 里放多张表）→ 整个数据点按普通文字显示，不产生任何数据。这种失效是静默的：代码只能通过"没收到数据"发现。
- 池名：@@ MDE_甲 只喂 is 甲 的执行点；@@ MDE__甲 是隐性的（屏幕不显示，只供数据）；@@ MDE_ 是公共池。
- 同一池名可以写多行数据点，自动合并进同一个 data。
- kv 是 dict：同名键**后写的覆盖先写的**，所以一组键值对里名字必须各不相同。

═══ 三、执行点：两种形式（全部） ═══
a) 普通
   写法：@@ MDE import 库名 is 池名 ／ @@ MDE from 库名 import 函数名 is 池名
   没有 is → 吃公共池。data 只有 kv / vals / raw 三个键。
   框架把函数返回值直接显示在执行点位置，按形状渲染、不做猜测：
     · 单行 str → 行内文本（粗体、行内码、链接可用），就在执行点原位
     · 多行 str（字符串里带真换行 \\n）→ 逐行显示
     · 表格 → 字符串里写出表头行 + 分隔行（|---|---|）+ 数据行，
       前端渲染成真表格，分隔行只定列数与对齐、自身不显示；
       缺分隔行就不认表格，整段原样当文字
       例：return "|项目|一月|\\n|---|---|\\n|收入|100|\\n|成本|60|"
     · list（非 global）→ 逐元素 str 后用逗号连成一行
   表格单元格里的竖线写成 \\|；单元格内不能换行、不能合并单元格。
   返回值里出现 @@ MDE… 或 '''标记 只当普通文字，不会生成数据点。
   图片：当前目录＝文档资产目录，写这里，返回 "![](x.png)"，别写绝对路径。
   kv 里的本地文件值已是绝对路径，直接 open(值,'rb')；解析自己定，只用标准库。
b) 全局 global
   写法：@@ MDE from 库名 import 函数名{global 标记名}（import 库名{global 标记名} 亦可；is 池 可与 global 并存，此时 data 同时带池数据）
   执行点自身不显示。
   标记 = 正文里的三单引号加名字：'''标记名。
   框架全文扫描该标记的每一处，按文档顺序放进 data['marks']：
     每项 {'mark': '标记名', 'ctx': '该标记所在那一段的文字（截断）'}
   函数必须返回 list[str]，长度等于 len(data['marks'])；第 i 项替换第 i 个标记。
   返回非 list、或长度不符 → 按执行失败处理，标记保持原文 '''标记名。
   替换只做一轮：替换文本里若再出现 '''标记名 不会被再次展开。
   '''标记名 在文档里本来是普通文字，只有被 {global} 接管时才替换；没声明就没变化。

═══ 四、代码怎么消费这些形状 ═══
- 一段文字 → vals 里的 str 元素
- 一串值   → vals 里的 list 元素，遍历它的元素
- 名字→值  → data['kv'] 的 items()/values()
- 表格     → vals 里的嵌套 list，先行后列
- 全文标记 → data['marks']
用户写的是哪种形式，就决定它落在哪种形状；代码必须按形状分支（isinstance），不能假设 vals[0] 一定是数字、也不能假设某形状一定存在。
两条硬规矩：
- **vals 是"装着不同形状的容器"，不是"一串值"本身**。每个元素都要先判形状再消费：
  isinstance(item, list) 才是向量/表格。禁止把整个 vals 直接 join / sum / 当 list[str] 用
  ——那会拿 list 去当字符串拼，当场 TypeError。
- **代码里每一处读 data（kv / vals / raw / marks），都必须在用法说明里对得上一行数据点**；
  对不上就是代码要了用户没给的东西。用 data['kv']['某名'] 却没有任何一行数据点写 `某名 == 值`，
  就是错（要么改成遍历 kv.values()，要么在用法说明里补上该键的数据点）。

═══ 五、写代码前先定两件事 ═══
1) 执行点用哪种：需要"全文某个标记的每一处"→ global；其余 → 普通。
2) 数据点写几行、每行哪种形式：把代码要吃的每一样东西列出来，每一样选**一种**形式。
   选择的唯一依据是那样东西的**形状**——整段文字／一串独立值／名字→值／一句话里的几个值／表格；
   不是它像哪个例子。一行数据点只产生一种形状；要两种形状就写两行（同一池名自动合并）。
   global 执行点不需要数据点，除非它还要额外吃池数据（is 池 与 global 并存）。
   判定结果写进代码第二行注释，并原样落进用法说明。

═══ 六、违反即废的硬约束 ═══
- 禁 input()、sys.stdin（后台子进程无人按键，当场 EOF），禁 print（stdout 被框架独占传结果）。
- 代码需要的每一样东西都必须在 data 里指得出来；指不出来 → 返回一句说明文字（如 '未找到关键词，请在数据点里写一行词列表，如 {你好,中国话}'），不提问、不用 0 或空串冒充结果。
- 只许用二的六种写法，禁止自造（例如把 (()) 当向量容器装一串独立值；一行数据点兼两种形状 —— 一行只能产一种形状）。
- 禁止猜用户的键名（if k in ['苹果','A','B']）；代码自己在用法说明里约定的键名可以按名取，但必须写进用法说明让用户照着填。
- 一个操作一个顶层 def；禁止把多个操作合并进一个 def、禁止加参数开关；run(data) 只做汇总。
- 返回值显式转成 str（numpy 数值、None、dict 都要转），否则显示不可控。
- 用户指定了输出形态就逐字照办：说 ^[x] 就产出 ^[1]、^[2]，不要自行加 {}、** 等修饰；用法说明里的「返回值」必须与代码实际输出逐字一致。
- 输出里要出现字面 { 或 } 字符时，str.format() 与 f-string 里的花括号必须双写（{{ }}），或改用 % / 字符串拼接；单写会被当成替换字段 —— '^{[{}]}'.format(1) 直接抛 'int' object is not subscriptable。
- 中文没有空格分词：统计用 count 子串，不要 split()。

═══ 七、两个语法标本（只示范两段输出的形状；判定按五，不要照抄标本的语义） ═══
标本 A（普通执行点）：
```python
# run-name: flat
# 依据：普通执行点；一行数据点产一种形状，代码按形状分支
def run(data):
    out = []
    for item in data['vals']:
        if isinstance(item, list):
            for row in item:
                if isinstance(row, list):
                    out.extend(str(c) for c in row)
                else:
                    out.append(str(row))
        else:
            out.append(str(item))
    for v in data['kv'].values():
        out.append(str(v))
    if not out:
        return '没有收到数据，请检查数据点写法'
    return ' / '.join(out)
```
```text
数据点写法：@@ MDE_甲{A == 3, B == 4}（产生 kv，一组名字→值）
执行点写法：@@ MDE import flat is 甲
返回值：3 / 4
注意：vals 四种形状与 kv 都会被吃；没有任何数据时返回提示文字
```
标本 B（global 执行点）：
标本里的替换文本（#1）只是占位，不是格式规范：用户说 ^[x] 就输出 ^[1]、^[2]，不要自行加 {} 等修饰。
```python
# run-name: indexes
# 依据：global 执行点；data['marks'] 每项一处标记，返回等长列表逐个替换
def run(data):
    marks = data.get('marks') or []
    return ['#%d' % (i + 1) for i in range(len(marks))]
```
```text
数据点写法：无（global 的标记本身就是数据源）
执行点写法：@@ MDE from indexes import run{global p}
返回值：正文每处 '''p 依次替换成 #1、#2…
注意：返回 list 长度必须等于标记数；少一个即整点失败、标记保持原文
```

═══ 八、输出格式（严格两段，多一个字都不要） ═══
1) 一个 ```python 代码块：首行 # run-name: 短名（英文小写+下划线，即入库名）；第二行 # 依据：<形式编号或 global> + 一句判定；然后是代码。
2) 紧跟一个 ```text 块，行序固定：
   数据点写法：<可原样粘贴的一行>（这一行产生什么形状）
   ……每个数据点 1 行；如果不需要数据点，写「数据点写法：无」
   内容必须取自**用户文档里的实际内容，或末尾给的「当前文档数据点样例」**——
   禁止把二的语法说明行原样搬过来充数（那是语法示意，不是用户数据）；也禁止写
   「段落内容」「词1」「示例文本」这类占位符——那一行是要直接粘进文档跑的，占位符等于没做完。
   执行点写法：<@@ MDE …>
   ……每个函数 1 行
   返回值：<照上面写法真算出来的具体结果；global 写它替换成什么>
   注意：<值的约束、空数据时的行为>
输出前自检一遍（不通过就重写，不许把问题留给用户）：
① 代码里每一次读 data，都能在上面某一行数据点里找到来源（键名、形状都要对得上）；
② vals 的每个元素都判了形状，没有把整个 vals 当 list[str] 直接拼接；
③ 需要几样不同形状的东西，就有几行数据点；
④ 全局执行点返回的是 list，长度跟标记数对得上。
除这两个代码块外，不得输出任何解释、前言、后语。"""


def _lr_valid_name(name):
    """run 库条目名：字母/数字/下划线/连字符/点/中文（\w unicode 含中文）。
    防路径穿越（拒绝 /\ .. 等）。"""
    return bool(re.match(r"^[\w.-]+$", str(name or ""), re.U)) and ".." not in str(name)


def _lr_parse_llm_output(raw):
    """拆模型输出（v2.6.2 输出契约）：
      1) 第一个 ```python 围栏 → code（无围栏则整段当代码，兼容旧行为）
      2) 其后的 ```text/```md/```markdown 围栏 → usage（用户侧用法说明）
      3) usage 缺失但尾巴里有「数据点写法/执行点写法」→ 直接取尾巴
    返回 (code, name, usage)。"""
    s = str(raw or "")
    m = re.search(r"```(?:python|py)?[ \t]*\r?\n([\s\S]*?)```", s)
    if m:
        code = m.group(1).strip()
        rest = s[m.end():]
    else:
        code = s.strip()
        rest = ""
    nm = re.search(r"#\s*run-name\s*[:：]\s*(.+)", code)
    name = nm.group(1).strip() if nm else ""
    usage = ""
    mu = re.search(r"```(?:text|md|markdown)?[ \t]*\r?\n([\s\S]*?)```", rest)
    if mu:
        usage = mu.group(1).strip()
    else:
        tail = rest.replace("```", "").strip()
        if "数据点写法" in tail or "执行点写法" in tail:
            usage = tail
    return code, name, usage


# 常见 import 名 ≠ pip 包名映射（提醒命令要正确）
_LR_PIP_MAP = {
    "PIL": "Pillow", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4", "yaml": "PyYAML", "OpenSSL": "pyOpenSSL",
    "Crypto": "pycryptodome", "dateutil": "python-dateutil",
    "dotenv": "python-dotenv", "attr": "attrs", "skimage": "scikit-image",
    "serial": "pyserial", "usb": "pyusb", "win32com": "pywin32",
    "win32api": "pywin32", "win32gui": "pywin32",
}


def _lr_pip_cmd(module):
    """缺包提醒的安装命令（用户自装：便携包无 pip，任何有 pip 的
    Python 都行，--target 落 pylibs；需 cp311 版本的编译型包）。
    路径动态：PYLIBS_DIR 随 md_server.py 所在目录（拷到哪跟到哪，
    用户 maby_tool 安装位的命令即该位路径——非写死）。
    反斜杠不转义：这是给用户复制进终端的命令原文，单反斜杠即正确
    形态（v2.6.1 前误做双重转义，显示为 C:\\\\Users 形态）"""
    pkg = _LR_PIP_MAP.get(module, module)
    return 'pip install --target "%s" %s' % (PYLIBS_DIR, pkg), pkg


def _lr_missing_from_error(err):
    """错误串 → 缺包结构（module/pip_name/cmd）。仅 ModuleNotFoundError。"""
    m = re.search(r"No module named '([\w.]+)'", str(err))
    if not m:
        return None
    module = m.group(1).split(".")[0]
    cmd, pkg = _lr_pip_cmd(module)
    return {"module": module, "pip_name": pkg, "cmd": cmd}


def _lr_check_deps(code):
    """静态依赖检测：解析 import → 便携 python find_spec → 缺哪些包。
    返回 [{module, installed, pip_name, cmd}]（只含三方包；标准库过滤
    在子进程里用 sys.stdlib_module_names——3.11 支持，与执行环境同源）。"""
    mods = []
    for m in re.finditer(
            r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
            str(code or ""), re.M):
        # 取顶层模块名去重
        top = (m.group(1) or m.group(2) or "").split(".")[0]
        if top and top not in mods:
            mods.append(top)
    if not mods:
        return []
    py = PORTABLE_PY if os.path.exists(PORTABLE_PY) else sys.executable
    driver = (
        "import sys, json, importlib.util\n"
        "mods = json.loads(sys.stdin.read())\n"
        "out = []\n"
        "for m in mods:\n"
        "    if m in sys.stdlib_module_names:\n"
        "        continue\n"
        "    out.append({'module': m,"
        " 'installed': importlib.util.find_spec(m) is not None})\n"
        "sys.stdout.write(json.dumps(out, ensure_ascii=False))\n"
    )
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = PYLIBS_DIR if os.path.isdir(PYLIBS_DIR) else ""
    try:
        cp = subprocess.run(
            [py, "-c", driver],
            input=json.dumps(mods).encode("utf-8"),
            capture_output=True, timeout=15, env=env,
            creationflags=_NO_WIN)
        raw = cp.stdout.decode("utf-8", "replace").strip()
        deps = json.loads(raw) if raw else []
    except Exception:
        return []
    for d in deps:
        cmd, pkg = _lr_pip_cmd(d["module"])
        d["pip_name"] = pkg
        d["cmd"] = cmd
    return deps


def _lr_driver_code(mod, fn):
    """子进程驱动：stdin 喂 data JSON → import 用户模块 → 调函数 → stdout JSON。
    多行字符串经 -c 执行；UTF-8 输入输出由 env（PYTHONIOENCODING）保证。
    v2.6：返回 str（普通执行点）或 list[str]（global 执行点——前端按
    标记顺序逐个替换）；其他类型 str() 化。"""
    return (
        "import sys, json\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "try:\n"
        "    import importlib\n"
        "    m = importlib.import_module(%r)\n"
        "    f = getattr(m, %r)\n"
        "    data = json.loads(sys.stdin.read())\n"
        "    r = f(data)\n"
        "    if isinstance(r, (list, tuple)):\n"
        "        r = [str(x) for x in r]\n"
        "    elif not isinstance(r, str):\n"
        "        r = str(r)\n"
        "    sys.stdout.write(json.dumps({'ok': True, 'result': r},"
        " ensure_ascii=False))\n"
        "except Exception as e:\n"
        "    sys.stdout.write(json.dumps({'ok': False, 'error': str(e)},"
        " ensure_ascii=False))\n"
    ) % (RUNS_DIR, PYLIBS_DIR, mod, fn)


def _doc_ref_base(doc_path):
    """文档里“相对路径”的解析基准：.md → 文档所在目录；.smd → 解包工作目录。
    未保存/文件不存在 → None（调用方自行回落）。"""
    if not doc_path:
        return None
    try:
        p = os.path.abspath(str(doc_path))
    except Exception:
        return None
    if not os.path.isfile(p):
        return None
    if _smd is not None and _smd.is_smd(p):
        try:
            return _smd.base_dir_for(p)
        except Exception:
            return None
    return os.path.dirname(p)


def _doc_assets_dir(doc_path):
    """文档资产目录（图片与外部引用文件的落点，v2.8）：
    .md → <目录>/<文档名>.assets/    .smd → <解包目录>/assets/
    与 /api/paste-image 的落位规则同一口径；未保存 → None。"""
    base = _doc_ref_base(doc_path)
    if not base:
        return None
    try:
        p = os.path.abspath(str(doc_path))
    except Exception:
        return None
    if _smd is not None and _smd.is_smd(p):
        return os.path.join(base, "assets")
    stem = os.path.splitext(os.path.basename(p))[0]
    return os.path.join(base, stem + ".assets")


def _within(path, root):
    """path 是否落在 root 内（拒绝 ../ 穿越；跨盘符安全失败）。"""
    try:
        return (os.path.commonpath([os.path.abspath(path),
                                    os.path.abspath(root)])
                == os.path.abspath(root))
    except Exception:
        return False


# 引用型相对路径：<名>.assets/xxx 或 assets/xxx（v2.8 粘贴外部文件落盘形状）
_ASSET_REL_RE = re.compile(r"^(?:[^/\\]+\.assets|assets)[/\\].+$")


def _lr_expand_refs(node, base):
    """data 里形如 <名>.assets/x / assets/x 的相对路径 → 绝对路径（v2.8）。
    只替换“真实存在且落在 base 内”的文件，其余字符串原样；vals 可嵌套。"""
    if isinstance(node, str):
        s = node.strip()
        if not s or not _ASSET_REL_RE.match(s) or os.path.isabs(s):
            return node
        try:
            ap = os.path.normpath(os.path.join(base, s.replace("\\", "/")))
        except Exception:
            return node
        if not _within(ap, base) or not os.path.isfile(ap):
            return node
        return ap.replace("\\", "/")
    if isinstance(node, list):
        return [_lr_expand_refs(x, base) for x in node]
    if isinstance(node, dict):
        return {k: _lr_expand_refs(v, base) for k, v in node.items()}
    return node


def _drop_empty_dir(d):
    """run 结束后清掉“为当 cwd 临时创建、且仍为空”的资产目录。"""
    try:
        if d and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    except Exception:
        pass


def _safe_asset_name(name):
    """外部引用文件名清洗（v2.8）：去路径、替换数据点分隔符
    （, = { } 与换行会让 @@ MDE 那一行解析错），保留扩展名与原名主干。"""
    n = os.path.basename(str(name or "").replace("\\", "/")).strip()
    if not n or n in (".", ".."):
        return ""
    n = re.sub(r"[,={}\r\n\t]", "_", n).strip().lstrip(".")
    if not n:
        return ""
    if len(n) > 120:
        stem, ext = os.path.splitext(n)
        n = stem[:100] + ext[:20]
    return n


def _lr_rewrite_imgs(result, assets_dir=None, ref_base=None):
    """run 结果里的相对路径图片引用 → /img 代理（v2.8 多基址）：
    文档资产目录优先（run 的 cwd 已是它）、ref_base 兜住 <名>.assets/x 写法、
    run_cache 兜底（旧约定仍可跑）；http/data/file:// 原样不动。"""
    bases = []
    for b in (assets_dir, ref_base, RUN_CACHE_DIR):
        if b and b not in bases:
            bases.append(b)

    def _rw(m):
        alt, src = m.group(1), m.group(2).strip()
        if re.match(r"^(https?:|data:|file:|/)", src):
            return m.group(0)
        for b in bases:
            p = os.path.join(b, src)
            if os.path.isfile(p):
                return "![%s](/img?path=%s)" % (
                    alt, urllib.parse.quote(p.replace("\\", "/")))
        return m.group(0)
    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _rw, result)


def _lr_run(mod, fn, data, doc_path=None):
    """执行 run：便携 python 子进程，超时 10s、stdout 1MB。返回 dict。

    v2.8 文档上下文（doc_path 给出时）：
    - 子进程 cwd = 本文档资产目录 —— run 里 save('x.png') 直接落到能跟着
      文档走的地方；目录不存在则临时创建，跑完仍空即删掉；
    - data 里 <名>.assets/x、assets/x 形式的相对路径展开成绝对路径 ——
      run 只拿到一个能 open() 的地址，怎么解析由 run 自己负责；
    - 结果图片改写多一个基址。
    文档未保存时全部回落 run_cache（旧行为，逐字节一致）。"""
    if not _lr_valid_name(mod) or not _lr_valid_name(fn):
        return {"ok": False, "error": "run 名或函数名不合法"}
    py = PORTABLE_PY if os.path.exists(PORTABLE_PY) else sys.executable
    path = os.path.join(RUNS_DIR, mod + ".py")
    if not os.path.exists(path):
        return {"ok": False, "error": "run 不存在：%s（low runner 界面可创建）" % mod}
    ref_base = _doc_ref_base(doc_path)
    assets_dir = _doc_assets_dir(doc_path)
    if ref_base and isinstance(data, dict):
        for _k in ("kv", "vals", "raw"):
            if _k in data:
                data[_k] = _lr_expand_refs(data[_k], ref_base)
    cwd = RUN_CACHE_DIR
    created = False
    if assets_dir:
        try:
            if not os.path.isdir(assets_dir):
                os.makedirs(assets_dir, exist_ok=True)
                created = True
            cwd = assets_dir
        except Exception:
            cwd = RUN_CACHE_DIR
    code = _lr_driver_code(mod, fn)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = PYLIBS_DIR if os.path.isdir(PYLIBS_DIR) else ""
    try:
        try:
            cp = subprocess.run(
                [py, "-c", code],
                input=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                capture_output=True, timeout=10, cwd=cwd, env=env,
                creationflags=_NO_WIN)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "run 执行超时（>10s）"}
        except Exception as e:
            return {"ok": False, "error": "子进程启动失败：%s" % e}
        out = cp.stdout.decode("utf-8", "replace").strip()
        if len(out) > 1024 * 1024:
            return {"ok": False, "error": "run 输出超过 1MB 限制"}
        try:
            j = json.loads(out)
        except Exception:
            err = cp.stderr.decode("utf-8", "replace").strip()
            if not out and cp.returncode not in (0, None):
                # 一个字都没输出就非零退出 = 进程没跑起来（典型 0xC0000142：
                # 控制台/DLL 初始化失败）。报准确退出码，别误报"输出非 JSON"。
                return {"ok": False, "error": "子进程异常退出（0x%08X）%s"
                        % (cp.returncode & 0xFFFFFFFF,
                           ("：" + err[:300]) if err else "")}
            return {"ok": False, "error": "run 输出非 JSON：%s%s"
                    % (out[:200], ("\nstderr: " + err[:300]) if err else "")}
        if j.get("ok") and isinstance(j.get("result"), (str, list)):
            if isinstance(j["result"], str):
                j["result"] = _lr_rewrite_imgs(
                    j["result"], assets_dir, ref_base)[:1024 * 1024]
            else:
                j["result"] = [_lr_rewrite_imgs(
                    str(x), assets_dir, ref_base)[:1024 * 1024]
                    for x in j["result"]]
            return j
        # 失败：错误串解析缺包（前端跟随错误块显示"缺少包"+ 安装命令）
        miss = _lr_missing_from_error(j.get("error") or "")
        if miss:
            j["missing"] = miss
        return j
    finally:
        if created:
            _drop_empty_dir(assets_dir)


# ---------------------------------------------------------------------------
# RAG（rag-assistant 检索增强）：只检索不生成 —— /api/kb/query 拿上下文，
# 拼进 LLM prompt 后仍走 llm_client 生成；原润色/解释路径零改动。
# 服务端为 rag-assistant 外部 API（:8767），与它的 Web UI（:8765/18765）隔离。
# ---------------------------------------------------------------------------
RAG_PORT = 8767
RAG_DEFAULTS = {"path": "", "kb": ""}   # 路径默认空：分发给谁都是无效值，由用户自填

_rag_lock = threading.Lock()
_rag_process = None        # 本服务拉起的 rag-assistant 子进程（手动启停）
_rag_starting = False      # 冷启动中（后台线程轮询就绪）
_rag_process_stderr = ""   # 子进程崩掉时的 Traceback 摘录（诊断用）

_RAG_SYS_POLISH = (
    "你是一个中文写作润色助手。用户给你一段文本，并附上从其知识库检索到的参考资料。"
    "请结合参考资料润色优化：保持原意、结构、篇幅和 Markdown 标记（#、*、`、链接等）完全不变，"
    "仅优化表达的通顺、准确与书面化，术语与事实尽量与参考资料一致。"
    "只输出润色后的文本，不要解释。\n\n【参考资料】\n%s")

_RAG_SYS_EXPLAIN = (
    "你是一个 Markdown 文档注释助手。用户给出一段文本，并附上从其知识库检索到的参考资料。"
    "请结合参考资料为它写一条简洁的备注/批注：解释它的含义或补充要点，2-4 句，第一人称可省略。"
    "直接输出备注内容，不要引号、不要'备注：'前缀。\n\n【参考资料】\n%s")

_WS_SYS_POLISH = (
    "你是一个中文写作润色助手。用户给你一段文本，并附上联网搜索到的网络资料。"
    "请结合网络资料润色优化：保持原意、结构、篇幅和 Markdown 标记（#、*、`、链接等）完全不变，"
    "仅优化表达的通顺、准确与书面化，事实性内容尽量与网络资料一致。"
    "只输出润色后的文本，不要解释。\n\n【网络资料】\n%s")

_WS_SYS_EXPLAIN = (
    "你是一个 Markdown 文档注释助手。用户给出一段文本，并附上联网搜索到的网络资料。"
    "请结合网络资料为它写一条简洁的备注/批注：解释它的含义或补充要点，2-4 句，第一人称可省略。"
    "直接输出备注内容，不要引号、不要'备注：'前缀。\n\n【网络资料】\n%s")


def _norm_rag_config(cfg):
    """RAG 配置归一：路径与知识库名；key 缺失/脏数据保留默认，防手写 settings.json 打崩。"""
    cfg = cfg if isinstance(cfg, dict) else {}
    out = dict(RAG_DEFAULTS)
    for k in ("path", "kb"):
        v = cfg.get(k)
        out[k] = v.strip() if isinstance(v, str) else out[k]
    return out


def _rag_saved_config():
    settings = _load_json(SETTINGS_PATH, {})
    cfg = settings.get("rag") if isinstance(settings, dict) else None
    return _norm_rag_config(cfg if isinstance(cfg, dict) else {})


def _rag_from_request(obj):
    """按请求携带的 rag 段构造配置；未携带则用已存配置。"""
    cfg = obj.get("rag") if isinstance(obj, dict) else None
    return _norm_rag_config(cfg) if isinstance(cfg, dict) else _rag_saved_config()


def _probe_rag():
    """探测 :8767 是否在线。先 socket 短超时探端口（毫秒级~0.5s，且 IPv4
    直连绕开 localhost→IPv6 解析），端口活着才走 HTTP 拿 health/KB 列表。
    本机对未监听端口可能是 drop 而非 RST，直接 HTTP 探测会等满超时。"""
    s = socket.socket()
    s.settimeout(0.5)
    try:
        if s.connect_ex(("127.0.0.1", RAG_PORT)) != 0:
            return {"online": False, "health": None, "kbs": []}
    finally:
        s.close()
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/api/health" % RAG_PORT)
        with urllib.request.urlopen(req, timeout=3) as resp:
            health = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"online": False, "health": None, "kbs": []}
    kbs = []
    try:
        req2 = urllib.request.Request("http://127.0.0.1:%d/api/kb/list" % RAG_PORT)
        with urllib.request.urlopen(req2, timeout=3) as resp2:
            kb_data = json.loads(resp2.read().decode("utf-8"))
        kbs_raw = kb_data.get("kbs", kb_data.get("data", []))
        if isinstance(kbs_raw, dict):
            kbs = list(kbs_raw.keys())
        elif isinstance(kbs_raw, list):
            kbs = [k if isinstance(k, str) else k.get("name", "") for k in kbs_raw]
    except Exception:
        pass
    return {"online": True, "health": health, "kbs": kbs}


def _rag_python_cmd(rag_path):
    """挑能跑 rag-assistant 重依赖（torch/chromadb…）的解释器：
    venv → PATH 里的 python → py -3 → 当前解释器兜底。
    本服务可能由内嵌纯净 Python 运行，直接用 sys.executable 大概率缺依赖。"""
    venv_py = os.path.join(rag_path, ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv_py):
        return [venv_py]
    for name in ("python", "python3"):
        w = shutil.which(name)
        if w and os.path.normcase(w) != os.path.normcase(sys.executable):
            return [w]
    w = shutil.which("py")
    if w:
        return [w, "-3"]
    return [sys.executable]


def _rag_start_async(rag_path):
    """异步冷启动 rag-assistant 外部 API。返回 (ok, msg)。"""
    global _rag_starting, _rag_process, _rag_process_stderr
    main_py = os.path.join(rag_path, "main.py")
    if not os.path.isfile(main_py):
        return False, "路径下未找到 main.py：%s" % main_py
    if _probe_rag()["online"]:
        return False, "RAG 服务已在运行（端口 %d），无需启动" % RAG_PORT
    with _rag_lock:
        if _rag_starting:
            return False, "正在启动中，请稍候"
        _rag_starting = True
    try:
        # stderr 落临时文件而非 pipe：子进程输出多时 pipe 缓冲区满会卡死双方
        stderr_tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".log", prefix="rag_", mode="w", encoding="utf-8")
        stderr_path = stderr_tmp.name
        # 子进程强制 UTF-8 输出，防中文/emoji 在 GBK 控制台报编码错
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = _rag_python_cmd(rag_path) + [main_py, "--port", "18765",
                                           "--api-port", str(RAG_PORT)]
        proc = subprocess.Popen(cmd, cwd=rag_path, env=env,
                                stdout=subprocess.DEVNULL, stderr=stderr_tmp,
                                creationflags=_NO_WIN)
        stderr_tmp.close()
        with _rag_lock:
            _rag_process = proc
            _rag_process_stderr = ""
    except Exception as e:
        with _rag_lock:
            _rag_starting = False
        return False, "启动失败：%s" % e

    def _poll():
        global _rag_starting, _rag_process_stderr
        try:
            for _ in range(45):          # 最多等 90 秒（embedding 冷加载）
                time.sleep(2)
                if _probe_rag()["online"]:
                    return
                if proc.poll() is not None:
                    # 子进程挂了：读临时文件找 Traceback
                    err = ""
                    try:
                        with open(stderr_path, "r", encoding="utf-8", errors="replace") as ef:
                            full = ef.read()
                        idx = full.rfind("Traceback (most recent call last)")
                        err = full[idx:][:2000] if idx >= 0 else full[-2000:]
                    except Exception:
                        err = "(无法读取启动输出)"
                    with _rag_lock:
                        _rag_process_stderr = err
                    return
        finally:
            with _rag_lock:
                _rag_starting = False
            try:
                os.unlink(stderr_path)
            except Exception:
                pass

    threading.Thread(target=_poll, daemon=True).start()
    return True, "RAG 启动中（冷加载 embedding 可能需数十秒），请稍候…"


def _rag_stop():
    """停 RAG：terminate 本服务拉起的子进程 → 清 :8767 全部 PID → 等端口释放。
    rag-assistant 带看护自动重启，kill 后端口可能复活，只能尽力而为；
    返回 True=端口仍活着（复活），False=已真停。"""
    global _rag_process, _rag_process_stderr
    with _rag_lock:
        if _rag_process is not None:
            try:
                _rag_process.terminate()
                _rag_process.wait(timeout=3)
            except Exception:
                try:
                    _rag_process.kill()
                except Exception:
                    pass
            _rag_process = None
            _rag_process_stderr = ""
    try:
        r = subprocess.run("netstat -ano", capture_output=True, text=True,
                           shell=True, timeout=5)
        for line in r.stdout.splitlines():
            if str(RAG_PORT) in line and ("LISTENING" in line or "ESTABLISHED" in line):
                parts = line.strip().split()
                if parts and parts[-1].isdigit():
                    subprocess.run(["taskkill", "/F", "/T", "/PID", parts[-1]],
                                   capture_output=True, timeout=5)
    except Exception:
        pass
    for _ in range(10):
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(("127.0.0.1", RAG_PORT))
            s.close()
            time.sleep(0.5)
        except Exception:
            return False        # 连不上 = 端口已释放
    return _probe_rag()["online"]


class ReuseTCPServer(socketserver.ThreadingTCPServer):
    # 线程化：LLM 润色/解释最长可达 timeout 秒（默认 180），单线程会卡死
    # 心跳/保存等全部路由；HTTP/1.0 每请求一线程，用完即回收
    daemon_threads = True
    allow_reuse_address = True


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            try:
                with open(EDITOR_HTML, "r", encoding="utf-8") as f:
                    html = f.read()
            except Exception as e:  # pragma: no cover
                self._send(500, "read editor failed: %s" % e)
                return
            build = hashlib.md5(html.encode("utf-8")).hexdigest()[:10]
            html = html.replace("<body>", '<body data-build="%s">' % build, 1)
            self._send(200, html, "text/html; charset=utf-8",
                       {"Cache-Control": "no-store"})
            return
        if u.path == "/api/version":
            # sessions：当前活跃页面会话数（页面加载完成即发首个 ping 登记）。
            # 启动画面据此判断"窗口真正加载出来了"再淡出（v1.11.1）。
            self._send(200, json.dumps(
                {"ok": True, "version": MD_SERVER_VERSION,
                 "sessions": len(_LIVE_SESSIONS)},
                ensure_ascii=False))
            return
        if u.path == "/api/ui-settings":
            # UI 状态全量读取（前端启动时同步 XHR 回放进 localStorage）
            self._send(200, json.dumps(
                {"ok": True, "data": _ui_settings_read()},
                ensure_ascii=False))
            return
        if u.path == "/api/ping":
            # 页面心跳：登记本会话存活（token 区分多窗口/多标签），并撤销待退出。
            # 注意：闲置（切标签页/最小化）绝不触发退出。
            _keepalive_ping(_live_tok(u.query))
            self._send(200, '{"ok":true}', "application/json; charset=utf-8")
            return
        if u.path == "/api/bye":
            # 页面卸载通知（pagehide -> sendBeacon）。刷新也会走到这里，
            # 因此只"登记"，由看门狗在宽限期后再决定是否退出。
            # 多窗口共享本服务：仅当【最后一个】会话 bye 后才进入待退出。
            _keepalive_bye(_live_tok(u.query))
            self._send(200, '{"ok":true}', "application/json; charset=utf-8")
            return
        if u.path == "/api/browse-dir":
            try:
                d = _pick_dir_subprocess()
                self._send(200, json.dumps({"ok": True, "dir": d or ""},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/open-file":
            # 浏览器模式专用：用原生"打开"框拿真实完整路径
            try:
                q = urllib.parse.parse_qs(u.query)
                initdir = q.get("dir", [""])[0]
                p = _pick_file_subprocess(initdir)
                if p:
                    _LAST_DOC_DIR[0] = os.path.dirname(p)
                self._send(200, json.dumps({"ok": True, "path": p},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/pick-save":
            # 原生"另存为"框：前端先来此拿用户所选路径，再去导出端点写盘
            try:
                q = urllib.parse.parse_qs(u.query)
                ext = (q.get("ext", ["docx"])[0] or "docx").strip().lstrip(".")
                initdir = q.get("dir", [""])[0] or ""
                name = q.get("name", [""])[0] or ("未命名文档." + ext)
                title = q.get("title", ["导出为 .%s" % ext])[0]
                path = _pick_save_subprocess(ext, initdir, title, name)
                if not path:
                    self._send(200, json.dumps({"ok": False, "canceled": True},
                                               ensure_ascii=False))
                    return
                if not path.lower().endswith(".%s" % ext.lower()):
                    path += ".%s" % ext
                self._send(200, json.dumps({"ok": True, "path": path},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/common-dirs":
            try:
                out = _common_dirs()
                self._send(200, json.dumps({"ok": True, "dirs": out},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/version":
            # sessions：当前活跃页面会话数（页面加载完成即发首个 ping 登记）。
            # 启动画面据此判断"窗口真正加载出来了"再淡出（v1.11.1）。
            self._send(200, json.dumps(
                {"ok": True, "version": MD_SERVER_VERSION,
                 "sessions": len(_LIVE_SESSIONS)},
                ensure_ascii=False))
            return
        if u.path == "/api/runs" and self.command == "GET":
            try:
                qs = urllib.parse.parse_qs(u.query)
                name = (qs.get("name") or [""])[0]
                if name:
                    if not _lr_valid_name(name):
                        self._send(200, json.dumps(
                            {"ok": False, "error": "名称不合法"},
                            ensure_ascii=False),
                            "application/json; charset=utf-8")
                        return
                    p = os.path.join(RUNS_DIR, name + ".py")
                    if not os.path.exists(p):
                        self._send(200, json.dumps(
                            {"ok": False, "error": "不存在"},
                            ensure_ascii=False),
                            "application/json; charset=utf-8")
                        return
                    code = open(p, encoding="utf-8").read()
                    self._send(200, json.dumps(
                        {"ok": True, "name": name, "code": code},
                        ensure_ascii=False),
                        "application/json; charset=utf-8")
                    return
                items = []
                if os.path.isdir(RUNS_DIR):
                    for fn_ in sorted(os.listdir(RUNS_DIR)):
                        if fn_.endswith(".py"):
                            fp = os.path.join(RUNS_DIR, fn_)
                            items.append({
                                "name": fn_[:-3],
                                "mtime": int(os.path.getmtime(fp)),
                                "size": os.path.getsize(fp)})
                self._send(200, json.dumps(
                    {"ok": True, "runs": items}, ensure_ascii=False),
                    "application/json; charset=utf-8")
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            return
        if u.path == "/favicon.ico":
            ico = os.path.join(HERE, "md-editor.ico")
            try:
                with open(ico, "rb") as f:
                    self._send(200, f.read(), "image/x-icon",
                               {"Cache-Control": "max-age=86400"})
            except Exception:
                self._send(404, "not found")
            return
        if u.path == "/api/fonts":
            try:
                import winreg
                fonts = set()
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        k = winreg.OpenKey(hive, "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts")
                    except OSError:
                        continue
                    i = 0
                    while True:
                        try:
                            name, _, _ = winreg.EnumValue(k, i)
                            i += 1
                        except OSError:
                            break
                        name = re.sub(r"\s*\((TrueType|OpenType|PostScript)\)$", "", name, flags=re.IGNORECASE)
                        for part in name.split("&"):
                            part = part.strip()
                            if part:
                                fonts.add(part)
                    try:
                        winreg.CloseKey(k)
                    except OSError:
                        pass
                self._send(200, json.dumps({"ok": True,
                    "fonts": sorted(fonts, key=lambda s: s.lower())}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path.startswith("/static/"):
            rel = urllib.parse.unquote(u.path[len("/static/"):])
            root = os.path.normpath(HERE)
            full = os.path.normpath(os.path.join(HERE, rel))
            if not (full == root or full.startswith(root + os.sep)):
                self._send(403, "forbidden")
                return
            ctypes_map = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
                ".html": "text/html; charset=utf-8", ".png": "image/png",
                ".svg": "image/svg+xml", ".ico": "image/x-icon",
            }
            ctype = ctypes_map.get(os.path.splitext(full)[1].lower(),
                                   "application/octet-stream")
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except Exception:
                self._send(404, "not found")
                return
            self._send(200, data, ctype)
            return
        if u.path == "/api/file":
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            if not p:
                self._send(400, json.dumps({"ok": False, "error": "missing path"}, ensure_ascii=False))
                return
            if _smd is not None and _smd.is_smd(p):
                # .smd 自包含文档：解包（幂等）后返回 doc.md 内容 + 工作目录，
                # 前端以 base 为图片基址（assets/ 引用经 /img 代理指向解包目录）
                try:
                    base = _smd.base_dir_for(p)
                    with open(os.path.join(base, _smd.DOC_NAME), "r", encoding="utf-8") as f:
                        content = f.read()
                    _LAST_DOC_DIR[0] = base
                    self._send(200, json.dumps({"ok": True, "smd": True, "base": base,
                                                "content": content}, ensure_ascii=False),
                               "application/json; charset=utf-8")
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
                return
            try:
                _LAST_DOC_DIR[0] = os.path.dirname(p)
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    data = f.read()
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
                return
            self._send(200, data, "text/plain; charset=utf-8")
            return
        if u.path == "/img":
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            if p and not os.path.isabs(p):
                cand = os.path.join(HERE, p)
                if os.path.exists(cand):
                    p = cand
            exts = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                    ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
                    ".bmp": "image/bmp"}
            ext = os.path.splitext(p)[1].lower()
            try:
                st = os.stat(p)
                with open(p, "rb") as f:
                    data = f.read()
            except Exception:
                self._send(404, "image not found")
                return
            # 协商缓存：ETag=mtime-size，浏览器每次请求都回源校验，
            # 文件没变回 304（不重传），变了立刻拿到新图 —— F5 即见效
            etag = '"%d-%d"' % (int(st.st_mtime), st.st_size)
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("ETag", etag)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", exts.get(ext, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/docs-list":
            docs_dir = os.path.join(HERE, "docs")
            items = []
            try:
                for f in sorted(os.listdir(docs_dir)):
                    if f.lower().endswith(".md"):
                        items.append({"name": os.path.splitext(f)[0],
                                      "file": f})
            except Exception:
                pass
            self._send(200, json.dumps({"ok": True, "docs": items},
                                       ensure_ascii=False))
            return
        if u.path == "/api/log":
            q = urllib.parse.parse_qs(u.query)
            msg = q.get("msg", [""])[0][:500]
            try:
                rt = os.path.join(HERE, "runtime")
                os.makedirs(rt, exist_ok=True)
                with io.open(os.path.join(rt, "ui.log"), "a",
                             encoding="utf-8") as f:
                    f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
            except Exception:
                pass
            self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
            return
        if u.path == "/api/open-external":
            q = urllib.parse.parse_qs(u.query)
            url = q.get("url", [""])[0]
            # 仅允许本机服务的 URL，防止被用作任意程序启动器
            if url.startswith("/"):
                url = "http://127.0.0.1:%d%s" % (PORT, url)
            if url.startswith("http://127.0.0.1:%d/" % PORT)                     or url.startswith("http://localhost:%d/" % PORT):
                threading.Thread(target=lambda: webbrowser.open(url),
                                 daemon=True).start()
                self._send(200, json.dumps({"ok": True},
                                           ensure_ascii=False))
            else:
                self._send(400, json.dumps({"ok": False,
                    "error": "仅允许打开本机服务地址"}, ensure_ascii=False))
            return
        if u.path == "/api/open-dir":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8")) \
                    if length else {}
                which = str(obj.get("dir", ""))
                d = {"pylibs": PYLIBS_DIR, "runs": RUNS_DIR,
                     "run_cache": RUN_CACHE_DIR}.get(which)
                if not d:
                    self._send(400, json.dumps(
                        {"ok": False, "error": "未知目录"},
                        ensure_ascii=False), "application/json; charset=utf-8")
                    return
                os.makedirs(d, exist_ok=True)
                if hasattr(os, "startfile"):
                    os.startfile(d)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", d])
                else:
                    subprocess.Popen(["xdg-open", d])
                self._send(200, json.dumps({"ok": True},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            return
        if u.path == "/doc":
            q = urllib.parse.parse_qs(u.query)
            fname = q.get("file", [""])[0]
            docs_dir = os.path.normpath(os.path.join(HERE, "docs"))
            full = os.path.normpath(os.path.join(docs_dir, fname))
            if (fname and full.startswith(docs_dir + os.sep)
                    and os.path.isfile(full)):
                try:
                    with io.open(full, "r", encoding="utf-8") as f:
                        body = f.read()
                    _LAST_DOC_DIR[0] = os.path.dirname(full)
                    self._send(200, json.dumps(
                        {"ok": True, "path": full, "content": body},
                        ensure_ascii=False))
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "error": str(e)},
                                               ensure_ascii=False))
            else:
                self._send(404, json.dumps({"ok": False,
                    "error": "文档不存在"}, ensure_ascii=False))
            return
        if u.path == "/api/annotations":
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            if not p:
                self._send(400, json.dumps({"ok": False, "error": "missing path"}, ensure_ascii=False))
                return
            try:
                data = _load_json(_annotations_path(p), [])
                if not isinstance(data, list):
                    data = []
                self._send(200, json.dumps({"ok": True, "annotations": data}, ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        if u.path == "/api/save-backups":
            # 打开文档时查询：是否有保存失败保留的备份（<文档>.tmp<时间戳>）
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            if not p:
                self._send(400, json.dumps({"ok": False, "error": "missing path"}, ensure_ascii=False))
                return
            out = []
            try:
                for fp in _smd_tmp_backups(os.path.abspath(p)):
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue
                    valid = False
                    try:
                        with zipfile.ZipFile(fp) as _z:
                            _z.namelist()
                        valid = True
                    except Exception:
                        pass
                    out.append({"path": fp, "name": os.path.basename(fp),
                                "mtime": int(st.st_mtime), "size": st.st_size,
                                "valid": valid})
                self._send(200, json.dumps({"ok": True, "backups": out},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        if u.path == "/api/llm-config":
            self._send(200, json.dumps({"ok": True, "config": _llm_saved_config(),
                                        "rag": _rag_saved_config()},
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")
            return
        if u.path == "/api/rag-status":
            result = _probe_rag()
            with _rag_lock:
                proc_alive = _rag_process is not None and _rag_process.poll() is None
                starting = _rag_starting
                stderr = _rag_process_stderr[:500] if _rag_process_stderr else ""
            cfg = _rag_saved_config()
            self._send(200, json.dumps({"ok": True, "online": result["online"],
                                        "kbs": result["kbs"], "local_process": proc_alive,
                                        "starting": starting, "stderr": stderr,
                                        "path": cfg["path"], "kb": cfg["kb"]},
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")
            return
        if u.path == "/open":
            q = urllib.parse.parse_qs(u.query)
            f = q.get("file", [""])[0]
            v = MD_SERVER_VERSION
            if f:
                target = "/?file=" + urllib.parse.quote(f) + "&v=%d" % v
            else:
                target = "/?v=%d" % v
            # 先回响应、再异步开浏览器：避免启动器等待超时后重复打开
            self._send(200, "ok")
            _url = "http://127.0.0.1:%d%s" % (PORT, target)
            threading.Timer(0.05, lambda: webbrowser.open(_url)).start()
            return
        # 根级静态兜底：工具目录内的图片/常见静态文件（防穿越，白名单扩展名）
        root = os.path.normpath(HERE)
        rel = urllib.parse.unquote(u.path.lstrip("/"))
        full = os.path.normpath(os.path.join(HERE, rel))
        static_exts = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                       ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml",
                       ".ico": "image/x-icon", ".css": "text/css", ".js": "application/javascript"}
        if (full.startswith(root + os.sep) and rel
                and os.path.splitext(full)[1].lower() in static_exts
                and os.path.isfile(full)):
            try:
                with open(full, "rb") as f:
                    data = f.read()
                self._send(200, data, static_exts[os.path.splitext(full)[1].lower()])
                return
            except Exception:
                pass
        self._send(404, "not found")

    def do_DELETE(self):
        # /api/runs?name=x —— BaseHTTPRequestHandler 按 method 分发，
        # DELETE 不进 do_POST（v2.4.4 修复：此前 404 HTML 错误页——删除
        # 按钮历史上被 confirm（WebView2 不弹、返回假）挡住从未真正执行，
        # 该路由缺陷从未暴露；二次点击确认交互上线后才首度验证暴露）
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/runs":
            try:
                qs = urllib.parse.parse_qs(u.query)
                name = (qs.get("name") or [""])[0]
                if not _lr_valid_name(name):
                    self._send(200, json.dumps(
                        {"ok": False, "error": "名称不合法"},
                        ensure_ascii=False),
                        "application/json; charset=utf-8")
                    return
                p = os.path.join(RUNS_DIR, name + ".py")
                if os.path.exists(p):
                    os.remove(p)
                self._send(200, json.dumps({"ok": True},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            return
        self._send(404, "not found")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/api/ping", "/api/bye"):
            # sendBeacon 走 POST（pagehide 心跳/卸载通知），路由与 GET 同一实现
            self.do_GET()
            return
        if u.path == "/api/ui-settings":
            # UI 状态增量合并写入：body={key:value}，value=null 表示删除该键。
            # 值一律为字符串（localStorage 原值原样存取，前端零转换）。
            try:
                obj = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))
                ).decode("utf-8"))
                if not isinstance(obj, dict):
                    raise ValueError("body must be a JSON object")
                with _UI_LOCK:
                    d = _ui_settings_read()
                    for k, v in obj.items():
                        if v is None:
                            d.pop(k, None)
                        else:
                            d[k] = v
                    _ui_settings_write(d)
                self._send(200, '{"ok":true}', "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/file":
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                obj = json.loads(raw.decode("utf-8"))
                p = obj.get("path", "")
                content = obj.get("content", "")
                if not p:
                    self._send(400, json.dumps({"ok": False, "error": "missing path"}, ensure_ascii=False))
                    return
                if _smd is not None and _smd.is_smd(p):
                    # .smd：正文写入解包目录 doc.md，增量追加进包（append 模式，
                    # 仅变化 entry；阈值触发时自动全量整理）。写前物化：手写的
                    # data URI / blob / 本机绝对路径中真实存在的图收进包内
                    # assets/，引用统一为 assets/ 契约；save_from_dir 按目录
                    # diff 自动追加新图。响应回传新正文供前端同步编辑区
                    base = _smd.base_dir_for(p)
                    if materialize_into:
                        content, _mi = materialize_into(
                            content, os.path.join(base, "assets"), "assets")
                    # newline=""：禁用换行翻译，磁盘=包内=响应字节一致
                    # （文本模式会把 LF 翻成 CRLF，save_from_dir 按原始字节进包）
                    with open(os.path.join(base, _smd.DOC_NAME), "w", encoding="utf-8",
                              newline="") as f:
                        f.write(content)
                    _n, _compacted = _smd.save_from_dir(p, base)
                    _LAST_DOC_DIR[0] = base
                    self._send(200, json.dumps({"ok": True, "smd": True, "base": base,
                                                "content": content,
                                                "images": []}, ensure_ascii=False))
                    return
                added = []
                if materialize_images:
                    content, added = materialize_images(p, content)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                _LAST_DOC_DIR[0] = os.path.dirname(p)
                self._send(200, json.dumps({"ok": True, "content": content,
                                            "images": added}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": _friendly_save_error(e, p)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/save-as":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                d = obj.get("dir", "").strip()
                name = (obj.get("name") or "未命名.md").strip()
                content = obj.get("content", "")
                if not d or not os.path.isdir(d):
                    self._send(400, json.dumps({"ok": False,
                        "error": "目录不存在"}, ensure_ascii=False))
                    return
                to_smd = _smd is not None and name.lower().endswith(".smd")
                if not to_smd and not name.lower().endswith(".md"):
                    name += ".md"
                path = os.path.join(d, name)
                if to_smd:
                    # 另存为 .smd：正文进 doc.md；资产三级来源——
                    # ① base/assets（.smd 会话，引用已是包内 assets/ 契约，整目录跟随）
                    # ② src 同目录 <stem>.assets（普通文档，磁盘契约），整目录跟随
                    #    后把 "<stem>.assets/" 引用统一改写为 "assets/"
                    # ③ materialize_into：手写 data URI / blob / 本机绝对路径中
                    #    真实存在的图当场收进包内 assets/（不存在的原样保留，破图可见）
                    # 响应回传改写后正文给前端同步编辑区（否则下次 Ctrl+S 把旧引用写回包）
                    stage = _smd.base_dir_for(path) if os.path.isfile(path) else \
                        os.path.join(_smd._tmp_root(),
                                     hashlib.md5(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:16])
                    os.makedirs(stage, exist_ok=True)
                    src = (obj.get("src") or "").strip()
                    base = (obj.get("base") or "").strip()
                    src_assets = None
                    cand = None
                    if base and os.path.isdir(os.path.join(base, "assets")):
                        src_assets = os.path.join(base, "assets")
                    elif src and os.path.isfile(src):
                        cand = os.path.join(os.path.dirname(src),
                                            os.path.splitext(os.path.basename(src))[0] + ".assets")
                        if os.path.isdir(cand):
                            src_assets = cand
                        else:
                            cand = None
                    if materialize_into:
                        content, _mi = materialize_into(
                            content, os.path.join(stage, "assets"), "assets")
                    dst_assets = os.path.join(stage, "assets")
                    if src_assets and os.path.normpath(src_assets) != os.path.normpath(dst_assets):
                        os.makedirs(dst_assets, exist_ok=True)
                        import shutil as _sh
                        for fn in os.listdir(src_assets):
                            fp = os.path.join(src_assets, fn)
                            if os.path.isfile(fp):
                                _sh.copy2(fp, os.path.join(dst_assets, fn))
                    if cand:
                        content, _nr = _rewrite_assets_ref(
                            content, os.path.basename(cand), "assets")
                    # newline=""：禁用换行翻译，磁盘=包内=响应字节一致
                    with open(os.path.join(stage, _smd.DOC_NAME), "w", encoding="utf-8",
                              newline="") as f:
                        f.write(content)
                    _smd.pack_from_dir(path, os.path.join(stage, _smd.DOC_NAME), dst_assets)
                    _LAST_DOC_DIR[0] = stage
                    self._send(200, json.dumps({"ok": True, "path": path, "smd": True,
                                                "base": stage, "content": content,
                                                "images": []},
                                               ensure_ascii=False))
                    return
                added = []
                base = (obj.get("base") or "").strip()
                if _smd is not None and base and os.path.isdir(os.path.join(base, "assets")):
                    # .smd 会话导出普通 .md：包内 "assets/" 契约反向换算为磁盘
                    # "<stem>.assets/" 契约，图片一并落盘到目标目录
                    newstem = os.path.splitext(name)[0]
                    dst_assets = os.path.join(d, newstem + ".assets")
                    os.makedirs(dst_assets, exist_ok=True)
                    import shutil as _sh
                    for fn in os.listdir(os.path.join(base, "assets")):
                        fp = os.path.join(base, "assets", fn)
                        if os.path.isfile(fp):
                            _sh.copy2(fp, os.path.join(dst_assets, fn))
                    content, _nr = _rewrite_assets_ref(content, "assets",
                                                       newstem + ".assets")
                if materialize_images:
                    content, added = materialize_images(path, content)
                else:
                    added = []
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                _LAST_DOC_DIR[0] = d
                self._send(200, json.dumps({"ok": True, "path": path,
                                            "content": content, "images": added},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": _friendly_save_error(e, path)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/restore-backup":
            # 用失败备份覆盖 .smd —— 仅在前端用户点过"恢复"确认后到达这里
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                p = os.path.abspath(obj.get("path") or "")
                bak = os.path.abspath(obj.get("backup") or "")
                if not p or not bak:
                    self._send(400, json.dumps({"ok": False, "error": "bad payload"}, ensure_ascii=False))
                    return
                # 安全校验：备份必须确实是该文档的 tmp（同目录同名 .tmp<时间戳>
                # 模式 + zip 有效性；防误传任意路径覆盖好包）
                ok_pat = bool(re.match(re.escape(os.path.basename(p)) + r"\.tmp\d+$",
                                       os.path.basename(bak)))
                same_dir = os.path.dirname(bak) == os.path.dirname(p)
                valid = False
                if ok_pat and same_dir and os.path.isfile(bak):
                    try:
                        with zipfile.ZipFile(bak) as _z:
                            _z.namelist()
                        valid = True
                    except Exception:
                        pass
                if valid:
                    os.replace(bak, p)   # 目标在不在都允许落位；base_dir_for 指纹检测会自动重解包
                    self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
                else:
                    self._send(400, json.dumps({"ok": False, "error": "备份与文档不匹配或已损坏"}, ensure_ascii=False))
            except OSError as e:
                self._send(500, json.dumps({"ok": False,
                    "error": _friendly_save_error(e, obj.get("path") or "")}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        if u.path == "/api/paste-image":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                doc_path = obj.get("docPath") or ""
                data_url = obj.get("dataUrl") or ""
                if not doc_path:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文档尚未保存"}, ensure_ascii=False))
                    return
                head, _, b64 = data_url.partition(",")
                ext = ".png"
                if "jpeg" in head: ext = ".jpg"
                elif "webp" in head: ext = ".webp"
                elif "gif" in head: ext = ".gif"
                if _smd is not None and _smd.is_smd(doc_path):
                    # .smd：图片落解包工作目录的 assets/，引用为 assets/<fname>
                    base = _smd.base_dir_for(doc_path)
                    assets = os.path.join(base, "assets")
                    os.makedirs(assets, exist_ok=True)
                    fname = "%s_%s%s" % (time.strftime("%Y%m%d_%H%M%S"),
                                         str(int(time.time() * 1000))[-4:], ext)
                    with open(os.path.join(assets, fname), "wb") as f:
                        f.write(base64.b64decode(b64))
                    self._send(200, json.dumps({"ok": True,
                        "rel": "assets/%s" % fname}, ensure_ascii=False))
                    return
                stem = os.path.splitext(os.path.basename(doc_path))[0]
                assets = os.path.join(os.path.dirname(doc_path), stem + ".assets")
                os.makedirs(assets, exist_ok=True)
                fname = "%s_%s%s" % (time.strftime("%Y%m%d_%H%M%S"),
                                     str(int(time.time() * 1000))[-4:], ext)
                with open(os.path.join(assets, fname), "wb") as f:
                    f.write(base64.b64decode(b64))
                self._send(200, json.dumps({"ok": True,
                    "rel": "%s.assets/%s" % (stem, fname)}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        # ---------- 外部文件引用（v2.8）----------
        if u.path == "/api/paste-file":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                doc_path = obj.get("docPath") or ""
                data_url = obj.get("dataUrl") or ""
                if not doc_path:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文档尚未保存"}, ensure_ascii=False))
                    return
                ref_base = _doc_ref_base(doc_path)
                assets = _doc_assets_dir(doc_path)
                if not ref_base or not assets:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文档路径无效或尚未保存"}, ensure_ascii=False))
                    return
                fname = _safe_asset_name(obj.get("name"))
                if not fname:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文件名不合法"}, ensure_ascii=False))
                    return
                _head, _, b64 = data_url.partition(",")
                try:
                    blob = base64.b64decode(b64) if b64 else b""
                except Exception:
                    blob = b""
                if not blob:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文件内容为空"}, ensure_ascii=False))
                    return
                if len(blob) > 20 * 1024 * 1024:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文件超过 20MB 上限（当前 %.1fMB）"
                                 % (len(blob) / 1048576.0)}, ensure_ascii=False))
                    return
                os.makedirs(assets, exist_ok=True)
                target = os.path.join(assets, fname)
                if not _within(target, assets):
                    self._send(400, json.dumps({"ok": False,
                        "error": "目标路径越界"}, ensure_ascii=False))
                    return
                if os.path.exists(target):
                    same = False
                    try:
                        with open(target, "rb") as f:
                            same = (f.read() == blob)
                    except Exception:
                        same = False
                    if not same:
                        # 同名不同内容：加短哈希后缀，绝不覆盖
                        stem2, ext2 = os.path.splitext(fname)
                        h = hashlib.sha256(blob).hexdigest()[:4]
                        cand = "%s__%s%s" % (stem2, h, ext2)
                        n = 1
                        while os.path.exists(os.path.join(assets, cand)):
                            cand = "%s__%s%d%s" % (stem2, h, n, ext2)
                            n += 1
                        fname = cand
                        target = os.path.join(assets, fname)
                with open(target, "wb") as f:
                    f.write(blob)
                rel = os.path.relpath(target, ref_base).replace("\\", "/")
                self._send(200, json.dumps({"ok": True, "rel": rel,
                    "name": fname, "size": len(blob)}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/open-ref":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                doc_path = obj.get("docPath") or ""
                rel = str(obj.get("rel") or "").strip()
                ref_base = _doc_ref_base(doc_path)
                assets = _doc_assets_dir(doc_path)
                if not ref_base or not assets:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文档路径无效或尚未保存"}, ensure_ascii=False))
                    return
                cands = []
                if _ASSET_REL_RE.match(rel):
                    cands.append(os.path.join(ref_base, rel))
                cands.append(os.path.join(assets, rel))
                target = None
                for c in cands:
                    c = os.path.normpath(c)
                    # 白名单：必须落在本文档资产目录内 —— 否则"打开"等于
                    # 双击运行任意程序（文档可以被别人发给你）
                    if _within(c, assets) and os.path.isfile(c):
                        target = c
                        break
                if not target:
                    self._send(400, json.dumps({"ok": False,
                        "error": "文件不存在或不在本文档资产目录内"},
                        ensure_ascii=False))
                    return
                if hasattr(os, "startfile"):
                    os.startfile(target)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", target])
                else:
                    subprocess.Popen(["xdg-open", target])
                self._send(200, json.dumps({"ok": True,
                    "path": target.replace("\\", "/")}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        # ---------- low runner（v2.4）----------
        if u.path == "/api/run":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                j = _lr_run(str(obj.get("mod", "")), str(obj.get("fn", "run")),
                            obj.get("data") or {}, obj.get("mdPath") or "")
                self._send(200, json.dumps(j, ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            return
        if u.path == "/api/runs":
            try:
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length", 0))
                    obj = json.loads(self.rfile.read(length).decode("utf-8"))
                    name = str(obj.get("name", "")).strip()
                    code = str(obj.get("code", ""))
                    if not _lr_valid_name(name):
                        self._send(200, json.dumps(
                            {"ok": False, "error": "名称不合法（仅字母数字下划线连字符点中文）"},
                            ensure_ascii=False),
                            "application/json; charset=utf-8")
                        return
                    with open(os.path.join(RUNS_DIR, name + ".py"), "w",
                              encoding="utf-8") as f:
                        f.write(code)
                    # 保存即依赖检测（v2.5：管理界面代码区显示缺哪些包
                    # + 安装命令；便携包无 pip，装包由用户自执行）
                    deps = _lr_check_deps(code)
                    self._send(200, json.dumps(
                        {"ok": True, "deps": deps}, ensure_ascii=False),
                        "application/json; charset=utf-8")
                    return
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            return
        if u.path == "/api/run-llm":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8")) \
                    if length else {}
                client = _llm_from_request(obj)
                prompt = str(obj.get("prompt", ""))[:4000]
                if not prompt.strip():
                    self._send(200, json.dumps(
                        {"ok": False, "error": "需求描述为空"},
                        ensure_ascii=False),
                        "application/json; charset=utf-8")
                    return
                sample = str(obj.get("sample", ""))[:2000]
                sys_msg = _LR_LLM_SYS + (
                    "\n当前文档数据点样例：\n" + sample if sample else "")
                r = client.chat([{"role": "system", "content": sys_msg},
                                 {"role": "user", "content": prompt}])
                code, name, usage = _lr_parse_llm_output(r)
                self._send(200, json.dumps(
                    {"ok": True, "code": code, "name": name, "usage": usage},
                    ensure_ascii=False),
                    "application/json; charset=utf-8")
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            return
        if u.path == "/api/export-html":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                html = build_standalone_html(obj.get("mdPath") or obj.get("path") or None,
                                              obj.get("bodyHtml", ""),
                                              obj.get("tsCss", ""),
                                              obj.get("page") or None)
                # 优先写到用户"另存为"所选路径；未提供时回退应用目录（兼容老调用）
                out = obj.get("path") or os.path.join(HERE, "document.html")
                d = os.path.dirname(out)
                if d:
                    os.makedirs(d, exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(html)
                self._send(200, json.dumps({"ok": True, "path": out},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/export-docx":
            try:
                _ensure_docx_deps()
                import docx_export
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                data = docx_export.build_docx(obj.get("mdPath") or obj.get("path"),
                                              obj.get("bodyHtml", ""),
                                              obj.get("tsCss", ""),
                                              obj.get("page") or None)
                # 优先写到用户"另存为"所选路径；未提供时回退应用目录（兼容老调用）
                out = obj.get("path") or os.path.join(HERE, "document.docx")
                d = os.path.dirname(out)
                if d:
                    os.makedirs(d, exist_ok=True)
                with open(out, "wb") as f:
                    f.write(data)
                self._send(200, json.dumps({"ok": True, "path": out},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/export-paged":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                md_path = obj.get("path") or None
                body_html = obj.get("bodyHtml", "")
                ts_css = obj.get("tsCss", "")
                page_cfg = obj.get("cfg", {}) or {}
                html = build_paged_html(md_path, body_html, ts_css, page_cfg)
                # /static/ 路由会把前缀剥掉后映射到工具目录（/static/x -> HERE/x），
                # 因此文件写在 HERE 下、URL 用 /static/<name> 即可正确访问
                name = "document.paged.html"
                with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
                    f.write(html)
                self._send(200, json.dumps({"ok": True, "url": "/static/" + name},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)},
                                           ensure_ascii=False))
            return
        if u.path == "/api/export":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                name = obj.get("name", "")
                content = obj.get("content", "")
                if not re.match(r"^[A-Za-z0-9._-]+\.html$", name):
                    self._send(400, json.dumps({"ok": False, "error": "bad name"}, ensure_ascii=False))
                    return
                with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
                    f.write(content)
                self._send(200, json.dumps({"ok": True, "url": "/static/" + name}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        if u.path == "/api/annotations":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                p = obj.get("path", "")
                anns = obj.get("annotations", [])
                if not p or not isinstance(anns, list):
                    self._send(400, json.dumps({"ok": False, "error": "bad payload"}, ensure_ascii=False))
                    return
                clean = []
                for a in anns:
                    if not isinstance(a, dict):
                        continue
                    clean.append({
                        "id": str(a.get("id", ""))[:64],
                        "text": str(a.get("text", ""))[:8000],
                        "note": str(a.get("note", ""))[:8000],
                        "created": a.get("created", 0),
                        "updated": a.get("updated", int(time.time())),
                    })
                if len(clean) > 2000:
                    clean = clean[:2000]
                apath = _annotations_path(p)
                _save_json(apath, clean)
                if _smd is not None and _smd.is_smd(p):
                    # .smd：批注随包分发——写解包目录后增量追加进包，
                    # 否则包内 annotations.json 停留在旧版（仅存于临时目录）
                    try:
                        _smd.save_from_dir(p, os.path.dirname(os.path.dirname(apath)))
                    except Exception as e:
                        self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
                        return
                self._send(200, json.dumps({"ok": True, "count": len(clean)}, ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        if u.path == "/api/llm-config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8"))
                cfg = obj.get("config")
                if not isinstance(cfg, dict):
                    self._send(400, json.dumps({"ok": False, "error": "bad payload"}, ensure_ascii=False))
                    return
                merged = _norm_llm_config(cfg)
                settings = _load_json(SETTINGS_PATH, {})
                if not isinstance(settings, dict):
                    settings = {}
                settings["llm"] = merged
                rag_cfg = obj.get("rag")          # 同一保存动作可捎带 RAG 段
                if isinstance(rag_cfg, dict):
                    settings["rag"] = _norm_rag_config(rag_cfg)
                _save_json(SETTINGS_PATH, settings)
                self._send(200, json.dumps({"ok": True, "config": merged,
                                            "rag": settings.get("rag", _rag_saved_config())},
                                           ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        # ---- LLM 动作路由：业务性失败（连不上/没模型）一律 200 + ok:false，前端统一读 error ----
        if u.path in ("/api/llm-models", "/api/llm-test", "/api/annotate", "/api/rewrite"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": "请求体解析失败: %s" % e},
                                           ensure_ascii=False), "application/json; charset=utf-8")
                return
            try:
                client = _llm_from_request(obj)
                if u.path == "/api/llm-models":
                    models = client.list_models()
                    self._send(200, json.dumps({"ok": True, "models": models}, ensure_ascii=False),
                               "application/json; charset=utf-8")
                    return
                if u.path == "/api/llm-test":
                    ok, msg = client.test_connection()
                    self._send(200, json.dumps({"ok": ok, "message": msg}, ensure_ascii=False),
                               "application/json; charset=utf-8")
                    return
                text = str(obj.get("text", ""))[:30000]
                if not text.strip():
                    self._send(200, json.dumps({"ok": False, "error": "选区内容为空"}, ensure_ascii=False),
                               "application/json; charset=utf-8")
                    return
                if client.backend in ("ollama", "openai") and not client.model:
                    self._send(200, json.dumps({"ok": False,
                                                "error": "该后端需先在 LLM 设置中选择模型"},
                                               ensure_ascii=False), "application/json; charset=utf-8")
                    return
                # 联网查询开启时：先搜索 → 资料拼 prompt → LLM；失败静默降级纯模型
                ws_cfg = _llm_config_from_request(obj).get("web_search") or {}
                ws_flag = "off"
                ws_ctx = ""
                if ws_cfg.get("enabled"):
                    if _ws_mod is None:
                        ws_flag = "degraded"
                    else:
                        sr = _ws_mod.WebSearch(ws_cfg).search(text[:200])
                        if sr.get("success") and sr.get("results"):
                            ws_flag = "ok"
                            ws_ctx = _ws_mod.format_results(sr["results"])
                        else:
                            ws_flag = "degraded"
                is_ann = (u.path == "/api/annotate")
                if ws_flag == "ok":
                    sysp = (_WS_SYS_EXPLAIN if is_ann else _WS_SYS_POLISH) % ws_ctx
                    result = client.chat([{"role": "system", "content": sysp},
                                          {"role": "user", "content": text}])
                else:
                    result = client.explain(text) if is_ann else client.polish(text)
                payload = {"ok": True, "web_search": ws_flag}
                payload["note" if is_ann else "text"] = result
                self._send(200, json.dumps(payload, ensure_ascii=False),
                           "application/json; charset=utf-8")
            except _LLM_ERR as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        # ---- RAG 启停：手动管理（编辑器退出不联动停，仅按钮触发） ----
        if u.path in ("/api/rag/start", "/api/rag/stop"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except Exception:
                obj = {}
            try:
                if u.path == "/api/rag/start":
                    path = str(obj.get("path", "")).strip()
                    if not path or not os.path.isdir(path):
                        self._send(200, json.dumps(
                            {"ok": False, "error": "rag-assistant 路径无效或不存在，请检查 AI 设置中的路径"},
                            ensure_ascii=False), "application/json; charset=utf-8")
                        return
                    ok, msg = _rag_start_async(path)
                    self._send(200, json.dumps(
                        {"ok": ok, "message": msg if ok else "", "error": "" if ok else msg},
                        ensure_ascii=False), "application/json; charset=utf-8")
                else:
                    alive = _rag_stop()
                    if alive:
                        self._send(200, json.dumps(
                            {"ok": False, "error": "RAG 带看护自动重启（停止后端口仍存活），请在其运行窗口手动退出"},
                            ensure_ascii=False), "application/json; charset=utf-8")
                    else:
                        self._send(200, json.dumps(
                            {"ok": True, "message": "RAG 服务已停止", "kbs": []},
                            ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        # ---- RAG 检索增强润色/解释：query 拿上下文 → 拼 prompt → 走 LLM ----
        if u.path in ("/api/rag/annotate", "/api/rag/rewrite"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                obj = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": "请求体解析失败: %s" % e},
                                           ensure_ascii=False), "application/json; charset=utf-8")
                return
            try:
                if _ragc is None:
                    raise _LLM_ERR("rag_client.py 加载失败，详见 runtime/_ragc.err")
                client = _llm_from_request(obj)
                text = str(obj.get("text", ""))[:30000]
                if not text.strip():
                    self._send(200, json.dumps({"ok": False, "error": "选区内容为空"},
                                               ensure_ascii=False),
                               "application/json; charset=utf-8")
                    return
                if client.backend in ("ollama", "openai") and not client.model:
                    self._send(200, json.dumps(
                        {"ok": False, "error": "该后端需先在 LLM 设置中选择模型"},
                        ensure_ascii=False), "application/json; charset=utf-8")
                    return
                rag_cfg = _rag_from_request(obj)
                try:
                    # 检索 query 用选中文本截断（embedding 输入不宜过长）
                    hit = _ragc.RAGClient().query(rag_cfg["kb"], text[:2000], top_k=5)
                except _ragc.RAGClientError as e:
                    raise _LLM_ERR("RAG 检索失败（服务可能未启动，可在 AI 设置中启动）：%s" % e)
                if not hit.get("has_context"):
                    raise _LLM_ERR("知识库未检索到相关内容（可稍后重试，或在 AI 设置中更换知识库）")
                sysp = (_RAG_SYS_POLISH if u.path == "/api/rag/rewrite"
                        else _RAG_SYS_EXPLAIN) % (hit.get("context") or "")
                result = client.chat([{"role": "system", "content": sysp},
                                      {"role": "user", "content": text}])
                if u.path == "/api/rag/annotate":
                    self._send(200, json.dumps({"ok": True, "note": result}, ensure_ascii=False),
                               "application/json; charset=utf-8")
                else:
                    self._send(200, json.dumps({"ok": True, "text": result}, ensure_ascii=False),
                               "application/json; charset=utf-8")
            except _LLM_ERR as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return
        self._send(404, "not found")

    def log_message(self, *a):  # 静默
        pass


class Server(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.httpd = ReuseTCPServer(("127.0.0.1", PORT), Handler)

    def run(self):
        self.httpd.serve_forever()

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 系统托盘（纯 ctypes，无 pystray）
# ---------------------------------------------------------------------------
def build_tray(server):
    import ctypes
    from ctypes import wintypes

    # 部分 ctypes 分发版未导出指针宽类型，这里显式定义（Win64）
    LRESULT = ctypes.c_longlong
    UINT_PTR = ctypes.c_ulonglong

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    WM_TRAY = 0x0400 + 1
    WM_COMMAND = 0x0111
    WM_DESTROY = 0x0002
    WM_RBUTTONUP = 0x0205
    WM_LBUTTONUP = 0x0202

    NIF_MESSAGE = 0x1
    NIF_ICON = 0x2
    NIF_TIP = 0x4
    NIM_ADD = 0x0
    NIM_DELETE = 0x1

    user32.EnumWindows.restype = wintypes.BOOL
    _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                    wintypes.WPARAM, wintypes.LPARAM]

    TPM_RIGHTBUTTON = 0x0002
    TPM_RETURNCMD = 0x0100

    MF_STRING = 0x0000
    IDI_APPLICATION = 32512
    ID_TRAY = 1
    ID_NEW = 1001
    ID_EXIT = 1002

    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD), ("pt", POINT),
        ]

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT), ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HANDLE), ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
            ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_char * 16),
            ("hBalloonIcon", wintypes.HICON),
        ]

    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, UINT_PTR, wintypes.LPCWSTR]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPCVOID]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = LRESULT
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

    hinst = kernel32.GetModuleHandleW(None)
    # 资源 ID 按 Windows 约定以 (LPWSTR)(UINT_PTR)id 形式传入
    # 托盘图标：优先用工具自带 md-editor.ico，取不到才退回系统默认
    hicon = None
    _ico = os.path.join(HERE, "md-editor.ico")
    try:
        if os.path.exists(_ico):
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                          ctypes.c_uint, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_uint]
            hicon = user32.LoadImageW(None, _ico, 1, 16, 16, 0x10)
    except Exception:
        hicon = None
    if not hicon:
        hicon = user32.LoadIconW(0, ctypes.c_wchar_p(IDI_APPLICATION))

    class Tray:
        def __init__(self):
            self.hwnd = None
            self._wndproc = None  # 防止回调被 GC

        def wndproc(self, hwnd, msg, wparam, lparam):
            if msg == WM_TRAY and lparam == WM_LBUTTONUP:
                self.toggle_editor()
                return 0
            if msg == WM_TRAY and lparam == WM_RBUTTONUP:
                self.show_menu()
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        def find_editor_windows(self):
            found = []
            _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                           wintypes.LPARAM)

            def cb(h, l):
                try:
                    if not user32.IsWindowVisible(h):
                        return True
                    n = user32.GetWindowTextLengthW(h)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        user32.GetWindowTextW(h, buf, n + 1)
                        if ("MDEditor" in buf.value
                                or "Markdown 编辑器" in buf.value):
                            found.append(h)
                except Exception:
                    pass
                return True

            try:
                user32.EnumWindows(_ENUMPROC(cb), 0)
            except Exception:
                pass
            return found

        def toggle_editor(self):
            wins = self.find_editor_windows()
            if not wins:
                webbrowser.open("http://127.0.0.1:%d/" % PORT)
                return
            h = wins[0]
            try:
                if user32.IsIconic(h):
                    user32.ShowWindow(h, 9)          # SW_RESTORE
                    user32.SetForegroundWindow(h)
                elif user32.GetForegroundWindow() == h:
                    user32.ShowWindow(h, 6)          # SW_MINIMIZE
                else:
                    user32.SetForegroundWindow(h)    # 前置已开窗口
            except Exception:
                pass

        def show_menu(self):
            hmenu = user32.CreatePopupMenu()
            user32.AppendMenuW(hmenu, MF_STRING, ID_NEW, "新建空白文档")
            user32.AppendMenuW(hmenu, MF_STRING, ID_EXIT, "退出")
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)
            cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                       pt.x, pt.y, 0, self.hwnd, None)
            user32.DestroyMenu(hmenu)
            if cmd == ID_NEW:
                webbrowser.open("http://127.0.0.1:%d/" % PORT)
            elif cmd == ID_EXIT:
                self.quit()

        def quit(self):
            # 关闭编辑器窗口（“退出”= 整个应用都关掉）
            for h in self.find_editor_windows():
                try:
                    user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
                except Exception:
                    pass
            time.sleep(0.25)
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(nid)
            nid.hWnd = self.hwnd
            nid.uID = ID_TRAY
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            try:
                server.stop()
            except Exception:
                pass
            user32.PostQuitMessage(0)

        def run(self):
            self._wndproc = WNDPROC(self.wndproc)
            cls = WNDCLASSEXW()
            cls.cbSize = ctypes.sizeof(cls)
            cls.lpfnWndProc = self._wndproc
            cls.hInstance = hinst
            cls.lpszClassName = "MDViewerTrayWnd"
            atom = user32.RegisterClassExW(ctypes.byref(cls))
            if not atom:
                raise ctypes.WinError(ctypes.get_last_error())
            self.hwnd = user32.CreateWindowExW(
                0, "MDViewerTrayWnd", None, 0, 0, 0, 0, 0,
                None, None, hinst, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(nid)
            nid.hWnd = self.hwnd
            nid.uID = ID_TRAY
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = hicon
            nid.szTip = "Markdown 编辑器"
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                raise ctypes.WinError(ctypes.get_last_error())
            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

    Tray().run()




# ---------------------------------------------------------------------------
# 分页导出组装（py 全权负责；前端只提交渲染好的 body 与排版 CSS）
# ---------------------------------------------------------------------------
PAGED_PAGE_BOX = {"bc": "@bottom-center", "br": "@bottom-right", "bl": "@bottom-left",
                  "tc": "@top-center", "tr": "@top-right"}

# 命名纸张的纵向高度（mm，portrait）——用于推导图片版面 max-height
PAPER_H_MM = {"A0": 1189, "A1": 841, "A2": 594, "A3": 420, "A4": 297, "A5": 210,
              "B0": 1414, "B1": 1000, "B2": 707, "B3": 500, "B4": 353, "B5": 250,
              "Letter": 279.4, "Legal": 355.6, "Ledger": 431.8}
PAPER_W_MM = {"A0": 841, "A1": 594, "A2": 420, "A3": 297, "A4": 210, "A5": 148,
              "B0": 1000, "B1": 707, "B2": 500, "B3": 353, "B4": 250, "B5": 176,
              "Letter": 215.9, "Legal": 215.9, "Ledger": 279.4}

# 分页导出基础正文样式（镜像编辑器预览 .markdown-body；固定色值——
# 导出文档里 CSS 变量未定义，不能直接搬预览样式；排版规范借鉴
# Cogito_Scribit STYLE_GUIDE 一章（表格）与十一章（版面缩放纪律））：
#   * border-box / pre pre-wrap+anywhere / code anywhere（十一章 print 硬约束）
#   * 表格 width:100% + table-layout:auto + th/td 细边框 keep-all+anywhere（1.1）
#   * thead 跨页自动重复表头 + tr/li break-inside:avoid（表格切分行不腰斩）
#   * 引用编号索引表（表头=编号|引用|出处）ref-table 固定列宽 8%/47%/45%（1.2）
# v2.10 图题/表题基础样式：与 markdown-editor.html 预览同口径。打印（paged）
# 与导出 HTML 的模板 CSS 是独立拷贝，此前一条 .mde-fig 规则都没有——
# t/b（flex-direction:column-reverse）、{N} 宽度（width:var(--figw)）、
# s 间距（calc × --figgap/--tabgap）、w 裁剪（nowrap+ellipsis）在打印件里
# 全部丢失（题注恒显示在图下方）。克隆保留 class 与内联 style（--figw 等
# 自定义属性随元素带过来），模板里有规则即可完整还原。
FIGCAP_BASE_CSS = """
.markdown-body figure.mde-fig{margin:.9em 0;max-width:100%;width:var(--figw,auto);break-inside:avoid;}
.markdown-body figure.mde-fig[data-fig-side="t"]{display:flex;flex-direction:column-reverse;align-items:flex-start;}
.markdown-body figure.mde-fig>img{max-width:100%;height:auto;margin:0;}
.markdown-body figure.mde-fig>.diagram{width:100%;max-width:100%;margin:0;}
.markdown-body figcaption.mde-figcap{width:100%;max-width:100%;overflow:hidden;font-size:.92em;line-height:1.5;}
.markdown-body figure.mde-fig[data-fig-side="b"]>figcaption{margin-top:calc(1em * var(--figgap,.3));}
.markdown-body figure.mde-fig[data-fig-side="t"]>figcaption{margin-bottom:calc(1em * var(--figgap,.3));}
.markdown-body figure.mde-fig[data-fig-mode="w"]>figcaption{white-space:nowrap;text-overflow:ellipsis;}
.markdown-body .mde-tblwrap{margin:.9em 0;}
.markdown-body .mde-tabcap{font-size:.92em;line-height:1.5;overflow:hidden;}
.markdown-body .mde-tblwrap[data-tab-side="t"]>.mde-tabcap{margin-bottom:calc(1em * var(--tabgap,.3));}
.markdown-body .mde-tblwrap[data-tab-side="b"]>.mde-tabcap{margin-top:calc(1em * var(--tabgap,.3));}
.markdown-body .mde-cnum{margin-right:.35em;}
.markdown-body .fill-col figure.mde-fig{width:auto !important;margin:0;}
"""

PAGED_BASE_CSS = """
*{box-sizing:border-box;}
.markdown-body{color:#222;line-height:1.7;word-wrap:break-word;overflow-wrap:anywhere;}
.markdown-body h1,.markdown-body h2,.markdown-body h3,.markdown-body h4,.markdown-body h5,.markdown-body h6{line-height:1.35;margin:1.4em 0 .6em;font-weight:650;}
.markdown-body h1{font-size:1.9em;border-bottom:1px solid #ddd;padding-bottom:.3em;}
.markdown-body h2{font-size:1.5em;border-bottom:1px solid #ddd;padding-bottom:.25em;}
.markdown-body h3{font-size:1.25em;}
.markdown-body h4{font-size:1.08em;}
.markdown-body p{margin:.85em 0;}
.markdown-body a{color:#4a6cf7;text-decoration:none;}
.markdown-body strong{font-weight:700;}
.markdown-body em{font-style:italic;}
.markdown-body del{opacity:.6;}
.markdown-body code{font-family:Consolas,monospace;font-size:.88em;background:#f4f4f4;padding:.15em .4em;border-radius:5px;overflow-wrap:anywhere;}
.markdown-body pre{background:#f4f4f4;border:1px solid #ddd;border-radius:6px;padding:14px 16px;margin:.9em 0;white-space:pre-wrap !important;overflow-wrap:anywhere !important;}
.markdown-body pre code{background:none;padding:0;font-size:.85em;line-height:1.6;}
.markdown-body blockquote{margin:.9em 0;padding:.4em 1em;border-left:3px solid #4a6cf7;background:#f5f7ff;border-radius:0 6px 6px 0;}
.markdown-body blockquote p{margin:.4em 0;}
.markdown-body ul,.markdown-body ol{margin:.7em 0;padding-left:1.6em;}
.markdown-body li{margin:.3em 0;break-inside:avoid;}
.markdown-body li.u-solid{list-style-type:disc;}
.markdown-body li.u-hollow{list-style-type:circle;}
.markdown-body li.task{list-style:none;margin-left:-1.4em;}
.markdown-body li.task input{margin-right:.5em;vertical-align:middle;}
.markdown-body hr{border:none;border-top:1px solid #ddd;margin:1.6em 0;}
.markdown-body table{border-collapse:collapse;margin:1em 0;width:100%;table-layout:auto;font-size:.93em;break-inside:auto;}
.markdown-body thead{display:table-header-group;}
.markdown-body tr{break-inside:avoid;}
.markdown-body th,.markdown-body td{border:1px solid #bbb;padding:7px 12px;text-align:left;word-break:keep-all;overflow-wrap:anywhere;}
.markdown-body th{background:#f0f2f6;font-weight:650;}
.markdown-body img{display:block;margin:0 auto;max-width:100%;max-height:__IMGMAXH__mm;break-inside:avoid;}
.markdown-body p:has(>img){margin:0;text-indent:0 !important;}
.markdown-body p:has(>img[data-img-align="center"]){text-align:center !important;}
.markdown-body p:has(>img[data-img-align="left"]){text-align:left !important;}
.markdown-body p:has(>img[data-img-align="right"]){text-align:right !important;}
.markdown-body .diagram[data-diagram-align="center"]{margin-left:auto;margin-right:auto;}
.markdown-body .diagram[data-diagram-align="right"]{margin-left:auto;}
.markdown-body .diagram[data-diagram-align="left"]{margin-right:auto;}
.markdown-body .fill-row{display:flex;gap:1em;margin:.6em 0;break-inside:avoid;}
.markdown-body .fill-col{min-width:0;}
.markdown-body .fill-col img{width:100% !important;height:auto;}
.markdown-body .fill-col table img{width:auto !important;max-width:100% !important;height:auto;}
.markdown-body .fill-col .diagram{width:100% !important;}
.markdown-body .fill-col .diagram svg{max-width:100%;height:auto;}
.markdown-body table.ref-table{table-layout:fixed;}
.markdown-body table.ref-table th:nth-child(1),.markdown-body table.ref-table td:nth-child(1){width:8%;}
.markdown-body table.ref-table th:nth-child(2),.markdown-body table.ref-table td:nth-child(2){width:47%;}
.markdown-body table.ref-table th:nth-child(3),.markdown-body table.ref-table td:nth-child(3){width:45%;}
"""

# ---------- 超高长图切片（导出渲染期产物，源资产 SSOT 不动） ----------
# 规则：渲染高 ≤ 版心的图整图原子一页；高 > 版心的长截图按小条带竖切
# 续排（像表格跨页一样流入剩余空间），条带渲染高 = 版心高/3（3 条正好满页）。
# 切点吸附静默行（截图里的空白行/段间距），不切断文字行、不重叠不遗漏。
# 切片落 HERE/_slice/<sha1>/，同字节图幂等复用；PIL 缺失或读图失败原样保留（fail-closed）。
_SLICE_SNAP_MM = 8.0  # 切点吸附搜索窗口（半宽）


def _slice_tall_images(body_html, icb_w_mm, img_maxh_mm):
    img_re = re.compile(r'<img[^>]*?src="(/img\?path=[^"]+)"[^>]*?>')

    def _quiet_cuts(bright, h, nominal, win):
        # 在 nominal±win 内找亮度最平稳处下刀（空白行/段间隙）；找不到用原切点
        lo, hi = max(1, nominal - win), min(h - 1, nominal + win)
        best, best_d = nominal, None
        for i in range(lo, hi + 1):
            d = abs(bright[i] - bright[i - 1])
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _repl(m):
        tag = m.group(0)
        try:
            from PIL import Image
        except ImportError:
            return tag
        path = urllib.parse.unquote(m.group(1).split("path=", 1)[1])
        if not os.path.isfile(path):
            return tag
        try:
            im = Image.open(path)
            im.load()
        except Exception:
            return tag
        w, h = im.size
        if w <= 1 or h <= 1:
            return tag
        # 宽度参数：style="width:N%"（前端 {N} 后缀产出）→ 版面宽度的 N%。无参数满宽。
        # 切片决策一切基于调整后的真实落地尺寸：eff_w_mm 为实际渲染宽，切片几何全按它换算
        pm = re.search(r'width:\s*([\d.]+)\s*%', tag)
        pct = 1.0
        if pm:
            try:
                pct = min(max(float(pm.group(1)), 0.0), 100.0) / 100.0
            except ValueError:
                pct = 1.0
            if pct <= 0.001:
                pct = 1.0  # 宽度为 0 的样式不当真，回满宽
        eff_w_mm = icb_w_mm * pct
        # 调整后渲染高不超版心 → 整图原子，不切
        if eff_w_mm * h / w <= img_maxh_mm:
            return tag
        import hashlib
        with open(path, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()[:12]
        # 条带像素高：渲染高 = 版心高/6（细条带续排，页面剩余留白上限 = 一条高）。
        # 1/3 版心实测留白过大（吸附后 3 条塞不进一页即剩 ~80mm 空白），故取 1/6
        strip_px = max(1, int(round(max(20.0, img_maxh_mm / 6.0) / eff_w_mm * w)))
        # 缓存键 = 内容 sha1 + 条带几何（strip_px）——几何参数变更时旧切片不复用
        digest = "%s-%d" % (digest, strip_px)
        n = (h + strip_px - 1) // strip_px
        gap = max(1, strip_px // 4)
        # 静默行亮度剖面：宽度压成 1px 即每行平均亮度（BILINEAR 均值）
        bright = list(im.convert("L").resize((1, h), Image.BILINEAR).getdata())
        win = max(1, int(round(_SLICE_SNAP_MM / eff_w_mm * w)))
        cuts = [0]
        for k in range(1, n):
            c = _quiet_cuts(bright, h, k * strip_px, win)
            if c <= cuts[-1] + gap:
                c = cuts[-1] + gap
            if c >= h - gap:
                break  # 剩余不足小条，并入末条
            cuts.append(c)
        cuts.append(h)
        out_dir = os.path.join(HERE, "_slice", digest)
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError:
            return tag
        am = re.search(r'alt="([^"]*)"', tag)
        alt = am.group(1) if am else ""
        # 条带继承源图宽度约束：按同一百分比显示时，条带高度与切片几何严格一致
        style = ' style="width:%s%%"' % pm.group(1).strip() if pm else ""
        tags = []
        for i in range(len(cuts) - 1):
            fp = os.path.join(out_dir, "strip-%02d.png" % (i + 1))
            if not os.path.exists(fp):  # 幂等：已切过的直接复用
                try:
                    im.crop((0, cuts[i], w, cuts[i + 1])).save(fp, "PNG")
                except Exception:
                    return tag
            tags.append('<img src="/static/_slice/%s/strip-%02d.png" alt="%s"%s>'
                        % (digest, i + 1, alt, style))
        return "".join(tags)

    return img_re.sub(_repl, body_html)

PAGED_FILLER_TMPL = """
(function(){
  var tpl = __TPL__;
  var sel = __SEL__;
  var size = __SIZE__;
  var lastN = -1, stable = 0, done = false;
  var mo = new MutationObserver(function(){ if(!done) lastN = -1; });
  mo.observe(document.body, {childList:true, subtree:true});
  /* 纯目录页判定：页内有目录且无任何正文标题锚——目录不计入页码（6.4） */
  function tocOnly(pg){
    return !!(pg.querySelector('.md-toc-wrap') && !pg.querySelector('[id^="md-h-"]'));
  }
  function pageOf(el){
    var n = el;
    while(n && !(n.classList && n.classList.contains('pagedjs_page'))) n = n.parentNode;
    return n;
  }
  var iv = setInterval(function(){
    var pgs = document.querySelectorAll('.pagedjs_page');
    var n = pgs.length;
    if(!n) return;
    if(n !== lastN){ lastN = n; stable = 0; return; }
    stable++;
    if(stable < 3) return;
    clearInterval(iv); mo.disconnect(); done = true;
    /* 页码映射：纯目录页不编号；正文页码 = 物理序 - 已跳过的目录页数 */
    var skip = [], shown = [], P = 0, c = 0, i;
    for(i=0;i<n;i++){ skip[i] = tocOnly(pgs[i]); if(!skip[i]) P++; }
    for(i=0;i<n;i++){ shown[i] = skip[i] ? 0 : ++c; }
    for(i=0;i<n;i++){
      if(skip[i]) continue;
      /* 外侧奇右偶左（6.4）；固定位置模式 odd/even 同盒 */
      var boxSel = (shown[i] % 2 === 1) ? sel.odd : sel.even;
      var el = pgs[i].querySelector(boxSel);
      if(el){
        el.textContent = tpl.replace('{p}', shown[i]).replace('{P}', P);
        el.style.fontSize = size + 'pt';
        el.style.color = '#666';
      }
    }
    /* 目录条目页码：按标题锚真实落页的显示页码回填（口径与页脚一致），
       点线引导 + 页码右对齐列（6.4 目录规范） */
    var links = document.querySelectorAll('.md-toc a[href^="#md-h-"]');
    for(i=0;i<links.length;i++){
      var href = links[i].getAttribute('href') || '';
      var dst = document.getElementById(decodeURIComponent(href.slice(1)));
      if(!dst) continue;
      var dpg = pageOf(dst);
      var idx = -1;
      for(var k=0;k<n;k++){ if(pgs[k] === dpg){ idx = k; break; } }
      if(idx < 0 || skip[idx]) continue;
      var dots = document.createElement('span');
      dots.className = 'toc-dots';
      var sp = document.createElement('span');
      sp.className = 'md-toc-pg';
      sp.textContent = shown[idx];
      links[i].appendChild(dots);
      links[i].appendChild(sp);
    }
  }, 300);
})();
"""


def _strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)




def build_standalone_html(md_path, body_html, ts_css, page_cfg=None):
    """普通 .html 导出组装（py 全权：图片路径还原 + katex css + 排版样式）。
    版心宽度按排版 page 节（纸宽−左右边距，mm），与预览栏/打印版口径一致
    （此前写死 max-width:820px，{N} 图片宽度语义随版心漂移）。"""
    katex_css = ""
    kp = os.path.join(HERE, "katex", "katex.min.css")
    if os.path.exists(kp):
        katex_css = io.open(kp, encoding="utf-8").read().replace(
            "url(fonts/", "url(/static/katex/fonts/")
    def _proxy(m):
        p = urllib.parse.unquote(m.group(1)).replace("\\", "/")
        return 'src="file:///' + p + '"'
    body = re.sub(r'src="/img\?path=([^"]+)"', _proxy, body_html)
    if md_path:
        mdir = os.path.dirname(md_path).replace("\\", "/")
        # 排除 data:（内嵌图/栅格化图表；历史缺陷：data: 被当相对路径拼上
        # 目录前缀，成 file:///dir/data:image/png;base64,... 垃圾 src）
        body = re.sub(r'src="(?!https?:|file:|data:|/|#)([^"]+)"',
                      lambda m: 'src="file:///%s/%s"' % (mdir, m.group(1)), body)
    m1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", body)
    title = re.sub(r"<[^>]+>", "", m1.group(1)).strip() if m1 else "未命名文档"
    ts = ts_css.replace("#preview", ".markdown-body")
    # 版心宽（mm）：纸宽−左右边距（与预览栏 applyPaperWidth 同口径）
    _pc = page_cfg or {}
    _paper = _pc.get("paper", "A4")
    if _paper == "custom":
        try:
            _pwv = float(_pc.get("pw") or 0)
        except Exception:
            _pwv = 0
        if _pwv <= 0:
            _paper = "A4"
    if _paper == "custom":
        _w_mm = _pwv
    else:
        _w_mm = PAPER_W_MM.get(_paper, 210.0)
    try:
        _mlv = float(_pc.get("ml", 18))
        _mrv = float(_pc.get("mr", 18))
    except Exception:
        _mlv, _mrv = 18.0, 18.0
    _w_mm = max(50.0, _w_mm - _mlv - _mrv)
    html = ('<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="UTF-8"><title>__TITLE__</title>'
        "<style>__KATEX__</style><style>div.md-math-block{overflow-x:auto;margin:.8em 0;}"
        "span.md-math-inline{white-space:nowrap;}__TS__</style>"
        '<style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",'
        '"Microsoft YaHei",sans-serif;width:__CONTENTW__mm;max-width:none;'
        'margin:40px auto;padding:0;'
        'line-height:1.7;color:#222;}'
        'h1,h2{border-bottom:1px solid #eee;padding-bottom:.3em;}'
        'code{background:#f4f4f4;padding:.15em .4em;border-radius:4px;font-family:Consolas,monospace;}'
        'pre{background:#f4f4f4;padding:14px;border-radius:8px;overflow:auto;}'
        'blockquote{border-left:3px solid #4a6cf7;background:#f5f7ff;padding:.4em 1em;margin:1em 0;}'
        'table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ddd;padding:7px 12px;}'
        'li.u-solid{list-style-type:disc;}li.u-hollow{list-style-type:circle;}'
        'li.task{list-style:none;}'
        'p:has(>img){text-indent:0 !important;}'
        'p:has(>img[data-img-align="center"]){text-align:center !important;}'
        'p:has(>img[data-img-align="left"]){text-align:left !important;}'
        'p:has(>img[data-img-align="right"]){text-align:right !important;}'
        '.diagram[data-diagram-align="center"]{margin-left:auto;margin-right:auto;}'
        '.diagram[data-diagram-align="right"]{margin-left:auto;}'
        '.diagram[data-diagram-align="left"]{margin-right:auto;}'
        '.fill-row{display:flex;gap:1em;margin:.6em 0;}'
        '.fill-col{min-width:0;}'
        '.fill-col img{width:100% !important;height:auto;}'
        '.fill-col table img{width:auto !important;max-width:100% !important;height:auto;}'
        '.fill-col .diagram{width:100% !important;}'
        '.fill-col .diagram svg{max-width:100%;height:auto;}'
        'img,svg{max-width:100%;}svg{height:auto;}a{color:#4a6cf7;}'
        '__FIGCAP__</style></head><body class="markdown-body">__BODY__'
        '<button id="__copyBtn" style="position:fixed;right:18px;bottom:18px;z-index:2147483647;'
        'padding:9px 16px;border:0;border-radius:8px;background:#4a6cf7;color:#fff;'
        'font:14px/1.2 -apple-system,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;'
        'cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.25)">一键复制</button>'
        '<script>'
        'function __inlineClone(src){'
        'var props=["font-family","font-size","font-weight","font-style","font-variant",'
        '"color","background-color","text-align","line-height","text-decoration",'
        '"letter-spacing","vertical-align","text-indent","border-top","border-bottom",'
        '"border-left","border-right","padding","margin"];'
        'var c=src.cloneNode(true);'
        'var all=[c].concat([].slice.call(c.querySelectorAll("*")));'
        'all.forEach(function(el){'
        'if(!el.style)return;'
        'var cs=getComputedStyle(el),keep=[];'
        'props.forEach(function(p){var v=cs.getPropertyValue(p);'
        'if(v&&v!=="none"&&v!=="normal"&&v!=="0px"&&v!=="rgba(0, 0, 0, 0)")keep.push(p+":"+v);});'
        'el.removeAttribute("class");el.removeAttribute("id");'
        'if(keep.length)el.style.cssText=keep.join(";");else el.removeAttribute("style");});'
        'return c;}'
        'document.getElementById("__copyBtn").addEventListener("click",function(){'
        'var btn=this,mb=document.querySelector(".markdown-body");'
        'if(!mb)return;'
        'var clone=__inlineClone(mb);'
        'var html=clone.outerHTML;'
        'var plain=mb.innerText||"";'
        'function ok(){var t=btn.textContent;btn.textContent="已复制";setTimeout(function(){btn.textContent=t;},1500);}'
        'function compat(){try{var r=document.createRange();r.selectNode(mb);'
        'var s=getSelection();s.removeAllRanges();s.addRange(r);'
        'document.execCommand("copy");s.removeAllRanges();ok();}catch(e){btn.textContent="复制失败";}}'
        'try{'
        'if(window.ClipboardItem&&navigator.clipboard&&navigator.clipboard.write){'
        'var b1=new Blob([html],{type:"text/html"});'
        'var b2=new Blob([plain],{type:"text/plain"});'
        'navigator.clipboard.write([new ClipboardItem({"text/html":b1,"text/plain":b2})]).then(ok,compat);'
        '}else{compat();}'
        '}catch(e){compat();}'
        '});'
        '</script>'
        '</body></html>')
    html = html.replace("__TITLE__", html_module.escape(title))
    html = html.replace("__KATEX__", katex_css)
    html = html.replace("__TS__", ts)
    html = html.replace("__FIGCAP__", FIGCAP_BASE_CSS)
    html = html.replace("__CONTENTW__", ("%.2f" % _w_mm).rstrip("0").rstrip("."))
    html = html.replace("__BODY__", body)
    return html


# ---------------------------------------------------------------------------
# docx 导出：依赖内置（随应用分发，无需联网）
#   - python-docx / lxml / latex2mathml / Pillow 的 cp311 wheel 一并归入
#     docxdeps/，随 MarkdownEditor-app 一起打包发布；
#   - 各包许可证文本收录于 docxdeps/LICENSES/，均为 BSD/MIT 等宽松许可，
#     可闭源分发、无需开源本应用代码，仅需随包附带其许可声明。
# ---------------------------------------------------------------------------
DOCX_DEPS = os.path.join(HERE, "docxdeps")
_docx_ready = False


def _ensure_docx_deps():
    """确保 docx 导出依赖可用。依赖随应用内置（docxdeps/），无需联网下载。"""
    global _docx_ready
    if _docx_ready:
        return True
    import sys
    # 1) 运行环境已可 import -> 直接用
    try:
        import docx  # noqa: F401
        import lxml  # noqa: F401
        import latex2mathml  # noqa: F401
        import PIL  # noqa: F401
        return True
    except Exception:
        pass
    # 2) 内置 docxdeps/ 已随应用分发 -> 加入 sys.path 复用
    if (os.path.isdir(os.path.join(DOCX_DEPS, "docx"))
            and os.path.isdir(os.path.join(DOCX_DEPS, "latex2mathml"))
            and os.path.isdir(os.path.join(DOCX_DEPS, "lxml"))
            and os.path.isdir(os.path.join(DOCX_DEPS, "PIL"))):
        sys.path.insert(0, DOCX_DEPS)
        _docx_ready = True
        return True
    raise RuntimeError(
        "docx 导出依赖缺失：找不到内置 docxdeps/ 目录"
        "（应在 MarkdownEditor-app/docxdeps/ 内随应用分发）")


def build_paged_html(md_path, body_html, ts_css, page_cfg):
    paper = page_cfg.get("paper", "A4")
    pw, ph = page_cfg.get("pw", ""), page_cfg.get("ph", "")
    if paper == "custom" and pw and ph:
        size_str = "%smm %smm" % (pw, ph)
        try:
            paper_h = float(ph)
        except (TypeError, ValueError):
            paper_h = PAPER_H_MM["A4"]
    else:
        size_str = paper
        paper_h = PAPER_H_MM.get(paper, 297)
    mt = page_cfg.get("mt", 25)
    mr = page_cfg.get("mr", 18)
    mb = page_cfg.get("mb", 25)
    ml = page_cfg.get("ml", 18)
    # 图片版面预算：max-height = 纸高 − 上下边距 − 2mm 安全余量。
    # 1mm 余量曾引爆长截图事故：图 246mm + 打印版 p/img 自身边距 > 247mm 版心，
    # 图在任一页都放不下 → Paged.js 反复推页产出连续空白页、图被溢出裁掉。
    # 现打印版 img margin=0 且 p:has(>img) margin=0，2mm 余量兜底舍入误差。
    # 浏览器对 img 的 max-width/max-height 约束天然保持宽高比——
    # 宽超按宽缩、高超按高缩，图片不超出版面。
    try:
        img_maxh = max(20.0, float(paper_h) - float(mt) - float(mb) - 2.0)
    except (TypeError, ValueError):
        img_maxh = 245.0
    # 版心宽（切片条带的渲染宽度基准）
    try:
        paper_w = (float(pw) if (paper == "custom" and pw)
                   else float(PAPER_W_MM.get(paper, 210.0)))
        icb_w = max(40.0, paper_w - float(mr) - float(ml))
    except (TypeError, ValueError):
        icb_w = 174.0
    pn = page_cfg.get("pn", {}) or {}
    toc_cfg = page_cfg.get("toc", {}) or {}

    # @page：纸张 + 边距 + 页码 margin box（占位空白，正文文本由填充脚本写入；
    # 页码形态照抄书册规范 STRUCTURE_GUIDE 6.4：默认外侧奇右偶左、纯数字、9pt 灰）
    page_css = "@page{size:%s;margin:%smm %smm %smm %smm;" % (size_str, mt, mr, mb, ml)
    if pn.get("on") == "on":
        sz = pn.get("size", 9)
        if pn.get("pos", "outer") == "outer":
            page_css += ('@bottom-right{content:" ";font-size:%spt;}'
                         '@bottom-left{content:" ";font-size:%spt;}' % (sz, sz))
        else:
            box = PAGED_PAGE_BOX.get(pn.get("pos"), "@bottom-center")
            page_css += '%s{content:" ";font-size:%spt;}' % (box, sz)
    page_css += "}"
    # 分页规则（STRUCTURE_GUIDE 6.2 书籍标准，逐条对齐 PRINT_CSS）：
    # h1 每篇独立起页；小节标题不落页末；段落防孤立行 2/2；
    # 单行 bullet 1/1（widows 2 会永久推页留白）；hr 禁断但不加 break-before
    #（与 h2 break-after 形成保护链会整块推页留半页空白，2026-08-28 判例）；
    # 纵向结构（table/pre）允许内容单元间拆页，横向结构（blockquote）不拆
    page_css += (
        ".md-toc-wrap{break-after:page;}"
        "h1{break-before:page;}"
        "h2,h3,h4{break-after:avoid;}"
        "p{orphans:2;widows:2;}li{orphans:1;widows:1;}"
        "hr{break-inside:avoid;break-after:avoid;}"
        "table{break-inside:auto;}blockquote{break-inside:avoid;}"
    )

    # TOC + 锚点
    heads = []

    def _head(m):
        lvl = int(m.group(1))
        inner = m.group(2)
        heads.append((lvl, inner))
        return '<h%s id="md-h-%d">%s</h%s>' % (lvl, len(heads), inner, lvl)

    body = re.sub(r"<h([123])[^>]*>([\s\S]*?)</h\1>", _head, body_html)
    toc_html = ""
    if toc_cfg.get("on") == "on" and heads:
        items = "".join(
            '<div class="toc-l%d"><a href="#md-h-%d">%s</a></div>' % (lvl, i, txt)
            for i, (lvl, txt) in enumerate(heads, 1))
        solo = "break-before:page;break-after:page;" if toc_cfg.get("solo", True) else "break-after:page;"
        toc_html = ('<div class="md-toc-wrap" style="%s"><nav class="md-toc">'
                    '<div class="md-toc-title">目 录</div>%s</nav></div>') % (solo, items)
        if toc_cfg.get("pos", "top") == "afterh1":
            body = re.sub(r"(<h1[\s\S]*?</h1>)", lambda m: m.group(1) + toc_html, body, count=1)
        else:
            body = toc_html + body

    # 引用编号索引表识别（STYLE_GUIDE 1.2）：表头 = 编号|引用|出处 → ref-table 固定列宽
    body = re.sub(
        r'<table>(\s*<thead>\s*<tr>\s*<th[^>]*>\s*编号\s*</th>\s*'
        r'<th[^>]*>\s*引用\s*</th>\s*<th[^>]*>\s*出处\s*</th>)',
        r'<table class="ref-table">\1', body)

    # 超高长图切片：高 > 版心的图切小条带续排（切点吸附静默行）
    body = _slice_tall_images(body, icb_w, img_maxh)

    # 图片 src 保持 /img 代理原样：打印版由系统浏览器打开的是服务端
    # http URL（/static/document.paged.html），http 页面按浏览器安全策略
    # 禁止加载 file:/// 本地资源（重写即真实图片全挂——v2.1.3 曾改反）；
    # /img 代理同源 http 可用，长图切片 /static/_slice/ 同理；图表为
    # data: 内嵌天然自包含。用户打印/存 PDF 由浏览器渲染完成后输出，
    # 图片像素已进最终产物，无需页面本身离线可开。

    # 基础正文样式（表格边框/图片版面/断行纪律）——此前缺失是表格边框
    # 在分页导出中消失的根因；置于 ts_css 之前，排版设置的 !important 仍可覆盖
    base_css = PAGED_BASE_CSS.replace("__IMGMAXH__", ("%.2f" % img_maxh)) + FIGCAP_BASE_CSS

    # 资源内嵌（全部本地，离线可用）
    katex_css = ""
    kp = os.path.join(HERE, "katex", "katex.min.css")
    if os.path.exists(kp):
        katex_css = io.open(kp, encoding="utf-8").read().replace(
            "url(fonts/", "url(/static/katex/fonts/")
    paged_js = ""
    pp = os.path.join(HERE, "pagedjs", "paged.polyfill.min.js")
    if os.path.exists(pp):
        paged_js = io.open(pp, encoding="utf-8").read().replace("</script", "<\\/script")

    # 页码填充脚本（Paged.js 分页完成、DOM 稳定后填入；模板/位置/字号由配置注入。
    # 外侧模式：奇页右下、偶页左下（书册规范 6.4），sel 传 odd/even 两个选择器）
    pn_pos = pn.get("pos", "outer")
    if pn_pos == "outer":
        sel = {"odd": ".pagedjs_margin-bottom-right .pagedjs_margin-content",
               "even": ".pagedjs_margin-bottom-left .pagedjs_margin-content"}
    else:
        _s = ".pagedjs_margin-%s .pagedjs_margin-content" % PAGED_PAGE_BOX.get(
            pn_pos, "bottom-center").replace("@", "")
        sel = {"odd": _s, "even": _s}
    filler_vals = {
        "__TPL__": json.dumps(pn.get("tpl", "{p}"), ensure_ascii=False),
        "__SEL__": json.dumps(sel),
        "__SIZE__": json.dumps(str(pn.get("size", 9))),
    }
    filler = PAGED_FILLER_TMPL
    for k, v in filler_vals.items():
        filler = filler.replace(k, v)
    filler = filler.replace("</script", "<\\/script")

    # 目录版式（STRUCTURE_GUIDE 6.4：点线引导 + 页码右对齐列；
    # 11.4 几何纪律：页码列统一右缘、点线与页码留间距不重叠）
    toc_css = (
        ".md-toc-title{font-size:1.7em;font-weight:700;text-align:center;margin:0 0 1.4em;}"
        ".md-toc .toc-l1{font-weight:600;margin:.9em 0 .25em;}"
        ".md-toc .toc-l2{padding-left:1.6em;}"
        ".md-toc .toc-l3{padding-left:3.2em;}"
        ".md-toc a{display:flex;align-items:baseline;text-decoration:none;color:inherit;padding:.18em 0;}"
        ".md-toc .toc-dots{flex:1;min-width:1.5em;border-bottom:1px dotted #999;"
        "margin:0 6px;transform:translateY(-.25em);}"
        ".md-toc .md-toc-pg{white-space:pre;font-variant-numeric:tabular-nums;}"
    )

    m1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", body)
    title = _strip_tags(m1.group(1)) if m1 else "未命名文档"
    title = title.strip() or "未命名文档"

    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="UTF-8"><title>%s</title>'
        "<style>%s</style><style>%s</style><style>%s%s%s</style>"
        '</head><body class="markdown-body"><div id="paged-content" class="markdown-body">%s</div>'
        "<script>%s</script>"
        "<script>%s</script></body></html>"
    ) % (
        html_module.escape(title),
        page_css,
        base_css,
        katex_css,
        toc_css,
        ts_css,
        body,
        paged_js,
        filler,
    )
    return html


if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    from md_assets import materialize_images
    from md_assets import materialize_into
except Exception:
    import traceback as _tb
    try:
        with open(os.path.join(HERE, "runtime", "md_assets.err"), "a",
                  encoding="utf-8") as _ef:
            _ef.write(_tb.format_exc() + "\n")
    except Exception:
        pass
    materialize_images = None
    materialize_into = None


_SHELL_FOLDERS_KEY = ("Software\\Microsoft\\Windows\\CurrentVersion\\"
                      "Explorer\\User Shell Folders")


def _shell_folder(regval, fallback=""):
    """读取 HKCU User Shell Folders 中的真实路径。
    这样能正确处理 OneDrive 重定向（例如桌面实际在 D:\\...\\OneDrive\\Desktop），
    而不是想当然地拼 C:\\Users\\<name>\\Desktop。失败则用 fallback。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            _SHELL_FOLDERS_KEY) as k:
            v, _ = winreg.QueryValueEx(k, regval)
            v = os.path.expandvars(v)
            if v and os.path.isdir(v):
                return v
    except Exception:
        pass
    return fallback


def _common_dirs():
    home = os.path.expanduser("~")
    cands = {
        "desktop": _shell_folder("Desktop", os.path.join(home, "Desktop")),
        "docs": _shell_folder("Personal", os.path.join(home, "Documents")),
        "downloads": _shell_folder(
            "{374DE290-123F-4565-9164-39C4925E467B}",
            os.path.join(home, "Downloads")),
        "home": home,
    }
    return {k: v for k, v in cands.items() if v and os.path.isdir(v)}


_LAST_DOC_DIR = [""]
_LAST_PING = [time.time()]          # 最近一次页面心跳时间
_START_TIME = [time.time()]         # 服务启动时间（用于宽限期）
_BYE_AT = [0.0]                     # 所有会话均已卸载的时间（0=无待退出）
_LIVE_SESSIONS = {}                 # 活跃页面会话: token -> 最后心跳时间
                                    # （token 由前端每标签生成，见 markdown-editor.html
                                    #  sessionToken；多窗口/多标签共享本服务）


def _live_tok(qs):
    """从 query string 取会话 token；缺失/损坏时归一为固定占位（兼容旧页面）"""
    try:
        return (urllib.parse.parse_qs(qs or "").get("tok", [""])[0] or "").strip() or "_legacy"
    except Exception:
        return "_legacy"


def _keepalive_ping(tok):
    """会话心跳：登记存活并撤销"全体待退出"。闲置（切标签/最小化）绝不触发退出。"""
    now = time.time()
    _LIVE_SESSIONS[tok] = now
    _LAST_PING[0] = now
    _BYE_AT[0] = 0.0                 # 任一会话恢复心跳 => 撤销待退出（刷新/重开场景）


def _keepalive_bye(tok):
    """会话卸载：只下线本会话；仅当【最后一个】会话下线才进入待退出倒计时。"""
    _LIVE_SESSIONS.pop(tok, None)
    try:
        with io.open(os.path.join(HERE, "runtime", "lifecycle.log"),
                     "a", encoding="utf-8") as _f:
            _f.write("%s bye tok=%s live=%d bye_at=%s\n"
                     % (time.strftime("%H:%M:%S"), tok, len(_LIVE_SESSIONS),
                        time.strftime("%H:%M:%S", time.localtime(_BYE_AT[0]))))
    except Exception:
        pass
    if _LIVE_SESSIONS:
        _BYE_AT[0] = 0.0             # 还有其他窗口/标签活着，服务继续保活
    elif _BYE_AT[0] == 0.0:
        _BYE_AT[0] = time.time()


def _run_picker(script, tmpname):
    """在独立进程中弹选择框；结果经临时文件回传（空串=取消或不可用）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    picker = os.path.join(here, script)
    if not os.path.exists(picker):
        return ""
    tmp = os.path.join(tempfile.gettempdir(), tmpname)
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    exe_dir = os.path.dirname(sys.executable)
    py_exe = os.path.join(exe_dir, "python.exe")
    if not os.path.exists(py_exe):
        py_exe = sys.executable
    try:
        subprocess.run([py_exe, picker, tmp], timeout=900,
                       creationflags=0x08000000)
    except Exception:
        pass
    try:
        return io.open(tmp, encoding="utf-8").read().strip()
    except Exception:
        return ""


def _pick_file_subprocess(initdir=""):
    """原生"打开文件"框（GetOpenFileNameW，过滤 .md/.smd）；独立子进程弹窗，
    路径经临时文件回传（与 _pick_dir_subprocess 同模式）。取消/失败返回空串。"""
    here = os.path.dirname(os.path.abspath(__file__))
    picker = os.path.join(here, "_pickfile.py")
    if not os.path.exists(picker):
        return ""
    tmp = os.path.join(tempfile.gettempdir(), "mdeditor_pickfile.txt")
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    exe_dir = os.path.dirname(sys.executable)
    py_exe = os.path.join(exe_dir, "python.exe")
    if not os.path.exists(py_exe):
        py_exe = sys.executable
    try:
        subprocess.run([py_exe, picker, tmp, initdir or ""], timeout=900,
                       creationflags=0x08000000)
    except Exception:
        pass
    try:
        return io.open(tmp, encoding="utf-8").read().strip()
    except Exception:
        return ""


def _pick_save_subprocess(ext, init_dir="", title="", default_name=""):
    """原生"另存为"框（GetSaveFileNameW，过滤 <ext>）；独立子进程弹窗，
    路径经临时文件回传。取消/失败返回空串。"""
    here = os.path.dirname(os.path.abspath(__file__))
    picker = os.path.join(here, "_picksave.py")
    if not os.path.exists(picker):
        return ""
    tmp = os.path.join(tempfile.gettempdir(), "mdeditor_picksave.txt")
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    exe_dir = os.path.dirname(sys.executable)
    py_exe = os.path.join(exe_dir, "python.exe")
    if not os.path.exists(py_exe):
        py_exe = sys.executable
    try:
        subprocess.run([py_exe, picker, tmp, ext, init_dir or "",
                        title or "", default_name or ""],
                       timeout=900, creationflags=0x08000000)
    except Exception:
        pass
    try:
        return io.open(tmp, encoding="utf-8").read().strip()
    except Exception:
        return ""


def _pick_dir_subprocess():
    """只使用现代文件夹选择框（IFileOpenDialog + FOS_PICKFOLDERS）。
    用户取消 -> 返回空串，不再回退（回退会二次弹老式框，用户已明确弃用）。
    现代框不可用时返回空串并写诊断日志。"""
    r = _run_picker("_pickdir_modern.py", "mdeditor_pickdir2.txt")
    if r == "@CANCEL@":
        _pickdir_log("modern: 用户取消")
        return ""
    if r:
        _pickdir_log("modern: 选中 %s" % r)
        return r
    _pickdir_log("modern: 不可用/无返回（未回退）")
    return ""


def _pickdir_log(msg):
    try:
        import time as _t
        with io.open(os.path.join(HERE, "runtime", "pickdir.log"), "a",
                     encoding="utf-8") as f:
            f.write("%s %s\n" % (_t.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def _idle_watchdog(grace=None, check=0.5):
    """只在【所有窗口/标签都确实关闭】时退出服务。

    多窗口/多标签共享本后端，会话以 token 区分（前端每标签生成，见
    markdown-editor.html sessionToken；/api/ping、/api/bye 带 ?tok=）：
    - 主判定：全部会话都收到卸载通知(/api/bye，pagehide→sendBeacon)后
      进入宽限倒计时；宽限期内出现任何新会话心跳（刷新/重开）即撤销。
    - 保活：只要还有任一会话存活（_LIVE_SESSIONS 非空），服务绝不退出
      ——关闭某个窗口不影响其它窗口（这正是多开的核心语义）。
    - 兜底：WebView2 被直接拽掉时 pagehide 跑不到、bye 发不出，该会话
      按最后心跳停滞超 orphan 宽限（默认 5 分钟）做幽灵清理；全部会话
      清光后按 max(最后心跳, 服务启动) 超 orphan 同样回收，防僵尸端口。
      后台标签页心跳节流最长约 1 分钟，5 分钟足够保守，不误杀
      最小化/切走的窗口。

    明确不做的事：**不做"空闲超时"判定**。
    切换标签页、最小化、长时间不操作都不等于关闭 —— 只要会话还在，
    服务就活着。可用环境变量 MD_EXIT_GRACE/MD_EXIT_ORPHAN_GRACE
    覆盖宽限期（便于测试）。"""
    if grace is None:
        grace = float(os.environ.get("MD_EXIT_GRACE", "8"))
    orphan = float(os.environ.get("MD_EXIT_ORPHAN_GRACE", "300"))
    _START_TIME[0] = time.time()
    if not _auto_stop_enabled():
        return

    def _do_stop(reason):
        try:
            with io.open(os.path.join(HERE, "runtime", "lifecycle.log"),
                         "a", encoding="utf-8") as f:
                f.write("%s %s -> stop service\n"
                        % (time.strftime("%H:%M:%S"), reason))
        except Exception:
            pass
        if _smd is not None:
            try:
                _smd.clear_tmp()   # 会话结束，清 .smd 解包缓存
            except Exception:
                pass
        os._exit(0)

    while True:
        time.sleep(check)
        now = time.time()
        # 幽灵清理：无 bye 的会话心跳停滞超过 orphan（页面/窗口被强杀）
        for t in [t for t, ts in _LIVE_SESSIONS.items() if now - ts >= orphan]:
            del _LIVE_SESSIONS[t]
        if _LIVE_SESSIONS:
            continue          # 仍有存活窗口/标签，服务保活
        bye = _BYE_AT[0]
        if not bye:
            # 兜底：从未 bye 且已无存活会话，心跳断流超 orphan 宽限。
            # 基准取「最后心跳 / 服务启动」的较大者——页面从未打开过的
            # 孤儿服务（起服务后 5 分钟无页面接入）同样回收。
            if now - max(_LAST_PING[0], _START_TIME[0]) >= orphan:
                _do_stop("heartbeat lost (page killed without bye)")
            continue
        if now - bye < grace:
            continue
        # 宽限期内又收到过心跳 => 是刷新/重开，撤销退出
        if now - _LAST_PING[0] < grace:
            continue
        _do_stop("page closed")


def _auto_stop_enabled():
    """runtime/settings.json 里的 auto_stop（默认开启）。"""
    try:
        import json as _json
        p = os.path.join(HERE, "runtime", "settings.json")
        d = _json.loads(io.open(p, encoding="utf-8").read())
        return bool(d.get("auto_stop", True))
    except Exception:
        return True


def main():
    if _smd is not None:
        try:
            _smd.clear_tmp()   # 启动清掉上次会话的 .smd 解包缓存（数据以 .smd 为准）
        except Exception:
            pass
    srv = Server()
    srv.start()
    atexit.register(srv.stop)
    # 空闲自动退出：页面关闭后无人使用，服务自行结束（无需手动 md_stop）
    threading.Thread(target=_idle_watchdog, daemon=True).start()
    ev = threading.Event()
    try:
        ev.wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
