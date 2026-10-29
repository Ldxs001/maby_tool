/* _test_v2180_merge.cjs — @@ begin 并写（page / full / color）解析测试
 * 运行：node _test_v2180_merge.cjs
 * v2.19.0 起并写为**流式嵌套 DOM**（begin 展开成嵌套容器），end 为**集合语义**
 * （@@ end X 只关 X；@@ end X Y 同关 X Y；关剩下的继续收内容）。
 * 只测解析器输出结构；出纸效果见 _test_v2180_e2e.py
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

console.log('\n— 基本并写（begin 展开成嵌套）—');
t('page{noll} full → page 外 full 内两层嵌套', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n封面\n@@ end page full');
  if (cnt(h, '<div') !== 2) return false;
  if (h.indexOf('<div class="page-region" data-pn="noll"') !== 0) return false;
  if (h.indexOf('<div class="full-page" data-full-pos="m">') < 0) return false;
  if (!attrOf(h, 'data-pr-id')) return false;
  return h.indexOf('<p>封面</p>') >= 0;
});
t('end 拆两行（end full 后 end page）与合并 end 等价', () => {
  const a = parseMarkdown('@@ begin page{noll} full\n封面\n@@ end page full')
    .replace(/data-pr-id="pr\d+"/, 'data-pr-id="prN"');
  const b = parseMarkdown('@@ begin page{noll} full\n封面\n@@ end full\n@@ end page')
    .replace(/data-pr-id="pr\d+"/, 'data-pr-id="prN"');
  return a === b;
});
t('full{t} page{i}（顺序反转 → fail-closed 原文露出）', () => {
  const h = parseMarkdown('@@ begin full{t} page{i}\n扉页\n@@ end full page');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 0 &&
    h.indexOf('@@ begin full{t} page{i}') >= 0 && h.indexOf('<p>扉页</p>') >= 0;
});
t('page{1} full{m} color{r} 三层嵌套（page>full>color）', () => {
  const h = parseMarkdown('@@ begin page{1} full{m} color{r}\n三合一\n@@ end page full color');
  if (cnt(h, '<div') !== 3) return false;
  const a = h.indexOf('<div class="mde-color" style="color:#e53935">');
  const b = h.indexOf('<div class="full-page" data-full-pos="m">');
  const c = h.indexOf('<div class="page-region"');
  return a > b && b > c && a > 0 &&
    attrOf(h, 'data-pn') === '1' && h.indexOf('<p>三合一</p>') >= 0;
});
t('full + color 裸词（无 page 时不出 data-pn）', () => {
  const h = parseMarkdown('@@ begin full color r\n红扉页\n@@ end full color');
  return cnt(h, '<div') === 2 && cls(h) === 'full-page' &&
    h.indexOf('<div class="full-page" data-full-pos="m">') === 0 &&
    h.indexOf('<div class="mde-color" style="color:#e53935">') > 0 &&
    !attrOf(h, 'data-pn');
});
t('color 裸词在前（错序 → fail-closed 原文露出）', () => {
  const h = parseMarkdown('@@ begin color r full\n红扉页2\n@@ end color full');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 0 &&
    h.indexOf('@@ begin color r full') >= 0 && h.indexOf('<p>红扉页2</p>') >= 0;
});
t('color 花括号色值（8 位带透明度）', () => {
  const h = parseMarkdown('@@ begin page{noll} color{99b3c180}\n半透明\n@@ end page color');
  return h.indexOf('color:#99b3c180') >= 0 &&
    h.indexOf('<div class="page-region" data-pn="noll"') === 0 &&
    h.indexOf('<div class="mde-color" style="color:#99b3c180">') > 0;
});

console.log('\n— end 集合语义 —');
t('@@ end color 只关 color，page/full 继续收内容', () => {
  const h = parseMarkdown('@@ begin page{1} full color{r}\n段一\n@@ end color\n段二\n@@ end full\n@@ end page');
  /* 段一在 page>full>color 三层；段二在 page>full 两层（color 层已关） */
  if (cnt(h, 'mde-color') !== 1) return false;
  if (cnt(h, '<p>段一</p>') !== 1 || cnt(h, '<p>段二</p>') !== 1) return false;
  return h.indexOf('style="color:#e53935"><p>段一</p></div><p>段二</p></div></div>') >= 0;
});
t('@@ end page color 同关两个，full 继续收（full 在新段重开）', () => {
  const h = parseMarkdown('@@ begin page{noll} full color{r}\n段一\n@@ end page color\n段二\n@@ end full');
  /* 段一：page>full>color 三层；段二：只剩 full 一层（page/color 已关） */
  if (cnt(h, 'page-region') !== 1) return false;
  if (cnt(h, 'full-page') !== 2) return false;   /* 首段一层 + 续段重开一层 */
  if (cnt(h, 'mde-color') !== 1) return false;
  return h.indexOf('<div class="page-region" data-pn="noll"') === 0 &&
    h.indexOf('<div class="full-page" data-full-pos="m"><p>段二</p></div>') > 0;
});
t('end 成员书写顺序无关（end color page == end page color）', () => {
  const a = parseMarkdown('@@ begin page{1} full color{r}\n段一\n@@ end page color\n段二\n@@ end full')
    .replace(/data-pr-id="pr\d+"/, 'data-pr-id="prN"');
  const b = parseMarkdown('@@ begin page{1} full color{r}\n段一\n@@ end color page\n段二\n@@ end full')
    .replace(/data-pr-id="pr\d+"/, 'data-pr-id="prN"');
  return a === b;
});
t('end 了没开的家族 → 整块 fail-closed', () => {
  const h = parseMarkdown('@@ begin page{1} full\n段一\n@@ end color\n@@ end full page');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 0 &&
    h.indexOf('@@ begin page{1} full') >= 0 && h.indexOf('<p>段一</p>') >= 0;
});
t('DOM 层级由 begin 声明序决定；end full 后段二只留在 page 层', () => {
  /* page 外 full 内：@@ end full 只关内层 full，段二不再有 full-page */
  const h = parseMarkdown('@@ begin page{1} full\n段一\n@@ end full\n段二\n@@ end page');
  if (cnt(h, 'page-region') !== 1 || cnt(h, 'full-page') !== 1) return false;
  return h.indexOf('<div class="page-region"') === 0 &&
    h.indexOf('<p>段一</p></div><p>段二</p></div>') > 0;
});
t('只关一个家族后未关剩余 → 未闭合 fail-closed', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n封面\n@@ end page');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 0 &&
    h.indexOf('@@ begin page{noll} full') >= 0 && h.indexOf('<p>封面</p>') >= 0;
});

console.log('\n— fail-closed 五种 —');
[
  ['同族重复', '@@ begin page{noll} page{1}\nx\n@@ end page page'],
  ['page 参数非法', '@@ begin page{x} full\nx\n@@ end page full'],
  ['full 参数非法', '@@ begin full{q} page{1}\nx\n@@ end full page'],
  ['color 色值非法', '@@ begin color zz full\nx\n@@ end color full'],
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
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end page full');
  return cnt(h, 'fill-row') === 1 && cnt(h, 'fill-col') === 2 && cnt(h, 'page-region') === 1;
});
t('并写块内嵌 @@ begin full → 正常嵌套 full-page', () => {
  const h = parseMarkdown('@@ begin page{noll} color r\n@@ begin full{t}\n内层整页\n@@ end full\n@@ end page color');
  /* 外层声明 page+color，内层才是 full → 全文两个 full-page（并写无 full、内层 1 个）……
     实际：外层无 full 层，全文只有内层 1 个 full-page，嵌在 page>color 里 */
  return cnt(h, 'full-page') === 1 && cnt(h, 'page-region') === 1 &&
    h.indexOf('<div class="page-region"') === 0 &&
    h.indexOf('<div class="full-page" data-full-pos="t">') > 0 &&
    h.indexOf('内层整页') >= 0;
});
t('并写块内嵌 @@ begin color（外层无 color）→ 正常嵌套 mde-color', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin color b\n内层蓝\n@@ end color\n@@ end page full');
  return cnt(h, 'mde-color') === 1 && cnt(h, 'page-region') === 1 &&
    h.indexOf('color:#1e88e5') >= 0;
});
t('并写块内嵌 @@ begin color（外层已含 color）→ 同族 fail-closed 原文露出', () => {
  const h = parseMarkdown('@@ begin page{1} color{r}\n外\n@@ begin color{g}\n内\n@@ end color\n外2\n@@ end color\n@@ end page');
  return cnt(h, 'page-region') === 1 && cnt(h, 'mde-color') === 1 &&
    h.indexOf('<p>@@ begin color{g}</p>') >= 0 &&
    h.indexOf('<p>@@ end color</p>') >= 0 &&
    h.indexOf('<p>内</p>') >= 0 && h.indexOf('<p>外2</p>') >= 0;
});
t('并写块内嵌 @@ begin page → 主链逆序 fail-closed 原文露出（全文只一个 page-region）', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin page{1}\n内层区\n@@ end page\n@@ end page full');
  return cnt(h, 'page-region') === 1 && h.indexOf('内层区') >= 0 &&
    h.indexOf('<p>@@ begin page{1}</p>') >= 0;
});

console.log('\n— 内容解析 —');
t('区内标题／列表／表格照常', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n## 章\n\n- 甲\n- 乙\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n@@ end page full');
  return h.indexOf('<h2') >= 0 && h.indexOf('<ul>') >= 0 && h.indexOf('<table') >= 0 &&
    cnt(h, 'page-region') === 1;
});
t('并写块前后的普通段落正常', () => {
  const h = parseMarkdown('前文\n\n@@ begin page{noll} full\n中\n@@ end page full\n\n后文');
  return cnt(h, '<p>前文</p>') === 1 && cnt(h, '<p>后文</p>') === 1 && cnt(h, 'page-region') === 1;
});
t('两个并写块各自的 pr-id 不同', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n甲\n@@ end page full\n\n@@ begin page{1} full\n乙\n@@ end page full');
  const ids = h.match(/data-pr-id="(pr\d+)"/g) || [];
  return ids.length === 2 && ids[0] !== ids[1];
});

console.log('\n' + (fail === 0 ? 'ALL PASS' : 'FAILED ' + fail) +
  '  (' + pass + '/' + (pass + fail) + ')');
process.exit(fail === 0 ? 0 : 1);
