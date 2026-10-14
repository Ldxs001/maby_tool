# -*- coding: utf-8 -*-
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
import json
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser

PORT = 18765
VERSION = 2  # 与 md_server.py 的 MD_SERVER_VERSION 保持一致
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


def kill_stale_services():
    """清掉除自身以外的所有 pythonw 旧服务进程（自愈换代）"""
    me = os.getpid()
    try:
        subprocess.run(
            ["taskkill", "/F", "/FI", "PID ne %d" % me, "/IM", "pythonw.exe"],
            creationflags=NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
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
            "http://127.0.0.1:%d/open%s" % (PORT, q), timeout=5).read()
    except Exception:
        sep = "&" if q else "?"
        webbrowser.open("http://127.0.0.1:%d/%sv=%d" % (PORT, q and (q + sep) or (sep), VERSION))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if port_open():
        if server_version() == VERSION:
            pass  # 版本匹配，直接复用
        else:
            # 旧版服务占着端口：自愈换代
            kill_stale_services()
            time.sleep(0.6)
            start_server()
            if not wait_version():
                open_in_browser(path)  # 兜底：至少把页面打开
                return
    else:
        start_server()
        if not wait_version():
            open_in_browser(path)
            return
    open_in_browser(path)


if __name__ == "__main__":
    main()
