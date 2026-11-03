# -*- coding: utf-8 -*-
"""v2.33.0 判据（四）：注册表 → 字体文件 → name 表，能否确定性拿到
(family, subfamily, usWeightClass, italic)。

这是「字重真实可用」的根：不靠词表猜后缀，直接读字体本身。
"""
import os
import re
import sys
import time
import winreg

def font_files():
    """注册表 → [(注册名, 文件绝对路径)]。"""
    out = []
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            k = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, val, _ = winreg.EnumValue(k, i)
                i += 1
            except OSError:
                break
            name = re.sub(r"\s*\((TrueType|OpenType|PostScript)\)$", "", name, flags=re.I)
            if not isinstance(val, str) or not val:
                continue
            p = val if os.path.isabs(val) else os.path.join(windir, "Fonts", val)
            out.append((name, p))
        winreg.CloseKey(k)
    return out


def read_faces(path):
    """返回该文件里所有 face 的 (family, subfamily, full, weight, italic)。"""
    from fontTools.ttLib import TTFont, TTCollection
    faces = []
    try:
        if path.lower().endswith((".ttc", ".otc")):
            coll = TTCollection(path, lazy=True)
            fonts = list(coll.fonts)
        else:
            fonts = [TTFont(path, lazy=True, fontNumber=0)]
    except Exception as e:
        return [], "open-fail:%s" % e
    for f in fonts:
        try:
            names = {}
            for rec in f["name"].names:
                if rec.platformID == 3 and rec.langID in (0x409, 0x804):
                    try:
                        names[(rec.nameID, rec.langID)] = rec.toUnicode()
                    except Exception:
                        pass
            pick = lambda nid: names.get((nid, 0x409)) or names.get((nid, 0x804))
            fam16, sub17 = pick(16), pick(17)
            fam1, sub2 = pick(1), pick(2)
            full = pick(4)
            wt = 400
            try:
                wt = int(f["OS/2"].usWeightClass)
            except Exception:
                pass
            it = False
            try:
                it = bool(f["head"].macStyle & 0x02)
            except Exception:
                pass
            if not it and sub2:
                it = "italic" in sub2.lower() or "oblique" in sub2.lower()
            faces.append({
                "fam16": fam16, "sub17": sub17, "fam1": fam1, "sub2": sub2,
                "full": full, "w": wt, "i": it,
            })
        except Exception as e:
            faces.append({"err": str(e)})
    return faces, ""


t0 = time.time()
items = font_files()
print("注册表字体项:", len(items), "条")
print("枚举耗时: %.2fs" % (time.time() - t0))

WANT = ["Microsoft YaHei", "Microsoft YaHei Light", "Microsoft YaHei Bold",
        "Arial", "Arial Bold", "Arial Black", "SimSun & NSimSun", "SimSun",
        "KaiTi", "FangSong", "Segoe UI", "Segoe UI Light", "Segoe UI Semibold",
        "Times New Roman", "Times New Roman Bold Italic"]

t0 = time.time()
seen = 0
for nm, p in items:
    if nm not in WANT:
        continue
    seen += 1
    faces, err = read_faces(p)
    print("\n[注册名] %s\n  文件: %s  %s" % (nm, os.path.basename(p), err))
    for fa in faces[:4]:
        if "err" in fa:
            print("    !!", fa["err"])
            continue
        print("    fam16=%-28s sub17=%-16s w=%-4s i=%s"
              % (fa["fam16"] or "-", fa["sub17"] or "-", fa["w"], fa["i"]))
        print("    fam1 =%-28s sub2 =%-16s full=%s"
              % (fa["fam1"] or "-", fa["sub2"] or "-", fa["full"] or "-"))
print("\n匹配到 %d 项，读表耗时 %.2fs" % (seen, time.time() - t0))

# 全量耗时估算（只读 name+OS/2+head，lazy）
t0 = time.time()
n = 0
for nm, p in items[:120]:
    read_faces(p)
    n += 1
print("抽样 %d 项耗时 %.2fs → 全量估 %.1fs" % (n, time.time() - t0, (time.time() - t0) / n * len(items)))
