# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
"""P0「引用样式收口」一致性断言（跑法：python _test_quote_css.py）。

不测行为，只测**收口之后输出没变**。五条断言：

  A1  PY 生成器两种口径的产出 == P0 之前的字面量（逐字节）
  A2  JS 生成器（从 markdown-editor.html 里抠出来真跑）== PY 生成器
      跨语言做不到共用一份实现，就把"两个实现不可分叉"钉死
  A3  分页 CSS（PAGED_BASE_CSS 里那条 .markdown-body blockquote）== 生成器 margin 口径
      它在大三引号字符串里，插不了函数调用，只能靠这条断言保同步
  A4  预览主 CSS（:330）没被顺手改 —— 它是静态 <style>，P0 不许碰
  A5  两处调用点真的换成了生成器，旧字面量不再出现（防回退）

全绿才算 P0 做完。任何一条红，别往下走 P1。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "markdown-editor.html")
SERVER = os.path.join(HERE, "md_server.py")

# P0 之前的字面量（从 Edit 的 old_string 逐字抄下，那就是磁盘上的真实旧串）
OLD_EXPORT = ("border-left:3px solid #4a6cf7;background:#f5f7ff;"
              "padding:.4em 1em;margin:1em 0;")
OLD_PAGED = (".markdown-body blockquote{margin:.9em 0;padding:.4em 1em;"
             "border-left:3px solid #4a6cf7;background:#f5f7ff;"
             "border-radius:0 6px 6px 0;}")

fails = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s%s" % (name, ("  <<< " + detail) if detail else ""))
        fails.append(name)


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


_HTML_CACHE = []


def html_src():
    if not _HTML_CACHE:
        _HTML_CACHE.append(read(HTML))
    return _HTML_CACHE[0]


def _extract_fn(src, name):
    """抠出一个顶层函数（两空格缩进的 `}` 收尾）。

    JS 里不能用括号配平——函数体全是 CSS 字符串，满地的 `{` `}` 会配错。
    这两个函数内部缩进都 ≥4 空格，"行首恰好两个空格 + }" 只可能是函数结束。
    """
    m = re.search(r"function %s\([^)]*\)\{[\s\S]*?\n  \}\n" % re.escape(name),
                  src)
    return m.group(0) if m else None


sys.path.insert(0, HERE)
import md_server as M  # noqa: E402


def js_quote_css():
    """把 HTML 里的 _quoteCss 抠出来真跑一遍，返回两次调用的产物。"""
    script = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        "const i=src.indexOf('function _quoteCss(');"
        "if(i<0){console.error('NOT_FOUND');process.exit(2);}"
        "let d=0,st=false,e=-1;"
        "for(let j=i;j<src.length;j++){const c=src[j];"
        "if(c==='{'){d++;st=true;}"
        "else if(c==='}'){d--;if(st&&d===0){e=j+1;break;}}}"
        "if(e<0){console.error('UNBALANCED');process.exit(2);}"
        "const f=eval('('+src.slice(i,e)+')');"
        "process.stdout.write(JSON.stringify([f({}),"
        "f({radius:'0 6px 6px 0',margin:'.9em 0'})]));"
    )
    r = subprocess.run(["node", "-e", script, HTML],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None, (r.stderr or "").strip()
    return json.loads(r.stdout), ""


def js_export_blockquote():
    """真跑 buildStandaloneHtml（stub 掉 DOM 依赖），返回它产出的 blockquote 规则。

    防的是"拆分拼接写错"——A1/A2 只证明生成器对，证明不了调用处拼得对：
    少个分号、多个括号，A5 那种 `in` 断言看不出来。
    """
    script = (
        "const fs=require('fs');"
        "const qf=fs.readFileSync(process.argv[1],'utf8');"
        "const bf=fs.readFileSync(process.argv[2],'utf8');"
        "const doc={getElementById:function(){"
        "return {innerHTML:'<p>x</p>',textContent:''};}};"
        "const mk=new Function('document','katexCssText','escapeHtml',"
        "'getText','currentFile','_quoteCss','return ('+bf+')');"
        "const f=mk(doc,'',function(s){return s;},"
        "function(){return '# T';},null,eval('('+qf+')'));"
        "const html=f();"
        "const m=html.match(/blockquote\\{[^}]*\\}/);"
        "process.stdout.write(m?m[0]:'NO_MATCH');"
    )
    qf = _extract_fn(html_src(), "_quoteCss")
    bf = _extract_fn(html_src(), "buildStandaloneHtml")
    if not qf or not bf:
        return None, "extract failed: _quoteCss=%s buildStandaloneHtml=%s" % (
            bool(qf), bool(bf))
    tmp = tempfile.mkdtemp(prefix="_p0q_")
    qp = os.path.join(tmp, "qf.js")
    bp = os.path.join(tmp, "bf.js")
    with io.open(qp, "w", encoding="utf-8", newline="") as f:
        f.write(qf)
    with io.open(bp, "w", encoding="utf-8", newline="") as f:
        f.write(bf)
    try:
        r = subprocess.run(["node", "-e", script, qp, bp],
                           capture_output=True, text=True, encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0:
        return None, (r.stderr or "").strip()
    return r.stdout, ""


def js_quote_rules(cases):
    """把 _qcHex / _quoteRules 抠出来真跑，返回各档 CSS 与色值白名单结果。

    同样不用括号配平：函数体里全是 CSS 字符串，按「下一个标记之前最后一个
    行首两空格的 }」切，内部嵌套函数缩进 ≥4 空格，不会误判。
    """
    script = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        "function grab(name,next){"
        "const i=src.indexOf('function '+name+'(');"
        "const j=src.indexOf(next);"
        "if(i<0||j<0||j<i)throw new Error('MARKER '+name);"
        "return src.slice(i,src.lastIndexOf('\\n  }',j)+4);}"
        "const qs=src.indexOf('var _Q_STYLES=');"
        "if(qs<0)throw new Error('NO_Q_STYLES');"
        "const declSrc=src.slice(qs,src.indexOf(';',qs)+1);"
        "const code=declSrc"
        "+grab('_qcHex','/* v2.42.0 全局引用样式')"
        "+grab('_quoteRules','function buildStandaloneHtml(');"
        "const m=eval('(function(){'+code+'return {h:_qcHex,r:_quoteRules};})()');"
        "const cases=JSON.parse(process.argv[2]);"
        "const hex=['#ABCDEF','abcdef','#12345678','red','','#1234567'];"
        "process.stdout.write(JSON.stringify({"
        "rules:cases.map(function(c){return m.r(c[0],c[1]);}),"
        "hex:hex.map(m.h)}));"
    )
    r = subprocess.run(["node", "-e", script, HTML,
                        json.dumps(cases, ensure_ascii=False)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None, (r.stderr or "").strip()
    return json.loads(r.stdout), ""


def js_quote_roundtrip():
    """把面板「回填 / 写回」两段真实代码抠出来，配极简 DOM mock 跑一遍。

    静态断言只能证明"代码写上了"，证明不了 00000000 会不会被 .slice(0,7)
    洗成 #000000。这里真跑一次 回填→写回 闭环，才是 round-trip 的证据。
    """
    src = html_src()
    marks = [
        ("F0", "    var _qNone=function(v){"),
        ("F1", "    document.getElementById('tsQuoteBgColor').disabled=_qBgN;"),
        ("W0", "    var _qBdN=!!document.getElementById('tsQuoteBdNone').checked;"),
        ("W1", "?String(document.getElementById('tsQuoteBgColor').value||'').toLowerCase():'');"),
    ]
    pos = {}
    for key, needle in marks:
        i = src.find(needle)
        if i < 0:
            return None, "MARKER NOT FOUND: " + key
        pos[key] = i
    fill = src[pos["F0"]:pos["F1"] + len(marks[1][1])]
    write = src[pos["W0"]:pos["W1"] + len(marks[3][1])]

    script = (
        "const mk=function(){"
        "const st={};return {getElementById:function(id){"
        "if(!st[id])st[id]={checked:false,value:'#4a6cf7',disabled:false};"
        "return st[id];}};};"
        "const fill=new Function('tsCfg','document',FILL_CODE);"
        "const write=new Function('tsCfg','document',WRITE_CODE);"
        "function run(cfg,uncheck){"
        "const d=mk();fill(cfg,d);"
        "const f={bdNone:d.getElementById('tsQuoteBdNone').checked,"
        "bdDis:d.getElementById('tsQuoteBdColor').disabled,"
        "bgNone:d.getElementById('tsQuoteBgNone').checked,"
        "bgDis:d.getElementById('tsQuoteBgColor').disabled};"
        "if(uncheck)d.getElementById('tsQuoteBdNone').checked=false;"
        "write(cfg,d);return {fill:f,bd:cfg.quote.bd,bg:cfg.quote.bg};}"
        "const out={"
        "a:run({quote:{style:'bar',bd:'#00000000',bg:''}},false),"
        "b:run({quote:{style:'bar',bd:'#00000000',bg:''}},true),"
        "c:run({quote:{style:'bar',bd:'',bg:''}},false),"
        "d:run({quote:{style:'bar',bd:'',bg:'#00000000'}},false),"
        "e:run({quote:{style:'bar',bd:'#cc0000',bg:'#ffff00'}},false)};"
        "process.stdout.write(JSON.stringify(out));"
    )
    script = ("const FILL_CODE=" + json.dumps(fill, ensure_ascii=False) + ";\n"
              "const WRITE_CODE=" + json.dumps(write, ensure_ascii=False) + ";\n"
              + script)
    r = subprocess.run(["node", "-e", script], capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        return None, (r.stderr or "").strip()
    return json.loads(r.stdout), ""


def js_quote_cfg(raw_cases):
    """把 tsCfg 里 o.quote 的真实初始化段抠出来，配 _qcHex 跑旧配置回放。

    覆盖「无 quote 键的旧配置」「非法 style / 脏色」「8 位全透明 / 半透明」
    三条读入链路，而不是只测白名单函数本身。
    """
    src = html_src()
    i = src.index("    o.quote={style:")
    j = src.index("};", i) + 2
    code = src[i:j]
    hf = _extract_fn(src, "_qcHex")
    if not hf:
        return None, "extract _qcHex failed"
    script = (
        "const HEX=" + json.dumps(hf, ensure_ascii=False) + ";"
        "const CODE=" + json.dumps(code, ensure_ascii=False) + ";"
        "const hf=new Function(HEX+'\\nreturn _qcHex;')();"
        "const f=new Function('raw','o','_qcHex',CODE);"
        "const cases=JSON.parse(process.argv[1]);"
        "const out=cases.map(function(raw){const o={};f(raw,o,hf);return o.quote;});"
        "process.stdout.write(JSON.stringify(out));"
    )
    r = subprocess.run(["node", "-e", script,
                        json.dumps(raw_cases, ensure_ascii=False)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None, (r.stderr or "").strip()
    return json.loads(r.stdout), ""


def main():
    html = read(HTML)
    srv = read(SERVER)

    print("[A1] PY 生成器 == P0 之前字面量")
    got_export = M._quote_css()
    got_paged = M._quote_css(radius="0 6px 6px 0", margin=".9em 0",
                             first="margin")
    check("导出口径逐字节一致", got_export == OLD_EXPORT, repr(got_export))
    check("分页口径逐字节一致",
          ".markdown-body blockquote{" + got_paged + "}" == OLD_PAGED,
          repr(got_paged))

    print("[A2] JS 生成器 == PY 生成器（跨语言不可分叉）")
    js, err = js_quote_css()
    if js is None:
        check("JS 侧可执行", False, err)
    else:
        check("默认参数两语言一致", js[0] == M._quote_css(), repr(js[0]))
        check("带 radius/margin 两语言一致",
              js[1] == M._quote_css(radius="0 6px 6px 0", margin=".9em 0"),
              repr(js[1]))

    print("[A3] 分页 CSS 那条规则与生成器同步")
    m = re.search(r"\.markdown-body blockquote\{[^}]*\}", srv)
    check("PAGED_BASE_CSS 里找得到该规则", bool(m))
    if m:
        check("与生成器 margin 口径逐字节一致", m.group(0) == OLD_PAGED,
              m.group(0))
        check("该规则在 PAGED_BASE_CSS 常量内（不是别处凑巧有一条）",
              m.start() > srv.index('PAGED_BASE_CSS = """'))

    print("[A4] 预览主 CSS 未被改动")
    m = re.search(r"\.markdown-body blockquote\{([^}]*)\}", html)
    check("预览里找得到该规则", bool(m))
    if m:
        body = m.group(1)
        for frag in ("border-left:3px solid var(--accent)",
                     "background:var(--accent-soft)",
                     "border-radius:0 var(--radius) var(--radius) 0",
                     "margin:.9em 0", "padding:.4em 1em",
                     "color:var(--text)"):
            check("含 %s" % frag, frag in body)

    print("[A5] 调用点已换、旧字面量不再出现")
    check("md_server.py 用上 _quote_css()",
          "'blockquote{' + _quote_css() + '}'" in srv)
    check("markdown-editor.html 用上 _quoteCss({})",
          "_quoteCss({})" in html)
    # 旧串只在两处注释/测试基线里允许出现，源码里不该再有"直接写死"的
    stray = re.findall(r"blockquote\{border-left:3px solid #4a6cf7", srv + html)
    check("源码里没有残留的写死串", len(stray) == 0, "found %d" % len(stray))

    print("[A6] 端到端：真跑 buildStandaloneHtml，产物里的引用规则不变")
    got, err = js_export_blockquote()
    if got is None:
        check("HTML 导出函数可执行", False, err)
    else:
        check("产物里的 blockquote 规则逐字节一致",
              got == "blockquote{" + OLD_EXPORT + "}", repr(got))

    print("[A7] 端到端：后端 HTML 导出产物里的引用规则不变")
    try:
        out = M.build_standalone_html(None, "<h1>t</h1><p>x</p>", "")
        m = re.search(r"blockquote\{[^}]*\}", out)
        check("后端产物里找得到该规则", bool(m))
        if m:
            check("与导出口径逐字节一致",
                  m.group(0) == "blockquote{" + OLD_EXPORT + "}", repr(m.group(0)))
    except Exception as e:  # noqa: BLE001
        check("后端导出可执行", False, repr(e))

    print("[A8] v2.42.0 四档规则生成器（_quoteRules）")
    RULES_CASES = [
        [{"style": "bar", "bd": "", "bg": ""}, "light"],
        [{"style": "bar", "bd": "", "bg": ""}, "dark"],
        [{"style": "bar", "bd": "#cc0000", "bg": ""}, "light"],
        [{"style": "bar", "bd": "", "bg": "#ffff00"}, "light"],
        [{"style": "box", "bd": "", "bg": ""}, "light"],
        [{"style": "round", "bd": "", "bg": ""}, "dark"],
        [{"style": "quote", "bd": "", "bg": ""}, "light"],
        [{"style": "quote", "bd": "#008800", "bg": "#f0fff0"}, "light"],
        [{"style": "corner", "bd": "", "bg": "#f0fff0"}, "light"],
        [{"style": "brace", "bd": "", "bg": "#f0fff0"}, "light"],
        [{"style": "bar", "bd": "#00000000", "bg": "#00000000"}, "light"],
        [{"style": "xxx", "bd": "red", "bg": "zzz"}, "light"],
    ]
    got, err = js_quote_rules(RULES_CASES)
    if got is None:
        check("规则生成器可执行", False, err)
    else:
        R = got["rules"]
        check("默认态（bar＋两色留空）浅纸返回空串", R[0] == "", repr(R[0]))
        check("默认态深纸也返回空串", R[1] == "", repr(R[1]))
        check("只改边框色：写死色值且丢掉 var()",
              "border-left:3px solid #cc0000" in R[2] and "var(--accent" not in R[2],
              R[2])
        check("只改底色：底色写死、边框回落纸面默认",
              "background:#ffff00 !important" in R[3]
              and "border-left:3px solid #4a6cf7" in R[3], R[3])
        check("直角框用 border 简写（能盖掉基础 CSS 的 border-left）",
              "border:1px solid #4a6cf7" in R[4] and "border-radius:0;" in R[4], R[4])
        check("圆角框 6px、深纸取深色默认",
              "border:1px solid #7aa2f7" in R[5] and "border-radius:6px" in R[5], R[5])
        check("大引号：成对墨滴字形 U+275D / U+275E，开闭都在",
              r'content:"\275D"' in R[6] and r'content:"\275E"' in R[6]
              and "::before" in R[6] and "::after" in R[6], R[6])
        check("大引号：开引号在左上、闭引号在右下",
              "left:.02em;top:-.10em" in R[6] and "right:.02em;bottom:-.16em" in R[6],
              R[6])
        check("大引号：上下 padding 给字形让位，不写 margin",
              "padding:3.2em 1.2em 3.4em" in R[6] and "margin:" not in R[6], R[6])
        check("大引号：细体逗号引号与已砍档字形都不再出现",
              all(x not in R[6] for x in (r"\201C", r"\201D", r"\300C", r"\7B", r"\7D")),
              R[6])
        check("大引号：色跟用户值", "color:#008800" in R[7]
              and "background:#f0fff0 !important" in R[7], R[7])
        check("已砍档名 corner 回落 bar，不产字形",
              "border-left:3px solid #4a6cf7" in R[8] and "content:" not in R[8], R[8])
        check("已砍档名 brace 回落 bar，不产字形",
              "border-left:3px solid #4a6cf7" in R[9] and "content:" not in R[9], R[9])
        check("全透明：3px 占位保留、只是色透明（颜色不碰结构）",
              "border-left:3px solid #00000000;" in R[10]
              and "background:#00000000 !important" in R[10]
              and "padding:.4em 1em" in R[10], R[10])
        check("全脏值＝等同默认（返回空串）", R[11] == "", repr(R[11]))
        check("伪元素选择器逐个展开，不是只挂最后一项",
              ", .markdown-body blockquote::before" in R[6]
              and ".markdown-body blockquote, .markdown-body blockquote::before" not in R[6],
              R[6])
        check("底色一律带 !important（否则深纸面规则压过去）",
              all(("background:" not in r) or ("background:" in r and "!important" in r)
                  for r in R))
        check("默认态之外的规则都带深纸面选择器（同特异性靠源序赢）",
              all((".markdown-body.md-tone-dark blockquote{" in r)
                  for r in R if r))
        H = got["hex"]
        check("_qcHex 大小写归一", H[0] == "#abcdef", repr(H[0]))
        check("_qcHex 缺 # 补上", H[1] == "#abcdef", repr(H[1]))
        check("_qcHex 认 8 位", H[2] == "#12345678", repr(H[2]))
        check("_qcHex 挡非 HEX 色名", H[3] == "", repr(H[3]))
        check("_qcHex 空值回空", H[4] == "", repr(H[4]))
        check("_qcHex 挡 7 位残缺值", H[5] == "", repr(H[5]))

    print("[A9] 配置与面板接线")
    check("tsCfg 有 quote 三键", re.search(r"o\.quote=\{style:", html) is not None)
    check("applyTypeset 里拼进规则", "css+=_quoteRules(tsCfg.quote,_tone);" in html)
    for _id in ("tsQuoteStyle", "tsQuoteBdOn", "tsQuoteBdColor", "tsQuoteBdNone",
                "tsQuoteBgOn", "tsQuoteBgColor", "tsQuoteBgNone"):
        check("面板控件 %s 存在" % _id, ('id="%s"' % _id) in html)
        check("控件 %s 有回填" % _id, ("getElementById('%s')" % _id) in html)
    check("写回三态：勾「不画」优先落 00000000，未勾时关开关清空色值",
          "_qBdN?'#00000000':(document.getElementById('tsQuoteBdOn').checked" in html
          and "_qBgN?'#00000000':(document.getElementById('tsQuoteBgOn').checked" in html)

    print("[B1] P1b「不画」入口：源码接线")
    check("两个「不画」勾选框是 .ts-chk 族，不新开控件类型",
          'id="tsQuoteBdNone" class="ts-chk"' in html
          and 'id="tsQuoteBgNone" class="ts-chk"' in html)
    check("回填由 alpha=00 反推勾选，不是靠额外状态字段",
          "/^#[0-9a-f]{6}00$/" in html and "_qBdN=_qNone(tsCfg.quote.bd)" in html)
    check("勾上时取色器禁用（回填 + 联动两处）",
          "document.getElementById('tsQuoteBdColor').disabled=_qBdN" in html
          and "document.getElementById('tsQuoteBgColor').disabled=_qBgN" in html
          and "/^tsQuote(Bd|Bg)None$/" in html)
    check("联动挂在 tsBody 既有委托上，没另绑一套",
          html.count("getElementById('tsBody').addEventListener('change'") == 2)
    check("三态优先级：写回时「不画」不读取色器",
          "var _qBdN=!!document.getElementById('tsQuoteBdNone').checked;" in html
          and "_qBdN?'#00000000':" in html)
    _plan = read(os.path.join(HERE, "PLAN-引用样式-全局与临时覆盖.md"))
    check("方案 §2.2 已立「颜色只做颜色的事」原则，且不许回落 currentColor",
          "颜色只做颜色的事" in _plan and "不许回落 `currentColor`" in _plan)
    check("生成器已删净 alpha 结构分支（cOff/bOff 不再存在）",
          "var cOff=" not in html and "var bOff=" not in html)

    print("[B2] P1b「不画」入口：规则生成器真跑")
    bcases = [
        [{"style": "bar", "bd": "#00000000", "bg": ""}, "light"],
        [{"style": "box", "bd": "#00000000", "bg": "#00000000"}, "light"],
        [{"style": "quote", "bd": "#00000000", "bg": ""}, "light"],
        [{"style": "quote", "bd": "#008800", "bg": ""}, "light"],
        [{"style": "bar", "bd": "", "bg": ""}, "light"],
    ]
    bgot, berr = js_quote_rules(bcases)
    if bgot is None:
        check("js_quote_rules 可执行", False, berr)
        BR = [""] * 5
    else:
        BR = bgot["rules"]
        check("bar 透明：3px 竖线占位保留，色为 #00000000",
              "border-left:3px solid #00000000;" in BR[0]
              and "background:" in BR[0], BR[0])
        check("box 透明：1px 四边框占位保留，底色 #00000000",
              "border:1px solid #00000000;" in BR[1]
              and "background:#00000000 !important" in BR[1], BR[1])
        check("quote 透明：伪元素与上下留白全保留，只有字形色透明",
              "color:#00000000" in BR[2] and "currentColor" not in BR[2]
              and r'content:"\275D"' in BR[2] and r'content:"\275E"' in BR[2]
              and "padding:3.2em 1.2em 3.4em" in BR[2], BR[2])
        check("quote 正常设色：字形色跟用户值（回归 P1 行为）",
              "color:#008800" in BR[3] and r'content:"\275E"' in BR[3], BR[3])
        check("默认态仍返回空串（J1 版面零变化继续成立）", BR[4] == "", repr(BR[4]))

    print("[B3] P1b「不画」入口：回填→写回 round-trip 真跑")
    rgot, rerr = js_quote_roundtrip()
    if rgot is None:
        check("回填/写回代码可抠出并可执行", False, rerr)
    else:
        a, b, c, d, e = rgot["a"], rgot["b"], rgot["c"], rgot["d"], rgot["e"]
        check("8 位全透明回填：勾「不画」且禁用取色器",
              a["fill"]["bdNone"] is True and a["fill"]["bdDis"] is True, str(a["fill"]))
        check("★ round-trip：00000000 点一次「应用」不被洗成 #000000",
              a["bd"] == "#00000000", "got %r" % a["bd"])
        check("底色同理：勾「不画」→ 写回仍 00000000",
              d["fill"]["bgNone"] is True and d["fill"]["bgDis"] is True
              and d["bg"] == "#00000000", str(d))
        check("取消勾选后回到 6 位色，不再强制透明",
              b["bd"] != "#00000000", "got %r" % b["bd"])
        check("默认配置 {bar,'',''} 不勾、不禁用、写回仍双空（逐字节不变）",
              not c["fill"]["bdNone"] and not c["fill"]["bdDis"]
              and not c["fill"]["bgNone"] and c["bd"] == "" and c["bg"] == "", str(c))
        check("普通 6 位色往返无损（P1 行为零回归）",
              e["bd"] == "#cc0000" and e["bg"] == "#ffff00"
              and not e["fill"]["bdNone"] and not e["fill"]["bdDis"], str(e))

    print("[B4] V4 真实出件 / V5 旧配置回放")
    try:
        _out = M.build_standalone_html(
            None, "<h1>t</h1><blockquote><p>q</p></blockquote>", "")
        check("默认态真出件：导出 HTML 不含新增引用规则（版面零变化）",
              ".markdown-body.md-tone-dark blockquote" not in _out
              and "border-left:3px solid #00000000" not in _out)
        check("默认态真出件：基线 blockquote 规则仍是 P0 旧串",
              "blockquote{" + OLD_EXPORT + "}" in _out)
    except Exception as e:  # noqa: BLE001
        check("默认态真出件可执行", False, repr(e))

    _cfgs = [{},
             {"quote": {"style": "corner", "bd": "red", "bg": "zzz"}},
             {"quote": {"style": "quote", "bd": "#00000000", "bg": "#FF000080"}},
             {"quote": {"style": "round", "bd": "ABCDEF", "bg": ""}}]
    cgot, cerr = js_quote_cfg(_cfgs)
    if cgot is None:
        check("旧配置读入代码可抠出并可执行", False, cerr)
    else:
        _def = {"style": "bar", "bd": "", "bg": ""}
        check("V5 无 quote 键的旧配置 → 回落默认 {bar,'',''}", cgot[0] == _def, str(cgot[0]))
        check("V5 非法 style + 脏色 → 整组回落，版面不变", cgot[1] == _def, str(cgot[1]))
        check("V5 旧配置回落态下 _quoteRules 仍返回空串",
              js_quote_rules([[cgot[0], "light"], [cgot[1], "dark"]])[0]["rules"] == ["", ""])
        check("V5 8 位全透明读入不丢 alpha、大小写归一",
              cgot[2]["style"] == "quote" and cgot[2]["bd"] == "#00000000"
              and cgot[2]["bg"] == "#ff000080", str(cgot[2]))
        check("V5 缺 # 的 6 位色读入补 # 并归一",
              cgot[3]["style"] == "round" and cgot[3]["bd"] == "#abcdef", str(cgot[3]))

    # ================================================================
    # C 组 · P2「> 内容{参数}」后缀临时覆盖
    # harness 跑的是 markdown-editor.html 里抠出来的原函数字节，不是等价重写
    # ================================================================
    print("[C] v2.42.0 P2 行末参数 / 结构判据 / 逐块 CSS")
    import _p2_cases  # noqa: E402
    (p2, src2), p2err = _p2_cases.run()
    if p2 is None:
        check("P2 harness 可执行", False, p2err[1] if isinstance(p2err, tuple) else str(p2err))
    else:
        G = p2["grammar"]
        check("C1-1 {bar} 只给样式", G[0] == {"style": "bar", "bd": "", "bg": ""}, str(G[0]))
        check("C1-2 {b} 单色落边框色", G[1] == {"style": "", "bd": "#1e88e5", "bg": ""}, str(G[1]))
        check("C1-3 {b a} 先边框后底色",
              G[2] == {"style": "", "bd": "#1e88e5", "bg": "#757575"}, str(G[2]))
        check("C1-4 {round b a} 样式+两色",
              G[3] == {"style": "round", "bd": "#1e88e5", "bg": "#757575"}, str(G[3]))
        check("C1-5 {b round a} 样式与颜色顺序自由，等价上一行", G[4] == G[3], str(G[4]))
        check("C1-19 两个颜色仍按出现顺序分（{a b} ≠ {b a}）",
              G[18] == {"style": "", "bd": "#757575", "bg": "#1e88e5"}
              and G[18] != G[2], str(G[18]))
        check("C1-6 {00000000 a} 全透明是合法颜色",
              G[5] == {"style": "", "bd": "#00000000", "bg": "#757575"}, str(G[5]))
        check("C1-7 ASCII 引号包样式名", G[6] == G[3], str(G[6]))
        check("C1-8 中文引号包样式名", G[7] == G[3], str(G[7]))
        check("C1-9 带 # 的 6 位色容忍", G[8] == {"style": "", "bd": "#cc0000", "bg": ""}, str(G[8]))
        check("C1-10 8 位 RRGGBBAA 不丢 alpha", G[9] == {"style": "", "bd": "#ff000080", "bg": ""}, str(G[9]))
        check("C1-11 全角空格归一", G[10] == {"style": "box", "bd": "", "bg": ""}, str(G[10]))
        check("C1-12 {} 三项全空 → null（不剥）", G[11] is None, str(G[11]))
        check("C1-13 两个样式 → null", G[12] is None, str(G[12]))
        check("C1-14 三个颜色 → null", G[13] is None, str(G[13]))
        check("C1-15 未知裸词 → null", G[14] is None, str(G[14]))
        check("C1-16 {\"\" b a} 空引号占位 → null（整组作废）", G[15] is None, str(G[15]))
        check("C1-17 {quote} 只给大引号档", G[16] == {"style": "quote", "bd": "", "bg": ""}, str(G[16]))
        check("C1-18 两色都可全透明",
              G[17] == {"style": "", "bd": "#00000000", "bg": "#00000000"}, str(G[17]))

        L = p2["looks"]
        check("C1b 别家方言花括号不报 D217（红/上标/MDE/table 参数）",
              L[:4] == [False, False, False, False], str(L[:4]))
        check("C1b 含样式名或全色但整体非法 → 报 D217",
              L[4:] == [True, True, True, False], str(L[4:]))

        O = p2["owner"]
        for k, (line, want) in enumerate(_p2_cases.OWNER):
            check("C2-%02d 归属 %s" % (k + 1, line[:30]),
                  O[k]["owns"] is want, "bp=%s owns=%s want=%s" % (O[k]["bp"], O[k]["owns"], want))

        B = p2["blocks"]
        check("C3-1 {box b a} 产出三个 data-q* 且正文里参数被剥掉",
              'data-qstyle="box"' in B[0]["html"]
              and 'data-qbd="#1e88e5"' in B[0]["html"]
              and 'data-qbg="#757575"' in B[0]["html"]
              and "{box b a}" not in B[0]["html"], B[0]["html"])
        check("C3-2 纯文字 {c} 归引用（青色边框），不是图片对齐",
              'data-qbd="#00acc1"' in B[1]["html"] and "{c}" not in B[1]["html"], B[1]["html"])
        check("C3-3 {c} 被图片认领 → 引用一个属性都不写",
              "data-q" not in B[2]["html"] and "![图](a.png){c}" in B[2]["html"], B[2]["html"])
        check("C3-4 {c}{b a} 前归图后归引用",
              "![图](a.png){c}" in B[3]["html"] and 'data-qbd="#1e88e5"' in B[3]["html"]
              and "{b a}" not in B[3]["html"], B[3]["html"])
        check("C3-5 {}{b a} 空占位归图、后组归引用",
              "![图](a.png){}" in B[4]["html"] and 'data-qbg="#757575"' in B[4]["html"], B[4]["html"])
        check("C3-6 半角括号收尾的正文不再误判",
              'data-qbd="#1e88e5"' in B[5]["html"] and "原文(he said)" in B[5]["html"], B[5]["html"])
        check("C3-7 无参数 → 零属性、零诊断",
              "data-q" not in B[6]["html"] and B[6]["diag"] == [], str(B[6]))
        check("C3-8 非法参数不剥、原串露出、且不误报",
              "data-q" not in B[7]["html"] and "{zzz}" in B[7]["html"]
              and B[7]["diag"] == [], str(B[7]))
        check("C3-9 像参数但非法 → 不剥 + D217",
              "data-q" not in B[8]["html"] and "{box zzz}" in B[8]["html"]
              and any(d["code"] == "D217" for d in B[8]["diag"]), str(B[8]))
        check("C3-10 整块只剩参数 → D218 且属性仍在",
              'data-qstyle="bar"' in B[9]["html"]
              and any(d["code"] == "D218" for d in B[9]["diag"]), str(B[9]))
        check("C3-11 @@ color r{红} 不剥不报",
              "data-q" not in B[10]["html"] and "{红}" in B[10]["html"]
              and B[10]["diag"] == [], str(B[10]))
        check("C3-12 x^{2} 上标不剥不报",
              "x^{2}" in B[11]["html"] and B[11]["diag"] == [], str(B[11]))
        check("C3-13 多行块只认最后一个非空行的参数",
              'data-qstyle="quote"' in B[12]["html"]
              and "data-qbd" not in B[12]["html"], B[12]["html"])
        check("C3-14 参数独占末行，剥完不影响前两行",
              'data-qstyle="round"' in B[13]["html"]
              and "内容" in B[13]["html"] and "第二行" in B[13]["html"], B[13]["html"])

        I = p2["inline"]
        check("C4-1 无 data-q* → 逐块 CSS 空串（默认态零字节变化）", I[0] == "", repr(I[0]))
        check("C4-2 quote 档逐块规则含属性选择器 / 伪元素 / 两色",
              '[data-qstyle="quote"]' in I[1] and 'content:"\\275D"' in I[1]
              and "color:#008800" in I[1] and "background:#f0fff0 !important" in I[1], I[1][:200])
        check("C4-3 深纸面选择器带同一组属性（压过 !important）",
              '.markdown-body.md-tone-dark blockquote[data-qstyle="quote"]' in I[1], I[1][:200])
        check("C4-4 只写边框色时样式回落全局 quote，伪元素仍在",
              'content:"\\275D"' in I[2] and "color:#cc0000" in I[2]
              and 'data-qstyle' not in I[2], I[2][:200])
        check("C4-5 块写 {bar} 时 force 生效，压回竖线不返回空串",
              "border-left:3px solid #4a6cf7" in I[3]
              and 'content:"\\275D"' not in I[3], I[3][:200])
        check("C4-6 同参数组合去重（两块只产一条规则）",
              I[4].count("border:1px solid") == 1, I[4][:300])

        check("C5-1 RE_IMG 全库只有一份声明", src2.count("var RE_IMG=/") == 1)
        check("C5-2 内联层真的改用共享正则",
              "text.replace(RE_IMG,function(m,alt,src,title,wpct,algn,captoks){" in src2
              and "text=text.replace(/!\\[" not in src2)
        check("C5-3 render 收尾与 applyTypeset 各挂一次 _quoteApplyInline",
              src2.count("_quoteApplyInline();") == 2)
        check("C5-4 D217 / D218 诊断码已落地",
              "'D217'" in src2 and "'D218'" in src2)
        check("C5-5 语法提示表加了 ^[ ]*> 一行",
              "[/^[ ]*>/,[['> 引用{box b a}'" in src2)
        check("C5-6 QINLINE 哨兵 + 幂等切片",
              "/*QINLINE*/" in src2 and "base.indexOf('/*QINLINE*/')" in src2)
        check("C5-7 _quoteRulesFor 是唯一规则实现（全局与逐块共用）",
              src2.count("function _quoteRulesFor(") == 1
              and src2.count("_quoteRulesFor(") == 3)

    print("[C6] 导出链把逐块 CSS 原样带走（真跑后端出件）")
    _qts = ("/*QINLINE*/#preview blockquote[data-qstyle=\"box\"]"
            "{border:1px solid #e53935;background:#fff8e1 !important;}")
    try:
        _o = M.build_standalone_html(
            None, '<blockquote data-qstyle="box"><p>x</p></blockquote>', _qts)
        check("C6-1 导出 HTML 保留 data-q* 属性", 'data-qstyle="box"' in _o)
        check("C6-2 逐块 CSS 随 tsCss 进产物，#preview 按既有规则替换",
              'blockquote[data-qstyle="box"]' in _o
              and "#preview blockquote[data-qstyle" not in _o)
        check("C6-3 默认基线规则仍在（不与逐块规则打架）",
              "blockquote{" + OLD_EXPORT + "}" in _o)
    except Exception as e:  # noqa: BLE001
        check("C6 真出件可执行", False, repr(e))

    print("")
    if fails:
        print("TOTAL_FAIL=%d  %s" % (len(fails), ", ".join(fails)))
        return 1
    print("TOTAL_FAIL=0  全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
