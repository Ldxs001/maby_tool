/* _test_v2170_parse.cjs — v2.17.0 页区指令 @@ begin page{…} 解析测试
 * 运行：node _test_v2170_parse.cjs
 * 只测解析器输出结构，页码映射见 _test_v2170_filler.py
 */
const { parseMarkdown } = require('./md-parser.js');

let pass = 0, fail = 0;
function t(name, fn) {
  let ok = false, note = '';
  try { ok = fn() === true; } catch (e) { ok = false; note = '  ← ' + e.message; }
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (ok ? '' : note));
  ok ? pass++ : fail++;
}
function cnt(s, sub) { return s.split(sub).length - 1; }
function attrOf(html, name) {
  const m = html.match(new RegExp(name + '="([^"]*)"'));
  return m ? m[1] : null;
}

console.log('\n— 四种合法档位 —');
['noll', '1', 'i', 'I'].forEach(pn => {
  t('{@@ begin page{' + pn + '}} → .page-region[data-pn=' + pn + ']', () => {
    const h = parseMarkdown('@@ begin page{' + pn + '}\n内容\n@@ end page');
    if (cnt(h, 'class="page-region"') !== 1) return false;
    if (attrOf(h, 'data-pn') !== pn) return false;         /* 大小写 I 必须原样 */
    if (!attrOf(h, 'data-pr-id')) return false;
    return h.indexOf('<p>内容</p>') >= 0;
  });
});

console.log('\n— fail-closed 四种 —');
t('参数非法 {x}：标记行原文、内容照常', () => {
  const h = parseMarkdown('@@ begin page{x}\n正文\n@@ end page');
  if (cnt(h, 'class="page-region"') !== 0) return false;
  return h.indexOf('@@ begin page{x}') >= 0 && h.indexOf('<p>正文</p>') >= 0 &&
    h.indexOf('@@ end page') >= 0;
});
t('无参数 @@ begin page：标记行原文', () => {
  const h = parseMarkdown('@@ begin page\n正文\n@@ end page');
  return cnt(h, 'class="page-region"') === 0 && h.indexOf('@@ begin page') >= 0;
});
t('未闭合：标记行原文，其后内容照常渲染', () => {
  const h = parseMarkdown('@@ begin page{1}\n正文没有结束');
  return cnt(h, 'class="page-region"') === 0 &&
    h.indexOf('@@ begin page{1}') >= 0 && h.indexOf('正文没有结束') >= 0;
});
t('空参数 {}：标记行原文', () => {
  const h = parseMarkdown('@@ begin page{}\n正文\n@@ end page');
  return cnt(h, 'class="page-region"') === 0;
});

console.log('\n— 嵌套不支持（内层退化为文本） —');
t('嵌套：只出一个 page-region，内层两行都不成指令', () => {
  const h = parseMarkdown(
    '@@ begin page{1}\n外\n@@ begin page{i}\n内\n@@ end page\n外2\n@@ end page');
  if (cnt(h, 'class="page-region"') !== 1) return false;
  if (attrOf(h, 'data-pn') !== '1') return false;
  /* 内层行带零宽前缀，正则不再匹配；渲染上仍可见原文 */
  if (h.indexOf('\u200b') < 0) return false;
  return h.indexOf('page{i}') >= 0;
});

console.log('\n— 区域实例与内容 —');
t('相邻两区 data-pr-id 不同（各自从 1 重编的前提）', () => {
  const h = parseMarkdown(
    '@@ begin page{1}\n甲\n@@ end page\n\n@@ begin page{1}\n乙\n@@ end page');
  const ids = (h.match(/data-pr-id="([^"]+)"/g) || []).map(s => s.slice(13, -1));
  return ids.length === 2 && ids[0] !== ids[1];
});
t('区外内容不吞：区域前后各一段', () => {
  const h = parseMarkdown('前\n\n@@ begin page{1}\n区\n@@ end page\n\n后');
  return h.indexOf('<p>前</p>') >= 0 && h.indexOf('<p>后</p>') >= 0 &&
    cnt(h, 'class="page-region"') === 1;
});
t('区内 markdown 正常渲染（标题 + 空行分段）', () => {
  const h = parseMarkdown('@@ begin page{1}\n## 章\n\n第一段\n\n第二段\n@@ end page');
  return h.indexOf('<h2') >= 0 && cnt(h, '<p>') === 2;
});
t('区内既有指令仍生效（@@ blank{1}）', () => {
  const h = parseMarkdown('@@ begin page{1}\n甲\n\n@@ blank{1}\n\n乙\n@@ end page');
  return h.indexOf('class="mde-blank"') >= 0;
});
t('区内表格不破（管道表）', () => {
  const h = parseMarkdown('@@ begin page{1}\n| a | b |\n| --- | --- |\n| 1 | 2 |\n@@ end page');
  return h.indexOf('<table') >= 0 && h.indexOf('class="page-region"') >= 0;
});

console.log('\n' + (fail === 0 ? 'ALL PASS' : 'FAILED ' + fail) +
  '  (' + pass + '/' + (pass + fail) + ')');
process.exit(fail === 0 ? 0 : 1);
