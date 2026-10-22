# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""独立"另存为"对话框进程（纯 ctypes 调 comdlg32.GetSaveFileNameW）。

便携 Python 是嵌入式版、没有 tkinter，因此必须走原生 Win32 API。
用法: python _picksave.py <输出文件> <扩展名> [初始目录] [标题] [默认文件名]
取消时写入空串。
"""
import sys
import io
import ctypes
from ctypes import wintypes


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", ctypes.c_void_p),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
    ]


# OFN_OVERWRITEPROMPT | OFN_EXPLORER | OFN_NOCHANGEDIR
# 覆盖已存在文件前先询问；使用新样式对话框；不改变进程当前目录
FLAGS = 0x00000002 | 0x00080000 | 0x00000008


def pick_save(ext, init_dir="", title="", default_name=""):
    comdlg32 = ctypes.windll.comdlg32
    user32 = ctypes.windll.user32
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)   # STA
    except Exception:
        pass
    try:
        buf = ctypes.create_unicode_buffer(32768)
        if default_name:
            buf.value = default_name
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        # 以"当前前台窗口"为主人：对话框会随浏览器窗口置前，不再被压在下面
        try:
            ofn.hwndOwner = user32.GetForegroundWindow()
        except Exception:
            ofn.hwndOwner = None
        ext_l = (ext or "docx").lstrip(".").lower()
        ofn.lpstrFilter = ("%s 文档 (*.%s)\0*.%s\0所有文件 (*.*)\0*.*\0\0"
                           % (ext_l.upper(), ext_l, ext_l))
        ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
        ofn.nMaxFile = 32768
        ofn.lpstrTitle = title or ("导出为 .%s" % ext_l)
        ofn.lpstrInitialDir = init_dir or None
        ofn.Flags = FLAGS
        ofn.lpstrDefExt = ext_l
        comdlg32.GetSaveFileNameW.restype = wintypes.BOOL
        comdlg32.GetSaveFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
        if not comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
            return ""
        return buf.value
    finally:
        try:
            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            pass


try:
    out = sys.argv[1]
    ext = sys.argv[2] if len(sys.argv) > 2 else "docx"
    init_dir = sys.argv[3] if len(sys.argv) > 3 else ""
    title = sys.argv[4] if len(sys.argv) > 4 else ""
    default_name = sys.argv[5] if len(sys.argv) > 5 else ""
    result = pick_save(ext, init_dir, title, default_name)
except Exception:
    result = ""
try:
    io.open(out, "w", encoding="utf-8").write(result or "")
except Exception:
    pass
