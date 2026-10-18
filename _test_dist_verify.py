# -*- coding: utf-8 -*-
# 分发清单实测：按"最小可用分发集"组装干净目录，从零启动，逐项验证。
# 不带：runtime/、__pycache__/、_slice/、全部测试与诊断、安装脚本。
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse

SRC = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(SRC, "_dist_verify")
PY = os.path.join(SRC, "python", "python.exe")
NO_WINDOW = 0x08000000
RESULTS = []


def check(name, ok, extra=""):
    RESULTS.append((name, ok))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                       (" | " + extra) if extra else ""))


# --- 1) 组装（真实分发包内容，junction 模拟大目录拷贝） ---
shutil.rmtree(DIST, ignore_errors=True)
os.makedirs(DIST)
FILES = ["md_launch.pyw", "_md_run.py", "md_server.py",
         "markdown-editor.html", "md-editor.ico", "llm_client.py",
         "web_search.py", "rag_client.py", "_smd.py", "md_assets.py",
         "_splash.py", "_pickdir_modern.py", "_pickfile.py", "md_app.pyw",
         "LICENSE", "README.md"]
for f in FILES:
    shutil.copy2(os.path.join(SRC, f), os.path.join(DIST, f))
for d in ["python", "katex", "pagedjs", "docs", "LICENSES"]:
    subprocess.run(["cmd", "/c", "mklink", "/J",
                    os.path.join(DIST, d), os.path.join(SRC, d)],
                   capture_output=True, creationflags=NO_WINDOW)
check("dist assembled (16 files + 5 junctions)",
      all(os.path.exists(os.path.join(DIST, f)) for f in FILES)
      and all(os.path.isdir(os.path.join(DIST, d))
              for d in ["python", "katex", "pagedjs", "docs", "LICENSES"]))
check("no runtime/ pycache/ in dist",
      not os.path.exists(os.path.join(DIST, "runtime"))
      and not os.path.exists(os.path.join(DIST, "__pycache__")))


def get(path, timeout=3):
    return urllib.request.urlopen(
        "http://127.0.0.1:18766" + path, timeout=timeout).read()


# --- 2) 从分发目录冷启动（shim，无 pyc，全新环境） ---
p = subprocess.Popen([PY, os.path.join(DIST, "_md_run.py")], cwd=DIST,
                     creationflags=NO_WINDOW)
t0 = time.time()
ver = None
while time.time() - t0 < 20:
    try:
        d = json.loads(get("/api/version", timeout=0.3))
        ver = d
        break
    except Exception:
        time.sleep(0.05)
check("cold start from dist (no pyc)", ver is not None,
      "%.2fs" % (time.time() - t0) if ver else "timeout")
check("version == 52 with sessions", ver and ver.get("version") == 52
      and "sessions" in ver, str(ver))

# --- 3) 页面与静态资源 ---
body = get("/").decode("utf-8")
check("page served", "MDEditor" in body and
      'defer src="/static/katex/katex.min.js"' in body,
      "%d bytes" % len(body))
check("katex.min.js", len(get("/static/katex/katex.min.js")) > 200000)
fonts = json.loads(get("/static/katex/fonts/").decode("utf-8")) \
    if False else None
try:
    get("/static/katex/fonts/KaTeX_Main-Regular.woff2")
    check("katex font file", True)
except Exception as e:
    check("katex font file", False, repr(e))
check("favicon", len(get("/favicon.ico")) > 10000)

# --- 4) 内置文档（默认文章 + 版权声明） ---
d1 = json.loads(get("/doc?file=" + urllib.parse.quote(
    "MDEditor 使用指南.md")).decode("utf-8"))
check("default doc (使用指南)", d1.get("ok") and len(d1.get("content", "")) > 500,
      "%d chars" % len(d1.get("content", "")))
d2 = json.loads(get("/doc?file=" + urllib.parse.quote(
    "版权与开源组件声明.md")).decode("utf-8"))
check("license doc (版权声明)", d2.get("ok") and len(d2.get("content", "")) > 200)

# --- 5) pagedjs 可用（分页导出，服务端读文件） ---
req = urllib.request.Request(
    "http://127.0.0.1:18766/api/export-paged",
    data=json.dumps({"bodyHtml": "<h1>分发验证</h1><p>paged 导出</p>",
                     "tsCss": "", "cfg": {}}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
check("paged export", r.get("ok") is True, r.get("url", r.get("error", "")))

# --- 6) 降级链路完整性：LLM 模块加载成功（无 _llm.err） ---
check("llm modules loaded (no _llm.err)",
      not os.path.exists(os.path.join(DIST, "runtime", "_llm.err")))

# --- 7) 首次写盘自动生成 runtime/（启动只读不建目录，保存设置才建） ---
req = urllib.request.Request(
    "http://127.0.0.1:18766/api/llm-config",
    data=json.dumps({"config": {"backend": "lmstudio"}}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=3).read()
except Exception:
    pass
check("runtime/ auto-created on first save",
      os.path.isdir(os.path.join(DIST, "runtime"))
      and os.path.isfile(os.path.join(DIST, "runtime", "settings.json")))

# --- 8) splash 在分发目录可起（进程能存活=消息循环正常） ---
sp = subprocess.Popen([PY, os.path.join(DIST, "_splash.py"),
                       "", "4", "18766", "52"], cwd=DIST,
                      creationflags=NO_WINDOW)
time.sleep(1.0)
alive = sp.poll() is None
check("splash process alive in dist", alive)
sp.terminate()
sp.wait(3)

# --- 清理 ---
print("cleanup: terminating server...", flush=True)
p.terminate()
try:
    p.wait(3)
except Exception:
    p.kill()
print("cleanup: stopping dist processes...", flush=True)
sp2 = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
     "-like '*_dist_verify\\*' -and $_.ProcessId -ne $PID } | ForEach-Object "
     "{ Stop-Process -Id $_.ProcessId -Force }"],
    capture_output=True, creationflags=NO_WINDOW, timeout=15)
print("cleanup: stopping processes done rc=%s" % sp2.returncode, flush=True)
time.sleep(0.5)
# junction 只删链接不伤源：os.rmdir 对 junction 是 unlink 语义；
# 实体目录随后 rmtree。带重试——句柄释放可能滞后于进程退出。
import time as _t
for attempt in range(5):
    for d in ["python", "katex", "pagedjs", "docs", "LICENSES"]:
        j = os.path.join(DIST, d)
        if os.path.isdir(j):
            try:
                os.rmdir(j)
            except OSError:
                pass
    try:
        shutil.rmtree(DIST, ignore_errors=False)
    except Exception:
        pass
    if not os.path.exists(DIST):
        break
    _t.sleep(0.5)
check("cleanup (source dirs intact)",
      os.path.isdir(os.path.join(SRC, "python"))
      and os.path.isdir(os.path.join(SRC, "katex"))
      and not os.path.exists(DIST))

fails = [n for n, ok in RESULTS if not ok]
print("\n%d/%d passed" % (len(RESULTS) - len(fails), len(RESULTS)))
if fails:
    print("FAILED:", "; ".join(fails))
    sys.exit(1)