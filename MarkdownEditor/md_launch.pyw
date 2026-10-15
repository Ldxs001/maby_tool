# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""
MD 编辑器启动器（无控制台窗口）
Explorer 右键 / 双击传入 .md 路径时：
1. 端口空闲 → 拉起 md_server.py
2. 端口占用 → 校验服务版本：匹配则复用；不匹配（旧版本服务）则
   清掉旧服务进程后自行拉起最新版（自愈换代，用户无感）
3. 通知后端打开浏览器到对应 ?file= 页面
"""
import sys
import os
import io
import json
import socket
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
import webbrowser

PORT = 18765
try:
    # 版本单一来源：直接读 md_server，杜绝两边手改漏同步
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from md_server import MD_SERVER_VERSION as VERSION
except Exception:
    VERSION = 11
HERE = os.path.dirname(os.path.abspath(__file__))
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def port_open():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def server_version():
    """端口上服务的版本号；无 /api/version（旧版）或连接失败返回 None"""
    try:
        r = urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=1.5)
        return json.loads(r.read().decode("utf-8")).get("version", 0)
    except Exception:
        return None


def start_server():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.Popen(
        [sys.executable, os.path.join(HERE, "md_server.py")],
        startupinfo=si,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _list_pythonw_cmdlines():
    """列出 (pid, commandline)；wmic 不可用时退回 PowerShell CIM。"""
    cmds = [
        ["wmic", "process", "where", "name='pythonw.exe'", "get",
         "ProcessId,CommandLine", "/format:csv"],
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | "
         "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"],
    ]
    for c in cmds:
        try:
            r = subprocess.run(c, capture_output=True, text=True,
                               errors="replace", creationflags=NO_WINDOW)
            out = r.stdout or ""
            if out.strip():
                return out
        except Exception:
            continue
    return ""


def kill_stale_apps():
    """关闭所有旧的 md_app 窗口。
    页面本身 no-store（不存在页面缓存），因此'关掉旧窗口 + 开新窗口'
    即可保证用户看到的永远是当前代码。"""
    me = os.getpid()
    exe = os.path.basename(sys.executable).lower()
    out = _list_pythonw_cmdlines()
    killed = []
    for ln in out.splitlines():
        if "md_app.pyw" not in ln:
            continue
        parts = [p for p in ln.replace("|", ",").split(",") if p.strip()]
        if not parts:
            continue
        pid = parts[-1].strip()
        if pid.isdigit() and int(pid) != me:
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                killed.append(pid)
            except Exception:
                pass
    return killed


def kill_stale_services():
    """清掉旧的 md_server（按命令行精确匹配，不误伤其它 pythonw 脚本）"""
    me = os.getpid()
    killed = []
    for ln in _list_pythonw_cmdlines().splitlines():
        if "md_server.py" not in ln:
            continue
        parts = [p for p in ln.replace("|", ",").split(",") if p.strip()]
        if not parts:
            continue
        pid = parts[-1].strip()
        if pid.isdigit() and int(pid) != me:
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                killed.append(pid)
            except Exception:
                pass
    return killed


def kill_port_holder():
    """兜底：杀掉占用本服务端口的进程（服务可能不是以 pythonw 启动的）。"""
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                           errors="replace", creationflags=NO_WINDOW)
        me = os.getpid()
        for ln in (r.stdout or "").splitlines():
            if ":%d " % PORT not in ln or "LISTENING" not in ln.upper():
                continue
            pid = ln.split()[-1].strip()
            if pid.isdigit() and int(pid) != me:
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               creationflags=NO_WINDOW,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    except Exception:
        pass


def wait_version(timeout=15):
    t = 0.0
    while t < timeout:
        if server_version() == VERSION:
            return True
        time.sleep(0.25)
        t += 0.25
    return False


def open_in_browser(path):
    q = ("?file=" + urllib.parse.quote(path)) if path else ""
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/open%s" % (PORT, q), timeout=8).read()
    except urllib.error.URLError:
        # 仅在“连不上服务”时兜底；HTTP 状态错误/超时不重复打开
        sep = "&" if q else "?"
        webbrowser.open("http://127.0.0.1:%d/%sv=%d" % (PORT, q and (q + sep) or (sep), VERSION))
    except Exception:
        pass


_splash_proc = None


def load_settings():
    """读取 runtime/settings.json（缺失/损坏时用默认值）"""
    defaults = {"embed_window": False, "disable_gpu": False}
    try:
        p = os.path.join(HERE, "runtime", "settings.json")
        d = json.loads(io.open(p, encoding="utf-8").read())             if False else json.loads(open(p, encoding="utf-8").read())
        if isinstance(d, dict):
            defaults.update({k: d[k] for k in defaults if k in d})
    except Exception:
        pass
    return defaults


def embedded_available():
    """内嵌模式可用性：有 md_app.pyw，且（自带内核 或 系统 WebView2）存在。"""
    if not os.path.exists(os.path.join(HERE, "md_app.pyw")):
        return False
    if os.path.exists(os.path.join(HERE, "runtime", "WebView2", "msedgewebview2.exe")):
        return True
    # 系统 WebView2 Runtime
    for p in (r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application",
              r"C:\Program Files\Microsoft\EdgeWebView\Application"):
        try:
            if os.path.isdir(p) and any(d[0].isdigit() for d in os.listdir(p)):
                return True
        except Exception:
            pass
    return False


def launch_embedded(path=None):
    """尝试用内嵌窗口打开；成功返回 True。"""
    if not embedded_available():
        return False
    exe = os.path.join(HERE, "python", "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    args = [exe, os.path.join(HERE, "md_app.pyw")]
    if path:
        args.append(path)
    try:
        subprocess.Popen(args, cwd=HERE, creationflags=0x08000000)
        return True
    except Exception:
        return False


def start_splash(hold_seconds=25):
    """启动画面（独立子进程）。真实启动完成后由 close_splash() 淡出，
    hold_seconds 只是兜底上限。"""
    here = os.path.dirname(os.path.abspath(__file__))
    sp = os.path.join(here, "_splash.py")
    if not os.path.exists(sp):
        return
    exe = os.path.join(here, "python", "python.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    global _splash_proc
    try:
        _splash_proc = subprocess.Popen([exe, sp, "", str(hold_seconds),
                                         str(PORT), str(VERSION)],
                                        cwd=here, creationflags=0x08000000)
    except Exception:
        _splash_proc = None


def close_splash():
    """给启动画面窗口发 WM_CLOSE，让它淡出退出。"""
    try:
        import ctypes
        u = ctypes.windll.user32
        u.FindWindowW.restype = ctypes.c_void_p
        u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                   ctypes.c_size_t, ctypes.c_ssize_t]
        h = u.FindWindowW("MDEditorSplash2", None)
        if h:
            u.PostMessageW(ctypes.c_void_p(h), 0x0010, 0, 0)
    except Exception:
        pass
    # 兜底：淡出未完成（0.9s）则直接终止进程
    global _splash_proc
    if _splash_proc is not None:
        try:
            _splash_proc.wait(timeout=0.9)
        except Exception:
            try:
                _splash_proc.terminate()
            except Exception:
                pass
        _splash_proc = None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    # 先关掉所有旧编辑器窗口：页面 no-store，新窗口必然加载当前代码，
    # 避免"改了没生效/同时挂多个旧窗口"的问题
    kill_stale_apps()
    if port_open():
        if server_version() == VERSION:
            pass  # 版本匹配，直接复用
        else:
            # 旧版服务占着端口：自愈换代
            start_splash()
            kill_stale_services()
            kill_port_holder()
            time.sleep(0.6)
            start_server()
            if not wait_version():
                close_splash()
                open_in_browser(path)  # 兜底：至少把页面打开
                return
    else:
        start_splash()
        start_server()
        if not wait_version():
            close_splash()
            open_in_browser(path)
            return
    close_splash()
    st = load_settings()
    if st.get("embed_window") and launch_embedded(path):
        return
    open_in_browser(path)


if __name__ == "__main__":
    main()
