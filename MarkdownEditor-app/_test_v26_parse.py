# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""v2.6 六形式 + global 标记 node 级解析测试。
从 PARSER 段提取 JS 在 node 跑，断言 mdeParseBody / mdeParseTable /
parseMarkdown 产物。"""
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "markdown-editor.html"), encoding="utf-8").read()
m = re.search(r"/\*PARSER_START\*/(.*?)/\*PARSER_END\*/", src, re.S)

TESTS = r"""
const NL=String.fromCharCode(10);const TRI=String.fromCharCode(39,39,39);const BS=String.fromCharCode(92);
function P(s){return parseMarkdown(s);}
function PB(b){return mdeParseBody(b);}
let n=0,f=0;
function T(name,cond){n++;if(!cond){f++;console.log('FAIL:',name);}}

/* ── 形式 1：单值文本（兼容） ── */
let r=PB('今天买了苹果');
T('F1 单值 str', r.ok&&r.ch==='vals'&&r.val==='今天买了苹果'&&r.disp==='今天买了苹果');
r=PB('k == 3');
T('F2 单键值对', r.ok&&r.kvSingle&&r.singleKey==='k'&&r.singleVal==='3'&&r.disp==='3');
r=PB('备注 == 内部,口径');
T('F2b 单kv值含半角逗号fail（定稿）', !r.ok);

/* ── 形式 3：纯值向量 ── */
r=PB('8%,1.5%,0.6%');
T('F3 纯值向量 list', r.ok&&r.ch==='vals'&&JSON.stringify(r.val)===JSON.stringify(['8%','1.5%','0.6%']));
/* 行文抽取 */
r=PB('2025年，我国GDP总体上涨((8%))，同比上涨((1.5%))，是疫情以来第一次出现大于((0.6%))的上涨。');
T('F3b 行文纯值抽取', r.ok&&r.ch==='vals'&&JSON.stringify(r.val)===JSON.stringify(['8%','1.5%','0.6%']));
T('F3c 行文显示=去标记全文', r.disp.indexOf('((8%))')<0&&r.disp.indexOf('8%')>=0&&r.disp.indexOf('2025年')===0);

/* ── 形式 4：键值向量 ── */
r=PB('A == 8%, B == 1.5%, C == 0.6%');
T('F4 键值向量 dict', r.ok&&r.ch==='kv'&&r.val.A==='8%'&&r.val.B==='1.5%'&&r.val.C==='0.6%');
T('F4b 显示=值以、相连', r.disp==='8%、1.5%、0.6%');
r=PB('2025年上涨((A == 8%))，同比((B == 1.5%))');
T('F4c 行文键值抽取', r.ok&&r.ch==='kv'&&r.val.A==='8%'&&r.val.B==='1.5%');

/* ── fail-closed ── */
r=PB('((8%), 1.5%');  T('FC1 未闭合', !r.ok);
r=PB('(( ))');         T('FC2 空', !r.ok);
r=PB('a, ((b))');      T('FC3 直写混行文', !r.ok);
r=PB('a, ((b == 1))'); T('FC3b 直写混行文kv', !r.ok);
r=PB('((A == 1)), ((b))'); T('FC4 行文混用', !r.ok);
r=PB('A == 1, 纯文本段'); T('FC5 键值向量混无==段', !r.ok);

/* ── 表格型 ── */
const TBL='|职务|名称|年龄|'+NL+'|:-|:-|:-|'+NL+'|总经理|tony|59|'+NL+'|秘书|lily|18|';
let t=mdeParseTable('2','(2x2)',TBL);
T('TB1 :2(2x2) 坐标裁剪', t.ok&&JSON.stringify(t.val)===JSON.stringify([['tony','59'],['lily','18']]));
t=mdeParseTable('2','()',TBL);
T('TB2 空括号全表', t.ok&&JSON.stringify(t.val)===JSON.stringify([['职务','名称','年龄'],['总经理','tony','59'],['秘书','lily','18']]));
t=mdeParseTable('3','(2x2)',TBL+NL+NL+TBL);
T('TB3 :3 双表三层嵌套', t.ok&&t.val.length===2&&JSON.stringify(t.val[1])===JSON.stringify([['tony','59'],['lily','18']]));
t=mdeParseTable('2','(2x2)',TBL+NL+NL+TBL);
T('TB4 :2 多表 fail', !t.ok);
t=mdeParseTable('2','(9x9)',TBL);
T('TB5 坐标越界 fail', !t.ok);
t=mdeParseTable('2',null,TBL);
T('TB6 缺括号 fail', !t.ok);
t=mdeParseTable('2','(2x2)','|a|b|'+NL+'非表格行');
T('TB7 非表格行 fail', !t.ok);
t=mdeParseTable('2','(1x1)','|a|b'+BS+'|c|d|'+NL+'|:-|:-|'+NL+'|x|y|z|w|');
T('TB8 转义与补齐', t.ok&&t.val[0][1]==='b|c'&&t.val[1][2]==='z'&&t.val[1][3]==='w'&&t.val[0][3]===''&&t.val[0].length===4);

/* ── parseMarkdown 集成 ── */
let h=P('@@ MDE_甲{8%,1.5%}');
T('PM1 向量 span + data-dp-val', h.indexOf('data-dp-val=')>0&&h.indexOf('data-dp-alias="甲"')>0);
h=P('@@ MDE_甲{A == 1, B == 2}');
T('PM2 键值向量 span', h.indexOf('data-dp-val=')>0);
h=P('值：@@ MDE_{x == 3} 个');
T('PM3 兼容单键值', h.indexOf('>3<')>0);
h=P('@@ MDE_甲{a, ((b))}');
T('PM4 fail-closed 原文保留', h.indexOf('mde-dp')<0&&h.indexOf('((b))')>0);
/* 表格块 */
const TB='@@ MDE_甲:2(2x2){'+NL+'|职务|名称|年龄|'+NL+'|:-|:-|:-|'+NL+'|总经理|tony|59|'+NL+'|秘书|lily|18|'+NL+'}';
h=P(TB);
T('PM5 表格块 span+摘要', h.indexOf('data-dp-val=')>0&&h.indexOf('[数据表 2×2]')>=0);
T('PM6 表格值进 data-dp-val', h.indexOf('tony')>0&&h.indexOf('%22tony%22')>0||h.indexOf('tony')>0&&h.indexOf('&quot;')>0);
/* 执行点 global */
h=P('@@ MDE import 序号 is zzz{global p}');
T('PM7 global 执行点', h.indexOf('data-run-global="p"')>0&&h.indexOf('mde-run-global')>0);
h=P('@@ MDE from utils import add{global q}');
T('PM8 from+global', h.indexOf('data-run-global="q"')>0&&h.indexOf('data-run-fn="add"')>0);
/* 标记 */
h=P('台风'+TRI+'p 出现，扰动'+TRI+'p 结束');
T('PM9 标记 span', (h.match(/mde-mark/g)||[]).length===2&&h.indexOf('data-mark="p"')>0);
/* 行内代码内 ''' 不识别 */
h=P('代码 `a'+TRI+'b` 结束');
T('PM10 行内代码保护', h.indexOf('mde-mark')<0);

console.log(n+' tests, '+f+' failures');
if(f>0){process.exit(1);}
"""

open(os.path.join(HERE, "_tmp_v26.js"), "w", encoding="utf-8").write(
    m.group(1) + TESTS)
r = subprocess.run(["node", "_tmp_v26.js"], capture_output=True, text=True,
                   encoding="utf-8")
os.remove(os.path.join(HERE, "_tmp_v26.js"))
print(r.stdout)
if r.stderr:
    print("ERR:", r.stderr[:400])