# -*- coding: utf-8 -*-
"""v2.41.0 V2（方案 §11）链接▾ 专项：菜单 / 网络图片 / 本地图片 / 本地文件 / 粘贴对拍。

判据（全部 PASS/FAIL，16 项）：
  L1  链接▾ 恰好三项（插入图片… / 插入本地文件… / 取消链接），无重复插入链接、无置灰占位
  L2  主按钮仍开链接弹窗并插入 [文字](地址)
  L3  网络图片合法地址产 ![说明](URL)，预览 <img src> 原样不被本地代理改写
  L4  非法协议 / 空地址拒绝插入，弹窗不关
  L5  图片弹窗 Esc 关闭后选区与滚动守恒
  L6  插入本地文件… → 数据点方言 + 文件真落进 <stem>.assets/ + 渲染区「打开」按钮
  L7  点「打开」按钮确实请求 /api/open-ref（拦截，不真调系统程序）
  L8  插入本地图片… → ![]() + 预览走 /img?path=
  L9  粘贴文件（DataTransfer）与菜单同形态对拍
  L10 粘贴图片与菜单同形态对拍
  L11 唯一实现守门：两个 paste 端点 fetch 各一处、服务端无 /file 新路由
  L12 长文档滚中段后走文件选择插入，编辑区/预览栏滚动守恒
  L13 全页静态 id 无重复，图片弹窗与导入面板两个按钮各就位
  L14 点「选择本地图片…」恰好 1 次文件选择框、/api/open-file 零请求
  L15 导入面板「浏览…」仍绑 imPickFile（路由拦截，不真弹系统框）
  L16 全程零 page error

跑法：python _test_v2410_link.py   （自起 18767 服务，跑完关服务并清测试目录）
"""
import base64
import io
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv = ["md_server.py"]
import md_server  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 18767
URL = "http://127.0.0.1:%d/" % PORT
TMP = os.path.join(HERE, "Temp", "_v2410_link_case")
DOC = os.path.join(TMP, "v2410link.md")
STEM = "v2410link"
ATT = os.path.join(TMP, "sample.txt")
IMG = os.path.join(TMP, "sample.png")
PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
           "//8/AwAI/AL+X6Z9WQAAAABJRU5ErkJggg==")

fails = []


def chk(name, ok, detail=""):
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("   [%s]" % detail) if detail else ""))
    if not ok:
        fails.append(name)


HELPERS = r"""() => {
  const ed=document.getElementById('editor');
  const pv=document.getElementById('previewPane');
  window.__ed=ed; window.__pv=pv;
  window.__setCaret=function(pos){
    let acc=0,node=null,off=0;
    const w=document.createTreeWalker(ed,NodeFilter.SHOW_TEXT); let n;
    while((n=w.nextNode())){ if(pos<=acc+n.nodeValue.length){node=n;off=pos-acc;break;} acc+=n.nodeValue.length; }
    if(!node){node=ed;off=0;}
    const r=document.createRange(); r.setStart(node,off); r.setEnd(node,off);
    ed.focus(); const s=getSelection(); s.removeAllRanges(); s.addRange(r);
  };
  window.__setDoc=function(t){
    ed.textContent=t; ed.dispatchEvent(new Event('input',{bubbles:true}));
  };
  window.__caret=function(){
    const s=getSelection();
    if(!s||!s.rangeCount) return -1;
    const r=s.getRangeAt(0);
    if(r.startContainer!==ed&&!ed.contains(r.startContainer)) return -2;
    const p=document.createRange(); p.setStart(ed,0);
    p.setEnd(r.startContainer,r.startOffset);
    return p.toString().length;
  };
  window.__state=function(){
    return {caret:window.__caret(), edTop:ed.scrollTop, pvTop:pv.scrollTop,
            len:ed.textContent.length, txt:ed.textContent};
  };
  window.__linkMenu=function(){
    const sp=[...document.querySelectorAll('#fmtBtns .tb-split')]
      .find(x=>{const b=x.querySelector('.tb-btn'); return b && b.textContent==='链接';});
    if(!sp) return null;
    sp.querySelector('.tb-caret').click();
    return [...document.querySelectorAll('#fmtMenu button')]
      .map(b=>({t:b.textContent,dis:b.disabled}));
  };
  window.__menuClick=function(prefix){
    const b=[...document.querySelectorAll('#fmtMenu button')]
      .find(x=>x.textContent.indexOf(prefix)===0);
    if(b){b.click();return true;}
    return false;
  };
  window.__pasteFile=function(name,mime,b64){
    const bin=atob(b64), arr=new Uint8Array(bin.length);
    for(let i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);
    const f=new File([arr],name,{type:mime});
    const dt=new DataTransfer(); dt.items.add(f);
    let ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});
    if(!ev.clipboardData) Object.defineProperty(ev,'clipboardData',{value:dt});
    ed.focus(); ed.dispatchEvent(ev);
  };
}"""

LONG = "\n".join(["第 %03d 行正文内容，用于把文档撑到需要滚动的高度。" % i
                  for i in range(1, 121)])


def text(pg):
    return pg.evaluate("() => document.getElementById('editor').textContent")


def reset(pg, doc, pos=None):
    pg.evaluate("(t)=>window.__setDoc(t)", doc)
    pg.wait_for_timeout(600)
    if pos is not None:
        pg.evaluate("(p)=>window.__setCaret(p)", pos)
    pg.wait_for_timeout(150)


def open_img(pg):
    pg.evaluate("() => window.__linkMenu()")
    pg.wait_for_timeout(120)
    pg.evaluate("() => window.__menuClick('插入图片')")


def main():
    if os.path.isdir(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP)
    with io.open(DOC, "w", encoding="utf-8") as f:
        f.write("# V2 链接测试\n\n占位段落。\n")
    with io.open(ATT, "w", encoding="utf-8") as f:
        f.write("attachment payload")
    with open(IMG, "wb") as f:
        f.write(base64.b64decode(PNG_B64))

    httpd = md_server.ReuseTCPServer(("127.0.0.1", PORT), md_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1360, "height": 860})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            reqs = []
            pg.on("request", lambda r: reqs.append(r.url))
            # 拦截「打开」请求，避免测试真的拉起系统关联程序
            pg.route("**/api/open-ref", lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"ok":true}'))
            # /api/open-file 会拉起服务端原生框：全程拦截，测试不弹系统对话框
            pg.route("**/api/open-file*", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body='{"ok":true,"path":""}'))

            pg.goto(URL + "?file=" + urllib.parse.quote(DOC, safe=""))
            # 只等页面就绪，不等特定正文：服务端 ui-settings 可能残留上一次异常
            # 退出留下的未落盘草稿（按路径隔离），恢复动作会覆盖 ?file= 载入的正文。
            pg.wait_for_function(
                "() => (document.getElementById('editor')||{textContent:''}).textContent.length>0",
                timeout=20000)
            pg.wait_for_timeout(900)
            pg.evaluate(HELPERS)
            reset(pg, "# V2 链接测试\n\n占位段落。\n", 0)  # 显式确定态，后续每例各自 reset

            # ---- L1 菜单结构 ----
            items = pg.evaluate("() => window.__linkMenu()") or []
            titles = [x["t"] for x in items]
            chk("L1 链接▾ 恰好三项且无重复/占位",
                len(items) == 3
                and any(t.startswith("插入图片") for t in titles)
                and any(t.startswith("插入本地文件") for t in titles)
                and any(t.startswith("取消链接") for t in titles)
                and not any("插入链接（窗口）" in t or "待 v2.42" in t or "v2.42" in t
                            for t in titles)
                and not any(x["dis"] for x in items),
                repr(titles))
            pg.evaluate("() => document.body.click()")

            # ---- L2 主按钮仍开链接弹窗 ----
            reset(pg, "前缀文字后缀", 4)
            pg.evaluate("""() => [...document.querySelectorAll('#fmtBtns .tb-split')]
              .find(x=>{const b=x.querySelector('.tb-btn');return b&&b.textContent==='链接';})
              .querySelector('.tb-btn').click()""")
            pg.wait_for_timeout(180)
            visible = pg.evaluate("() => !document.getElementById('linkOverlay').hidden")
            pg.fill("#lkText", "示例链接")
            pg.fill("#lkUrl", "https://example.dev")
            pg.evaluate("() => document.getElementById('lkGo').click()")
            pg.wait_for_timeout(400)
            chk("L2 主按钮开链接弹窗并插入",
                visible and "[示例链接](https://example.dev)" in text(pg),
                text(pg)[:80])

            # ---- L3 网络图片合法 ----
            reset(pg, "前文。", 3)
            open_img(pg)
            pg.wait_for_timeout(180)
            pg.fill("#imUrl", "https://example.dev/a.png")
            pg.fill("#imAlt", "示例图")
            pg.evaluate("() => document.getElementById('imGo').click()")
            pg.wait_for_timeout(700)
            src = pg.evaluate("""() => {const i=document.querySelector('#preview img');
                                      return i?i.getAttribute('src'):'';}""")
            chk("L3 网络图片产 ![说明](URL) 且预览 src 原样",
                "![示例图](https://example.dev/a.png)" in text(pg)
                and src == "https://example.dev/a.png",
                "txt=%r src=%r" % (text(pg)[:60], src))

            # ---- L4 非法协议 / 空地址 ----
            reset(pg, "前文。", 3)
            open_img(pg)
            pg.wait_for_timeout(150)
            pg.fill("#imUrl", "javascript:alert(1)")
            pg.evaluate("() => document.getElementById('imGo').click()")
            pg.wait_for_timeout(200)
            still = pg.evaluate("() => !document.getElementById('imgOverlay').hidden")
            no_ins = text(pg) == "前文。"
            pg.fill("#imUrl", "")
            pg.evaluate("() => document.getElementById('imGo').click()")
            pg.wait_for_timeout(200)
            chk("L4 非法协议与空地址均拒绝插入",
                still and no_ins and text(pg) == "前文。",
                repr(text(pg)[:60]))
            pg.evaluate("() => document.getElementById('imCancel').click()")

            # ---- L5 弹窗 Esc 关闭 + 滚动守恒 ----
            reset(pg, LONG, 1000)
            pg.evaluate("() => {window.__ed.scrollTop=1400; window.__pv.scrollTop=700;}")
            pg.wait_for_timeout(200)
            before = pg.evaluate("() => window.__state()")
            open_img(pg)
            pg.wait_for_timeout(150)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(500)
            after = pg.evaluate("() => window.__state()")
            chk("L5 图片弹窗 Esc 关闭后选区与滚动守恒",
                abs(before["edTop"] - after["edTop"]) <= 2
                and abs(before["pvTop"] - after["pvTop"]) <= 2
                and abs(before["caret"] - after["caret"]) <= 2,
                "before=%s after=%s" % (before["edTop"], after["edTop"]))

            # ---- L6 插入本地文件（菜单） ----
            reset(pg, "正文开头。", 5)
            with pg.expect_file_chooser(timeout=15000) as fc:
                pg.evaluate("() => window.__linkMenu()")
                pg.wait_for_timeout(120)
                pg.evaluate("() => window.__menuClick('插入本地文件')")
            fc.value.set_files(ATT)
            pg.wait_for_function(
                "() => document.getElementById('editor').textContent.indexOf('MDE_')>=0",
                timeout=15000)
            pg.wait_for_timeout(700)
            t6 = text(pg)
            asset = os.path.join(TMP, STEM + ".assets", "sample.txt")
            btn = pg.evaluate("""() => {const b=document.querySelector('#preview .mde-ref-open');
                                      return b?b.getAttribute('data-ref'):'';}""")
            chk("L6 菜单选文件 → 数据点 + 真实落盘 + 渲染区打开按钮",
                "@@ MDE_" in t6 and ".assets/sample.txt" in t6
                and t6.startswith("正文开头。")
                and os.path.isfile(asset)
                and io.open(asset, encoding="utf-8").read() == "attachment payload"
                and btn and btn.endswith(".assets/sample.txt"),
                "txt=%r btn=%r" % (t6[:110], btn))

            # ---- L7 打开按钮走 /api/open-ref ----
            n0 = len([u for u in reqs if "/api/open-ref" in u])
            pg.evaluate("""() => {const b=document.querySelector('#preview .mde-ref-open');
                                 if(b)b.click();}""")
            pg.wait_for_timeout(600)
            n1 = len([u for u in reqs if "/api/open-ref" in u])
            chk("L7 打开按钮确实请求 /api/open-ref", n1 > n0, "%d -> %d" % (n0, n1))

            # ---- L8 插入本地图片（菜单） ----
            reset(pg, "图片前文。", 5)
            open_img(pg)
            pg.wait_for_timeout(150)
            with pg.expect_file_chooser(timeout=15000) as fc2:
                pg.evaluate("() => document.getElementById('imPickImg').click()")
            fc2.value.set_files(IMG)
            pg.wait_for_function(
                "() => document.getElementById('editor').textContent.indexOf('![](')>=0",
                timeout=15000)
            pg.wait_for_timeout(800)
            t8 = text(pg)
            src8 = pg.evaluate("""() => {const i=document.querySelector('#preview img');
                                       return i?i.getAttribute('src'):'';}""")
            chk("L8 菜单选本地图片 → ![]() + 预览 /img?path=",
                "![](" + STEM + ".assets/" in t8 and t8.startswith("图片前文。")
                and src8.startswith("/img?path="),
                "txt=%r src=%r" % (t8[:100], src8[:90]))

            # ---- L9 粘贴文件对拍 ----
            reset(pg, "粘贴文件。", 5)
            pg.evaluate("(a)=>window.__pasteFile(a[0],a[1],a[2])",
                        ["paste.txt", "text/plain",
                         base64.b64encode(b"attachment payload").decode()])
            pg.wait_for_function(
                "() => document.getElementById('editor').textContent.indexOf('paste.txt')>=0",
                timeout=15000)
            pg.wait_for_timeout(500)
            t9 = text(pg)
            btn9 = pg.evaluate("""() => !!document.querySelector('#preview .mde-ref-open')""")
            chk("L9 粘贴文件与菜单同形态（数据点 + 打开按钮）",
                "@@ MDE_" in t9 and ".assets/paste.txt" in t9 and btn9,
                t9[:110])

            # ---- L10 粘贴图片对拍 ----
            reset(pg, "粘贴图片。", 5)
            pg.evaluate("(a)=>window.__pasteFile(a[0],a[1],a[2])",
                        ["paste.png", "image/png", PNG_B64])
            pg.wait_for_function(
                "() => document.getElementById('editor').textContent.indexOf('![](')>=0",
                timeout=15000)
            pg.wait_for_timeout(500)
            t10 = text(pg)
            chk("L10 粘贴图片与菜单同形态（![]()）",
                "![](" + STEM + ".assets/" in t10 and t10.startswith("粘贴图片。"),
                t10[:100])

            # ---- L11 唯一实现守门 ----
            html = io.open(os.path.join(HERE, "markdown-editor.html"),
                           encoding="utf-8").read()
            srv = io.open(os.path.join(HERE, "md_server.py"),
                          encoding="utf-8").read()
            chk("L11 两个 paste 端点各一处、服务端无 /file 新路由",
                html.count("fetch('/api/paste-image'") == 1
                and html.count("fetch('/api/paste-file'") == 1
                and html.count("function pasteImageFile(") == 1
                and html.count("function pasteAttachFile(") == 1
                and 'u.path == "/file"' not in srv
                and 'GET /file?path=' not in srv)

            # ---- L12 长文档滚动守恒（文件选择路径） ----
            reset(pg, LONG, 1000)
            pg.evaluate("() => {window.__ed.scrollTop=1400; window.__pv.scrollTop=700;}")
            pg.wait_for_timeout(220)
            b12 = pg.evaluate("() => window.__state()")
            with pg.expect_file_chooser(timeout=15000) as fc3:
                pg.evaluate("() => window.__linkMenu()")
                pg.wait_for_timeout(120)
                pg.evaluate("() => window.__menuClick('插入本地文件')")
            fc3.value.set_files(ATT)
            pg.wait_for_timeout(1400)
            a12 = pg.evaluate("() => window.__state()")
            chk("L12 文件选择插入后编辑区/预览栏滚动守恒",
                abs(b12["edTop"] - a12["edTop"]) <= 2
                and abs(b12["pvTop"] - a12["pvTop"]) <= 2
                and "@@ MDE_" in a12["txt"],
                "ed %d->%d pv %d->%d" % (b12["edTop"], a12["edTop"],
                                          b12["pvTop"], a12["pvTop"]))

            # ---- L13 全页静态 id 唯一 + 两个按钮各就位 ----
            id_list = re.findall(r'\bid="([^"]+)"', html)
            static_ids = [x for x in id_list if "'+" not in x]
            id_dups = sorted({x for x in static_ids if static_ids.count(x) > 1})
            btn_state = pg.evaluate(r"""() => {
              const a=document.getElementById('imPickImg'), b=document.getElementById('imPick');
              return {a:a?a.textContent:'', b:b?b.textContent:''};
            }""")
            chk("L13 全页静态 id 无重复且两个选文件按钮各就位",
                not id_dups
                and html.count('id="imPickImg"') == 1
                and html.count('id="imPick"') == 1
                and "选择本地图片" in btn_state["a"]
                and "浏览" in btn_state["b"],
                "dups=%r a=%r b=%r" % (id_dups[:5], btn_state["a"], btn_state["b"]))

            # ---- L14 只开一个文件框、零 /api/open-file ----
            reset(pg, "单窗口验证。", 5)
            open_img(pg)
            pg.wait_for_timeout(150)
            chooser_hits = []
            watch = [True]

            def _chooser(fc):
                if watch[0]:
                    chooser_hits.append(1)
                    fc.set_files(IMG)

            pg.on("filechooser", _chooser)
            n0 = len([u for u in reqs if "/api/open-file" in u])
            pg.evaluate("() => document.getElementById('imPickImg').click()")
            pg.wait_for_timeout(1200)
            watch[0] = False
            n1 = len([u for u in reqs if "/api/open-file" in u])
            chk("L14 选择本地图片只开 1 个文件框且不触发后端原生框",
                len(chooser_hits) == 1 and n1 == n0 and "![](" in text(pg),
                "choosers=%d open-file %d->%d txt=%r" % (
                    len(chooser_hits), n0, n1, text(pg)[:60]))

            # ---- L15 导入面板「浏览…」监听仍在 ----
            n2 = len([u for u in reqs if "/api/open-file" in u])
            pg.evaluate("() => document.getElementById('imPick').click()")
            pg.wait_for_timeout(500)
            n3 = len([u for u in reqs if "/api/open-file" in u])
            chk("L15 导入面板浏览…仍绑 imPickFile（请求被拦截未弹框）",
                n3 == n2 + 1, "%d -> %d" % (n2, n3))

            # ---- L16 零 page error ----
            chk("L16 全程零 page error", not errs, repr(errs[:3]))
            b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        if os.path.isdir(TMP):
            shutil.rmtree(TMP, ignore_errors=True)

    print("\nPASS %d / FAIL %d" % (16 - len(fails), len(fails)))
    for f in fails:
        print("  FAILED: " + f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
