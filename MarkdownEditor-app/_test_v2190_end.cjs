/* _test_v2190_end.cjs — v2.19.0 end 集合语义专项测试
 * 运行：node _test_v2190_end.cjs
 * 语义（用户定稿）：并写是嵌套的简写。@@ end X 只关 X；@@ end X Y 同关
 * X Y（成员须当前开着）；end 行书写顺序无关；关剩下的家族继续收内容，
 * 后续内容按剩余集合重开内层容器（page div 只开一次）。
 */
const { parseMarkdown } = require('./md-parser.js');

let pass = 0, fail = 0;
function t(name, fn) {
  let ok = false, note = '';
  try { ok = fn() === true; } catch (e) { ok = false; note = '  ← ' + e.message; }
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (ok ? '' : note));
  ok ? pass++ : fail++;
}
const cnt = (s, sub) => s.split(sub).length - 1;
const norm = h => h.replace(/data-pr-id="pr\d+"/g, 'data-pr-id="prN"');

console.log('\n— 一、end 单关：@@ end X 只关 X —');
t('end color：色层关掉，page>full 继续收', () => {
  const h = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end color\n乙\n@@ end full\n@@ end page'));
  return cnt(h, 'mde-color') === 1 && cnt(h, 'page-region') === 1 &&
    h.indexOf('mde-color" style="color:#e53935"><p>甲</p></div><p>乙</p>') > 0;
});
t('end full：整页层关掉，page 继续收（段二无 full-page）', () => {
  const h = norm(parseMarkdown('@@ begin page{1} full\n甲\n@@ end full\n乙\n@@ end page'));
  return cnt(h, 'full-page') === 1 && cnt(h, 'page-region') === 1 &&
    h.indexOf('<p>甲</p></div><p>乙</p></div>') > 0;
});
t('end page：最外层关掉（page div 闭合，full 仍在内层？——不，page 是最外层，full 在其内，先关 page 即外层先关 → 剩 full 独立收）', () => {
  const h = norm(parseMarkdown('@@ begin page{1} full\n甲\n@@ end page\n乙\n@@ end full'));
  /* page 关掉后剩 full：段二重开 full-page（不在 page 内） */
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 2 &&
    h.indexOf('<div class="full-page" data-full-pos="m"><p>乙</p></div>') > 0;
});

console.log('\n— 二、end 并写：@@ end X Y 同关多个 —');
t('end page color 同关两个，full 继续', () => {
  const h = norm(parseMarkdown('@@ begin page{noll} full color{r}\n甲\n@@ end page color\n乙\n@@ end full'));
  return cnt(h, 'page-region') === 1 && cnt(h, 'mde-color') === 1 &&
    cnt(h, 'full-page') === 2 &&
    h.indexOf('<div class="full-page" data-full-pos="m"><p>乙</p></div>') > 0;
});
t('end full color 同关两个（内层优先关），page 继续', () => {
  const h = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end full color\n乙\n@@ end page'));
  return cnt(h, 'page-region') === 1 && cnt(h, 'mde-color') === 1 &&
    cnt(h, 'full-page') === 1 && h.indexOf('<p>乙</p></div>') > 0;
});
t('end 三成员同关整块（等价于单家族块的收尾）', () => {
  const h = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end page full color'));
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 &&
    cnt(h, 'mde-color') === 1 && cnt(h, '<div') === 3;
});

console.log('\n— 三、等价性：拆行 / 乱序同效 —');
t('end 拆行 == end 并写（同集合）', () => {
  const a = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end page color\n乙\n@@ end full'));
  const b = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end page\n@@ end color\n乙\n@@ end full'));
  return a === b;
});
t('end 成员乱序 == 顺序书写', () => {
  const a = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end color full\n乙\n@@ end page'));
  const b = norm(parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end full color\n乙\n@@ end page'));
  return a === b;
});

console.log('\n— 四、fail-closed：end 了没开的 / 未关完 —');
t('end 未开的家族 → 整块原文露出', () => {
  const h = parseMarkdown('@@ begin page{1} full\n甲\n@@ end fill\n@@ end page full');
  return cnt(h, 'page-region') === 0 && h.indexOf('@@ begin page{1} full') >= 0;
});
t('end 超额（同一家族关两次）→ 整块原文露出', () => {
  const h = parseMarkdown('@@ begin page{1} full\n甲\n@@ end full full\n@@ end page');
  return cnt(h, 'page-region') === 0 && h.indexOf('@@ begin page{1} full') >= 0;
});
t('关剩一个后未关 → 未闭合 fail-closed', () => {
  const h = parseMarkdown('@@ begin page{1} full color{r}\n甲\n@@ end color');
  return cnt(h, 'page-region') === 0 && h.indexOf('@@ begin page{1} full') >= 0;
});

console.log('\n— 五、与内层块的配对：内层 end 不误关并写成员 —');
t('并写 page+color，内层 color 块的 end color 只降内层深度', () => {
  const h = norm(parseMarkdown('@@ begin page{1} color{r}\n外\n@@ begin color b\n内\n@@ end color\n外2\n@@ end color\n@@ end page'));
  /* 内层 color b 是独立块正常渲染；外层 color 由最后一个 end color 关 */
  return cnt(h, 'page-region') === 1 && cnt(h, 'mde-color') === 2 &&
    h.indexOf('style="color:#1e88e5"><p>内</p>') > 0 &&
    h.indexOf('<p>外2</p>') > 0;
});
t('并写内层 fill 的 end fill 不碰 page/full 深度', () => {
  const h = norm(parseMarkdown('@@ begin page{1} full\n@@ begin fill\n甲\n\n乙\n@@ end fill\n丙\n@@ end page full'));
  return cnt(h, 'fill-row') === 1 && cnt(h, 'fill-col') === 2 &&
    cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 &&
    h.indexOf('<p>丙</p>') > 0;
});

console.log('\n' + (fail === 0 ? 'ALL PASS' : 'FAILED ' + fail) +
  '  (' + pass + '/' + (pass + fail) + ')');
process.exit(fail === 0 ? 0 : 1);
