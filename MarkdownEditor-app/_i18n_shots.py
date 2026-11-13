"""英文态取证截图：工具栏、配置▾、关于、排版引用样式、插图/链接/公式、分页栏、选中文具条。

用法：python _i18n_shots.py [port]
输出：_shots_i18n/*.png
"""
import os
import sys
from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "18799"
URL = "http://127.0.0.1:%s/" % PORT
OUT = "_shots_i18n"
os.makedirs(OUT, exist_ok=True)


def show(pg, oid):
    pg.evaluate(
        "(id) => { const e = document.getElementById(id); if (e) e.hidden = false; }", oid
    )


def hide(pg, oid):
    pg.evaluate(
        "(id) => { const e = document.getElementById(id); if (e) e.hidden = true; }", oid
    )


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1600, "height": 1000})
    pg = ctx.new_page()
    pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_timeout(1500)
    pg.evaluate("() => { applyLang('en'); }")
    pg.wait_for_timeout(500)
    pg.screenshot(path=OUT + "/01_toolbar_en.png",
                  clip={"x": 0, "y": 0, "width": 1600, "height": 220})

    pg.click("#btnConfigMore")
    pg.wait_for_timeout(300)
    pg.screenshot(path=OUT + "/02_cfg_menu_en.png",
                  clip={"x": 900, "y": 0, "width": 700, "height": 300})
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(200)

    pg.click("#btnConfig")
    pg.wait_for_timeout(900)
    pg.screenshot(path=OUT + "/03_about_en.png")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)

    pg.click("#btnConfigMore")
    pg.wait_for_timeout(250)
    pg.click('#rmenu button[data-ri="1"]')
    pg.wait_for_timeout(900)
    pg.evaluate("""() => {
        const rows = [...document.querySelectorAll('#tsOverlay .ts-row')];
        const hit = rows.find(r => (r.textContent || '').includes('Quote style'));
        if (hit) hit.scrollIntoView({block: 'center'});
    }""")
    pg.wait_for_timeout(300)
    pg.screenshot(path=OUT + "/04_ts_quote_en.png")
    hide(pg, "tsOverlay")

    show(pg, "linkOverlay")
    pg.wait_for_timeout(250)
    pg.screenshot(path=OUT + "/05_link_en.png",
                  clip={"x": 400, "y": 250, "width": 800, "height": 420})
    hide(pg, "linkOverlay")

    show(pg, "imgOverlay")
    pg.wait_for_timeout(250)
    pg.screenshot(path=OUT + "/06_img_en.png",
                  clip={"x": 350, "y": 200, "width": 900, "height": 520})
    hide(pg, "imgOverlay")

    pg.click("#btnMath")
    pg.wait_for_timeout(1000)
    pg.screenshot(path=OUT + "/07_eq_en.png")
    pg.keyboard.press("Escape")

    show(pg, "ppOverlay")
    pg.wait_for_timeout(300)
    pg.screenshot(path=OUT + "/08_pp_en.png",
                  clip={"x": 0, "y": 0, "width": 1600, "height": 190})
    hide(pg, "ppOverlay")

    pg.evaluate("""() => {
        const t = document.getElementById('selTools');
        t.hidden = false;
        t.style.left = '300px'; t.style.top = '420px';
    }""")
    pg.wait_for_timeout(250)
    pg.screenshot(path=OUT + "/09_seltools_en.png",
                  clip={"x": 260, "y": 380, "width": 420, "height": 110})

    pg.click("#btnConfigMore")
    pg.wait_for_timeout(250)
    pg.click('#rmenu button[data-ri="2"]')
    pg.wait_for_timeout(1200)
    pg.screenshot(path=OUT + "/11_lr_en.png")
    hide(pg, "lrOverlay")

    pg.click("#btnConfigMore")
    pg.wait_for_timeout(250)
    pg.click('#rmenu button[data-ri="3"]')
    pg.wait_for_timeout(1200)
    pg.screenshot(path=OUT + "/12_llm_en.png")
    hide(pg, "llmOverlay")

    pg.evaluate("() => applyLang('zh')")
    pg.wait_for_timeout(500)
    pg.screenshot(path=OUT + "/10_back_zh.png",
                  clip={"x": 0, "y": 0, "width": 1600, "height": 220})
    b.close()
print("ok")
