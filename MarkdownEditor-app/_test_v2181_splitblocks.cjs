/* _test_v2181_splitblocks.cjs — v2.18.1 splitBlocks @@ 块感知修复测试
 * 运行：node _test_v2181_splitblocks.cjs
 * 背景：预览按块增量渲染（splitBlocks 切块 → 逐块 parseMarkdown）。
 *   v2.13.1 的感知集合只有 full|fill|color，v2.17 的 page 与 v2.18 的
 *   并写行不在集合内 → 块内 H1/H2 触发下刀，begin/end 被劈进相邻块，
 *   逐块解析各自 fail-closed 原样露出（用户实测「并写在预览栏露出」）。
 *   另修：恢复条件改深度计数——旧「遇任意 @@ end 清 wrap」会被嵌套
 *   color 的 @@ end color 提前解除保护。
 * 抽取方式：从 markdown-editor.html 抠 splitBlocks 函数源码 eval，
 *   parseMarkdown 用 md-parser.js（sync 测试保证两者一致）。
 */
const fs = require('fs');
const { parseMarkdown } = require('./md-parser.js');

const html = fs.readFileSync('markdown-editor.html', 'utf8');
const m = html.match(/function splitBlocks\(src\)\{[\s\S]*?return blocks;\s*\n  \}/);
if (!m) { console.log('FAIL  splitBlocks 函数抽取失败'); process.exit(1); }
const splitBlocks = new Function('return (' + m[0].replace(/^function /, 'function ') + ')')();

let pass = 0, fail = 0;
function t(name, fn) {
  let ok = false, note = '';
  try { ok = fn() === true; } catch (e) { ok = false; note = '  ← ' + e.message; }
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (ok ? '' : note));
  ok ? pass++ : fail++;
}
const cnt = (s, sub) => s.split(sub).length - 1;
const joined = (src) => splitBlocks(src).map(b => parseMarkdown(b)).join('');

/* 1. 并写块含 H1：整块不切，解析出 page-region，标记不露出 */
t('并写 page{noll} full + H1：单块渲染 page-region，begin/end 不露出', () => {
  const src = '@@ begin page{noll} full{t}\n# 封面\n副标题\n@@ end page full\n\n## 第二章\n正文';
  const blocks = splitBlocks(src);
  if (blocks.length !== 2) return false;
  const h = joined(src);
  return cnt(h, 'page-region') === 1 && h.indexOf('@@ begin') < 0 && h.indexOf('@@ end') < 0 &&
    cnt(h, '<h1>') === 1 && cnt(h, '<h2>') === 1;
});

/* 2. page 单家族 + H1（v2.17 漏洞回归） */
t('page 单家族 + H1：整块不切，page-region 正常', () => {
  const src = '@@ begin page{1}\n# 章扉\n@@ end page\n\n## 第一节\n正文';
  return cnt(joined(src), 'page-region') === 1 &&
    joined(src).indexOf('@@ begin') < 0;
});

/* 3. 深度计数：full 内嵌 color，end color 不提前解除保护 */
t('full 内嵌 color（end color 在中段）：后续 H2 不被劈出块', () => {
  const src = ['@@ begin full',
    '@@ begin color r',
    '红字',
    '@@ end color',
    '## 块内标题',
    '@@ end full',
    '',
    '## 块外标题'].join('\n');
  const blocks = splitBlocks(src);
  /* 前 6 行必须同块；最后 2 行是另一块 */
  return blocks.length === 2 &&
    blocks[0].indexOf('@@ begin full') === 0 &&
    blocks[0].indexOf('@@ end full') >= 0 &&
    blocks[1] === '## 块外标题';
});

/* 4. 并写块内嵌 color 同理 */
t('并写 page{noll} full 内嵌 color：end color 不解除保护', () => {
  const src = ['@@ begin page{noll} full',
    '@@ begin color g',
    '绿字',
    '@@ end color',
    '## 扉页标题',
    '@@ end page'].join('\n');
  const blocks = splitBlocks(src);
  return blocks.length === 1 && blocks[0].indexOf('@@ end page') >= 0;
});

/* 5. 无 @@ 的普通文档：H1/H2 照常切块（原行为不回退） */
t('普通文档 H1/H2 照常切块', () => {
  const blocks = splitBlocks('# 一\n文\n\n## 二\n文\n\n# 三\n文');
  return blocks.length === 3;
});

/* 6. fence 内 H1 不切块、fence 内标记行不计数 */
t('fence 内 H1 不切块；fence 内 @@ begin 不触发 wrap', () => {
  const src = '```js\n# 不是标题\n@@ begin full\n```\n\n## 真标题';
  const blocks = splitBlocks(src);
  return blocks.length === 2 && blocks[1] === '## 真标题';
});

/* 7. 非法嵌套（逆序）整块保持，fail-closed 交给解析器 */
t('fill 内 full（逆序非法）：整块保持，解析器对称露出', () => {
  const src = ['@@ begin fill',
    '甲',
    '',
    '@@ begin full',
    '乙',
    '@@ end full',
    '@@ end fill'].join('\n');
  const blocks = splitBlocks(src);
  if (blocks.length !== 1) return false;
  const h = parseMarkdown(blocks[0]);
  return cnt(h, 'fill-row') === 1 && cnt(h, 'full-page') === 0 &&
    cnt(h, '@@ begin full') === 1 && cnt(h, '@@ end full') === 1;
});

/* 8. 未闭合块吞到文末（粒度变粗但渲染正确） */
t('未闭合块吞到文末', () => {
  const blocks = splitBlocks('@@ begin full\n# 题\n后续全部');
  return blocks.length === 1;
});

/* 9. 组合端到端：并写封面 + page 罗马区 + 正文，逐块解析全链无泄漏 */
t('组合文档端到端：无任何标记泄漏', () => {
  const src = [
    '@@ begin page{noll} full{t}',
    '# 书名',
    '副题',
    '@@ end page full',
    '',
    '@@ begin page{i}',
    '# 序',
    '@@ end page',
    '',
    '## 第一章',
    '正文',
  ].join('\n');
  const h = joined(src);
  return cnt(h, 'page-region') === 2 && h.indexOf('@@ begin') < 0 && h.indexOf('@@ end') < 0 &&
    cnt(h, '<h1>') === 2 && cnt(h, '<h2>') === 1;
});

console.log('\n' + pass + '/' + (pass + fail) + (fail ? '  FAIL' : '  ALL PASS'));
process.exit(fail ? 1 : 0);
