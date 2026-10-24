/* md-parser.test.cjs — 抽取版解释器回归测试（Node CommonJS）
 * 覆盖 MDEditor 全部方言语法：基础排版 + low runner（数据点 / 执行点 / 标记）+ 上下标。
 * 运行：node md-parser.test.cjs
 *
 * 说明：
 *   1. 公式 $...$ 与图表真实出图由 UI 层（extractMath / renderDiagrams）处理，
 *      本解释器（parseMarkdown）只产出结构化 HTML：公式原样保留、图表出占位。
 *   2. 独立调用 parseMarkdown 时，行内语法按 CommonMark 反斜杠转义（\, → ,）。
 *   3. 已知缺陷（未纳入断言，详见文件末 KNOWN BUGS）：未闭合数据点会死循环。
 */
const P = require('./md-parser.js');
const { parseMarkdown, parseInline } = P;

let pass = 0, fail = 0;
function t(name, fn) {
  let ok = false, note = '';
  try { ok = fn() === true; } catch (e) { ok = false; note = '  ← ' + e.message; }
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (ok ? '' : note));
  ok ? pass++ : fail++;
}
function section(title) { console.log(''); console.log('— ' + title + ' —'); }

/* ===== 属性取值 / 解码 ===== */
function attrOf(html, name) {
  const m = html.match(new RegExp(name + '="([^"]*)"'));
  return m ? m[1] : null;
}
function dec(s) {
  return s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
/* data-dp-val → {ch, val}；无该属性（fail-closed）→ null */
function dpOf(html) {
  const raw = attrOf(html, 'data-dp-val');
  return raw === null ? null : JSON.parse(dec(raw));
}
function j(v) { return JSON.stringify(v); }

/* ============================================================
 * 一、基础排版方言（v2.0 起）
 * ============================================================ */
const baseSrc = [
  '# 标题', '',
  '**粗** 与 *斜* 与 ~~删~~ 与 `code` 与 [链接](http://x.com)', '',
  '+ 实心项', '- 空心项', '* 这不是列表（斜体）*', '',
  '- [x] 已办任务', '- [ ] 未办任务', '',
  '1. 一', '2. 二', '3. 三', '',
  '```python', 'def f(): return 1', '```', '',
  '```mermaid {40c}', 'graph TD; A-->B', '```', '',
  '```dot', 'digraph G { a->b }', '```', '',
  '```vega', '{"$schema":"https://vega.github.io/schema/vega/v5.json"}', '```', '',
  '| 左 | 右 | 中 |', '| :--- | ---: | :---: |', '| a | b | c |', '',
  '![图](a.png){30c}', '',
  '@@ begin fill {50|50}', '![左](l.png){50}', '', '![右](r.png){50}', '@@ end fill', '',
  '<<<', '被缩进包围的内容', '<<<', '',
  '行内公式 $E=mc^2$ 与块级 $$ \\sum_i x_i $$ 由 UI 层处理。'
].join('\n');
const bh = parseMarkdown(baseSrc);

section('一、基础排版方言');
t('标题 <h1>', () => /<h1>标题<\/h1>/.test(bh));
t('粗体 <strong>', () => /<strong>粗<\/strong>/.test(bh));
t('斜体 <em>', () => /<em>斜<\/em>/.test(bh));
t('删除 <del>', () => /<del>删<\/del>/.test(bh));
t('行内代码 <code>', () => /<code>code<\/code>/.test(bh));
t('链接 target=_blank', () => /<a href="http:\/\/x\.com"[^>]*target="_blank"/.test(bh));
t('列表 + 实心 u-solid', () => /class="u-solid"/.test(bh));
t('列表 - 空心 u-hollow', () => /class="u-hollow"/.test(bh));
t('星号不作列表（纯斜体）', () => !/<li[^>]*>\* 这不是列表/.test(bh) && /<em> 这不是列表（斜体）<\/em>/.test(bh));
t('任务列表 checked', () => /<li class="task"><input type="checkbox" disabled checked>/.test(bh));
t('任务列表 unchecked', () => /<li class="task"><input type="checkbox" disabled>/.test(bh));
t('有序接力 <ol>', () => /<ol/.test(bh));
t('代码块 lang-python', () => /<pre><code class="lang-python">/.test(bh));
t('图表 mermaid 占位', () => /data-diagram="mermaid"/.test(bh));
t('图表 mermaid 宽度40%', () => /style="width:40%"/.test(bh));
t('图表 mermaid 对齐 center', () => /data-diagram-align="center"/.test(bh));
t('图表 dot 占位', () => /data-diagram="dot"/.test(bh));
t('图表 vega 占位', () => /data-diagram="vega"/.test(bh));
t('图表 data-code 编码', () => /data-code="/.test(bh));
t('表格 th 居中', () => /<th style="text-align:center">中<\/th>/.test(bh));
t('表格 td 右对齐', () => /<td style="text-align:right">b<\/td>/.test(bh));
t('表格 td 左对齐', () => /<td style="text-align:left">a<\/td>/.test(bh));
t('图片 {30c} 宽度30%', () => /width:30%/.test(bh) && /<img src="a\.png"/.test(bh));
t('图片 {30c} 居中', () => /margin-left:auto !important;margin-right:auto !important/.test(bh));
t('分栏 fill-row', () => /class="fill-row"/.test(bh));
t('分栏 fill-col 50%', () => /class="fill-col" style="width:50%"/.test(bh));
t('缩进块 ind-blk', () => /class="ind-blk" style="margin-left:/.test(bh));
t('行内公式原样保留', () => bh.includes('$E=mc^2$'));

/* ============================================================
 * 二、low runner 数据点（v2.6 六形式 + 四种池名 + fail-closed）
 *    产出：<span class="mde-dp" data-dp data-dp-alias data-dp-val>
 *    data-dp-val = {"ch":"kv"|"vals", "val": …}
 * ============================================================ */
section('二、数据点 · 六形式');

t('形式1 单值文本（无逗号无 ==）→ vals 字符串', () => {
  const h = parseInline('@@ MDE_{本月累计增长}');
  const v = dpOf(h);
  return v.ch === 'vals' && v.val === '本月累计增长' && h.includes('>本月累计增长</span>');
});

t('形式2 单键值对 → kv 对象 + 只显示值', () => {
  const h = parseInline('@@ MDE_{a == 3}');
  const v = dpOf(h);
  return v.ch === 'kv' && j(v.val) === '{"a":"3"}' && h.includes('>3</span>');
});

t('形式3 纯值向量 → vals 数组', () => {
  const v = dpOf(parseInline('@@ MDE_{1,2,3}'));
  return v.ch === 'vals' && j(v.val) === '["1","2","3"]';
});

t('形式4 键值对向量 → kv 多对', () => {
  const h = parseInline('@@ MDE_{a == 1,b == 2}');
  const v = dpOf(h);
  return v.ch === 'kv' && j(v.val) === '{"a":"1","b":"2"}' && h.includes('>1、2</span>');
});

t('行进抽取 ((v)) → vals 数组 + 显示去标记', () => {
  const h = parseInline('@@ MDE_{同比 ((12.5%)) 环比 ((3.1%))}');
  const v = dpOf(h);
  return v.ch === 'vals' && j(v.val) === '["12.5%","3.1%"]'
    && h.includes('>同比 12.5% 环比 3.1%</span>');
});

t('行进抽取 ((k == v)) → kv 对象', () => {
  const h = parseInline('@@ MDE_{本月 ((收入 == 120)) 万元}');
  const v = dpOf(h);
  return v.ch === 'kv' && j(v.val) === '{"收入":"120"}' && h.includes('>120</span>');
});

t('形式5 表格 :2 坐标裁剪 → 二维（屏幕仍显示整张原表）', () => {
  const h = parseMarkdown([
    '@@ MDE_:2(2x2){', '| 名称 | 数值 |', '| --- | --- |',
    '| 甲 | 1 |', '| 乙 | 2 |', '}'
  ].join('\n'));
  const v = dpOf(h);
  const cells = ['名称', '数值', '甲', '乙'];
  return v.ch === 'vals'
    && j(v.val) === '[["1"],["2"]]'          // 数据只给裁剪区
    && /^<div class="mde-dp mde-dp-block"/.test(h)
    && h.includes('<table>')
    && cells.every(c => h.includes('>' + c + '<'))   // 显示整张原表
    && !h.includes('[数据表');               // 不再造尺寸标签
});

t('形式5 表格 :2() 全表 → 含表头三行', () => {
  const h = parseMarkdown([
    '@@ MDE_:2(){', '| 名称 | 数值 |', '| --- | --- |',
    '| 甲 | 1 |', '| 乙 | 2 |', '}'
  ].join('\n'));
  const v = dpOf(h);
  return j(v.val) === '[["名称","数值"],["甲","1"],["乙","2"]]'
    && (h.match(/<tr>/g) || []).length === 3;
});

const t3html = parseMarkdown([
  '@@ MDE_:3(){', '| a | b |', '| - | - |', '| 1 | 2 |', '',
  '| c | d |', '| - | - |', '| 3 | 4 |', '}'
].join('\n'));

t('形式6 表格 :3 多表 → 三层数据', () => {
  const v = dpOf(t3html);
  return v.ch === 'vals'
    && j(v.val) === '[[["a","b"],["1","2"]],[["c","d"],["3","4"]]]';
});

t('[BUG-3] 形式6 :3 → 渲染成两张真表格', () => {
  const n = (t3html.match(/<table>/g) || []).length;
  return n === 2 && !t3html.includes('[数据块');
});

t('表格型显性/隐性只差一个下划线：显性出表格、隐性整块不渲染', () => {
  const body = ['| a | b |', '| - | - |', '| 1 | 2 |'];
  const on = parseMarkdown(['@@ MDE_:2(){'].concat(body, ['}']).join('\n'));
  const off = parseMarkdown(['@@ MDE__:2(){'].concat(body, ['}']).join('\n'));
  const dp = k => (k.match(/data-dp-val="[^"]*"/) || [''])[0];
  return on.includes('<table>') && on.includes('mde-dp-block')
    && !off.includes('<table>')                     // 隐性不产出任何可见内容
    && off.includes('mde-dp-hidden')
    && dp(on) === dp(off);                          // 两者交给 run 的数据完全相同
});

t('表格型缺分隔行也渲染成表格（结构行自动补，可见字符不动）', () => {
  const h = parseMarkdown(['@@ MDE_:2(){', '| 项目 | 一月 |', '| 收入 | 100 |', '}'].join('\n'));
  return h.includes('<table>') && h.includes('<th>项目</th>') && h.includes('<td>收入</td>')
    && !h.includes('| 项目 | 一月 |');            // 竖线不残留在屏幕上
});

t('表格型是块级元素：不套在 <p> 里（否则 HTML 会提前闭合 p）', () => {
  const h = parseMarkdown(['@@ MDE_:2(){', '| a | b |', '| - | - |', '| 1 | 2 |', '}'].join('\n'));
  return /^<div class="mde-dp mde-dp-block"/.test(h) && !/<p><div/.test(h);
});

t('跨行数据点（形式1 长文本）', () => {
  const h = parseMarkdown([
    '@@ MDE_{2024 年营收 ((12.3 亿))，', '全年同比 ((+8%))}'
  ].join('\n'));
  const v = dpOf(h);
  return v && v.ch === 'vals' && j(v.val) === '["12.3 亿","+8%"]' && /^<p><span class="mde-dp"/.test(h);
});

section('三、数据点 · 四种池名 / fail-closed');

t('公共显性 @@ MDE_{} → 可见', () => {
  const h = parseInline('@@ MDE_{a == 3}');
  return /class="mde-dp"/.test(h) && !/mde-dp-hidden/.test(h) && !/display:none/.test(h);
});

t('公共隐性 @@ MDE__{} → display:none', () => {
  const h = parseInline('@@ MDE__{a == 3}');
  return /class="mde-dp mde-dp-hidden" style="display:none"/.test(h) && h.includes('></span>');
});

t('别名显性 @@ MDE_甲{} → data-dp-alias=甲', () => {
  const h = parseInline('@@ MDE_甲{a == 3}');
  return attrOf(h, 'data-dp-alias') === '甲' && !/mde-dp-hidden/.test(h);
});

t('别名隐性 @@ MDE__甲{} → 隐性 + 别名', () => {
  const h = parseInline('@@ MDE__甲{a == 3}');
  return attrOf(h, 'data-dp-alias') === '甲' && /mde-dp-hidden/.test(h);
});

t('data-dp 存原文（URI 编码）', () => {
  const h = parseInline('@@ MDE_{a == 3}');
  return attrOf(h, 'data-dp') === encodeURIComponent('a == 3');
});

t('[BUG-2] fail-closed 直写与行进混用 → 原文不动', () => {
  const h = parseInline('@@ MDE_{a, ((b))}');
  return h === '@@ MDE_{a, ((b))}' && !h.includes('mde-dp');
});

t('[BUG-2] fail-closed 键值向量有段缺 == → 原文不动', () => {
  const h = parseInline('@@ MDE_{a == 1,b}');
  return h === '@@ MDE_{a == 1,b}' && !h.includes('mde-dp');
});

t('[BUG-2] fail-closed 行进未闭合 (( → 原文不动', () => {
  const h = parseInline('@@ MDE_{同比 ((12.5%}');
  return !h.includes('mde-dp') && h.includes('@@ MDE_{同比');
});

/* ============================================================
 * 四、执行点（import / from … import / is 别名 / {global 标记}）
 *    产出：<span class="mde-run" data-run-mod data-run-fn data-run-alias
 *          data-run-global data-run-orig>
 * ============================================================ */
section('四、执行点');

t('公共 import：模块 / 函数默认 run / 无别名', () => {
  const h = parseInline('@@ MDE import stats');
  return /class="mde-run"/.test(h)
    && attrOf(h, 'data-run-mod') === 'stats'
    && attrOf(h, 'data-run-fn') === 'run'
    && attrOf(h, 'data-run-alias') === '';
});

t('from … import …：模块与函数分开取', () => {
  const h = parseInline('@@ MDE from 数据源 import 汇总');
  return attrOf(h, 'data-run-mod') === '数据源' && attrOf(h, 'data-run-fn') === '汇总';
});

t('is 别名 → data-run-alias', () => {
  const h = parseInline('@@ MDE from stats import run is 甲');
  return attrOf(h, 'data-run-alias') === '甲';
});

t('可见执行点占位 …', () => {
  const h = parseInline('@@ MDE import stats');
  return h.includes('>…</span>') && !/mde-run-global/.test(h);
});

t('{global p} → mde-run-global + 无占位 + 不写内联 display:none', () => {
  const h = parseInline('@@ MDE import stats {global p}');
  return /mde-run-global/.test(h)
    && attrOf(h, 'data-run-global') === 'p'
    && !h.includes('>…</span>')
    && !/style="display:none"/.test(h);
});

t('data-run-orig 存原文（URI 编码）', () => {
  const h = parseInline('@@ MDE import stats');
  return attrOf(h, 'data-run-orig') === encodeURIComponent('@@ MDE import stats');
});

/* ============================================================
 * 五、'''标记（配合 {global p} 使用）
 *    产出：<span class="mde-mark" data-mark="p">'''p</span>
 * ============================================================ */
section('五、三引号标记');

t('行内 \'\'\'名称 → mde-mark', () => {
  const h = parseInline('\'\'\'p 的实例内容');
  return /class="mde-mark" data-mark="p"/.test(h) && h.includes('\'\'\'p');
});

t('中文标记名', () => {
  const h = parseInline('\'\'\'第一段');
  return attrOf(h, 'data-mark') === '第一段';
});

t('代码围栏内 \'\'\' 不转标记', () => {
  const h = parseMarkdown(['```text', '\'\'\'p 原样', '```'].join('\n'));
  return h.includes('\'\'\'p 原样') && !h.includes('mde-mark');
});

/* ============================================================
 * 六、上下标（v2.6.10，LaTeX 写法但不加 $）
 *    ^{任意内容} → <sup>、_{任意内容} → <sub>
 * ============================================================ */
section('六、上下标');

t('上标 ^{1}', () => parseInline('a^{1}') === 'a<sup>1</sup>');
t('上标 ^{[1]}（引用编号）', () => parseInline('引用^{[1]}') === '引用<sup>[1]</sup>');
t('上标 ^{世界之光}（中文）', () => parseInline('x^{世界之光}') === 'x<sup>世界之光</sup>');
t('下标 _{2}', () => parseInline('H_{2}O') === 'H<sub>2</sub>O');
t('上下标连写', () => parseInline('v_{max}^{2}') === 'v<sub>max</sub><sup>2</sup>');
t('a^b 不带花括号 → 原位', () => parseInline('a^b') === 'a^b');
t('^{未闭合 → 原位', () => parseInline('a^{b') === 'a^{b');
t('\\^{1} 转义 → 字面', () => parseInline('\\^{1}') === '^{1}');
t('多个下标不被 _.._ 斜体吃掉', () => parseInline('x_{a} 与 y_{b}') === 'x<sub>a</sub> 与 y<sub>b</sub>');
t('行内代码内 ^{1} 不解析', () => parseInline('`x^{1}`') === '<code>x^{1}</code>');
t('正文段落内生效', () => parseMarkdown('速度 v_{max}^{2}，单位 m/s^{2}').includes('<sub>max</sub><sup>2</sup>'));
t('表格单元格内生效', () => parseMarkdown('| 量 |\n| --- |\n| m^{2} |').includes('<th>量</th>') &&
  parseMarkdown('| 量 |\n| --- |\n| m^{2} |').includes('<td>m<sup>2</sup></td>'));

/* ============================================================
 * 七、导出面（供外部调用 / 改造）
 * ============================================================ */
section('七、导出面');
t('9 个导出函数齐备', () => ['parseMarkdown', 'parseInline', 'parseList', 'parseTable',
  'parseFenceLang', 'splitRow', 'escapeHtml', 'escAttr', 'sanitizeUrl'
].every(k => typeof P[k] === 'function'));
t('parseMarkdown(src, {indents}) 第二参生效（列表档叠加到下一个容器）', () => {
  const s = ['<<<', '+ 项', '<<<', '<<<', '内层', '<<<'].join('\n');
  const a = parseMarkdown(s);
  const b = parseMarkdown(s, { indents: { p: 0, quote: 0, li: 40 } });
  return a.split('margin-left:40px').length === 1 && b.includes('margin-left:40px');
});

/* ============================================================
 * 八、未闭合数据点 fail-closed（BUG-1 回归：不许死循环）
 *    条件：行首 @@ MDE…{ 且该行之后全文再无 }。修复前 parseMarkdown 在本段
 *    无限空转（浏览器 = 打开文件即卡死）；修复后该行按普通文本渲染。
 *    注意：这些断言本身就是防呆——若退回死循环，测试会挂住而不是 FAIL，
 *    所以外跑请带超时：timeout 60 node md-parser.test.cjs
 * ============================================================ */
section('八、未闭合数据点 fail-closed');

t('未闭合数据点：原文保留、不卡死', () =>
  parseMarkdown('@@ MDE_{a == 3') === '<p>@@ MDE_{a == 3</p>');

t('未闭合表格型：原文保留、不卡死', () => {
  const h = parseMarkdown(['@@ MDE_:2(2x2){', '| a | b |'].join('\n'));
  return h.startsWith('<p>@@ MDE_:2(2x2){</p>') && h.includes('| a | b |');
});

t('未闭合后接正文：正文不被吞', () => {
  const h = parseMarkdown(['@@ MDE_{a == 3', '', '正文', '第二段'].join('\n'));
  return h.includes('@@ MDE_{a == 3') && h.includes('正文') && h.includes('第二段');
});

t('未闭合在文档中间、下文另有 } → 不丢正文', () => {
  const h = parseMarkdown(['@@ MDE_{a == 3', '', '@@ MDE_{b == 4}', '', '正文'].join('\n'));
  return h.includes('正文');
});

console.log('');
console.log('合计 ' + (pass + fail) + ' 条：PASS ' + pass + ' / FAIL ' + fail);
console.log(pass && !fail ? '✅ ALL CORE CHECKS PASS' : '❌ SOME CHECKS FAILED');

/* ============================================================
 * 历史缺陷留档（v2.6.11 已修，断言见「八」段）
 *
 * BUG-1 未闭合数据点死循环 —— 行首 @@ MDE…{ 且该行之后全文再无 } 时，
 *   段落兜底分支在守卫处 break、para 为空却不推进 i，回到同一行无限空转
 *   （浏览器 = 打开文件即卡死）。修法：兜底处 if(!para.length){para.push(lines[i]);i++;}
 * BUG-2 fail-closed 原文被上下标吃掉 —— return m 没进占位符，_ {…} 变 <sub>。
 *   修法：toks.push(escapeHtml(m)) 后再返回占位符。
 * BUG-3 :3 标签恒不出现 —— tbl.dim 是字符串 '3'，写成 ===3 恒 false。
 *   修法：String(tbl.dim)==='3'。
 * ============================================================ */

process.exit(fail ? 1 : 0);
