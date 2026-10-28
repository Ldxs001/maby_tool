# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwProject. Licensed under GNU AGPL v3 (or later).
"""v2.14.0 关态零影响对拍：v2.13.5(718f90c) vs 当前，同文档同设置。

只比两件后端拿到的输入——`#ts-style` 文本与 `#preview` 的 innerHTML。
两者逐字节相同，即可断言「开关关闭时导出/打印的样式与正文完全不变」。
（主 CSS 里 li.task 少了 margin-left:-1.4em 是有意修复，不在本对拍范围，
 由 _test_v2140_hang.py 的 task 几何断言覆盖。）

排版设置走真实 UI 操作：localStorage 里那份启动时会被服务端 ui-settings
覆盖，直接注入 LS 是无效验证（踩过）。脚本会备份并还原 ui-settings.json。

用法：python _test_v2140_parity.py <旧版html路径> [被测md路径]
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18766
NO_WINDOW = 0x08000000
HTML = os.path.join(HERE, "markdown-editor.html")
UI_SETTINGS = os.path.join(HERE, "runtime", "ui-settings.json")

DOC = """# 对拍文档

正文首行缩进两字符，用来确认段落缩进链没有被列表改动波及。

1. 有序第一项
2. 有序第二项
   续行文字不换段

- 实心点
- [ ] 待办项
- [x] 已办项

1. 一级
   - 二级
     1. 三级
2. 一级回到二

<<<
引用块里的列表：
- 甲
- 乙
<<<

| 表头甲 | 表头乙 |
|---|---|
| 1 | 2 |

> 引用段落

```js
const a = 1;   // 代码块
```

行内公式 $a^2+b^2=c^2$ 与分隔线：

---
"""

SET_TS = """()=>{
  document.getElementById('btnTypeset').click();
  var q=function(s){return document.querySelector(s);};
  q('input[data-tssz="p"]').value='14';
  q('select[data-algn="p"]').value='justify';
  q('select[data-ind="p"]').value='first';
  q('input[data-indchars="p"]').value='2';
  q('select[data-ind="li"]').value='block';
  q('input[data-indchars="li"]').value='2';
  q('select[data-ind="quote"]').value='block';
  q('input[data-indchars="quote"]').value='2';
  document.getElementById('tsGapOn').checked=true;
  document.getElementById('tsGapEm').value='0.85';
  document.getElementById('tsThree').checked=true;
  var h=document.getElementById('tsHangOn');
  if(h)h.checked=false;              /* 旧版无此开关；关态对拍要求关 */
  document.getElementById('tsApply').click();
}"""

fails = []


def check(name, cond, detail=""):
    print("%-52s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def kill_stale():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "($_.CommandLine -like '*md_server.py*' -or $_.CommandLine -like '*_md_run.py*') -and $_.Name -like "
         "'*python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId "
         "-Force }"],
        capture_output=True)


def alive():
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=0.3).read()
        return True
    except Exception:
        return False


def snapshot(doc):
    kill_stale()
    time.sleep(0.3)
    srv = subprocess.Popen(
        [os.path.join(HERE, "python", "python.exe"), "md_server.py"],
        creationflags=NO_WINDOW)
    t0 = time.time()
    while not alive() and time.time() - t0 < 20:
        time.sleep(0.1)
    assert alive(), "服务未就绪"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://127.0.0.1:%d/?file=" % PORT)
            pg.wait_for_timeout(900)
            pg.evaluate(SET_TS)
            pg.wait_for_timeout(500)
            pg.evaluate(
                "d=>{var ed=document.getElementById('editor');"
                "ed.textContent=d;"
                "ed.dispatchEvent(new Event('input',{bubbles:true}));}", doc)
            # 首行不一定是可检索文本（可能是 ---、<<< 或 frontmatter），
            # 改用「正文渲染量」判收敛
            pg.wait_for_function(
                "()=>{var pv=document.getElementById('preview');"
                "return pv&&pv.textContent.replace(/\\s/g,'').length>200;}",
                timeout=25000)
            pg.wait_for_timeout(900)
            r = pg.evaluate(
                "()=>({css:(document.getElementById('ts-style')||{}).textContent||'',"
                "body:document.getElementById('preview').innerHTML})")
            r["errs"] = errs
            b.close()
        return r
    finally:
        srv.terminate()
        try:
            srv.wait(3)
        except Exception:
            srv.kill()


def main():
    old = sys.argv[1] if len(sys.argv) > 1 else None
    if not old or not os.path.exists(old):
        print("用法: python _test_v2140_parity.py <旧版html路径> [被测md]")
        return 2
    doc = DOC
    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        with open(sys.argv[2], encoding="utf-8") as f:
            doc = f.read()
        print("被测文档：%s（%d 字符）" % (sys.argv[2], len(doc)))

    uiset_bak = None
    if os.path.exists(UI_SETTINGS):
        with open(UI_SETTINGS, "rb") as f:
            uiset_bak = f.read()
    bak = HTML + ".v2140.bak"
    shutil.copy2(HTML, bak)
    try:
        shutil.copy2(old, HTML)
        a = snapshot(doc)
        shutil.copy2(bak, HTML)
        b = snapshot(doc)
    finally:
        shutil.copy2(bak, HTML)
        os.remove(bak)
        if uiset_bak is not None:
            with open(UI_SETTINGS, "wb") as f:
                f.write(uiset_bak)

    check("旧版无 page errors", not a["errs"], "; ".join(a["errs"][:2]))
    check("新版无 page errors", not b["errs"], "; ".join(b["errs"][:2]))
    # 先确认这份 ts-style 真的带上了列表/段间距规则——否则「一致」是空验证
    for who, r in (("旧版", a), ("新版", b)):
        check("%s ts-style 含列表 inside 规则" % who,
              "list-style-position:inside" in r["css"])
        check("%s ts-style 含段间距 0.85em" % who, "0.85em" in r["css"])
        check("%s ts-style 含三线表规则" % who,
              "border-top:2px solid" in r["css"])
        check("%s ts-style 无外凸残留" % who, "--mde-mark-ol" not in r["css"])
    check("ts-style 逐字节一致", a["css"] == b["css"],
          "len %d vs %d" % (len(a["css"]), len(b["css"])))
    check("preview innerHTML 逐字节一致", a["body"] == b["body"],
          "len %d vs %d" % (len(a["body"]), len(b["body"])))
    if a["css"] != b["css"]:
        import difflib
        d = list(difflib.unified_diff(a["css"].split("}"),
                                      b["css"].split("}"),
                                      lineterm="", n=0))
        print("\n".join(d[:14]))
    if a["body"] != b["body"]:
        import difflib
        d = list(difflib.unified_diff(a["body"].splitlines(),
                                      b["body"].splitlines(),
                                      lineterm="", n=0))
        print("\n".join(d[:14]))

    print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
