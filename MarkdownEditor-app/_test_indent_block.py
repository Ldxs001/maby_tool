# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""<<< 缩进包围块测试（v2.1）：
- 继承链只流容器级：顶层段落(p 档)/列表(li 档)/引用(quote 档)更新 curInd；空行/标题/围栏/hr/表格清零
- <<< 冻结 curInd 为块内左边界；块内封闭（正文 text-indent 不进链）；闭合后 += 容器级叠加(max)
- 开闭同符号状态翻转、不支持嵌套；未闭合 fail-closed（字面保留）；标记行吞掉
前端部分从 markdown-editor.html 提取 /*PARSER_START*/../*PARSER_END*/ 段跑 node。
"""
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "markdown-editor.html")


def js_part():
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r"/\*PARSER_START\*/(.*?)/\*PARSER_END\*/", src, re.S)
    assert m, "PARSER segment not found"
    harness = "globalThis.window={__IND_PX__:{p:2,quote:1,li:2}};\n" + m.group(1) + r"""
const NL=String.fromCharCode(10);
let fails=0;
function block(src){ // 返回所有 ind-blk 的 margin 值数组（px，v2.2.1 起正文字号基准）
  const out=parseMarkdown(src);
  const ms=[...out.matchAll(/class="ind-blk" style="margin-left:([0-9.]+)px"/g)].map(x=>x[1]);
  return {out,ms};
}
function ck(name,cond,extra){
  if(cond){console.log('PASS '+name);}else{fails++;console.log('FAIL '+name+' | '+(extra||''));}
}
/* 1) 顶层段落(2em) 紧邻 <<< → 继承 2em；块内列表叠加 li=2 → 4em */
let r=block('正文一段'+NL+'<<<'+NL+'1. a'+NL+'2. b'+NL+'<<<'+NL);
ck('inherit from paragraph (div=curInd only)', r.ms.length===1 && r.ms[0]==='2', JSON.stringify(r.ms));
/* 2) 空行打断 → 0em */
r=block('正文一段'+NL+NL+'<<<'+NL+'1. a'+NL+'<<<'+NL);
ck('blank resets to 0', r.ms.length===1 && r.ms[0]==='0', JSON.stringify(r.ms));
/* 3) 块内正文封闭：正文 text-indent 不进链，第二块仍继承 2em */
r=block('正文一段'+NL+'<<<'+NL+'块内一段话'+NL+'<<<'+NL+'<<<'+NL+'1. a'+NL+'<<<'+NL);
ck('inner paragraph sealed, chain 2->2', r.ms.length===2 && r.ms[0]==='2' && r.ms[1]==='2', JSON.stringify(r.ms));
/* 4) 块内列表叠加(li=2)：块 margin 4em；下一块继承 4em */
r=block('正文一段'+NL+'<<<'+NL+'1. a'+NL+'<<<'+NL+'<<<'+NL+'1. b'+NL+'<<<'+NL);
ck('ladder: div 2->4 (curInd carries overlay)', r.ms.length===2 && r.ms[0]==='2' && r.ms[1]==='4', JSON.stringify(r.ms));
/* 5) 块内引用叠加(quote=1)：2+1=3em */
r=block('正文一段'+NL+'<<<'+NL+'> 引用一句'+NL+'<<<'+NL);
ck('quote block margin = curInd only', r.ms.length===1 && r.ms[0]==='2', JSON.stringify(r.ms));
/* 6) 未闭合 fail-closed：<<< 字面保留（escapeHtml 转义），无 ind-blk */
r=block('正文一段'+NL+'<<<'+NL+'后面没有闭合');
ck('unclosed fail-closed literal', r.ms.length===0 && r.out.indexOf('&lt;&lt;&lt;')>=0, r.out.slice(0,120));
/* 7) 标记行吞掉：闭合块输出不含独立 <<< 段落 */
ck('markers swallowed', (r2=>r2.out.indexOf('<p>&lt;&lt;&lt;</p>')<0)(block('<<<'+NL+'内容'+NL+'<<<'+NL)));
/* 8) 标题清零：标题后 <<< 从 0 起步 */
r=block('正文一段'+NL+'# 大标题'+NL+'<<<'+NL+'1. a'+NL+'<<<'+NL);
ck('heading resets', r.ms.length===1 && r.ms[0]==='0', JSON.stringify(r.ms));
/* 9) 空行打断两个连续块的阶梯：A(2+2=4) 后空行，B 从 0 起 */
r=block('正文一段'+NL+'<<<'+NL+'1. a'+NL+'<<<'+NL+NL+'<<<'+NL+'1. b'+NL+'<<<'+NL);
ck('blank breaks ladder', r.ms.length===2 && r.ms[0]==='2' && r.ms[1]==='0', JSON.stringify(r.ms));
/* 10) 回归：列表编号接力不受影响 */
const lst=parseMarkdown('1. a'+NL+'2. b'+NL+NL+'1. c'+NL);
ck('ol relay regression', lst.indexOf('start="1"')>=0 || lst.indexOf('<ol>')>=0, lst.slice(0,100));
console.log('FAILS='+fails);
"""
    tmp = os.path.join(HERE, "_tmp_indent.js")
    open(tmp, "w", encoding="utf-8").write(harness)
    r = subprocess.run(["node", tmp], capture_output=True, text=True)
    os.remove(tmp)
    out = r.stdout
    print(out.rstrip())
    if r.stderr.strip():
        print("STDERR:", r.stderr[:300])
    n_fail = len(re.findall(r"^FAIL ", out, re.M)) + (
        0 if re.search(r"^FAILS=0$", out, re.M) else 1)
    n_pass = len(re.findall(r"^PASS ", out, re.M))
    print("%s indent-block cases (%d pass / %d fail)" % (
        "PASS" if (n_fail == 0 and n_pass >= 10) else "FAIL", n_pass, n_fail))
    return n_fail == 0 and n_pass >= 10


if __name__ == "__main__":
    ok = js_part()
    raise SystemExit(0 if ok else 1)
