# -*- coding: utf-8 -*-
"""P2 C 组断言的用例与 Node harness 生成（由 _test_quote_css.py 调用）。"""
import io
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "markdown-editor.html")

# 十条结构判据（方案 §4.4 原表，逐条照抄）
OWNER = [
    ("![图](a.png){c}", True),
    ("![图](a.png){}", True),
    ("![图](a.png){b a}", False),
    ("![图](a.png){c}{b a}", False),
    ("![图](a.png){}{b a}", False),
    ("原文(he said){b a}", False),
    ("见 [文](u){b}", False),
    ("![图](a.png){40c:题注}", True),
    ("图 ![a](1.png){c} 与 ![b](2.png){b}", False),
    ("![图](a.png){c} 后文{b a}", False),
]

GRAMMAR = [
    "bar", "b", "b a", "round b a", "b round a", "00000000 a",
    '"round" b a', "\u201cround\u201d b a", "#cc0000", "ff000080",
    "\u3000 box \u3000", "", "bar box", "b a r", "zzz", '"" b a',
    "quote", "00000000 00000000", "a b",
]

# 引用块原文 → 期望（在 Python 侧断言，harness 只回传真实产物）
BLOCKS = [
    ["> 内容{box b a}"],
    ["> 内容{c}"],
    ["> ![图](a.png){c}"],
    ["> ![图](a.png){c}{b a}"],
    ["> ![图](a.png){}{b a}"],
    ["> 原文(he said){b a}"],
    ["> 这是一段正文"],
    ["> 内容{zzz}"],
    ["> 内容{box zzz}"],
    ["> {bar}"],
    ["> @@ color r{红}"],
    ["> x^{2}"],
    ["> 内容{b a}", "> 第二行{quote}"],
    ["> 内容", "> 第二行", "> {round}"],
]

DEF_CFG = {"page": {"tone": "light"}, "quote": {"style": "bar", "bd": "", "bg": ""}}

# 视觉探针用的一组真实参数组合（同一份 tsCfg 下五块并存）
VISUAL = [{
    "cfg": DEF_CFG,
    "els": [
        {"data-qstyle": "box", "data-qbd": "#e53935", "data-qbg": "#fff8e1"},
        {"data-qstyle": "round", "data-qbd": "#1e88e5", "data-qbg": "#f5f7ff"},
        {"data-qstyle": "quote", "data-qbd": "#3d4657", "data-qbg": "#eef1fb"},
        {"data-qbd": "#00acc1"},
        {"data-qstyle": "bar", "data-qbd": "#00000000", "data-qbg": "#f0f0f0"},
    ],
}]

INLINE = [
    {"cfg": DEF_CFG, "els": []},
    {"cfg": DEF_CFG,
     "els": [{"data-qstyle": "quote", "data-qbd": "#008800", "data-qbg": "#f0fff0"}]},
    {"cfg": {"page": {"tone": "light"}, "quote": {"style": "quote", "bd": "", "bg": ""}},
     "els": [{"data-qbd": "#cc0000"}]},
    {"cfg": {"page": {"tone": "light"}, "quote": {"style": "quote", "bd": "", "bg": ""}},
     "els": [{"data-qstyle": "bar"}]},
    {"cfg": DEF_CFG,
     "els": [{"data-qstyle": "box"}, {"data-qstyle": "box"}]},
]


def build_harness():
    """把真实源码里的六段抠出来拼成一个可跑的 Node 文件。

    不用「重写一份等价实现」来测——那只能证明两份实现互相同意，证明不了
    工具里那一份对。这里跑的就是 markdown-editor.html 里的原函数字节。
    """
    src = io.open(HTML, encoding="utf-8").read()

    def cut(a, b, start=0):
        i = src.index(a, start)
        j = src.index(b, i + len(a))
        return src[i:j]

    color_decl = cut("var MDE_COLOR_ABBR=", "function _colorVal(s){")
    ci = src.index("function _colorVal(s){")
    color_fn = src[ci:src.index("\n}\n", ci) + 3]
    ri = src.index("var RE_IMG=/")
    re_img = src[ri:src.index("\n", ri) + 1]
    p2_funcs = cut("var _Q_STYLES=", "/* ---- v2.33.0 @@ begin font")
    css_funcs = cut("  function _qcHex(v){", "  function buildStandaloneHtml(){")
    bi = src.index("    if(/^[ ]*>/.test(line)){")
    branch = src[bi:src.index("\n    if(line.indexOf('|')>=0", bi)]
    branch = branch.replace("continue;", ";")   # 脱离外层循环，continue 非法

    js = r'''
const fs=require('fs');
const CASES=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
''' + color_decl + color_fn + re_img + p2_funcs + css_funcs + r'''
var tsCfg=CASES.cfg0;
function runBlock(linesArr){
  var html='',lines=linesArr,i=0,line=linesArr[0]||'',_base=0,_lv=0,_lv3=0,
      opts={diag:[]},curInd=0,IPX={quote:1};
  var _dgE=function(rel,code,msg,sev){
    opts.diag.push({line:rel,code:code,msg:msg,sev:sev||'err'});};
  var parseMarkdown=function(x){return '<INNER>'+x+'</INNER>';};
''' + branch + r'''
  return {html:html,diag:opts.diag};
}
function mockEls(arr){
  return {querySelectorAll:function(){
    return arr.map(function(o){return {getAttribute:function(k){
      return o[k]===undefined?null:o[k];}};});}};
}
const out={
  grammar:CASES.grammar.map(function(r){return _quoteParseParam(r);}),
  looks:CASES.looks.map(function(r){return _qLooksLikeParam(r);}),
  owner:CASES.owner.map(function(o){
    const bp=_qTrailingBrace(o.line);
    return {bp:bp,owns:bp<0?null:_imgOwnsTrailingBrace(o.line,bp)};}),
  blocks:CASES.blocks.map(function(b){return runBlock(b);}),
  inline:[]
};
for(const c of CASES.inline){
  tsCfg=c.cfg;
  out.inline.push(_quoteInlineCss(mockEls(c.els)));
}
out.visual=[];
for(const c of CASES.visual){
  tsCfg=c.cfg;
  out.visual.push(_quoteInlineCss(mockEls(c.els)));
}
process.stdout.write(JSON.stringify(out));
'''
    return js, src


def run():
    js, src = build_harness()
    cases = {
        "cfg0": DEF_CFG,
        "grammar": GRAMMAR,
        "looks": ["红", "2", "k == v", "50l:r(50|30|20)", "box 红", "b a", "b a r", "zzz"],
        "owner": [{"line": a, "want": b} for a, b in OWNER],
        "blocks": BLOCKS,
        "inline": INLINE,
        "visual": VISUAL,
    }
    fd, jp = tempfile.mkstemp(suffix=".json", prefix="mde_p2_")
    os.close(fd)
    io.open(jp, "w", encoding="utf-8").write(json.dumps(cases, ensure_ascii=False))
    fd, sp = tempfile.mkstemp(suffix=".cjs", prefix="mde_p2_")
    os.close(fd)
    io.open(sp, "w", encoding="utf-8").write(js)
    try:
        r = subprocess.run(["node", sp, jp], capture_output=True,
                           text=True, encoding="utf-8")
        if r.returncode != 0:
            return None, (src, (r.stderr or "").strip())
        return (json.loads(r.stdout), src), ""
    finally:
        os.remove(jp)
        os.remove(sp)
