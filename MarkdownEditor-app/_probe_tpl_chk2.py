# -*- coding: utf-8 -*-
"""母版勾选实测 v2：用带 typeset 的新母版全路径验证。"""
import json, os, time, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18767"
HERE = os.path.dirname(os.path.abspath(__file__))
TPLDIR = os.path.join(HERE, "runtime", "templates")
LOCK = os.path.join(HERE, "Temp", "_md_test_lock.json")
NEW_TPL = "_probe_tpl.smdm"
R = []
def chk(name, ok, detail=""):
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("  | " + str(detail)[:140] if detail else ""))

def api(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "X-MD-Automation": "1"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))

# 0) 老母版确认：包里没有 typeset
j = api("/api/template/new", {"name": "MDEditor 使用指南"})
chk("D0 老母版无 typeset（兼容分支）", not j.get("typeset"), j.get("typeset"))

# 1) 测试锁放行 runtime/templates，造一个带 typeset 的新母版
os.makedirs(TPLDIR, exist_ok=True)
with open(LOCK, "w", encoding="utf-8") as f:
    json.dump({"allow_dirs": [TPLDIR]}, f)
try:
    tgt = os.path.join(TPLDIR, NEW_TPL)
    if os.path.exists(tgt):
        os.remove(tgt)
    pg_fetch = None  # 由浏览器内 fetch 发起（自动化头由 wrapper 附加）
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.goto(BASE + "/"); pg.wait_for_timeout(2800)

        def tskey():
            return pg.evaluate("localStorage.getItem('md-editor-typeset-v3')")

        def toast_last():
            return pg.evaluate("""() => {
              const t = document.querySelectorAll('#mdToast .md-toast');
              return t.length ? t[t.length-1].textContent : '';
            }""")

        def open_menu():
            pg.click("#btnNewMore"); pg.wait_for_timeout(350)

        def click_tpl(name):
            pg.click('#newMoreMenu button[data-tpl="' + name + '"]'); pg.wait_for_timeout(900)

        r1 = pg.evaluate("""async () => {
          const r = await fetch('/api/save-as', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({dir: %r, name: %r,
              content: '# 探针母版\\n\\n正文一行。\\n'})});
          return await r.json();
        }""" % (TPLDIR, NEW_TPL))
        chk("D1 测试锁放行：自动化创建母版包", r1.get("ok") is True, r1)
        r2 = pg.evaluate("""async () => {
          const r = await fetch('/api/template/typeset', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({path: %r,
              typeset: {v:1, page:{mt:37, mr:18, mb:25, ml:18}}})});
          return await r.json();
        }""" % tgt)
        chk("D2 母版写入 typeset（mt=37）", r2.get("ok") is True, r2)
        j2 = api("/api/template/new", {"name": NEW_TPL.replace(".smdm", "")})
        chk("D3 新母版带 typeset 且 mt=37",
            bool(j2.get("typeset")) and j2["typeset"].get("page", {}).get("mt") == 37,
            j2.get("typeset"))

        # 场景一：不勾 → 排版不动
        pg.reload(); pg.wait_for_timeout(2800)
        t0 = tskey()
        mt0 = json.loads(t0)["page"]["mt"]
        open_menu(); pg.click("#tplTsOn"); pg.wait_for_timeout(150)
        click_tpl("_probe_tpl")
        t1 = tskey()
        chk("D4 不勾=mt 不变（%s）" % mt0, json.loads(t1)["page"]["mt"] == mt0)
        chk("D5 toast（只取文本）", "只取文本" in toast_last(), toast_last())

        # 场景二：勾上 → 母版排版套用（mt 25→37）
        open_menu(); pg.click("#tplTsOn"); pg.wait_for_timeout(150)
        click_tpl("_probe_tpl")
        t2 = tskey()
        chk("D6 勾上=母版排版套用（mt=37）", json.loads(t2)["page"]["mt"] == 37,
            json.loads(t2)["page"]["mt"])
        chk("D7 toast（排版一并套用+可撤销）",
            "排版一并套用" in toast_last() and "撤销" in toast_last(), toast_last())

        # C9 复测：等 flush 再 reload
        open_menu(); pg.click("#tplTsOn"); pg.wait_for_timeout(900)
        chk("D8 偏好存 '0'", pg.evaluate("localStorage.getItem('md-tpl-ts-on')") == "0")
        pg.reload(); pg.wait_for_timeout(2800)
        open_menu()
        chk("D9 重开页面勾选保持（不勾）",
            pg.evaluate("document.getElementById('tplTsOn').checked") is False)
        pg.click("#tplTsOn"); pg.wait_for_timeout(900)   # 还原默认勾上
        chk("D10 还原默认勾上",
            pg.evaluate("localStorage.getItem('md-tpl-ts-on')") == "1")
        b.close()
finally:
    # 清理：探针母版 + 测试锁
    tgt = os.path.join(TPLDIR, NEW_TPL)
    if os.path.exists(tgt):
        os.remove(tgt)
    if os.path.exists(LOCK):
        os.remove(LOCK)

print("-" * 40)
print("TOTAL: %d/%d PASS" % (sum(R), len(R)))
