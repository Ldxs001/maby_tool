# -*- coding: utf-8 -*-
"""v2.15.0 双语测试。

覆盖：
1  默认中文态：语言为 zh、工具栏中文标签在位、body[data-lang]=zh
2  切 EN：工具栏/状态栏/排版面板无中文残留（字体名与语言按钮除外）
3  切回 zh：工具栏/状态栏/预览 innerHTML 与切换前逐字节一致（可逆）
4  EN 下重开页面仍保持 EN（持久化）
5  题注前缀：EN 下 Figure/Table，zh 下「图/表」
6  打印产物：cfg.lang=zh 目录标题「目 录」；cfg.lang=en 为 Contents

端口说明：固定 18766 会被已安装的 MSIX 实例占住（它常驻监听），此时新起的
服务绑定失败、页面来自安装目录的旧 HTML，测试会「通过」却测的不是当前代码。
故本测试在 18799 起一个独立实例（临时启动器写入 runtime/，跑完删除）。

运行：cd MarkdownEditor-app && python _test_v2150_lang.py
"""
import io, json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18799
BASE = "http://127.0.0.1:%d" % PORT
RUNNER = os.path.join(HERE, "runtime", "_test_run_server.py")
fails = []
n = 0


def check(name, ok, detail=""):
    global n
    n += 1
    print(("  PASS " if ok else "  FAIL ") + name + ((" | " + str(detail)) if detail and not ok else ""))
    if not ok:
        fails.append(name)


def kill():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*_test_run_server*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)


def alive():
    try:
        urllib.request.urlopen(BASE + "/api/version", timeout=0.3).read()
        return True
    except Exception:
        return False


def post_paged(cfg, body_html):
    payload = json.dumps({"path": None, "bodyHtml": body_html,
                          "tsCss": "", "cfg": cfg}).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/export-paged", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


DOC = """# 题注测试

![示意图](none.png "测试图题"){40c}

@@ caption 测试表题
| 列1 | 列2 |
| --- | --- |
| 甲 | 乙 |

1. 第一项
2. 第二项
"""

RESET = ("()=>{['svOverlay','tsOverlay','lrOverlay','fmOverlay','llmOverlay',"
         "'annOverlay','rwOverlay','rpOverlay','findBar','selTools'].forEach(function(i){"
         "var e=document.getElementById(i); if(e) e.hidden=true;});}")

kill(); time.sleep(0.3)
# 独立端口的临时启动器（不改产品端口，也不与已安装实例抢 18766）
io.open(RUNNER, "w", encoding="utf-8", newline="\n").write(
    "import os, sys\n"
    "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
    "import md_server\n"
    "md_server.PORT = %d\n"
    "md_server.main()\n" % PORT)
srv = subprocess.Popen([os.path.join(HERE, "python", "python.exe"), RUNNER],
                       cwd=HERE, creationflags=0x08000000)
t0 = time.time()
while not alive() and time.time() - t0 < 25:
    time.sleep(0.1)
if not alive():
    print("服务未启动，测试中止")
    sys.exit(1)

from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 820})
        pg.goto(BASE + "/")
        pg.wait_for_timeout(900)
        pg.evaluate("""d=>{var ed=document.getElementById('editor');ed.textContent=d;
          ed.dispatchEvent(new Event('input',{bubbles:true}));}""", DOC)
        pg.wait_for_timeout(700)
        # 清掉可能的旧偏好，从中文开始；同时打开图表编号（题注前缀依赖它）
        pg.evaluate("""()=>{
          try{localStorage.setItem('md-editor-lang','zh');}catch(e){}
          try{
            var raw=JSON.parse(localStorage.getItem('md-editor-typeset-v3')||'{}');
            raw.ncap=Object.assign({}, raw.ncap||{}, {on:true, mode:'doc'});
            localStorage.setItem('md-editor-typeset-v3', JSON.stringify(raw));
          }catch(e){}
        }""")
        pg.reload(); pg.wait_for_timeout(1000)

        # 题注前缀只在「图表自动编号」开启时出现，经面板真实开关打开
        pg.click("#btnTypeset"); pg.wait_for_timeout(300)
        if not pg.is_checked("#tsCapNumOn"):
            pg.check("#tsCapNumOn")
        pg.click("#tsApply"); pg.wait_for_timeout(900)
        pg.evaluate(RESET)
        pg.wait_for_timeout(200)

        # reload 会重置编辑区，测试文档必须在重载之后注入
        pg.evaluate("""d=>{var ed=document.getElementById('editor');ed.textContent=d;
          ed.dispatchEvent(new Event('input',{bubbles:true}));}""", DOC)
        pg.wait_for_timeout(900)

        print("\n[1] 默认中文态")
        check("body[data-lang]=zh", pg.get_attribute("body", "data-lang") == "zh")
        tb = pg.inner_text("#toolbar")
        for w in ("排版", "保存", "另存为", "打印"):
            check("工具栏含「%s」" % w, w in tb)
        check("语言按钮显示 EN（可切到英文）", pg.inner_text("#btnLang").strip() == "EN")
        zh_html = pg.inner_html("#toolbar")
        zh_status = pg.inner_html("#status")
        zh_preview = pg.inner_html("#preview")

        print("\n[2] 切到 EN")
        pg.click("#btnLang"); pg.wait_for_timeout(400)
        check("body[data-lang]=en", pg.get_attribute("body", "data-lang") == "en")
        check("按钮变为「中」", pg.inner_text("#btnLang").strip() == "中")
        HAN = r"[\u4e00-\u9fff]"
        residue = pg.evaluate("""()=>{
          var han=/[\\u4e00-\\u9fff]/; var out=[];
          ['#toolbar','#status','#tsOverlay'].forEach(function(sel){
            var r=document.querySelector(sel); if(!r) return;
            var tw=document.createTreeWalker(r,NodeFilter.SHOW_TEXT,null), n2;
            while((n2=tw.nextNode())){
              var t=(n2.nodeValue||'').trim();
              if(!t||!han.test(t)) continue;
              var pe=n2.parentNode, skip=false;
              while(pe&&pe!==r){
                if(pe.tagName==='OPTGROUP'){skip=true;break;}
                if(pe.tagName==='SELECT'&&pe.hasAttribute('data-ts')){skip=true;break;}
                pe=pe.parentNode;
              }
              if(!skip&&t!=='中') out.push(sel+' :: '+t);
            }
          });
          return out;}""")
        check("工具栏/状态栏无中文残留（字体名除外）",
              all(("Chinese" in x) or ("Whole document" in x) or ("Per chapter" in x)
                  for x in residue), residue[:6])
        check("EN 下保存按钮显示 Save", "Save" in pg.inner_text("#toolbar"))
        check("EN 下语言按钮 title 已英文化",
              "Switch the interface language" in (pg.get_attribute("#btnLang", "title") or ""))

        print("\n[3] 打印与题注（EN）")
        ttl = pg.evaluate("""()=>{var s=[];document.querySelectorAll('#preview figcaption,#preview .mde-tabcap')
            .forEach(function(e){s.push(e.textContent.trim());});return s;}""")
        check("EN 题注以 Figure 开头", any(x.startswith("Figure") for x in ttl), ttl[:3])
        check("EN 表题以 Table 开头", any(x.startswith("Table") for x in ttl), ttl[:3])

        print("\n[4] 切回中文（可逆）")
        pg.click("#btnLang"); pg.wait_for_timeout(400)
        check("body[data-lang]=zh", pg.get_attribute("body", "data-lang") == "zh")
        check("工具栏 innerHTML 与切换前逐字节一致", pg.inner_html("#toolbar") == zh_html)
        check("状态栏 innerHTML 与切换前逐字节一致", pg.inner_html("#status") == zh_status)
        # 预览不在翻译范围内：切到 EN 再切回，正文 DOM 必须逐字节回到原样
        check("预览 innerHTML 与切换前逐字节一致（正文不受语言影响）",
              pg.inner_html("#preview") == zh_preview)
        ttl2 = pg.evaluate("""()=>{var s=[];document.querySelectorAll('#preview figcaption,#preview .mde-tabcap')
            .forEach(function(e){s.push(e.textContent.trim());});return s;}""")
        check("中文题注以「图」开头", any(x.startswith("图") for x in ttl2), ttl2[:3])

        print("\n[5] 持久化：切 EN 后重开仍是 EN")
        pg.click("#btnLang"); pg.wait_for_timeout(300)
        pg.reload(); pg.wait_for_timeout(900)
        check("重开后 body[data-lang]=en", pg.get_attribute("body", "data-lang") == "en")
        check("重开后按钮为「中」", pg.inner_text("#btnLang").strip() == "中")
        # 复位成中文，避免影响后续手工使用
        pg.click("#btnLang"); pg.wait_for_timeout(300)
        check("复位回 zh", pg.get_attribute("body", "data-lang") == "zh")
        b.close()

    print("\n[6] 打印产物标题随 cfg.lang")
    body = "<h1>章一</h1><h2>节一</h2><p>正文</p>"
    # 同一路径每次覆盖，故导出后立即读取
    got = {}
    for lang in ("zh", "en"):
        r = post_paged({"lang": lang, "toc": {"on": "on", "pos": "top", "solo": True}}, body)
        ok = r.get("ok") is True
        check("%s 打印成功" % lang, ok, r.get("error"))
        if ok:
            fn = r["url"].split("/")[-1].split("?")[0]
            got[lang] = io.open(os.path.join(HERE, "runtime", fn), encoding="utf-8").read()
        else:
            got[lang] = ""
    check("zh 产物目录标题为「目 录」", "目 录" in got.get("zh", ""))
    check("zh 产物不含英文目录标题", ">Contents<" not in got.get("zh", ""))
    check("en 产物目录标题为 Contents", ">Contents<" in got.get("en", ""))
    check("en 产物不含中文目录标题", "目 录" not in got.get("en", ""))
finally:
    srv.terminate()
    try:
        os.remove(RUNNER)
    except Exception:
        pass

print("\n%d 项，失败 %d" % (n, len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS")
