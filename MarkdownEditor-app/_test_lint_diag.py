# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_test_lint_diag.py -- 语法诊断（lint）回归测试（v2.22.0）

原则与口径：
  1. lint 与渲染同源：诊断由 PARSER core 的 fail-closed 降级分支直接上报
     （parseMarkdown(src,0,{diag:[]})），本测试验证每类降级都有诊断、
     诊断行号=文档绝对行（1-based）、且**全方言干净文档零诊断**（无误报）；
  2. lint 不改变渲染：带 diag 收集与不带的渲染输出逐字节一致；
  3. 输出只有 PASS / FAIL；exit 0 = PASS。

跑法：从 markdown-editor.html 提取 /*PARSER_START*/../*PARSER_END*/ 段
拼 node 脚本执行（与 _test_list_parse.py 同款）。
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "markdown-editor.html")
JS = os.path.join(HERE, "_tmp_lint_diag.js")

HARNESS = r"""
/* ---- lint 用例 ---- */
function lint(src){
  var arr=[];
  parseMarkdown(src,0,{diag:arr});
  return arr;
}
var CASES=[
  // [名, 源文, 期望[{code,line}]（null=只要求零诊断）]
  ['干净文档·全方言·零诊断',
   "# 大标题\n\n正文一段，含 *强调* 与 `代码`。\n\n+ 实心点项\n- 空心圈项\n1. 有序项\n\n| 列A | 列B |\n|---|---|\n| 1 | 2 |\n\n@@ caption{t} 表 1　示例\n| 列A | 列B |\n|---|---|\n| 1 | 2 |\n\n@@ blank{1.5}\n\n```js\nconsole.log(1);\n```\n\n<<<\n包围块内容\n<<<\n\n> 引用一行\n\n@@ begin fill{50|50}\n左栏\n\n右栏\n@@ end fill\n\n@@ begin color #c0392b\n着色内容\n@@ end color\n\n@@ begin full{m}\n独占页内容\n@@ end full\n\n@@ begin page{noll}\n页区内容\n@@ end page\n\n@@ MDE__{a == 3}\n\n@@ MDE_{a}\n\n@@ MDE_{甲 == 1}\n\n@@ MDE_甲{b == 2}\n\n@@ MDE__甲{c == 3}\n\n@@ MDE_{x, ((y))}\n",
   null],
  ['fill 比例段数≠栏数 → D202',
   "@@ begin fill{50|25|25}\n甲\n\n乙\n@@ end fill\n",
   [{code:'D202',line:1}]],
  ['fill 比例和≠100 → D202',
   "@@ begin fill{50|30}\n甲\n\n乙\n@@ end fill\n",
   [{code:'D202',line:1}]],
  ['fill 值越界 → D202',
   "@@ begin fill{50|120}\n甲\n\n乙\n@@ end fill\n",
   [{code:'D202',line:1}]],
  ['fill 无参栏数>4 → D202',
   "@@ begin fill\n甲\n\n乙\n\n丙\n\n丁\n\n戊\n@@ end fill\n",
   [{code:'D202',line:1}]],
  ['fill 未闭合 → D203',
   "@@ begin fill\n甲栏\n",
   [{code:'D203',line:1}]],
  ['fill 内嵌同族对（零宽）→ 外层按 1 栏 fail → D202+D204',
   "@@ begin fill\n@@ begin fill\n甲\n@@ end fill\n@@ end fill\n",
   [{code:'D202',line:1},{code:'D204',line:2}]],
  ['full 套 full → D204',
   "@@ begin full\n@@ begin full\n甲\n@@ end full\n@@ end full\n",
   [{code:'D204',line:2}]],
  ['page 套 page → D204',
   "@@ begin page{noll}\n@@ begin page{noll}\n甲\n@@ end page\n@@ end page\n",
   [{code:'D204',line:2}]],
  ['page 参数非法 → D232 + 尾 end 孤儿 → D401',
   "@@ begin page{abc}\n甲\n@@ end page\n",
   [{code:'D232',line:1},{code:'D401',line:3}]],
  ['page 未闭合 → D233',
   "@@ begin page{1}\n甲\n",
   [{code:'D233',line:1}]],
  ['color 色值非法 → D211',
   "@@ begin color nosuchcolor\n甲\n@@ end color\n",
   [{code:'D211',line:1}]],
  ['color 未闭合 → D212',
   "@@ begin color red\n甲\n",
   [{code:'D212',line:1}]],
  ['<<< 未闭合 → D101',
   "前文\n\n<<<\n没闭合\n",
   [{code:'D101',line:3}]],
  ['<<< 行尾带内容 → D102(warn)',
   "<<< 缩进内容\n",
   [{code:'D102',line:1}]],
  ['fence 未闭合 → D103(warn)',
   "```js\nvar a=1;\n",
   [{code:'D103',line:1}]],
  ['孤 end → D401',
   "正文。\n\n@@ end fill\n",
   [{code:'D401',line:3}]],
  ['begin 无值/坏家族 → D402',
   "@@ begin color\n甲\n",
   [{code:'D402',line:1}]],
  ['caption 不跟表格 → D403',
   "@@ caption{t} 表 1　X\n后面不是表格\n",
   [{code:'D403',line:1}]],
  ['blank n=0 → D404',
   "@@ blank{0}\n正文\n",
   [{code:'D404',line:1}]],
  ['MDE 数据点未闭合 → D301',
   "前文\n\n@@ MDE_{\n没闭合\n",
   [{code:'D301',line:3}]],
  ['MDE 内容违规（行文混直写）→ D302',
   "@@ MDE_{\na, ((b))\n}\n",
   [{code:'D302',line:1}]],
  ['并写顺序错 → D241 + 尾 end 孤儿 → D401',
   "@@ begin color red full\n甲\n@@ end full color\n",
   [{code:'D241',line:1},{code:'D401',line:3}]],
  ['单家族 begin 配双家族 end → 块未闭合 D222 + 孤 end D401',
   "@@ begin full\n甲\n@@ end full color\n",
   [{code:'D222',line:1},{code:'D401',line:3}]],
  ['行号=绝对行（前导 5 行 + 同族嵌套）',
   "l1\nl2\nl3\nl4\nl5\n@@ begin fill\n@@ begin fill\n甲\n@@ end fill\n@@ end fill\n",
   [{code:'D202',line:6},{code:'D204',line:7}]],
  ['lint 不改变渲染输出',
   "@@ begin fill{50|30}\n甲\n\n乙\n@@ end fill\n\n<<<\n没闭合\n",
   'RENDER_SAME'],
  ['干净片段（无方言）零诊断',
   "普通文本。\n\n- 列表项\n\n第二段。\n",
   null]
];

var fails=0,total=0;
CASES.forEach(function(c){
  total++;
  var name=c[0],src=c[1],exp=c[2];
  var got;
  try{ got=lint(src); }catch(e){ console.log('FAIL '+name+' | 解析抛异常: '+e.message); fails++; return; }
  if(exp==='RENDER_SAME'){
    var a=parseMarkdown(src,0),b=parseMarkdown(src,0,{diag:[]});
    if(a===b){ console.log('PASS '+name); }else{ console.log('FAIL '+name+' | 渲染输出不一致'); fails++; }
    return;
  }
  var want=exp?exp.map(function(x){return x.code+'@'+x.line;}).sort().join(','):'' ;
  var have=got.map(function(x){return x.code+'@'+x.line;}).sort().join(',');
  if(want===have){ console.log('PASS '+name); }
  else{ console.log('FAIL '+name+' | 期望['+want+'] 实得['+have+']'); fails++; }
});
console.log('合计 '+total+' 条：PASS '+(total-fails)+' / FAIL '+fails);
if(fails){ throw new Error('lint cases failed'); }
"""

def main():
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r"/\*PARSER_START\*/(.*?)/\*PARSER_END\*/", src, re.S)
    if not m:
        print("FAIL parser segment not found")
        return 1
    js = m.group(1) + "\n" + HARNESS + "\n"
    open(JS, "w", encoding="utf-8").write(js)
    r = subprocess.run(["node", JS], capture_output=True, text=True, encoding="utf-8", cwd=HERE)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    ok = r.returncode == 0 and "FAIL 0" in out
    try:
        os.remove(JS)
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
