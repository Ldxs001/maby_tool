# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MDEditor installer builder (system csc.exe only, zero third-party).

Stages the dist-checklist minimum set, packs payload.zip (UTF-8 entry names),
compiles a WinForms single-file installer with the Windows built-in C#
compiler, then (optionally) runs the built exe with --smoke and asserts the
extraction result.

Usage:
  python installer/_build_installer.py            # build MDEditor-Setup-vX.Y.Z.exe
  python installer/_build_installer.py --smoke    # smoke build + self-check first
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGING = os.path.join(SRC, "_setup_staging")
OUT = os.path.join(SRC, "_setup_out")
SMOKE_REPORT = os.path.join(tempfile.gettempdir(), "md_setup_smoke_report.txt")

# dist checklist minimum set (sections 1+2+3+4). Keep in sync with docs checklist.
DIST_DIRS = ["python", "katex", "pagedjs", "LICENSES",
             "mermaid", "viz", "wavedrom", "vega", "docxdeps"]
DIST_DOCS_FILES = ["MDEditor 使用指南.md", "版权与开源组件声明.md",
                   "low runner 数据形式规范.md"]
DIST_DOCS_DIRS = ["MDEditor 使用指南.assets", "版权与开源组件声明.assets"]
# 两份内置文档都用自有元数据通道：档案在 <文档>.assets/.mde/ 里，漏一整个目录 = 装完打开就没有元数据区。
# low runner run 库（种子：运行树 runtime/runs/ → 安装后 runtime/runs/，
# md_server 启动 makedirs 不会清掉既有文件）。
# 全量打包：run 库是示例与文档的实指对象，缺一个就断链（使用指南、规范、
# CHANGELOG 里都直接点名 these 文件），因此这里不写死清单，直接扫目录取全部 .py。
# 只取 *.py：__pycache__ 等运行态产物不进包。
_RUNS_SRC = os.path.join(SRC, "runtime", "runs")
DIST_RUNS = sorted(f for f in os.listdir(_RUNS_SRC)
                   if f.endswith(".py") and os.path.isfile(os.path.join(_RUNS_SRC, f)))
if not DIST_RUNS:
    raise SystemExit("FAIL no run library files found in %s" % _RUNS_SRC)
_MAIL_SEED = "_report_mail.txt"   # 举报收件邮箱种子（不入库，随包分发）
DIST_FILES = ["md_launch.pyw", "_md_run.py", "md_server.py", "markdown-editor.html",
              "md-editor.ico", "uninstall-md.ico", "llm_client.py", "web_search.py",
              "rag_client.py", "_smd.py", "md_assets.py", "_splash.py",
              "_pickdir_modern.py", "_pickfile.py", "_picksave.py",
              "docx_export.py", "md_meta.py",
              "md_app.pyw", "LICENSE", "COPYRIGHT", "README.md",
              "install.cmd", "MarkdownEditor.cs", "_mklnk.ps1",
              "uninstall.cmd", "UninstallMDEditor.cs", "desktop-shortcut.cmd", "md_stop.cmd"]

# 构建期预编译的二进制（由 make_prebuilt_exes 生成，随包分发）。
# MarkdownEditor.exe 是右键菜单 / 打开方式的入口，UninstallMDEditor.exe 是
# 「应用和功能」里的卸载入口 —— 两者都不能依赖目标机上有编译器。
PREBUILT_EXES = ["MarkdownEditor.exe", "UninstallMDEditor.exe"]


def detect_version():
    with open(os.path.join(SRC, "CHANGELOG.md"), encoding="utf-8") as f:
        m = re.search(r"^## v(\d+\.\d+\.\d+)", f.read(), re.M)
    if not m:
        raise SystemExit("FAIL cannot detect version from CHANGELOG.md")
    return m.group(1)


def find_csc():
    root = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "Microsoft.NET", "Framework64")
    vers = sorted((d for d in os.listdir(root) if d.startswith("v4")), reverse=True)
    if not vers:
        raise SystemExit("FAIL .NET Framework 4 csc.exe not found")
    return os.path.join(root, vers[0], "csc.exe")


def make_prebuilt_exes():
    """构建期预编译 MarkdownEditor.exe 与 UninstallMDEditor.exe。

    两者都是系统集成入口（右键菜单 / 「应用和功能」卸载项），必须在包内就存在。
    过去是 install.cmd 在用户机器上现场编译：目标机没有 csc.exe 时卸载入口指向
    不存在的文件；且每次安装都执行编译器，是杀软与企业 EDR 的经典误报触发点。
    现在改为构建期产出、随包分发，install.cmd 只在缺失时兜底现场编译。
    """
    csc = find_csc()
    manifest = os.path.join(SRC, "installer", "app.manifest")
    targets = [
        # (source, output, icon, dpi-manifest)
        ("MarkdownEditor.cs", "MarkdownEditor.exe", "md-editor.ico", None),
        # 卸载器是带界面的常驻窗口，manifest 声明 PerMonitorV2 后 DPI 自缩放
        # 代码才会拿到真实 DPI（否则系统按 DPI-unaware 虚拟化，125% 下发糊）。
        ("UninstallMDEditor.cs", "UninstallMDEditor.exe", "uninstall-md.ico", manifest),
    ]
    for src, out, ico, mfst in targets:
        src_path = os.path.join(SRC, src)
        if not os.path.exists(src_path):
            raise SystemExit("FAIL prebuilt source missing: %s" % src)
        out_path = os.path.join(SRC, out)
        args = [csc, "/nologo", "/target:winexe", "/out:" + out_path]
        ico_path = os.path.join(SRC, ico)
        if os.path.exists(ico_path):
            args.append("/win32icon:" + ico_path)
        if mfst and os.path.exists(mfst):
            args.append("/win32manifest:" + mfst)
        args.append(src_path)
        r = subprocess.run(args, capture_output=True, timeout=600)
        if r.returncode != 0 or not os.path.exists(out_path):
            print((r.stdout or b"").decode("mbcs", "replace"))
            print((r.stderr or b"").decode("mbcs", "replace"))
            raise SystemExit("FAIL prebuilt compile: %s" % out)
        print("prebuilt: %s (%d bytes)" % (out, os.path.getsize(out_path)))


def _clear_readonly_tree(root):
    """递归解掉只读位。构建产物可覆盖是前提，而 docs 里的元数据档案
    （.mde/zero.json）建档即只读，copytree(dirs_exist_ok=True) 覆盖它必
    PermissionError（实测复现）。只解位，不动内容。"""
    if not root or not os.path.isdir(root):
        return
    for dp, _dns, fns in os.walk(root):
        for fn in fns:
            try:
                os.chmod(os.path.join(dp, fn), 0o666)
            except Exception:
                pass


def make_staging(ver):
    # 覆盖式重建：不整目录 rmtree —— 70MB / 1200 个文件的批量删除既慢，也容易被
    # 环境的安全策略整批拦截（构建中间产物本就该可覆盖）。写完按「应到文件集合」
    # 清残留，保证包内不会混进上一轮的文件。
    os.makedirs(STAGING, exist_ok=True)
    _clear_readonly_tree(STAGING)      # 只读档案会让下面的 copytree 覆盖失败
    for d in DIST_DIRS:
        shutil.copytree(os.path.join(SRC, d), os.path.join(STAGING, d), dirs_exist_ok=True)
    docs = os.path.join(STAGING, "docs")
    os.makedirs(docs, exist_ok=True)
    for f in DIST_DOCS_FILES:
        shutil.copy2(os.path.join(SRC, "docs", f), os.path.join(docs, f))
    for d in DIST_DOCS_DIRS:
        shutil.copytree(os.path.join(SRC, "docs", d), os.path.join(docs, d), dirs_exist_ok=True)
    for f in DIST_FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(STAGING, f))
    # 举报收件邮箱种子：不入库（.gitignore 排除），只随构建产物分发。
    # 缺失不影响构建，但商店包会失去「打开邮件客户端」路径、只剩复制。
    _mail_seed_src = os.path.join(SRC, _MAIL_SEED)
    if os.path.exists(_mail_seed_src):
        shutil.copy2(_mail_seed_src, os.path.join(STAGING, _MAIL_SEED))
        print("mail seed: %s 已打入" % _MAIL_SEED)
    else:
        print("mail seed: 缺 %s → 举报入口只保留复制路径" % _MAIL_SEED)
    # 预编译二进制：构建期产出，随包分发（见 make_prebuilt_exes）
    for f in PREBUILT_EXES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(STAGING, f))
    # app.manifest：install.cmd 兜底现场编译卸载器时需要同一份 PerMonitorV2
    # 声明，老包升级路径上重新编译出来的卸载器才不会在高 DPI 下发糊。
    shutil.copy2(os.path.join(SRC, "installer", "app.manifest"),
                 os.path.join(STAGING, "app.manifest"))
    # low runner run 库种子（runtime/runs/ → 安装后 runtime/runs/，全量 .py）
    rdst = os.path.join(STAGING, "runtime", "runs")
    os.makedirs(rdst, exist_ok=True)
    for f in DIST_RUNS:
        shutil.copy2(os.path.join(_RUNS_SRC, f), os.path.join(rdst, f))

    # 残留清理：算出本轮应在的文件集合，删掉 staging 里多出来的（通常为 0 个）
    expect = set()
    for d in DIST_DIRS:
        base = os.path.join(SRC, d)
        for root, _dirs, fs in os.walk(base):
            for fn in fs:
                expect.add(os.path.relpath(os.path.join(root, fn), SRC).replace(os.sep, "/"))
    for f in DIST_DOCS_FILES:
        expect.add("docs/" + f)
    for d in DIST_DOCS_DIRS:
        for root, _dirs, fs in os.walk(os.path.join(SRC, "docs", d)):
            for fn in fs:
                rel = os.path.relpath(os.path.join(root, fn), os.path.join(SRC, "docs"))
                expect.add("docs/" + rel.replace(os.sep, "/"))
    for f in DIST_FILES:
        expect.add(f)
    if os.path.exists(os.path.join(SRC, _MAIL_SEED)):
        expect.add(_MAIL_SEED)
    for f in PREBUILT_EXES:
        expect.add(f)
    expect.add("app.manifest")
    for f in DIST_RUNS:
        expect.add("runtime/runs/" + f)
    stale = []
    for root, _dirs, fs in os.walk(STAGING):
        for fn in fs:
            rel = os.path.relpath(os.path.join(root, fn), STAGING).replace(os.sep, "/")
            if rel not in expect:
                stale.append(rel)
    for rel in stale:
        os.remove(os.path.join(STAGING, rel.replace("/", os.sep)))

    # docx 导出功能件断言（缺一即 FAIL：md_server 运行时 import，安装包内缺了就是坏功能）
    _docx_must = [
        os.path.join(STAGING, "docx_export.py"),
        os.path.join(STAGING, "_picksave.py"),
        os.path.join(STAGING, "docxdeps", "docx"),
        os.path.join(STAGING, "docxdeps", "lxml"),
        os.path.join(STAGING, "docxdeps", "PIL"),
        os.path.join(STAGING, "docxdeps", "latex2mathml"),
        os.path.join(STAGING, "docxdeps", "LICENSES", "README.md"),
    ]
    # low runner 种子断言（缺一即 FAIL：示例 run 随包分发，缺了就断链）
    _runs_must = [os.path.join(rdst, f) for f in DIST_RUNS]
    _miss_docx = [p for p in _docx_must if not os.path.exists(p)]
    _miss_runs = [p for p in _runs_must if not os.path.exists(p)]
    if _miss_docx:
        raise SystemExit("FAIL staging missing docx export files: %s" % _miss_docx)
    if _miss_runs:
        raise SystemExit("FAIL staging missing run library files: %s" % _miss_runs)
    n = sum(len(fs) for _, _, fs in os.walk(STAGING))
    print("staging: %d files, %d stale removed" % (n, len(stale)))
    return n


def make_payload_zip():
    zpath = os.path.join(OUT, "payload.zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _dirs, files in os.walk(STAGING):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, STAGING).replace(os.sep, "/")
                z.write(full, arc)
    return zpath


def compile_installer(ver, out_name):
    os.makedirs(OUT, exist_ok=True)
    zpath = make_payload_zip()
    # ver.txt：第 1 行版本号，第 2 行 payload.zip 的 SHA256（安装期校验用）。
    import hashlib
    with open(zpath, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    vpath = os.path.join(OUT, "ver.txt")
    with open(vpath, "w", encoding="utf-8", newline="\n") as f:
        f.write(ver + "\n" + digest + "\n")
    # csc reads source as ANSI unless BOM; add BOM so Chinese literals survive.
    cs_bom = os.path.join(OUT, "_setup_win_bom.cs")
    with open(os.path.join(SRC, "installer", "_setup_win.cs"), encoding="utf-8") as f:
        text = f.read()
    with open(cs_bom, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text)
    # 版本号写进独立源文件：与 CHANGELOG 版本同源，不会脱节。
    # 装配版本必须是 4 段数字（2.11.1 -> 2.11.1.0），文件版本保留三段显示。
    parts = ver.split(".")
    while len(parts) < 4:
        parts.append("0")
    asm_ver = ".".join(parts[:4])
    ver_cs = os.path.join(OUT, "_setup_ver.cs")
    with open(ver_cs, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("// generated by _build_installer.py -- do not edit\n")
        f.write("using System.Reflection;\n")
        f.write('[assembly: AssemblyVersion("%s")]\n' % asm_ver)
        f.write('[assembly: AssemblyFileVersion("%s")]\n' % asm_ver)
        f.write('[assembly: AssemblyInformationalVersion("%s")]\n' % ver)
    exe = os.path.join(OUT, out_name)
    if os.path.exists(exe):
        os.remove(exe)
    manifest = os.path.join(SRC, "installer", "app.manifest")
    args = [find_csc(), "/nologo", "/target:winexe", "/platform:anycpu",
            "/out:" + exe,
            "/win32icon:" + os.path.join(SRC, "md-editor.ico"),
            "/win32manifest:" + manifest,
            "/r:System.IO.Compression.dll",
            "/r:System.IO.Compression.FileSystem.dll",
            "/r:System.Windows.Forms.dll",
            "/r:System.Drawing.dll",
            "/res:" + zpath,
            "/res:" + vpath,
            cs_bom, ver_cs]
    r = subprocess.run(args, capture_output=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(exe):
        print((r.stdout or b"").decode("mbcs", "replace"))
        print((r.stderr or b"").decode("mbcs", "replace"))
        raise SystemExit("FAIL csc compile")
    return exe, os.path.getsize(zpath)


def run_smoke(exe):
    if os.path.exists(SMOKE_REPORT):
        os.remove(SMOKE_REPORT)
    # payload 内 run 库清单（独立于 C# smoke 报告：直接查包，最贴近用户拿到的东西）
    with zipfile.ZipFile(os.path.join(OUT, "payload.zip")) as z:
        _zip_runs = sorted(n.rsplit("/", 1)[-1] for n in z.namelist()
                           if n.startswith("runtime/runs/") and n.endswith(".py"))
    _runs_ok = _zip_runs == DIST_RUNS
    subprocess.run([exe, "--smoke"], timeout=600, capture_output=True)
    for _ in range(40):
        if os.path.exists(SMOKE_REPORT):
            break
        import time
        time.sleep(0.5)
    if not os.path.exists(SMOKE_REPORT):
        raise SystemExit("FAIL smoke report missing")
    rep = {}
    with open(SMOKE_REPORT, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                rep[k] = v
    checks = [
        ("payload extracted", int(rep.get("total_files", "0")) > 500, rep.get("total_files", "?")),
        ("guide md exists (exact Chinese name)",
         rep.get("guide_md_exists") == "1" and "MDEditor 使用指南.md" in rep.get("docs_listing", ""),
         rep.get("docs_listing", "")[:200]),
        ("license doc exists", rep.get("license_doc_exists") == "1", ""),
        ("uninstall icon in payload", rep.get("uninstall_icon_exists") == "1", ""),
        ("uninstaller source in payload", rep.get("uninstaller_cs_exists") == "1", ""),
        ("launcher shim exe in payload", rep.get("shim_exe_exists") == "1",
         rep.get("shim_exe_size", "?")),
        ("uninstaller exe in payload", rep.get("uninstaller_exe_exists") == "1",
         rep.get("uninstaller_exe_size", "?")),
        ("pythonnet DLL >= 400KB", int(rep.get("pythonnet_dll_size", "0")) > 400 * 1024,
         rep.get("pythonnet_dll_size", "?")),
        ("katex fonts >= 50", int(rep.get("katex_fonts_count", "0")) >= 50,
         rep.get("katex_fonts_count", "?")),
        ("pythonw.exe present", rep.get("pythonw_exists") == "1", ""),
        ("mermaid vendor in payload (>=3MB)",
         int(rep.get("mermaid_vendor_size", "0")) > 3 * 1024 * 1024,
         rep.get("mermaid_vendor_size", "?")),
        ("viz-js vendor in payload (>=1MB)",
         int(rep.get("viz_vendor_size", "0")) > 1024 * 1024,
         rep.get("viz_vendor_size", "?")),
        ("wavedrom vendor in payload (>=50KB)",
         int(rep.get("wavedrom_vendor_size", "0")) > 50 * 1024,
         rep.get("wavedrom_vendor_size", "?")),
        ("wavedrom skins in payload (>=30KB x2)",
         int(rep.get("wavedrom_skin_size", "0")) > 30 * 1024
         and int(rep.get("wavedrom_skin_dark_size", "0")) > 30 * 1024,
         rep.get("wavedrom_skin_size", "?") + "/" + rep.get("wavedrom_skin_dark_size", "?")),
        ("vega-embed vendor in payload (>=50KB)",
         int(rep.get("vega_embed_vendor_size", "0")) > 50 * 1024,
         rep.get("vega_embed_vendor_size", "?")),
        ("version parsed", rep.get("version", "?") != "?", rep.get("version", "?")),
        ("webview2 detected (this machine)", rep.get("webview2") == "1", ""),
        ("run library complete in payload (%d files)" % len(DIST_RUNS), _runs_ok,
         ",".join(_zip_runs)),
    ]
    fails = [name for name, ok, _ in checks if not ok]
    for name, ok, extra in checks:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name, (" | " + extra) if extra else ""))
    return not fails


def cleanup_old_exes(keep_ver):
    """只保留当前版本与上一个版本的安装包。

    历史安装包堆在同一目录里容易被误发（Release 挂错版本），且每个 30MB+
    很快占满磁盘。保留上一版是为了「回退到上一版」时手上有包可用。
    """
    import re
    if not os.path.isdir(OUT):
        return
    vers = []
    for fn in os.listdir(OUT):
        m = re.match(r"^MDEditor-Setup-v(\d+\.\d+\.\d+)\.exe$", fn)
        if m:
            vers.append((tuple(int(x) for x in m.group(1).split(".")), fn))
    vers.sort(reverse=True)
    for idx, (_v, fn) in enumerate(vers):
        if idx >= 2:
            try:
                os.remove(os.path.join(OUT, fn))
                print("cleanup: removed old installer %s" % fn)
            except OSError:
                pass
    # smoke 中间产物不进发行
    for fn in ("_setup_smoke.exe",):
        p = os.path.join(OUT, fn)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def main():
    smoke_mode = "--smoke" in sys.argv
    ver = detect_version()
    make_prebuilt_exes()
    n = make_staging(ver)
    print("staging ready: %d files (v%s)" % (n, ver))
    out_name = "_setup_smoke.exe" if smoke_mode else "MDEditor-Setup-v%s.exe" % ver
    exe, zsize = compile_installer(ver, out_name)
    print("BUILD OK: %s (%d KB, payload.zip %d KB)"
          % (exe, os.path.getsize(exe) // 1024, zsize // 1024))
    if smoke_mode:
        ok = run_smoke(exe)
        print("SMOKE %s" % ("PASS" if ok else "FAIL"))
        sys.exit(0 if ok else 1)
    cleanup_old_exes(ver)


if __name__ == "__main__":
    main()
