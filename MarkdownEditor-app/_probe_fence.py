# -*- coding: utf-8 -*-
"""自动化写围栏四项实测（端口 18767 隔离实例）。PASS/FAIL 输出。"""
import json, os, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18767"
HERE = os.path.dirname(os.path.abspath(__file__))  # 项目根（本脚本在项目根）
DOCS = os.path.join(HERE, "docs")
TMP = os.path.join(HERE, "Temp")
T_DOC = os.path.join(DOCS, "_fence_probe_tmp.md")
T_OK = os.path.join(TMP, "_fence_probe_ok.md")
R = []

def chk(name, ok, detail=""):
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("  | " + str(detail)[:120] if detail else ""))

def api(path, obj, auto=False):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "X-MD-Automation": "1" if auto else "0"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8")), e.code

for f in (T_DOC, T_OK):
    if os.path.exists(f):
        os.remove(f)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(BASE + "/")
    pg.wait_for_timeout(2500)
    wd = pg.evaluate("navigator.webdriver === true")
    chk("T0 Playwright 页 navigator.webdriver=true", wd is True)
    hdr = pg.evaluate("""async () => {
      const r = await fetch('/api/ping', {cache:'no-store'});
      return 'ok';
    }""")
    # T1 自动化浏览器内 POST /api/file 写 docs/ → 必须被围栏拦下
    res = pg.evaluate("""async (p) => {
      const r = await fetch('/api/file', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({path: p, content: 'fence probe'})});
      return {code: r.status, body: await r.json()};
    }""", T_DOC)
    chk("T1 浏览器(自动化)写 docs/ 被拦", res["code"] != 200 and
        "自动化" in json.dumps(res["body"], ensure_ascii=False), res)
    # T2 自动化浏览器内写 Temp/ → 放行
    res2 = pg.evaluate("""async (p) => {
      const r = await fetch('/api/file', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({path: p, content: 'fence probe ok'})});
      return {code: r.status, body: await r.json()};
    }""", T_OK)
    chk("T2 浏览器(自动化)写 Temp/ 放行", res2["code"] == 200 and res2["body"].get("ok") is True, res2)
    # T2b save-as 同闸
    res3 = pg.evaluate("""async (d) => {
      const r = await fetch('/api/save-as', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({dir: d, name: '_fence_probe_saveas.md', content: 'x'})});
      return {code: r.status, body: await r.json()};
    }""", DOCS)
    chk("T2b 浏览器(自动化) save-as 写 docs/ 被拦", res3["code"] != 200 and
        "自动化" in json.dumps(res3["body"], ensure_ascii=False), res3)
    b.close()

# T3 非自动化（无 X-MD-Automation:1 头，模拟真人）写 docs/ → 放行（真实用户不受影响）
body, code = api("/api/file", {"path": T_DOC, "content": "real user save"}, auto=False)
chk("T3 真人(无头)写 docs/ 放行", code == 200 and body.get("ok") is True, (code, body))
chk("T3b 文件确实落盘", os.path.exists(T_DOC))

# T4 兜底：带自动化头直连（非浏览器）同样被拦 —— 闸在服务端，不依赖浏览器
body4, code4 = api("/api/file", {"path": T_DOC, "content": "auto"}, auto=True)
chk("T4 直连带自动化头写 docs/ 被拦", code4 != 200 and "自动化" in body4.get("error", ""), (code4, body4))

# 清理探针产物
for f in (T_DOC, T_OK, T_DOC + ".assets"):
    if os.path.exists(f):
        os.remove(f)
print("-" * 40)
print("TOTAL: %d/%d PASS" % (sum(R), len(R)))
