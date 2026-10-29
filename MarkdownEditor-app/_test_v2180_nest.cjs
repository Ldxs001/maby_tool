/* _test_v2180_nest.cjs — v2.18.0 @@ begin 嵌套规则（同族禁套 + 主链层级）解析测试
 * 运行：node _test_v2180_nest.cjs
 * 规则（用户定稿）：四族同族自嵌套一律禁止；color 不占主链、任意层可开；
 * 主链 page(1) > full(2) > fill(3) 严格递增，跳级允许（page 直套 fill 合法）、
 * 逆序/同级一律 fail-closed（标记行零宽露出、内容照常渲染、不吞字）。
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
const ZW = '\u200b';

console.log('\n— 同族自嵌套：一律禁止（整对零宽露出，外层照常） —');
t('full 套 full：full-page 只 1 个，内层标记零宽露出', () => {
  const h = parseMarkdown('@@ begin full{m}\nA\n@@ begin full{b}\nB\n@@ end full\n@@ end full');
  return cnt(h, 'full-page') === 1 &&
    h.indexOf(ZW + '@@ begin full{b}') >= 0 && h.indexOf(ZW + '@@ end full') >= 0 &&
    h.indexOf('A') >= 0 && h.indexOf('B') >= 0;
});
t('page 套 page：page-region 只 1 个，内层零宽露出', () => {
  const h = parseMarkdown('@@ begin page{1}\nA\n@@ begin page{noll}\nB\n@@ end page\n@@ end page');
  return cnt(h, 'page-region') === 1 &&
    h.indexOf(ZW + '@@ begin page{noll}') >= 0 && h.indexOf(ZW + '@@ end page') >= 0;
});
t('fill 套 fill：外层照常分栏，内层标记零宽混入栏内容', () => {
  const h = parseMarkdown('@@ begin fill\n甲\n\n@@ begin fill\n乙\n\n丙\n@@ end fill\n@@ end fill');
  return cnt(h, 'fill-row') === 1 && cnt(h, 'fill-col') === 3 &&
    h.indexOf(ZW + '@@ begin fill') >= 0 && h.indexOf(ZW + '@@ end fill') >= 0;
});
t('color 块套 color 块：mde-color 只 1 个，内层零宽露出', () => {
  const h = parseMarkdown('@@ begin color r\nA\n@@ begin color b\nB\n@@ end color\n@@ end color');
  return cnt(h, 'mde-color') === 1 &&
    h.indexOf(ZW + '@@ begin color b') >= 0 && h.indexOf(ZW + '@@ end color') >= 0;
});

console.log('\n— 主链层级：page(1) > full(2) > fill(3) 严格递增 —');
t('page > full：两层都正常', () => {
  const h = parseMarkdown('@@ begin page{1}\n@@ begin full\nA\n@@ end full\n@@ end page');
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 &&
    h.indexOf('page-region') < h.indexOf('full-page');
});
t('page > full > fill：三层都正常', () => {
  const h = parseMarkdown('@@ begin page{i}\n@@ begin full\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end full\n@@ end page');
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 && cnt(h, 'fill-row') === 1;
});
t('full > fill（跳过 page）：正常', () => {
  const h = parseMarkdown('@@ begin full\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end full');
  return cnt(h, 'full-page') === 1 && cnt(h, 'fill-row') === 1;
});
t('page > fill（跳过 full）：正常', () => {
  const h = parseMarkdown('@@ begin page{1}\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end page');
  return cnt(h, 'page-region') === 1 && cnt(h, 'fill-row') === 1;
});
t('fill 内套 full：逆序 → begin/end 对称露出、内容照常', () => {
  const h = parseMarkdown('@@ begin fill\n甲\n\n@@ begin full\n乙\n@@ end full\n@@ end fill');
  return cnt(h, 'full-page') === 0 && cnt(h, 'fill-row') === 1 &&
    h.indexOf('<p>@@ begin full</p>') >= 0 && h.indexOf('<p>@@ end full</p>') >= 0 &&
    h.indexOf('<p>乙</p>') >= 0;
});
t('full 内套 page：逆序 → begin/end 对称露出、内容照常', () => {
  const h = parseMarkdown('@@ begin full\n@@ begin page{1}\nA\n@@ end page\n@@ end full');
  return cnt(h, 'page-region') === 0 && cnt(h, 'full-page') === 1 &&
    h.indexOf('<p>@@ begin page{1}</p>') >= 0 && h.indexOf('<p>@@ end page</p>') >= 0 &&
    h.indexOf('<p>A</p>') >= 0;
});
t('fill 内套 page：逆序 → fail-closed', () => {
  const h = parseMarkdown('@@ begin fill\n甲\n\n@@ begin page{1}\nA\n@@ end page\n@@ end fill');
  return cnt(h, 'page-region') === 0 && cnt(h, 'fill-row') === 1;
});

console.log('\n— color 不占主链：任意层可开、可自由组合 —');
t('color 块内套 full：正常（color 透明，_lv 不变）', () => {
  const h = parseMarkdown('@@ begin color r\n@@ begin full\nA\n@@ end full\n@@ end color');
  return cnt(h, 'mde-color') === 1 && cnt(h, 'full-page') === 1;
});
t('fill 栏内套 color 块：正常', () => {
  const h = parseMarkdown('@@ begin fill\n@@ begin color b\n甲\n@@ end color\n\n乙\n@@ end fill');
  return cnt(h, 'fill-row') === 1 && cnt(h, 'mde-color') === 1;
});
t('full 内 color 与 fill 交错：color 独立、fill 正常', () => {
  const h = parseMarkdown('@@ begin full\n@@ begin color g\nA\n@@ end color\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end full');
  return cnt(h, 'mde-color') === 1 && cnt(h, 'full-page') === 1 && cnt(h, 'fill-row') === 1;
});

console.log('\n— 并写容器的内部层级（v2.19 流式嵌套模型）—');
t('并写 page+full 内套 fill：正常（容器 _lv=2，fill 3>2）', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end page full');
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 && cnt(h, 'fill-row') === 1;
});
t('并写 page+full 内套 full：同族 → 原文露出（外层 full-page 只 1 个）', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin full\nA\n@@ end full\n@@ end page full');
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 &&
    h.indexOf('<p>@@ begin full</p>') >= 0 && h.indexOf('<p>A</p>') >= 0 &&
    h.indexOf('<p>@@ end full</p>') >= 0;
});
t('并写 page+full 内套 page：主链逆序 → 原文露出（全文只一个 page-region）', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin page{1}\nA\n@@ end page\n@@ end page full');
  return cnt(h, 'page-region') === 1 &&
    h.indexOf('<p>@@ begin page{1}</p>') >= 0 && h.indexOf('<p>A</p>') >= 0;
});
t('并写 page+color 内套 fill：正常（fill 不在并写集合，照常嵌套）', () => {
  const h = parseMarkdown('@@ begin page{1} color r\n@@ begin fill\n甲\n\n乙\n@@ end fill\n@@ end page color');
  return cnt(h, 'page-region') === 1 && cnt(h, 'mde-color') === 1 && cnt(h, 'fill-row') === 1;
});
t('并写 page+color 内套 full：正常（容器 _lv=1，full 2>1，full 嵌在 page>color 内）', () => {
  const h = parseMarkdown('@@ begin page{1} color r\n@@ begin full\nA\n@@ end full\n@@ end page color');
  return cnt(h, 'page-region') === 1 && cnt(h, 'mde-color') === 1 && cnt(h, 'full-page') === 1;
});

console.log('\n— 深度跟踪：per-family 计数下内外层 end 各归各 —');
t('并写内层 fill 未闭合：fill fail-closed 露出，end full 关掉 full 成员后分段', () => {
  const h = parseMarkdown('@@ begin page{noll} full\n@@ begin fill\n甲\n@@ end full\n@@ end page');
  /* @@ end full 命中并写成员 full → 分段点；fill 未闭合由递归 fail-closed */
  return cnt(h, 'page-region') === 1 && cnt(h, 'full-page') === 1 &&
    cnt(h, 'fill-row') === 0 && h.indexOf('@@ begin fill') >= 0;
});
t('fill 内嵌 full 块：end full 弹栈不关外层，end fill 才闭合', () => {
  const h = parseMarkdown('@@ begin fill\n甲\n\n@@ begin full\nA\n@@ end full\n\n乙\n@@ end fill');
  /* 外层 fill 正常闭合于自己的 end fill（end full 在 _scanBeginBlock 里弹掉
     full 栈、不关 fill）；分栏按空行 → 3 栏；full 在栏内 _lv=3 被拒 */
  return cnt(h, 'fill-row') === 1 && cnt(h, 'fill-col') === 3 &&
    cnt(h, 'full-page') === 0 && h.indexOf('<p>@@ begin full</p>') >= 0 &&
    h.indexOf('<p>@@ end full</p>') >= 0;
});

console.log('\n— 零版行为回归：文档流顶层旧写法逐字节不变 —');
t('单 full / 单 page / 单 color / 单 fill 顶层输出含层级参数默认 0', () => {
  const a = parseMarkdown('@@ begin full{t}\nA\n@@ end full');
  const b = parseMarkdown('@@ begin page{1}\nB\n@@ end page');
  const c = parseMarkdown('@@ begin color r\nC\n@@ end color');
  const d = parseMarkdown('@@ begin fill\n甲\n\n乙\n@@ end fill');
  return a.indexOf('<div class="full-page" data-full-pos="t">') === 0 &&
    b.indexOf('<div class="page-region" data-pn="1"') === 0 &&
    c.indexOf('<div class="mde-color" style="color:#e53935">') === 0 &&
    d.indexOf('<div class="fill-row">') === 0;
});

console.log('\n合计 ' + (pass + fail) + ' 条：PASS ' + pass + ' / FAIL ' + fail);
process.exit(fail ? 1 : 0);
