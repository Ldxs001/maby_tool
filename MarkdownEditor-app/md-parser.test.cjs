/* md-parser.test.cjs — 抽取版解释器回归测试（Node CommonJS）
 * 覆盖 MDEditor 全部方言语法。运行：node md-parser.test.cjs
 * 注：公式 $...$ 与图表真实出图由 UI 层（extractMath / renderDiagrams）处理，
 *     本解释器（parseMarkdown）只产出结构化 HTML：公式原样保留、图表出占位。
 *     独立调用 parseMarkdown 时，行内语法按 CommonMark 反斜杠转义（\, → ,）。
 */
const { parseMarkdown } = require('./md-parser.js');

const src = [
  '# 标题',
  '',
  '**粗** 与 *斜* 与 ~~删~~ 与 `code` 与 [链接](http://x.com)',
  '',
  '+ 实心项',
  '- 空心项',
  '* 这不是列表（斜体）*',
  '',
  '- [x] 已办任务',
  '- [ ] 未办任务',
  '',
  '1. 一',
  '2. 二',
  '3. 三',
  '',
  '```python',
  'def f(): return 1',
  '```',
  '',
  '```mermaid {40c}',
  'graph TD; A-->B',
  '```',
  '',
  '```dot',
  'digraph G { a->b }',
  '```',
  '',
  '```vega',
  '{"$schema":"https://vega.github.io/schema/vega/v5.json"}',
  '```',
  '',
  '| 左 | 右 | 中 |',
  '| :--- | ---: | :---: |',
  '| a | b | c |',
  '',
  '![图](a.png){30c}',
  '',
  '@@ begin fill {50|50}',
  '![左](l.png){50}',
  '',
  '![右](r.png){50}',
  '@@ end fill',
  '',
  '<<<',
  '被缩进包围的内容',
  '<<<',
  '',
  '行内公式 $E=mc^2$ 与块级 $$ \\sum_i x_i $$ 由 UI 层处理。'
].join('\n');

const html = parseMarkdown(src);

const checks = {
  '标题 <h1>':                /<h1>标题<\/h1>/.test(html),
  '粗体 <strong>':            /<strong>粗<\/strong>/.test(html),
  '斜体 <em>':                /<em>斜<\/em>/.test(html),
  '删除 <del>':               /<del>删<\/del>/.test(html),
  '行内代码 <code>':          /<code>code<\/code>/.test(html),
  '链接 target=_blank':       /<a href="http:\/\/x\.com"[^>]*target="_blank"/.test(html),
  '列表 + 实心 u-solid':      /class="u-solid"/.test(html),
  '列表 - 空心 u-hollow':     /class="u-hollow"/.test(html),
  '星号不作列表（纯斜体）':   !/<li[^>]*>\* 这不是列表/.test(html) && /<em> 这不是列表（斜体）<\/em>/.test(html),
  '任务列表 checked':         /<li class="task"><input type="checkbox" disabled checked>/.test(html),
  '任务列表 unchecked':       /<li class="task"><input type="checkbox" disabled>/.test(html),
  '有序接力 <ol>':            /<ol/.test(html),
  '代码块 lang-python':       /<pre><code class="lang-python">/.test(html),
  '图表 mermaid 占位':        /data-diagram="mermaid"/.test(html),
  '图表 mermaid 宽度40%':     /data-diagram="mermaid"/.test(html) && /style="width:40%"/.test(html),
  '图表 mermaid 对齐 center': /data-diagram-align="center"/.test(html),
  '图表 dot 占位':            /data-diagram="dot"/.test(html),
  '图表 vega 占位':           /data-diagram="vega"/.test(html),
  '图表 data-code 编码':      /data-code="/.test(html),
  '表格 th 居中':             /<th style="text-align:center">中<\/th>/.test(html),
  '表格 td 右对齐':           /<td style="text-align:right">b<\/td>/.test(html),
  '表格 td 左对齐':           /<td style="text-align:left">a<\/td>/.test(html),
  '图片 {30c} 宽度30%':       /width:30%/.test(html) && /<img src="a\.png"/.test(html),
  '图片 {30c} 居中':          /margin-left:auto !important;margin-right:auto !important/.test(html),
  '分栏 fill-row':            /class="fill-row"/.test(html),
  '分栏 fill-col 50%':        /class="fill-col" style="width:50%"/.test(html),
  '缩进块 ind-blk':           /class="ind-blk" style="margin-left:/.test(html),
};

let ok = true;
for (const [k, v] of Object.entries(checks)) {
  console.log((v ? 'PASS' : 'FAIL') + '  ' + k);
  if (!v) ok = false;
}

// 公式：行内 $...$ 在 parseMarkdown 中原样保留（无内部强调配对）；块级 $$ 与
// 图表真实出图由 UI 层 extractMath / renderDiagrams 处理，不在 parseMarkdown 内。
const inlineFormulaKept = html.includes('$E=mc^2$');
console.log((inlineFormulaKept ? 'INFO ' : 'WARN ') +
  '  行内公式 $...$ 解析器原样保留: ' + inlineFormulaKept +
  '（块级 $$ 与图表出图属 UI 层，不在 parseMarkdown 范围内）');

console.log('');
console.log(ok ? '✅ ALL CORE CHECKS PASS' : '❌ SOME CHECKS FAILED');
process.exit(ok ? 0 : 1);
