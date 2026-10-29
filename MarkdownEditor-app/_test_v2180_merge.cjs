/* _test_v2180_merge.cjs — v2.18.0 @@ begin 并写（page / full / color）解析测试
 * 运行：node _test_v2180_merge.cjs
 * 只测解析器输出结构与小节边界；出纸效果见 _test_v2180_e2e.py
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
const cls = h => (h.match(/class="([^"]*)"/) || [, ''])[1];

console.log('\n— 基本并写 —');
t('page{noll} full → 一个 div、两个类、full 缺省居中', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n封面\n@@ end page');
  if (cnt(h, '<div') !== 1) return false;
  if (cls(h) !== 'page-region full-page') return false;
  if (attrOf(h, 'data-pn') !== 'noll') return false;
  if (attrOf(h, 'data-full-pos') !== 'm') return false;
  if (!attrOf(h, 'data-pr-id')) return false;
  return h.indexOf('<p>封面</p>') >= 0;
});
t('full{t} page{i}（顺序反转 → fail-closed 原文露出）', () => {
  const h = parseMarkdown('@@ begin full{t} page{i}\n扉页\n@@ end full');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 0 &&
    h.indexOf('@@ begin full{t} page{i}') >= 0 && h.indexOf('<p>扉页</p>') >= 0;
});
t('page{1} full{m} color{r} 三个全并', () => {
  const h = parseMarkdown('@@ begin page{1} full{m} color{r}\n三合一\n@@ end color');
  if (cls(h) !== 'page-region full-page mde-color') return false;
  return h.indexOf('style="color:#e53935"') >= 0 &&
    attrOf(h, 'data-pn') === '1' && attrOf(h, 'data-full-pos') === 'm';
});
t('full + color 裸词（无 page 时不出 data-pn）', () => {
  const h = parseMarkdown('@@ begin full color r\n红扉页\n@@ end full');
  return cls(h) === 'full-page mde-color' && !attrOf(h, 'data-pn') &&
    h.indexOf('style="color:#e53935"') >= 0;
});
t('color 裸词在前（错序 → fail-closed 原文露出）', () => {
  const h = parseMarkdown('@@ begin color r full\n红扉页2\n@@ end full');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 0 &&
    h.indexOf('@@ begin color r full') >= 0 && h.indexOf('<p>红扉页2</p>') >= 0;
});
t('color 花括号色值（8 位带透明度）', () => {
  const h = parseMarkdown('@@ begin page{noll} color{99b3c180}\n半透明\n@@ end page');
  return h.indexOf('color:#99b3c180') >= 0 && cls(h) === 'page-region mde-color';
});

console.log('\n— 结束标记认任一声明过的家族 —');
['page', 'full', 'color'].forEach(fam => {
  t('@@ end ' + fam + ' 能闭合 page+full+color 块', () => {
    const h = parseMarkdown('@@ begin page{noll} full color r\nx\n@@ end ' + fam);
    return cnt(h, '<div') === 1 && cnt(h, 'page-region') === 1;
  });
});
t('未声明的家族名不闭合（继续收集 → 未闭合即原文）', () => {
  const h = parseMarkdown('@@ begin page{noll} full\nx\n@@ end color\n后文');
  return cnt(h, 'page-region') === 0 && h.indexOf('@@ begin page{noll} full') >= 0;
});

console.log('\n— fail-closed 五种 —');
[
  ['同族重复', '@@ begin page{noll} page{1}\nx\n@@ end page'],
  ['page 参数非法', '@@ begin page{x} full\nx\n@@ end page'],
  ['full 参数非法', '@@ begin full{q} page{1}\nx\n@@ end full'],
  ['color 色值非法', '@@ begin color zz full\nx\n@@ end color'],
  ['未闭合', '@@ begin page{noll} full\nx'],
].forEach(([n, src]) => {
  t(n + '：标记行原文、内容照常', () => {
    const h = parseMarkdown(src);
    if (cnt(h, 'page-region') !== 0) return false;
    return h.indexOf('@@ begin') >= 0;
  });
});

console.log('\n— 单家族输出与 v2.17 逐字节一致 —');
t('单 full{t}', () => {
  const h = parseMarkdown('@@ begin full{t}\n单\n@@ end full');
  return h === '<div class="full-page" data-full-pos="t"><p>单</p></div>';
});
t('单 page{noll}', () => {
  const h = parseMarkdown('@@ begin page{noll}\n单\n@@ end page');
  return h.replace(/data-pr-id="pr\d+"/, 'data-pr-id="prN"') ===
    '<div class="page-region" data-pn="noll" data-pr-id="prN"><p>单</p></div>';
});
t('单 color（块级）', () => {
  const h = parseMarkdown('@@ begin color r\n单\n@@ end color');
  return h === '<div class="mde-color" style="color:#e53935"><p>单</p></div>';
});
t('单 fill（无参等分两栏）', () => {
  const h = parseMarkdown('@@ begin fill\n甲\n\n乙\n@@ end fill');
  return cnt(h, 'fill-row') === 1 && cnt(h, 'fill-col') === 2 && cnt(h, '<div') === 3;
});

console.log('\n— 嵌套照旧放行 —');
t('并写块内嵌 @@ begin fill → 正常 fill-row', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end page');
  return cnt(h, 'fill-row') === 1 && cnt(h, 'fill-col') === 2 && cnt(h, 'page-region') === 1;
});
t('并写块内嵌 @@ begin full → 正常嵌套 full-page', () => {
  const h = parseMarkdown('@@ begin page{noll} color r\n@@ begin full{t}\n内层整页\n@@ end full\n@@ end page');
  /* 外层是 page+color，内层才是 full → 全文只有一个 full-page，且必须嵌在 page-region 里 */
  return cnt(h, 'full-page') === 1 && cnt(h, 'page-region') === 1 &&
    h.indexOf('<div class="page-region mde-color"') === 0 &&
    h.indexOf('<div class="full-page" data-full-pos="t">') > 0 &&
    h.indexOf('内层整页') >= 0;
});
t('并写块内嵌 @@ begin color → 正常嵌套 mde-color', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin color b\n内层蓝\n@@ end color\n@@ end page');
  return cnt(h, 'mde-color') === 1 && cnt(h, 'page-region') === 1 &&
    h.indexOf('color:#1e88e5') >= 0;
});
t('并写块内嵌 @@ begin page → 零宽退回（全文只一个 page-region）', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin page{1}\n内层区\n@@ end page\n@@ end page');
  return cnt(h, 'page-region') === 1 && h.indexOf('内层区') >= 0;
});

console.log('\n— 内容解析 —');
t('区内标题／列表／表格照常', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n## 章\n\n- 甲\n- 乙\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n@@ end page');
  return h.indexOf('<h2') >= 0 && h.indexOf('<ul>') >= 0 && h.indexOf('<table') >= 0 &&
    cnt(h, 'page-region') === 1;
});
t('并写块前后的普通段落正常', () => {
  const h = parseMarkdown('前文\n\n@@ begin page{noll} full\n中\n@@ end page\n\n后文');
  return cnt(h, '<p>前文</p>') === 1 && cnt(h, '<p>后文</p>') === 1 && cnt(h, 'page-region') === 1;
});
t('两个并写块各自的 pr-id 不同', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n甲\n@@ end page\n\n@@ begin page{1} full\n乙\n@@ end page');
  const ids = h.match(/data-pr-id="(pr\d+)"/g) || [];
  return ids.length === 2 && ids[0] !== ids[1];
});

console.log('\n' + (fail === 0 ? 'ALL PASS' : 'FAILED ' + fail) +
  '  (' + pass + '/' + (pass + fail) + ')');
process.exit(fail === 0 ? 0 : 1);
