# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""MDEditor 内嵌窗口应用
- pywebview 开原生窗口指向本地服务（无浏览器 UI）
- 自带 WebView2 内核优先（runtime/WebView2），不存在则用系统内核
- 暴露 py API 供页面直接调用（原生文件/目录对话框、保存、粘贴图片、窗口控制）
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
PORT = 18765
sys.path.insert(0, HERE)

BUNDLED_RUNTIME = os.path.join(HERE, "runtime", "WebView2")
USER_DATA = os.path.join(HERE, "runtime", "userdata")
WIN_CONF = os.path.join(HERE, "runtime", "window.json")
SETTINGS = os.path.join(HERE, "runtime", "settings.json")
LOG = os.path.join(HERE, "runtime", "md_app.log")


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
            "http://127.0.0.1:%d/api/version" % PORT, timeout=2).read().decode())
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
        subprocess.Popen([exe, os.path.join(HERE, "md_server.py")],
                         cwd=HERE, creationflags=0x08000000)
    except Exception as e:
        log("start service failed: %s" % e)
        return False
    for _ in range(60):
        if service_alive():
            return True
        time.sleep(0.25)
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


class Api:
    """供前端通过 window.pywebview.api.* 直接调用。"""

    def __init__(self):
        self.window = None

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

    def pick_open(self):
        """打开 .md 文件：返回 {path, content}"""
        try:
            import webview
            res = self.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("Markdown (*.md;*.markdown;*.txt)", "All files (*.*)"))
            if not res:
                return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            content = io.open(path, encoding="utf-8", errors="replace").read()
            return {"path": path, "content": content}
        except Exception as e:
            log("pick_open err: %s" % e)
            return None

    def _materialize(self, doc_path, content):
        try:
            from md_assets import materialize_images
            new, saved = materialize_images(doc_path, content)
            log("materialized %d image(s): %s" % (len(saved), saved))
            return new, saved
        except Exception as e:
            log("materialize err: %s" % e)
            return content, []

    def read_file(self, path):
        try:
            return {"path": path, "content": io.open(path, encoding="utf-8", errors="replace").read()}
        except Exception as e:
            return {"error": str(e)}

    def save_file(self, path, content):
        try:
            content, added = self._materialize(path, content)
            io.open(path, "w", encoding="utf-8", newline="").write(content)
            return {"ok": True, "path": path, "images": added}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_as(self, default_name, content, last_dir=""):
        try:
            import webview
            res = self.window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=last_dir if last_dir and os.path.isdir(last_dir) else "",
                save_filename=default_name or "未命名.md")
            if not res:
                return {"ok": False, "cancelled": True}
            path = res if isinstance(res, str) else (res[0] if res else "")
            if not path:
                return {"ok": False, "cancelled": True}
            if not path.lower().endswith(".md"):
                path += ".md"
            content, added = self._materialize(path, content)
            io.open(path, "w", encoding="utf-8", newline="").write(content)
            return {"ok": True, "path": path, "images": added}
        except Exception as e:
            log("save_as err: %s" % e)
            return {"ok": False, "error": str(e)}

    def paste_image(self, doc_path, data_url):
        try:
            import base64
            if not doc_path:
                return {"ok": False, "error": "文档尚未保存"}
            head, _, b64 = data_url.partition(",")
            ext = ".png"
            for k, v in (("jpeg", ".jpg"), ("webp", ".webp"), ("gif", ".gif")):
                if k in head:
                    ext = v
            stem = os.path.splitext(os.path.basename(doc_path))[0]
            assets = os.path.join(os.path.dirname(doc_path), stem + ".assets")
            os.makedirs(assets, exist_ok=True)
            fname = "%s_%s%s" % (time.strftime("%Y%m%d_%H%M%S"),
                                 str(int(time.time() * 1000))[-4:], ext)
            with open(os.path.join(assets, fname), "wb") as f:
                f.write(base64.b64decode(b64))
            return {"ok": True, "rel": "%s.assets/%s" % (stem, fname)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
        path = os.path.join(HERE, "runtime", "hang.log")
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
    win.events.closing += on_closing
    ensure_default_settings()
    st = load_settings()
    start_args = ["--disable-gpu"] if st.get("disable_gpu") else None
    if start_args:
        log("disable_gpu settings -> software rendering")


    webview.start(args=start_args)
    log("window closed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("fatal: %s" % e)
        sys.exit(1)
