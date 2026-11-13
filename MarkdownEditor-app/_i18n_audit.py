"""英文态残留中文审计：逐个打开面板后扫 I18N_ROOTS，列出未翻译项。

只读脚本，不改产品代码。用法：python _i18n_audit.py [port]
"""
import json
import sys
from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "18799"
URL = "http://127.0.0.1:%s/" % PORT

SCAN = r"""
() => {
  const CJK = /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/;
  const roots = (window.I18N_ROOTS || []).slice();
  const out = {texts: [], attrs: [], missing: []};
  const seen = new Set();
  for (const sel of roots) {
    const root = document.querySelector(sel);
    if (!root) { out.missing.push(sel); continue; }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = walker.nextNode())) {
      const t = (n.nodeValue || "").trim();
      if (!t || !CJK.test(t)) continue;
      const p = n.parentElement;
      if (p && (p.tagName === "SCRIPT" || p.tagName === "STYLE")) continue;
      const key = sel + "|" + t;
      if (seen.has(key)) continue;
      seen.add(key);
      out.texts.push({root: sel, tag: p ? p.tagName.toLowerCase() : "?",
                      id: p ? (p.id || "") : "", cls: p ? String(p.className) : "",
                      text: t});
    }
    for (const el of root.querySelectorAll("*")) {
      for (const a of ["title", "placeholder", "aria-label", "alt"]) {
        const v = el.getAttribute(a);
        if (!v || !CJK.test(v)) continue;
        const key = sel + "|@" + a + "|" + v;
        if (seen.has(key)) continue;
        seen.add(key);
        out.attrs.push({root: sel, attr: a, id: el.id || "", tag: el.tagName.toLowerCase(),
                        text: v});
      }
    }
  }
  return out;
}
"""

OPENERS = ["aboutOpen", "tsOpen", "lrOpen", "llmOpen", "hbOpen", "tbOpen",
           "linkOpen", "imgOpen", "eqOpen"]


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        pg.goto(URL, wait_until="networkidle")
        pg.wait_for_timeout(1500)
        pg.evaluate("() => { try { applyLang('en'); } catch(e) {} }")
        pg.wait_for_timeout(300)
        agg = {"texts": {}, "attrs": {}, "missing": set()}

        def scan():
            res = pg.evaluate(SCAN)
            for x in res["texts"]:
                agg["texts"][(x["root"], x["text"])] = x
            for x in res["attrs"]:
                agg["attrs"][(x["root"], x["attr"], x["text"])] = x
            agg["missing"].update(res["missing"])

        # 关于与快捷键面板要走真按钮：快捷键表是渲染时逐行生成的，直接扫静态 DOM 看不到
        pg.click("#btnConfig")
        pg.wait_for_timeout(900)
        scan()
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(200)
        for fn in OPENERS:
            pg.evaluate(
                "(fn) => { try { const f = window[fn] || eval(fn); if (typeof f === 'function') f(); } catch(e) {} }",
                fn,
            )
            pg.wait_for_timeout(700)
            scan()
        b.close()
    out = {
        "texts": list(agg["texts"].values()),
        "attrs": list(agg["attrs"].values()),
        "missing": sorted(agg["missing"]),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
