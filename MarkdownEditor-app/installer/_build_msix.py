# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MDEditor MSIX builder (Microsoft Store channel).

清单式打包：从与安装包同一份 staging 载荷出发，剔除安装/卸载链（商城版由
系统接管安装与卸载），加 AppxManifest 与商城徽标，用 Windows SDK 的
makeappx 出 .msix。不用 MSIX Packaging Tool 捕获式打包——那会把 install.cmd
的注册表操作捕获进包，包失效且过不了审。

包身份（Identity Name / Publisher）必须与合作伙伴中心保留的应用名称一致，
否则商城拒收。身份从 installer/_msix_identity.json 读取（不入库），也可用
参数覆盖：

  python installer/_build_msix.py --name MDEditor --publisher "CN=XXXX"

产出：_setup_out/MDEditor-vX.Y.Z-Store.msix（未签名；商城上传用未签名包，
由微软在审核后用自家证书签名分发。本地侧载测试用 _sign_msix.cmd 自签）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
OUT = os.path.join(SRC, "_setup_out")
IDENTITY_JSON = os.path.join(HERE, "_msix_identity.json")

# 商城版不需要的安装/卸载链与构建源文件（载荷与 Release 共享，商城版由
# 系统接管安装、关联与卸载，这些文件在容器里没有意义，剔除减小体积、
# 也避免审核误读）。
MSIX_EXCLUDE = {
    "install.cmd", "uninstall.cmd", "desktop-shortcut.cmd", "md_stop.cmd",
    "MarkdownEditor.cs", "UninstallMDEditor.cs",
    "UninstallMDEditor.exe", "uninstall-md.ico",
    "_mklnk.ps1", "app.manifest",
}

# 相对 staging 根的目录排除。default-docx-template 是 python-docx wheel 里
# 附带的解包态开发模板（含 [Content_Types].xml / _rels/.rels），运行时只用
# templates/default.docx；makeappx 对包内嵌套的这两个保留名文件直接报
# 0x8007007b，实测该目录零引用，剔除。
MSIX_EXCLUDE_DIRS = {
    os.path.join("docxdeps", "docx", "templates", "default-docx-template"),
}

# 商城徽标（PIL 从 md-editor.ico 派生）。
# 注意：tile 内**不要再缩边**。Windows 绘制 tile 时会自己加 padding，
# 图标自己在内部再缩一圈，结果是文件/开始菜单里只剩中间一小块
# （v2.26.0 及之前的 0.88 就吃了这个亏）。
LOGOS = [
    # (文件名, 宽, 高)
    ("Square44x44Logo.png", 44, 44),
    ("Square150x150Logo.png", 150, 150),
    ("Wide310x150Logo.png", 310, 150),
    ("LargeTile.png", 310, 310),
    ("StoreLogo.png", 50, 50),
]

# 文件类型图标：清单里 FileTypeAssociation 若不给 Logo，Windows 会拿
# Square44x44Logo 顶替，于是 .md 在资源管理器里显示成「应用图标」而非
# 「文件图标」。这里单独派生一套，且必须多尺寸 targetsize 变体——
# 只给一张大图，小视图（16/24/32）会被硬缩，点阵字必糊。
FILE_TYPE_ICON = "MdFileIcon"
FILE_TYPE_ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]

MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="{name}"
            Publisher="{publisher}"
            Version="{version}"
            ProcessorArchitecture="neutral" />
  <Properties>
    <DisplayName>{display_name}</DisplayName>
    <PublisherDisplayName>{publisher_display}</PublisherDisplayName>
    <Logo>assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop"
                        MinVersion="10.0.17763.0"
                        MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="zh-cn" />
  </Resources>
  <Applications>
    <Application Id="MDEditor"
                 Executable="MarkdownEditor.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{display_name}"
                          Description="Markdown / SMD editor"
                          BackgroundColor="#17263F"
                          Square150x150Logo="assets\\Square150x150Logo.png"
                          Square44x44Logo="assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="assets\\Wide310x150Logo.png"
                         Square310x310Logo="assets\\LargeTile.png"
                         ShortName="{display_name}" />
      </uap:VisualElements>
      <Extensions>
        <uap3:Extension Category="windows.fileTypeAssociation">
          <uap3:FileTypeAssociation Name="mddoc">
            <uap:Logo>assets\\MdFileIcon.png</uap:Logo>
            <uap:SupportedFileTypes>
            <uap:FileType>.md</uap:FileType>
            <uap:FileType>.smd</uap:FileType>
            </uap:SupportedFileTypes>
          </uap3:FileTypeAssociation>
        </uap3:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
    <Capability Name="internetClient" />
  </Capabilities>
</Package>
"""


def detect_version():
    sys.path.insert(0, HERE)
    import _build_installer
    return _build_installer.detect_version()


def load_identity():
    d = {}
    if os.path.exists(IDENTITY_JSON):
        with open(IDENTITY_JSON, encoding="utf-8") as f:
            d = json.load(f)
    return d


def make_logos(dst_dir):
    from PIL import Image
    ico = Image.open(os.path.join(SRC, "md-editor.ico"))
    best = ico
    try:
        # ico.info["sizes"] 里挑最大的图层
        sizes = ico.info.get("sizes") or {}
        biggest = max(sizes) if sizes else ico.size
        best = ico.copy()
        best.size = biggest
    except Exception:
        best = ico.copy()
    best = best.convert("RGBA")
    os.makedirs(dst_dir, exist_ok=True)
    for name, w, h in LOGOS:
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        # 铺满：不再乘系数。见 LOGOS 上方注释。
        scale = min(w / best.size[0], h / best.size[1])
        nw, nh = max(1, int(best.size[0] * scale)), max(1, int(best.size[1] * scale))
        im = best.resize((nw, nh), Image.LANCZOS)
        canvas.paste(im, ((w - nw) // 2, (h - nh) // 2), im)
        canvas.save(os.path.join(dst_dir, name))


def make_file_type_icons(dst_dir):
    """派生文件类型图标（.md / .smd 在资源管理器里显示的那一枚）。

    直接从 ico 取对应尺寸的**原始档**，不缩放——ico 里 16/24/32 是单独
    画的点阵字形，缩放会糊。基名给 256 档，各 targetsize 给对应档。
    """
    from PIL import Image
    ico_path = os.path.join(SRC, "md-editor.ico")
    ico = Image.open(ico_path)
    have = sorted(ico.info.get("sizes") or {(256, 256)})
    have_px = sorted({s[0] for s in have}) or [256]
    os.makedirs(dst_dir, exist_ok=True)

    def pick(px):
        cand = [s for s in have_px if s >= px]
        return cand[0] if cand else have_px[-1]

    written = 0
    for px in FILE_TYPE_ICON_SIZES:
        real = pick(px)
        try:
            # IcoImageFile.getimage 直接解出该档原始位图，不经过缩放
            im = ico.ico.getimage((real, real)).convert("RGBA")
        except Exception:
            probe = Image.open(ico_path)
            probe.size = (real, real)
            im = probe.convert("RGBA")
        if im.size != (px, px):
            im = im.resize((px, px), Image.LANCZOS)
        name = ("%s.png" % FILE_TYPE_ICON) if px == 256 else \
               ("%s.targetsize-%d.png" % (FILE_TYPE_ICON, px))
        im.save(os.path.join(dst_dir, name))
        written += 1
    return written


def _clear_win_attrs(root):
    """把整个目录树的 Windows 文件属性复位为普通（清掉 Hidden / ReadOnly）。

    makeappx 会**静默跳过带隐藏属性的文件**：元数据档案 `zero.json` 按设计带
    ReadOnly + Hidden，如果不复位，包里就没有它——exe 通道（zipfile 打包）不受
    影响，于是表现为「安装版有元数据、商城版没有」，且构建全程零报错。
    包内条目属性对部署无意义（安装位本身只读），复位不改变运行行为。
    """
    if os.name != "nt":
        return
    import ctypes
    FILE_ATTRIBUTE_NORMAL = 0x80
    for dp, dns, fns in os.walk(root):
        for name in fns + dns:
            try:
                ctypes.windll.kernel32.SetFileAttributesW(
                    os.path.join(dp, name), FILE_ATTRIBUTE_NORMAL)
            except Exception:
                pass


def stage_msix(ver):
    sys.path.insert(0, HERE)
    import _build_installer
    _build_installer.make_staging(ver)          # 复用安装包的同一份 staging
    src_stage = _build_installer.STAGING
    dst = os.path.join(SRC, "_setup_msix_stage")
    if os.path.isdir(dst):
        # 上一轮留下的元数据档案是只读的：rmtree 删不掉它，ignore_errors 又把
        # 失败吞了，随后 copy2 覆盖同一个 zero.json 直接 PermissionError。
        # 先递归解位再删，构建目录本来就不需要只读位。
        for _dp, _dns, _fns in os.walk(dst):
            for _fn in _fns:
                try:
                    os.chmod(os.path.join(_dp, _fn), 0o666)
                except Exception:
                    pass
        shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    n = 0
    for root, dirs, files in os.walk(src_stage):
        rel = os.path.relpath(root, src_stage)
        if rel != "." and os.path.normpath(rel) in MSIX_EXCLUDE_DIRS:
            dirs[:] = []
            continue
        target = os.path.normpath(os.path.join(dst, rel)) if rel != "." else dst
        os.makedirs(target, exist_ok=True)
        for fn in files:
            if rel == "." and fn in MSIX_EXCLUDE:
                continue
            shutil.copy2(os.path.join(root, fn), os.path.join(target, fn))
            n += 1
    _clear_win_attrs(dst)          # 隐藏文件会被 makeappx 丢弃，见函数注释
    make_logos(os.path.join(dst, "assets"))
    n_fti = make_file_type_icons(os.path.join(dst, "assets"))
    print("msix staging: %d files + %d logos + %d file-type icons"
          % (n, len(LOGOS), n_fti))
    return dst


def find_tool(name):
    kit = os.path.join(os.environ.get("ProgramFiles(x86)",
                                      r"C:\Program Files (x86)"),
                       "Windows Kits", "10", "bin")
    if not os.path.isdir(kit):
        raise SystemExit("FAIL Windows SDK not found: %s" % kit)
    vers = sorted((d for d in os.listdir(kit) if d[0].isdigit()), reverse=True)
    for v in vers:
        p = os.path.join(kit, v, "x64", name)
        if os.path.exists(p):
            return p
    raise SystemExit("FAIL %s not found in Windows SDK" % name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--publisher")
    ap.add_argument("--display-name")
    ap.add_argument("--publisher-display")
    args = ap.parse_args()

    ident = load_identity()
    name = args.name or ident.get("name") or "MDEditorPlaceholder"
    publisher = args.publisher or ident.get("publisher") or "CN=MDEditorPlaceholder"
    display = args.display_name or ident.get("display_name") or "MDEditor"
    pub_disp = (args.publisher_display or ident.get("publisher_display") or "wUwproject")
    if (args.name or args.publisher) is None and name.endswith("Placeholder"):
        print("[WARN] placeholder identity in use -- 商城上传前必须替换为"
              "合作伙伴中心保留的 Name/Publisher（installer/_msix_identity.json）")

    ver = detect_version()
    stage = stage_msix(ver)
    with open(os.path.join(stage, "AppxManifest.xml"), "w",
              encoding="utf-8", newline="\r\n") as f:
        f.write(MANIFEST_TEMPLATE.format(
            name=name, publisher=publisher, display_name=display,
            publisher_display=pub_disp, version="%s.0" % ver))

    os.makedirs(OUT, exist_ok=True)
    out_msix = os.path.join(OUT, "MDEditor-v%s-Store.msix" % ver)
    if os.path.exists(out_msix):
        os.remove(out_msix)
    makeappx = find_tool("makeappx.exe")
    r = subprocess.run([makeappx, "pack", "/o", "/d", stage, "/p", out_msix],
                       capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace") + \
          (r.stderr or b"").decode("utf-8", "replace")
    if r.returncode != 0 or not os.path.exists(out_msix):
        print(out)
        raise SystemExit("FAIL makeappx pack")
    # 包内条目数必须等于 stage 文件数：makeappx 遇到隐藏文件是静默跳过，
    # 只报「pack 成功」。不做这条对账，「元数据档案没进包」只能靠人眼发现。
    import urllib.parse
    import zipfile
    stage_files = set()
    for dp, _dns, fns in os.walk(stage):
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), stage).replace(os.sep, "/")
            stage_files.add(rel)
    # makeappx 会把非 ASCII 名百分号编码，并自行加两个清单元数据；比对前先归一
    GENERATED = {"AppxBlockMap.xml", "[Content_Types].xml"}
    with zipfile.ZipFile(out_msix) as z:
        packed = {urllib.parse.unquote(x) for x in z.namelist()
                  if not x.endswith("/")} - GENERATED
    dropped = sorted(stage_files - packed)
    if dropped:
        raise SystemExit("FAIL 包内缺 %d 个 stage 文件（makeappx 丢弃隐藏文件？）: %s"
                         % (len(dropped), dropped[:5]))
    print("pack check: %d stage files all packaged" % len(stage_files))
    print("PACK OK: %s (%d KB)" % (out_msix, os.path.getsize(out_msix) // 1024))
    print("identity: Name=%s Publisher=%s" % (name, publisher))
    print("next: 未签名包直接上传合作伙伴中心；本地侧载测试运行 _sign_msix.cmd")


if __name__ == "__main__":
    main()
