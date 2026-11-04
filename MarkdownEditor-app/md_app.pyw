# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""MDEditor 内嵌窗口应用
- pywebview 开原生窗口指向本地服务（无浏览器 UI）
- 自带 WebView2 内核优先（runtime/WebView2），不存在则用系统内核
- 暴露 py API 供页面直接调用（原生目录/保存对话框选路径、常用目录、窗口控制；
  写盘一律由页面走服务端路由——桥不落盘，SSOT 单一实现）
用法：pythonw md_app.pyw [要打开的 .md 路径]
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18766
sys.path.insert(0, HERE)

BUNDLED_RUNTIME = os.path.join(HERE, "runtime", "WebView2")


def _resolve_runtime_dir():
    """可写 runtime 目录。与 md_server._resolve_runtime_dir 同一套判定：
    安装目录可写 → 原地（历史行为零变化）；只读（MSIX 商城包等）→
    %LOCALAPPDATA%\\MDEditor\\runtime。探针写测试，不猜 ACL。"""
    rt = os.path.join(HERE, "runtime")
    probe = os.path.join(rt, ".writable")
    try:
        os.makedirs(rt, exist_ok=True)
        with io.open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return rt
    except Exception:
        pass
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    alt = os.path.join(base, "MDEditor", "runtime")
    try:
        os.makedirs(alt, exist_ok=True)
    except Exception:
        alt = tempfile.gettempdir()
    return alt


RUNTIME_DIR = _resolve_runtime_dir()
USER_DATA = os.path.join(RUNTIME_DIR, "userdata")
WIN_CONF = os.path.join(RUNTIME_DIR, "window.json")
SETTINGS = os.path.join(RUNTIME_DIR, "settings.json")
LOG = os.path.join(RUNTIME_DIR, "md_app.log")


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def load_settings():
    """可选设置：disable_gpu=true 时改用软件渲染（排障用）。"""
    try:
        d = json.loads(io.open(SETTINGS, encoding="utf-8").read())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def ensure_default_settings():
    if os.path.exists(SETTINGS):
        return
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        io.open(SETTINGS, "w", encoding="utf-8").write(json.dumps({
            "_comment": "内嵌窗口设置。disable_gpu=true 改用软件渲染（界面卡顿时可试）",
            "disable_gpu": False
        }, ensure_ascii=False, indent=2))
    except Exception:
        pass


def service_alive(min_ver=0):
    try:
        d = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=0.3).read().decode())
        return int(d.get("version", 0)) >= min_ver if min_ver else True
    except Exception:
        return False


def ensure_service():
    if service_alive():
        return True
    try:
        exe = os.path.join(HERE, "python", "pythonw.exe")
        if not os.path.exists(exe):
            exe = sys.executable
        subprocess.Popen([exe, os.path.join(HERE, "_md_run.py")],
                         cwd=HERE, creationflags=0x08000000)
    except Exception as e:
        log("start service failed: %s" % e)
        return False
    end = time.time() + 15
    while time.time() < end:
        if service_alive():
            return True
        time.sleep(0.05)
    return False


def load_window_size():
    try:
        d = json.loads(io.open(WIN_CONF, encoding="utf-8").read())
        return int(d.get("w", 1360)), int(d.get("h", 880))
    except Exception:
        return 1360, 880


def save_window_size(w, h):
    try:
        os.makedirs(os.path.dirname(WIN_CONF), exist_ok=True)
        io.open(WIN_CONF, "w", encoding="utf-8").write(
            json.dumps({"w": int(w), "h": int(h)}))
    except Exception:
        pass


def _find_edge():
    """找 msedge.exe。打印要走真浏览器，优先用 Edge（用户的打印粘性设置
    就存在 Edge profile 里，换成别的浏览器等于换一套默认值）。

    顺序：App Paths 注册表（HKCU 先、HKLM 后，最准）→ 常见安装路径。
    都没有就返回空串，调用方退回默认浏览器。"""
    try:
        import winreg
        path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, path) as k:
                    p = winreg.QueryValueEx(k, "")[0]
                if p and os.path.exists(p):
                    return p
            except Exception:
                pass
    except Exception:
        pass
    for p in (os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                           r"Microsoft\Edge\Application\msedge.exe"),
              os.path.join(os.environ.get("ProgramFiles", ""),
                           r"Microsoft\Edge\Application\msedge.exe"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""),
                           r"Microsoft\Edge\Application\msedge.exe")):
        if p and os.path.exists(p):
            return p
    return ""


def _head_pages(pdf_path, heads, toc_pages=0):
    """从打印引擎产出的 PDF 里读出每个标题的**真实物理页号**。

    目录里的页码一直由页内测量盒估算（measure() 里 colOf 按列宽除），而
    打印引擎的分页规则更强：表格跨页重复表头、孤行下移、禁断块整块下压
    ——这些都不体现在列布局里，于是长表之后的内容整体偏早，目录就错
    （2026-11-04 实测：页脚真值 P=4，目录仍写 3）。

    做法：pypdf 提取每页文本，按标题在文档里的先后顺序逐页前扫。一次出片
    就能覆盖全部标题，不必为每个标题单独渲染。

    两个坑（都实测过）：
    1) 中文标题里混排不同字体时，PDF 的绘制顺序会让标题在提取文本里被拆
       开——首个标题「(一)上下标(角标)」用整串匹配就永远找不到。所以按
       10/8/6/4 字**长度递减**取前缀，短前缀在正文里足够区分。
    2) 目录页里所有标题文本都在，不跳过会把每个标题都记成目录那一页。
       判据不用「页里有『目录』二字」（正文讲目录功能也会命中，实测误伤
       23 页），改用「这一页能同时命中 ≥8 个标题」——目录页实测 27/28 个，
       正文最密的页只有 4 个。

    返回 {headId: 物理页号(1 起)}；命中率低于 80% 时整体返回空 dict，
    让调用方统一退回估算值（半对半错比统一估算更难排查）。
    """
    import unicodedata

    if not heads or not pdf_path or not os.path.exists(pdf_path):
        return {}
    try:
        import pypdf
    except Exception as e:
        log("_head_pages: 没有 pypdf（%s），退回测量盒估算" % e)
        return {}

    def norm(s):
        # 提取出来的中文常带康熙部首等兼容字符（「⼀」「⽂」「⻆」），NFKC
        # 归一后才能和 DOM 里的标题文本对上；空白一律去掉，避免断行干扰。
        s = unicodedata.normalize("NFKC", s or "")
        return "".join(s.split())

    try:
        rd = pypdf.PdfReader(pdf_path)
        pages = [norm(pg.extract_text() or "") for pg in rd.pages]
    except Exception as e:
        log("_head_pages: 读 PDF 失败 %s" % e)
        return {}
    n = len(pages)
    if n <= 0:
        return {}

    keys = [(hid, norm(txt)) for hid, txt in heads]
    keys = [(h, t) for h, t in keys if t]

    # 目录页：一页同时命中 ≥8 个标题的前 6 字
    skip = set()
    for i, p in enumerate(pages):
        c = 0
        for _h, t in keys:
            if t[:6] in p:
                c += 1
                if c >= 8:
                    skip.add(i)
                    break

    res = {}
    cur = 0
    for hid, txt in keys:
        found = -1
        for L in (10, 8, 6, 4):
            k = txt[:L]
            if len(k) < 3:
                continue
            for pi in range(cur, n):
                if pi in skip:
                    continue
                if k in pages[pi]:
                    found = pi
                    break
            if found >= 0:
                break
        if found < 0:
            continue
        res[hid] = found + 1
        cur = found

    total = len(keys)
    if total and len(res) * 5 < total * 4:          # < 80%
        log("_head_pages: 只命中 %d/%d，整体退回估算" % (len(res), total))
        return {}
    if len(res) != total:
        log("_head_pages: %d/%d 命中，其余条目退回估算" % (len(res), total))
    return res


class Api:
    """供前端通过 window.pywebview.api.* 直接调用。"""

    def __init__(self):
        self.window = None
        self._meas_lock = threading.Lock()

    # ---- 文件/目录对话框（原生，返回完整路径）----
    def pick_folder(self, last_dir=""):
        try:
            import webview
            res = self.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=last_dir if last_dir and os.path.isdir(last_dir) else "")
            if res:
                return res[0] if isinstance(res, (list, tuple)) else res
        except Exception as e:
            log("pick_folder err: %s" % e)
        return ""

    # ---- 打印窗口（v2.36.0-A）------------------------------------------
    def _abs_url(self, u):
        """站内相对地址（/static/document.print.html）补成绝对。

        内核 Navigate 与外部浏览器都拿不到 base 去拼相对 URI：pywebview
        的 create_window 会把它原样交给内核，结果渲染空白（2026-11-04
        主人实测「点打印弹出大白页」）。前端已经转过一次，这里是第二道
        保险，防止别的调用方漏转。"""
        u = str(u or "").strip()
        if not u:
            return ""
        low = u.lower()
        if not (low.startswith("http://") or low.startswith("https://")
                or low.startswith("file://")):
            try:
                base = getattr(self.window, "real_url", "") or ""
            except Exception:
                base = ""
            if base:
                u = urllib.parse.urljoin(base, u)
        return u

    def open_print(self, url=""):
        """把打印页交给**系统浏览器**（优先 Edge）打开，由页面自触发打印。

        为什么不留在应用内：WebView2 的打印预览是精简版——「选项」里只剩
        「背景图形」，没有「页眉和页脚」（主人 2026-11-04 截图实测），且
        没有任何 API 能关掉它。CoreWebView2PrintSettings 的
        ShouldPrintHeaderAndFooter 只对**静默打印 / 出 PDF** 生效，对带预览
        的对话框无效；ShowPrintUI 也只暴露 Browser / System 两种对话框，
        前者就是那个精简预览，后者干脆没有预览（WebView2Feedback #5744）。

        所以「弹出打印 + 不要系统页眉页脚」只能在真正的浏览器里达成：
        Edge 的预览有该勾选项，且状态来自 profile 的打印粘性设置
        （printing.print_preview_sticky_settings.appState.
        isHeaderFooterEnabled）。主人这台机器上该值已是 False，即预览
        一打开就是「页眉和页脚」关闭，无需每次手点。

        找不到 Edge 就退回默认浏览器（同一个 Chromium 打印预览体系），
        再不行退回应用内窗口——那时会带系统页眉页脚，但至少能打。
        """
        u = self._abs_url(url)
        if not u:
            return {"ok": False, "error": "empty url"}
        edge = _find_edge()
        if edge:
            try:
                # CREATE_NO_WINDOW：别为弹出浏览器闪一个黑框
                subprocess.Popen([edge, "--new-window", u],
                                 creationflags=0x08000000,
                                 close_fds=True)
                log("open_print: edge %s" % u)
                return {"ok": True, "route": "edge", "exe": edge}
            except Exception as e:
                log("open_print edge err: %s" % e)
        try:
            import webbrowser
            if webbrowser.open(u):
                log("open_print: default browser %s" % u)
                return {"ok": True, "route": "default"}
        except Exception as e:
            log("open_print browser err: %s" % e)
        log("open_print: fallback in-app window")
        return self.print_window(u)

    def print_window(self, url=""):
        """在应用内开一个独立窗口承载打印版（**兜底通道**）。

        注意（2026-11-04 更正）：这**不会**得到 Edge 那套完整打印预览。
        WebView2 无论打印版在 iframe 里还是顶层文档，弹出的都是它自己的
        精简预览，没有「页眉和页脚」开关。先前这里写着「顶层文档＝完整
        预览（含页眉页脚开关）」，那是未实测的假设，已被主人截图证伪。
        正常路径走 open_print，只有找不到任何浏览器时才落到这里。

        pywebview 的 create_window 在 start() 之后、非主线程调用会立即建窗
        （其源码 create_window 尾部就是按这个条件判断的），而 js_api 回调
        正好不在主线程——所以这里可以直接调用。
        """
        u = self._abs_url(url)
        if not u:
            return {"ok": False, "error": "empty url"}
        try:
            import webview
            w = webview.create_window("打印预览", u, width=1180, height=940,
                                      min_size=(640, 480))
            log("print_window: %s" % u)
            return {"ok": True, "uid": getattr(w, "uid", "")}
        except Exception as e:
            log("print_window err: %s" % e)
            return {"ok": False, "error": str(e)}

    # ---- 两遍法第一遍：用打印引擎量真实页数（v2.37.0）------------------
    def pdf_measure(self, url=""):
        """用 WebView2 的打印引擎（PrintToPdfAsync）出 PDF，数出**纸上真实**页数。

        为什么不能用页内测量盒：页脚上的数字必须在分页之前写进 CSS，而真实
        分页结果只有分页之后才存在——两者是"预言 vs 观察"。测量盒只是多列
        近似，实测与打印引擎差 1~3 页（本文档真值 57 页，测量盒报 56）。
        这里改用打印引擎本身出片：它就是打印预览那个引擎，数出来的就是纸面数。

        分区：每个 .page-region 都强制从新页开始，所以「单独渲染一个区」的
        页数 == 它在全文里的页数（实测 57 == 3+1+52+1）。据此逐区量，拿到
        每区的 {N}；P = 全文 − 目录页 − 所有 noll 区页。

        返回 {ok, total, toc, regions:{id:页数}, P, noll:[id], sec}
        """
        import re as _re
        u = str(url or "").strip()
        if not u:
            return {"ok": False, "error": "empty url"}
        low = u.lower()
        if not (low.startswith("http://") or low.startswith("https://")
                or low.startswith("file://")):
            try:
                base = getattr(self.window, "real_url", "") or ""
            except Exception:
                base = ""
            if base:
                u = urllib.parse.urljoin(base, u)
        if not self._meas_lock.acquire(blocking=False):
            return {"ok": False, "error": "busy"}
        out = {"ok": False}
        tmpdir = tempfile.mkdtemp(prefix="mde-meas-")
        w = None
        try:
            import webview
            from System import Action
            from webview.platforms.winforms import BrowserView

            def _pages(p):
                try:
                    return len(_re.findall(rb"/Type\s*/Page\b", open(p, "rb").read()))
                except Exception:
                    return -1

            w = webview.create_window("mde-measure", u, width=900, height=700,
                                      hidden=True)
            bw = None
            ctrl = None
            for _i in range(80):
                bw = BrowserView.instances.get(w.uid)
                if bw is not None and getattr(bw, "webview", None) is not None:
                    ctrl = bw.webview
                    break
                time.sleep(0.25)
            if ctrl is None:
                out["error"] = "measure-window-not-ready"
                return out
            log("pdf_measure: ctrl ready rounds=%s" % _i)
            ui_errs = []

            def ui(fn):
                """在 UI 线程执行 fn。凡碰 CoreWebView2 的都必须走这里。"""
                box = {}

                def g():
                    try:
                        fn()
                    except Exception as e:
                        box["err"] = "%s: %s" % (type(e).__name__, e)
                ctrl.Invoke(Action(g))
                if "err" in box:
                    ui_errs.append(box["err"])
                return box

            def core_ref():
                """取 CoreWebView2 引用——**必须**在 UI 线程里读。

                这个属性有线程亲和：后台线程直接读一定抛
                "CoreWebView2 can only be accessed from the UI thread"，
                于是永远拿不到值、循环空转到超时（2026-11-04 实测就是它：
                点打印转圈 20 秒毫无反应，日志停在窗口刚建好的那一刻）。
                返回 None 表示还没初始化完成，稍后重试即可。"""
                box = {}

                def g():
                    try:
                        box["c"] = ctrl.CoreWebView2
                    except Exception as e:
                        box["e"] = "%s: %s" % (type(e).__name__, e)
                ctrl.Invoke(Action(g))
                return box.get("c")

            core_obj = None
            for _i2 in range(80):
                core_obj = core_ref()
                if core_obj is not None:
                    break
                time.sleep(0.25)
            if core_obj is None:
                out["error"] = "core-unavailable"
                return out
            log("pdf_measure: core ready rounds=%s" % _i2)

            def js(code, tmo=25):
                r = {}

                def g():
                    r["t"] = core_obj.ExecuteScriptAsync(code)
                ctrl.Invoke(Action(g))
                if "t" not in r or not r["t"].Wait(tmo * 1000):
                    return None
                try:
                    return json.loads(str(r["t"].Result))
                except Exception:
                    return None

            t0 = time.time()
            # 先等**真实文档**就绪。窗口一建好就能 ExecuteScriptAsync，但
            # about:blank 的 readyState 也是 'complete'——旧写法第一查就误判
            # 就位，随后探 __PNCFG 得到 undefined 被记成 'no pn script'、
            # pnReady 等待被跳过（2026-11-04 日志 'readyState=loading
            # waited=0.0s' + 'no pn script' 就是这个竞态）。_wait_doc 要求
            # readyState=complete 且产物标记（__PNPAPER/#paged-content）在场。
            self._wait_doc(js)
            log("pdf_measure: doc ready waited=%.1fs" % (time.time() - t0))

            # 等页内两遍法量完（目录回填 + 页脚 CSS 就位，之后分页才稳定）。
            # 但**先看页面有没有挂页码脚本**：页码与目录都关时产物里根本没有
            # __PNCFG/__pnReady，盲等会把超时时间白烧掉（2026-11-04 实测：
            # 白等 12.4s，点打印的转圈从 5 秒变成 17 秒）。
            if js("String(typeof window.__PNCFG!=='undefined')") == "true":
                for _ in range(48):          # 最多 12s；实测 1~2s 就绪
                    if js("String(window.__pnReady===1)") == "true":
                        break
                    time.sleep(0.25)
                log("pdf_measure: pnReady=%s waited=%.1fs"
                    % (js("String(window.__pnReady===1)"), time.time() - t0))
            else:
                log("pdf_measure: no pn script (页码/目录均关)")
            time.sleep(0.4)

            # 纸张几何：从产物里带的 __PNPAPER 读（服务端写真实值）。写死
            # A4 的话，换 B5/A5/自定义纸型量出来的是「这份内容在 A4 上的
            # 页数」，不是纸上那个数。
            paper = {"w": 210.0, "h": 297.0, "mt": 25.0, "mr": 18.0,
                     "mb": 25.0, "ml": 18.0}
            try:
                _pj = js("(function(){try{return JSON.stringify("
                         "window.__PNPAPER||null)}catch(e){return ''}})()")
                if isinstance(_pj, str) and _pj:
                    _d = json.loads(_pj)
                    if isinstance(_d, dict):
                        for _k in list(paper):
                            if _d.get(_k) not in (None, ""):
                                paper[_k] = float(_d[_k])
            except Exception as e:
                log("pdf_measure: paper read failed: %s" % e)
            log("pdf_measure: paper=%s" % json.dumps(paper))

            # 区清单：id + 编号档位（noll 不占号，要从 P 里扣掉）
            spec = js("(function(){return [...document.querySelectorAll"
                      "('.page-region[data-pr-id]')].map(function(r){"
                      "return r.getAttribute('data-pr-id')+'|'+(r.getAttribute('data-pn')||'');"
                      "}).join(',');})()") or ""
            ids, noll = [], []
            for part in [x for x in str(spec).split(",") if x]:
                rid, _, pn = part.partition("|")
                ids.append(rid)
                if pn == "noll":
                    noll.append(rid)

            # 标题清单（id + 去空白文本，按 DOM 顺序）。目录里每个条目的
            # 页码要的是「这个标题落在纸面第几页」——这件事只有打印引擎知道，
            # 页内测量盒只能按列宽除，长表跨页重复表头时必然偏早。
            heads = []
            try:
                _hs = js("(function(){return Array.prototype.map.call("
                         "document.querySelectorAll('[id^=\"md-h-\"]'),"
                         "function(h){return [h.id,(h.textContent||'')"
                         ".replace(/\\s+/g,'')];});})()")
                if isinstance(_hs, list):
                    for it in _hs:
                        if isinstance(it, list) and len(it) >= 2 and it[1]:
                            heads.append((str(it[0]), str(it[1])))
            except Exception as e:
                log("pdf_measure: heads collect failed: %s" % e)
            log("pdf_measure: heads=%d" % len(heads))

            def shoot(tag):
                p = os.path.join(tmpdir, tag + ".pdf")
                bb = {}

                def f():
                    core = core_obj
                    st = core.Environment.CreatePrintSettings()
                    st.ShouldPrintHeaderAndFooter = False   # 绝不带系统页眉页脚
                    st.ShouldPrintBackgrounds = True
                    # 纸张与页边距：与打印页 CSS @page 同值，否则 PrintSettings
                    # 的默认 Letter 会盖掉 CSS 尺寸（英寸为单位）
                    mm = 1.0 / 25.4
                    st.PageWidth = paper["w"] * mm
                    st.PageHeight = paper["h"] * mm
                    st.MarginTop = paper["mt"] * mm
                    st.MarginBottom = paper["mb"] * mm
                    st.MarginLeft = paper["ml"] * mm
                    st.MarginRight = paper["mr"] * mm
                    bb["task"] = core.PrintToPdfAsync(p, st)
                ui(f)
                if "task" not in bb:
                    return -1
                if not bb["task"].Wait(60000):
                    log("pdf_measure: shoot %s timeout" % tag)
                    return -1
                n = _pages(p) if os.path.exists(p) else -1
                log("pdf_measure: shoot %s -> %s pages" % (tag, n))
                return n

            def show(keep, toc):
                js("(function(){var ks=%s;document.querySelectorAll"
                   "('.page-region[data-pr-id]').forEach(function(r){"
                   "r.style.display=(ks.indexOf(r.getAttribute('data-pr-id'))>=0)?'':'none';});"
                   "var tw=document.querySelector('.md-toc-wrap');"
                   "if(tw)tw.style.display=%s;return 1;})()"
                   % (json.dumps(keep), "''" if toc else "'none'"))
                # 等重排落地再出片。0.22s 够（实测 0.35 只是保守值，
                # 五次区切换光睡觉就 1.75s，是整轮耗时的大头之一）
                time.sleep(0.22)

            out["total"] = shoot("full")
            out["regions"] = {}
            for rid in ids:
                show([rid], False)
                out["regions"][rid] = shoot("r" + str(len(out["regions"])))
            # 目录页数（v2.39.1 修）：目录 .md-toc-wrap 在 noll 区**内部**时，
            # 「隐藏所有区、单显目录」会把目录连坐成白纸——父区 display:none
            # 无法被子元素翻回（实测 toc 量成 1 页空白，P=63，真值 61）。
            # 改算术：宿主区整区出两次片——不带目录一次（上面区循环已出，
            # regions[host]）、带目录一次（tocw），差 = 目录页数。区结构原样
            # 不动，不产生命名页换名催出的空白首页。目录不在任何区里
            # （独立前件）才走旧的单显路径。
            _twh = js("(function(){var tw=document.querySelector("
                      "'.md-toc-wrap');if(!tw)return '';"
                      "var h=tw.closest('.page-region');"
                      "return h?(h.getAttribute('data-pr-id')||''):'';})()") or ""
            _twh = str(_twh or "")
            if _twh and _twh in ids:
                show([_twh], True)
                _with = shoot("tocw")
                out["toc"] = max(0, (_with if _with > 0 else 0)
                                 - out["regions"].get(_twh, 0))
            else:
                show([], True)
                out["toc"] = shoot("toc")
            out["noll"] = noll
            # 标题真实落页：解析第一遍那份 full.pdf 的文本，按标题在文档里的
            # 先后顺序逐页前扫。这份 PDF 与最终打印页同一引擎、同一纸张，
            # 它的落页就是纸上的落页——不必为每个标题单独出片（50 个标题要
            # 多跑几十次渲染）。toc 页数此刻已知，用来跳过目录页（目录页里
            # 所有标题文本都在，不跳过会把每个标题都记成目录所在的页）。
            try:
                out["headPages"] = _head_pages(
                    os.path.join(tmpdir, "full.pdf"), heads,
                    int(out.get("toc") or 0))
                log("pdf_measure: headPages=%d/%d"
                    % (len(out.get("headPages") or {}), len(heads)))
            except Exception as e:
                log("pdf_measure: headPages failed: %s" % e)
                out["headPages"] = {}
            if out.get("total", -1) > 0:
                # P = 参与编号页数 = 全文 − 目录 − 所有 noll 区
                pn_total = out["total"] - max(0, out.get("toc", 0))
                for rid in noll:
                    v = out["regions"].get(rid, 0)
                    if v > 0:
                        pn_total -= v
                out["P"] = max(1, pn_total)
                out["ok"] = True
            if ui_errs:
                out["ui_errors"] = ui_errs[:4]
            out["sec"] = round(time.time() - t0, 2)
            return out
        except Exception as e:
            out["error"] = "%s: %s" % (type(e).__name__, e)
            return out
        finally:
            try:
                if w is not None:
                    w.destroy()
            except Exception:
                pass
            try:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
            self._meas_lock.release()

    # ---- 打印（v2.39.0：自建面板 + PrintAsync）------------------------
    # 为什么要自建：WebView2 与 Edge 的打印预览里「选项」栏都只剩「背景
    # 图形」，「页眉和页脚」这个开关在 UI 上已经不存在（2026-11-04 穿透
    # shadow DOM 实测）。而 CoreWebView2PrintSettings.ShouldPrintHeaderAndFooter
    # 对 PrintAsync 有效——那就自己出面板、自己调静默打印，页眉页脚由代码
    # 写死关闭，跟 profile、浏览器版本、换机器全都无关。

    # 纸型尺寸（mm）。PrintMediaSize 只提供 Default/Custom，给不了 A4/B5
    # 这种具名纸型（反射实测），所以换纸靠 PageWidth/PageHeight。
    _PAPER_MM = {
        "A4": (210.0, 297.0), "A5": (148.0, 210.0),
        "B5": (176.0, 250.0), "LETTER": (215.9, 279.4),
    }

    def list_printers(self):
        """本机打印机清单 + 默认打印机（给自建打印面板的下拉）。"""
        out = {"ok": False, "printers": [], "default": ""}
        try:
            import clr
            try:
                clr.AddReference("System.Drawing")
            except Exception:
                pass
            from System.Drawing.Printing import PrinterSettings
            out["printers"] = [str(n) for n in PrinterSettings.InstalledPrinters]
            try:
                out["default"] = str(PrinterSettings().PrinterName or "")
            except Exception:
                pass
            out["ok"] = True
        except Exception as e:
            log("list_printers err: %s" % e)
            out["error"] = str(e)
        return out

    def _open_hidden(self, url, width=1000, height=800):
        """建隐藏窗口、等 CoreWebView2 可用，返回 (win, ctrl, core, ui, js)。

        所有触碰 CoreWebView2 的读与调用都必须经 ui() 回 UI 线程：这个属性
        有线程亲和，后台线程直接读必抛 "can only be accessed from the UI
        thread"（2026-11-04 实测，转圈 20 秒毫无反应就是它）。
        """
        import webview
        from System import Action
        from webview.platforms.winforms import BrowserView

        w = webview.create_window("mde-print", url, width=width, height=height,
                                  hidden=True)
        ctrl = None
        for _i in range(80):
            bw = BrowserView.instances.get(w.uid)
            if bw is not None and getattr(bw, "webview", None) is not None:
                ctrl = bw.webview
                break
            time.sleep(0.25)
        if ctrl is None:
            raise RuntimeError("window-not-ready")

        def ui(fn):
            box = {}

            def g():
                try:
                    fn()
                except Exception as e:
                    box["err"] = "%s: %s" % (type(e).__name__, e)
            ctrl.Invoke(Action(g))
            return box

        def core_ref():
            box = {}

            def g():
                try:
                    box["c"] = ctrl.CoreWebView2
                except Exception as e:
                    box["e"] = "%s: %s" % (type(e).__name__, e)
            ctrl.Invoke(Action(g))
            return box.get("c")

        core = None
        for _i2 in range(80):
            core = core_ref()
            if core is not None:
                break
            time.sleep(0.25)
        if core is None:
            raise RuntimeError("core-unavailable")

        def js(code, tmo=25):
            r = {}

            def g():
                r["t"] = core.ExecuteScriptAsync(code)
            ctrl.Invoke(Action(g))
            if "t" not in r or not r["t"].Wait(tmo * 1000):
                return None
            try:
                return json.loads(str(r["t"].Result))
            except Exception:
                return None

        return w, ctrl, core, ui, js

    def _wait_doc(self, js, tries=80):
        """等**真实文档**就绪（v2.39.1）。

        about:blank 的 readyState 也是 'complete'——只看它，窗口刚建好、
        真导航还没开始时就会误判就位（2026-11-04 实测判例：pdf_measure
        打出 readyState=loading waited=0.0s、'no pn script' 假日志；pdf_save
        跳过 pnReady 等待，页内回填没跑完就 PrintToPdfAsync——目录页码
        全空、罗马区掉进全局序兜底）。产物页由服务端写入 __PNPAPER，
        #paged-content 也是产物专属标记，两者任一在场才算真文档。
        超时返回 False 但不阻塞调用方（fail-open，仅失去精确等待）。"""
        for _ in range(tries):
            if js("(function(){try{return String(document.readyState"
                  "===\"complete\"&&(typeof window.__PNPAPER!=='undefined'"
                  "||!!document.getElementById('paged-content')))}catch(e)"
                  "{return 'false'}})()") == "true":
                return True
            time.sleep(0.2)
        return False

    def _wait_ready(self, js, want_pn=True):
        """等真实文档就绪；有页码脚本再等页内两遍法就位（页脚数字得先写好）。"""
        self._wait_doc(js)
        if not want_pn:
            return
        if js("String(typeof window.__PNCFG!=='undefined')") == "true":
            for _ in range(48):
                if js("String(window.__pnReady===1)") == "true":
                    break
                time.sleep(0.25)
        time.sleep(0.25)

    def _doc_paper(self, js):
        """产物里带的纸张几何（服务端写的真实值）。读不到就按 A4。"""
        paper = {"w": 210.0, "h": 297.0, "mt": 25.0, "mr": 18.0,
                 "mb": 25.0, "ml": 18.0}
        try:
            _pj = js("(function(){try{return JSON.stringify("
                     "window.__PNPAPER||null)}catch(e){return ''}})()")
            if isinstance(_pj, str) and _pj:
                d = json.loads(_pj)
                if isinstance(d, dict):
                    for k in list(paper):
                        if d.get(k) not in (None, ""):
                            paper[k] = float(d[k])
        except Exception:
            pass
        return paper

    def do_print(self, url="", opts=None):
        """交给打印机。opts: printer / copies / range / duplex / paper / bg。

        页眉页脚在这里写死关闭——整条链路上只有这个位置能真正关掉它。
        """
        opts = opts or {}
        u = self._abs_url(url)
        if not u:
            return {"ok": False, "error": "empty url"}
        if not self._meas_lock.acquire(blocking=False):
            return {"ok": False, "error": "busy"}
        w = None
        try:
            w, ctrl, core, ui, js = self._open_hidden(u, 1100, 900)
            self._wait_ready(js)
            paper = self._doc_paper(js)
            pw, ph = self._PAPER_MM.get(str(opts.get("paper") or "").upper(),
                                        (paper["w"], paper["h"]))
            mm = 1.0 / 25.4
            bb = {}

            def f():
                st = core.Environment.CreatePrintSettings()
                st.ShouldPrintHeaderAndFooter = False
                st.ShouldPrintBackgrounds = bool(opts.get("bg", True))
                st.PageWidth = pw * mm
                st.PageHeight = ph * mm
                st.MarginTop = paper["mt"] * mm
                st.MarginBottom = paper["mb"] * mm
                st.MarginLeft = paper["ml"] * mm
                st.MarginRight = paper["mr"] * mm
                if opts.get("printer"):
                    st.PrinterName = str(opts["printer"])
                try:
                    st.Copies = max(1, min(99, int(opts.get("copies") or 1)))
                except Exception:
                    st.Copies = 1
                rng = str(opts.get("range") or "").strip()
                if rng:
                    st.PageRanges = rng
                dp = int(opts.get("duplex") or 0)
                if dp:
                    from System import Enum
                    names = {1: "OneSided", 2: "TwoSidedLongEdge",
                             3: "TwoSidedShortEdge"}
                    if dp in names:
                        st.Duplex = Enum.Parse(st.Duplex.GetType(), names[dp])
                bb["task"] = core.PrintAsync(st)

            err = ui(f)
            if "task" not in bb:
                return {"ok": False,
                        "error": err.get("err") or "print-not-started"}
            log("do_print: started printer=%s copies=%s"
                % (opts.get("printer"), opts.get("copies")))
            if not bb["task"].Wait(300000):
                return {"ok": False, "error": "timeout"}
            status = str(bb["task"].Result)
            log("do_print: status=%s" % status)
            return {"ok": status == "Succeeded", "status": status,
                    "error": "" if status == "Succeeded" else status}
        except Exception as e:
            log("do_print err: %s" % e)
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        finally:
            try:
                if w is not None:
                    w.destroy()
            except Exception:
                pass
            self._meas_lock.release()

    def pdf_save(self, url="", path=""):
        """导出 PDF 到 path（用打印引擎本身，分页与打印完全一致）。"""
        import re as _re
        u = self._abs_url(url)
        if not u:
            return {"ok": False, "error": "empty url"}
        # path 为空 = 给分页预览用：落到 runtime/preview.pdf，回一个站内 URL。
        # 预览显示的就是打印引擎出的 PDF 本身，纸页外观、页边距、页脚位置
        # 全是最终形态——屏幕上的 CSS 多列做不出「每页带页边距的纸」。
        url_out = ""
        if not path:
            try:
                path = os.path.join(_resolve_runtime_dir(), "preview.pdf")
                url_out = "/static/preview.pdf"
            except Exception as e:
                return {"ok": False, "error": "no-runtime-dir: %s" % e}
        if not self._meas_lock.acquire(blocking=False):
            return {"ok": False, "error": "busy"}
        w = None
        try:
            w, ctrl, core, ui, js = self._open_hidden(u, 1100, 900)
            self._wait_ready(js)
            paper = self._doc_paper(js)
            mm = 1.0 / 25.4
            bb = {}

            def f():
                st = core.Environment.CreatePrintSettings()
                st.ShouldPrintHeaderAndFooter = False
                st.ShouldPrintBackgrounds = True
                st.PageWidth = paper["w"] * mm
                st.PageHeight = paper["h"] * mm
                st.MarginTop = paper["mt"] * mm
                st.MarginBottom = paper["mb"] * mm
                st.MarginLeft = paper["ml"] * mm
                st.MarginRight = paper["mr"] * mm
                bb["task"] = core.PrintToPdfAsync(path, st)

            err = ui(f)
            if "task" not in bb:
                return {"ok": False,
                        "error": err.get("err") or "pdf-not-started"}
            if not bb["task"].Wait(120000):
                return {"ok": False, "error": "timeout"}
            n = 0
            try:
                n = len(_re.findall(rb"/Type\s*/Page\b",
                                    open(path, "rb").read()))
            except Exception:
                n = 0
            log("pdf_save: %s -> %s pages" % (path, n))
            return {"ok": True, "path": path, "pages": n, "url": url_out}
        except Exception as e:
            log("pdf_save err: %s" % e)
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        finally:
            try:
                if w is not None:
                    w.destroy()
            except Exception:
                pass
            self._meas_lock.release()

    def pick_save_path(self, default_name="", last_dir=""):
        """另存为：只弹原生保存对话框选路径，写盘由页面统一走服务端
        /api/save-as（SSOT——物化/契约改写/回传只在服务端一份实现）。
        返回完整路径；取消返回空串。缺后缀补 .md，已带 .md/.smd 尊重用户。"""
        try:
            import webview
            kwargs = dict(
                directory=last_dir if last_dir and os.path.isdir(last_dir) else "",
                save_filename=default_name or "未命名.md")
            # 文件类型限定为 .md/.smd（pywebview 6.x：每个元素须为完整 '描述 (通配)' 格式）
            try:
                dlg = self.window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    file_types=("Markdown (*.md;*.smd)",), **kwargs)
            except Exception as e2:
                # 过滤参数任何形态的失败（版本差异/格式差异）都回退无过滤调用，保证可用性
                log("pick_save_path file_types fallback: %s" % e2)
                dlg = self.window.create_file_dialog(webview.SAVE_DIALOG, **kwargs)
            res = dlg
            if not res:
                return ""
            path = res if isinstance(res, str) else (res[0] if res else "")
            if not path:
                return ""
            low = path.lower()
            if not (low.endswith(".md") or low.endswith(".smd")):
                path += ".md"
            return path
        except Exception as e:
            log("pick_save_path err: %s" % e)
            return ""

    def common_dirs(self):
        home = os.path.expanduser("~")
        cand = {"docs": os.path.join(home, "Documents"),
                "desktop": os.path.join(home, "Desktop"),
                "downloads": os.path.join(home, "Downloads"),
                "home": home}
        return {k: v for k, v in cand.items() if os.path.isdir(v)}

    def api_version(self):
        log("api_version() called BY PAGE -> bridge OK")
        return {"port": PORT, "embedded": True}

    # ---- 窗口控制（托盘/页面可调用）----
    def minimize(self):
        try:
            self.window.minimize()
        except Exception:
            pass
        return True

    def toggle(self):
        """最小化 <-> 恢复"""
        try:
            if self.window.events:  # 占位
                pass
        except Exception:
            pass
        return True

    def close_app(self):
        threading.Thread(target=self._shutdown, daemon=True).start()
        return True

    def _shutdown(self):
        time.sleep(0.15)
        try:
            self.window.destroy()
        except Exception:
            pass



def on_closing():
    try:
        w = webview.windows[0] if webview.windows else None
        if w is not None:
            save_window_size(w.width, w.height)
    except Exception:
        pass


def _install_hang_watchdog():
    """卡死自动取证（心跳式）：后台线程每 2 秒醒一次，
    若实际醒来延迟明显超出预期，说明主线程/GIL 被长时间占用（=卡死），
    此时把【所有线程的调用栈】写入 runtime/hang.log。
    只在检测到异常时写文件，不做无条件 dump。"""
    def _worker():
        import sys
        import traceback
        import time as _t
        path = os.path.join(RUNTIME_DIR, "hang.log")
        while True:
            try:
                t0 = _t.time()
                _t.sleep(2.0)
                delay = (_t.time() - t0) - 2.0
                if delay > 1.5:           # 睡 2 秒却晚了 1.5 秒以上
                    with io.open(path, "a", encoding="utf-8",
                                 errors="replace") as f:
                        f.write("\n===== 检测到阻塞 %.1fs  %s =====\n"
                                % (delay, _t.strftime("%H:%M:%S")))
                        for tid, frame in sys._current_frames().items():
                            f.write("--- thread %s ---\n" % tid)
                            traceback.print_stack(frame, file=f)
            except Exception:
                pass
    try:
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        log("hang watchdog armed (heartbeat) -> runtime/hang.log")
    except Exception as e:
        log("hang watchdog failed: %s" % e)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    q = ("?file=" + urllib.parse.quote(target)) if target else ""
    log("start, target=%s" % target)
    _install_hang_watchdog()

    if not ensure_service():
        log("service unavailable, abort")
        return 1

    # 自带内核优先
    if os.path.isdir(BUNDLED_RUNTIME) and os.path.exists(
            os.path.join(BUNDLED_RUNTIME, "msedgewebview2.exe")):
        os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = BUNDLED_RUNTIME
        log("using bundled runtime")
    else:
        log("bundled runtime missing, fallback to system")
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", USER_DATA)

    import webview
    api = Api()
    w, h = load_window_size()
    win = webview.create_window("MDEditor", "http://127.0.0.1:%d/%s" % (PORT, q),
                                width=w, height=h, min_size=(900, 600),
                                js_api=api)
    api.window = win
    win._serializable = False  # 打断 js_api 序列化循环引用（api.window ↔ win.js_api），否则 get_functions 无限递归卡死
    win.events.closing += on_closing
    ensure_default_settings()
    st = load_settings()
    start_args = ["--disable-gpu"] if st.get("disable_gpu") else None
    if start_args:
        log("disable_gpu settings -> software rendering")


    webview.start(icon=os.path.join(HERE, "md-editor.ico"), args=start_args)
    log("window closed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("fatal: %s" % e)
        sys.exit(1)
