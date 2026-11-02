# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""独立"打开文件"对话框进程（纯 ctypes 调 comdlg32.GetOpenFileNameW）。

便携 Python 是嵌入式版、没有 tkinter，因此必须走原生 Win32 API。
用法: python _pickfile.py <输出文件> [初始目录]
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


# OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER | OFN_NOCHANGEDIR
# | OFN_HIDEREADONLY | OFN_LONGNAMES
FLAGS = 0x00001000 | 0x00000800 | 0x00080000 | 0x00000008 | 0x00000004 | 0x00200000


def pick_file(init_dir="", mode=""):
    comdlg32 = ctypes.windll.comdlg32
    user32 = ctypes.windll.user32
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)   # STA
    except Exception:
        pass
    try:
        buf = ctypes.create_unicode_buffer(32768)
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        # 以"当前前台窗口"为主人：对话框会随浏览器窗口置前，不再被压在下面
        try:
            ofn.hwndOwner = user32.GetForegroundWindow()
        except Exception:
            ofn.hwndOwner = None
        # mode=template：只挑母版（导入母版库用），标题与过滤都收窄；
        # 其余走原来的 Markdown 口径，只是把 .smdm 一并列进首项。
        if mode == "template":
            ofn.lpstrFilter = ("母版 (*.smdm;*.smd)\0*.smdm;*.smd\0"
                               "所有文件 (*.*)\0*.*\0\0")
            ofn.lpstrTitle = "选择要导入的母版"
            ofn.lpstrDefExt = "smdm"
        else:
            ofn.lpstrFilter = ("Markdown (*.md;*.smd;*.smdm)\0*.md;*.smd;*.smdm\0"
                               "Markdown (*.md)\0*.md\0"
                               "自包含文档 (*.smd;*.smdm)\0*.smd;*.smdm\0"
                               "文本文件 (*.txt)\0*.txt\0"
                               "所有文件 (*.*)\0*.*\0\0")
            ofn.lpstrTitle = "打开 Markdown 文档"
            ofn.lpstrDefExt = "md"
        ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
        ofn.nMaxFile = 32768
        ofn.lpstrInitialDir = init_dir or None
        ofn.Flags = FLAGS
        comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
        comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
        if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return ""
        return buf.value
    finally:
        try:
            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            pass


try:
    init = sys.argv[2] if len(sys.argv) > 2 else ""
    mode = sys.argv[3] if len(sys.argv) > 3 else ""
    result = pick_file(init, mode)
except Exception:
    result = ""
try:
    io.open(sys.argv[1], "w", encoding="utf-8").write(result or "")
except Exception:
    pass
