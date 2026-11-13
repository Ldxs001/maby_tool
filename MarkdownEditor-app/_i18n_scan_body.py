"""英文态全页残留中文扫描（排除编辑器/预览/大纲/手册 iframe 等文档内容区）。

用法：python _i18n_scan_body.py [port]
"""
import json
import sys
from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "18799"
URL = "http://127.0.0.1:%s/" % PORT

SCAN = r"""
() => {
  const CJK = /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/;
  const skip = ["#editor", "#preview", "#outline", "#hbFrame", "#recent", "#fmtMenu",
                "#rmenu", "#openMoreMenu", "#newMoreMenu", "#exportMenu", "#printMenu"];
  const out = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
  let n;
  while ((n = walker.nextNode())) {
    const t = (n.nodeValue || "").trim();
    if (!t || t.length < 2 || !CJK.test(t)) continue;
    const p = n.parentElement;
    if (!p) continue;
    if (p.closest("script,style,textarea,#editor,#preview,#outline,#hbFrame")) continue;
    let blocked = false;
    for (const s of skip) { const r = document.querySelector(s); if (r && r.contains(p)) { blocked = true; break; } }
    if (blocked) continue;
    let chain = [];
    let e = p;
    for (let i = 0; i < 3 && e; i++) { chain.unshift(e.tagName.toLowerCase() + (e.id ? "#" + e.id : "")); e = e.parentElement; }
    const key = chain.join(">") + "|" + t;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({path: chain.join(">"), text: t.slice(0, 100), hidden: !p.offsetParent});
  }
  return out;
}
"""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg.goto(URL, wait_until="networkidle")
        pg.wait_for_timeout(1500)
        pg.evaluate("() => { try { applyLang('en'); } catch(e) {} }")
        for fn in ["aboutOpen", "tsOpen", "lrOpen", "llmOpen", "tbOpen", "linkOpen", "imgOpen", "eqOpen"]:
            pg.evaluate("(fn) => { try { const f = window[fn]; if (typeof f === 'function') f(); } catch(e) {} }", fn)
            pg.wait_for_timeout(500)
        res = pg.evaluate(SCAN)
        b.close()
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
