/* _test_v2132_rules.cjs —— v2.13.2 统一块级规则 + @@ blank{n} 行为矩阵
 * 口径（主人 2026-10-28 确认）：
 *   1. 块级语法「必须独占一行」（A）：整行只有该语法即按块渲染，前面可有
 *      缩进、可以紧贴列表项（编号不断）；整行里夹了别的文字就不是块级。
 *   2. 单回车 = 换行（<br>）；双回车 = 分段；多空行不产生额外空白。
 *   3. @@ blank{n} 硬控段间空白，n = 正文行数；必须独占一行；与前后段间距
 *      不叠加（CSS 侧清零，这里只验产物结构）。
 * 运行：node _test_v2132_rules.cjs
 */
const p = require('./md-parser.js');
let fail = 0, total = 0;
function chk(name, cond, detail) {
  total++;
  if (!cond) { fail++; console.log('FAIL', name, '|', String(detail).slice(0, 400)); }
  else console.log('ok  ', name);
}

/* ===== 一、图片紧贴列表（本次报障的原点） ===== */
{
  const src = '1. 资质与证书：\n![证书](a.png "图 1　证书"){70c:c t}\n2. 其他材料\n';
  const h = p.parseMarkdown(src);
  chk('紧贴列表:一个 ol 两项（编号连续 1→2）',
    (h.match(/<ol>/g) || []).length === 1 && (h.match(/<li>/g) || []).length === 2 && h.indexOf('<ol start') < 0, h);
  chk('紧贴列表:图片重建为 figure（{70} 宽度位回到 --figw）',
    h.indexOf('<figure class="mde-fig"') >= 0 && h.indexOf('--figw:70%') >= 0, h);
  chk('紧贴列表:题注 t 与对齐 c 生效',
    h.indexOf('data-fig-side="t"') >= 0 && h.indexOf('margin-left:auto') >= 0, h);
  chk('紧贴列表:figure 落在 li 内而非 ul 外',
    /<li>资质与证书：<figure/.test(h), h);
  chk('紧贴列表:图片后无凭空 <br>', h.indexOf('</figure><br>') < 0, h);
}
{
  /* 无题注：{70c} 仍按块级（包 <p>），宽度落在 img 自身 */
  const h = p.parseMarkdown('1. 说明\n![x](a.png){70c}\n2. 后项\n');
  chk('无题注紧贴列表:块级包 p 且宽度 70%',
    h.indexOf('<li>说明<p><img') >= 0 && h.indexOf('width:70%') >= 0, h);
  chk('无题注紧贴列表:编号仍连续', (h.match(/<li>/g) || []).length === 2 && h.indexOf('<ol start') < 0, h);
}
{
  /* 缩进的整行图片同样块级（缩进不改变「独占一行」的判定） */
  const h = p.parseMarkdown('1. 说明\n   ![x](a.png "图")\n2. 后项\n');
  chk('缩进整行图片:仍块级化', h.indexOf('<figure class="mde-fig"') >= 0, h);
}
{
  /* 行内图片（同行有文字）必须保持行内，不得块级化 */
  const h = p.parseMarkdown('1. 看图 ![x](a.png) 说明\n');
  chk('同行文字内的图片:保持行内', h.indexOf('<figure') < 0 && h.indexOf('<img') >= 0, h);
}
{
  /* 图片前后都有文字：顺序必须是 文→图→文 */
  const h = p.parseMarkdown('1. 前文\n![x](a.png "图")\n后文\n2. 末项\n');
  chk('文→图→文 顺序保持',
    /前文<figure/.test(h) && /<\/figure>后文<\/li>/.test(h), h);
}

/* ===== 二、分隔线紧贴列表（同一规则的另一处历史漏网） ===== */
{
  const h = p.parseMarkdown('1. a\n---\n2. b\n');
  chk('紧贴列表的 --- :成为 li 内 <hr>',
    h.indexOf('<li>a<hr></li>') >= 0 && (h.match(/<li>/g) || []).length === 2, h);
}
{
  const h = p.parseMarkdown('1. a\n\n---\n\n2. b\n');   // 空行截断（规则：双回车切断）
  chk('空行截断后 --- 成为独立 hr，编号重新起算（空行=新编号区域）',
    h.indexOf('<hr>') >= 0 && (h.match(/<ol>/g) || []).length === 2 && h.indexOf('<ol start') < 0, h);
}
{
  /* 主循环与列表内共用判据：--- / *** / ___ 三态一致 */
  ['---', '***', '___', '- - -'].forEach(function (s) {
    const a = p.parseMarkdown('x\n\n' + s + '\n\ny\n');
    const b = p.parseMarkdown('1. x\n' + s + '\n2. y\n');
    chk('分隔线判定一致 ' + JSON.stringify(s), a.indexOf('<hr>') >= 0 && b.indexOf('<hr>') >= 0, a + ' || ' + b);
  });
}

/* ===== 三、既有块级语法紧贴列表：不得因本次改动回归 ===== */
{
  const cases = [
    ['``` 围栏', '1. a\n```js\nx\n```\n2. b\n', '<pre>'],
    ['## 标题', '1. a\n## T\n2. b\n', '<h2>T</h2>'],
    ['> 引用', '1. a\n> q\n2. b\n', '<blockquote>'],
    ['表格', '1. a\n| h |\n| - |\n| c |\n2. b\n', '<table>'],
    ['<<<', '1. a\n<<<\n内\n<<<\n2. b\n', 'ind-blk'],
    ['@@ fill', '1. a\n@@ begin fill{50|50}\nx\n\ny\n@@ end fill\n2. b\n', 'fill-row'],
    ['@@ full', '1. a\n@@ begin full{t}\nz\n@@ end full\n2. b\n', 'full-page'],
  ];
  cases.forEach(function (c) {
    const h = p.parseMarkdown(c[1]);
    chk('紧贴列表仍生效 ' + c[0], h.indexOf(c[2]) >= 0, h);
  });
  // 这七类都是「物理打断」：脱离 li，编号靠 <ol start> 接力
  const h = p.parseMarkdown('1. a\n## T\n2. b\n');
  chk('物理打断类:编号由 start 接力', h.indexOf('<ol start="2">') >= 0, h);
}

/* ===== 四、@@ blank{n} ===== */
{
  const h = p.parseMarkdown('a\n\n@@ blank{2}\n\nb\n');
  chk('blank{2}:生成空 div 且高度=2 行',
    h.indexOf('class="mde-blank"') >= 0 &&
    h.indexOf('height:calc(2 * var(--mde-lh,1.7) * 1em)') >= 0, h);
  chk('blank{2}:data-blank 记录 n', h.indexOf('data-blank="2"') >= 0, h);
  chk('blank{2}:夹在两段之间不产生额外段', (h.match(/<p>/g) || []).length === 2, h);
}
{
  const h = p.parseMarkdown('a\n@@ blank{1.5}\nb\n');
  chk('blank{1.5}:小数生效', h.indexOf('calc(1.5 * var(--mde-lh,1.7) * 1em)') >= 0, h);
}
{
  const h = p.parseMarkdown('a\n@@ blank{99}\n');
  chk('blank{99}:钳到 50', h.indexOf('data-blank="50"') >= 0, h);
}
{
  const h = p.parseMarkdown('a\n\n@@ blank{0}\n\nb\n');
  chk('blank{0}:fail-closed 原文可见', h.indexOf('mde-blank') < 0 && h.indexOf('@@ blank{0}') >= 0, h);
}
{
  const h = p.parseMarkdown('a\n\n@@ blank{abc}\n\nb\n');
  chk('blank{abc}:fail-closed 原文可见', h.indexOf('mde-blank') < 0 && h.indexOf('blank{abc}') >= 0, h);
}
{
  const h = p.parseMarkdown('a\n\n@@ blank\n\nb\n');
  chk('blank 无参:fail-closed 原文可见', h.indexOf('mde-blank') < 0 && h.indexOf('@@ blank') >= 0, h);
}
{
  const h = p.parseMarkdown('文字 @@ blank{1} 尾\n');
  chk('blank 紧贴文字:不生效（必须独占一行）', h.indexOf('mde-blank') < 0, h);
}
{
  /* 列表项内同样可用（列表里也要能硬控空档） */
  const h = p.parseMarkdown('1. a\n@@ blank{1}\n2. b\n');
  chk('blank 在列表内（物理打断，编号接力）',
    h.indexOf('mde-blank') >= 0 && h.indexOf('<ol start="2">') >= 0, h);
}

/* ===== 五、空行 / 换行口径（现状即目标，锁死防回归） ===== */
{
  const h = p.parseMarkdown('a\nb\n');
  chk('单回车=换行', h.indexOf('<p>a<br>b</p>') >= 0, h);
}
{
  const h = p.parseMarkdown('a\n\nb\n');
  chk('双回车=分段', (h.match(/<p>/g) || []).length === 2, h);
}
{
  const a = p.parseMarkdown('a\n\n\n\n\nb\n');
  chk('多空行不产生额外空白', (a.match(/<p>/g) || []).length === 2 && a.indexOf('<br>') < 0, a);
}
{
  const h = p.parseMarkdown('1. a\n续1\n续2\n2. b\n');
  chk('列表内单回车=换行（续行 <br>）', h.indexOf('<li>a<br>续1<br>续2</li>') >= 0, h);
}

/* ── v2.13.3 回归：包围块不吃兄弟块缩进 ───────────────────────────────
 * 实测事故：排版里设了「列表缩进」后，紧贴有序列表的 @@ begin fill 会继承
 * 列表缩进档（curInd=IPX.li），凭空左缩进一档；而 fill 结束写了 curInd=0，
 * 于是「只有紧跟列表的那一个缩进，下一个包围就恢复」。fill/color 是容器级
 * 块，缩进由外层 .ind-blk 承担，自身不写 margin-left。 */
{
  global.window = { __IND_PX__: { p: 0, quote: 0, li: 32 } };   // 模拟「列表缩进 2 字符」
  const src = '1. 资质与证书：\n@@ begin fill{50|50}\n![](a.png "A"){70}\n\n![](b.png "B"){70}\n@@ end fill\n'
            + '@@ begin fill{50|50}\n![](c.png "C"){70}\n\n![](d.png "D"){70}\n@@ end fill\n2. 第二项\n';
  const h = p.parseMarkdown(src);
  const rows = h.match(/<div class="fill-row"[^>]*>/g) || [];
  chk('紧贴列表的 fill-row 不继承列表缩进档', rows.length === 2 && rows.every(r => r.indexOf('margin-left') < 0), rows.join(' '));
  chk('两个 fill-row 的样式完全一致（无「第一个缩进、第二个恢复」）', new Set(rows).size === 1, rows.join(' '));

  const hc = p.parseMarkdown('1. x\n@@ begin color r\nabc\n@@ end color\n');
  const cm = hc.match(/<div class="mde-color"[^>]*>/g) || [];
  chk('紧贴列表的 color 块不继承列表缩进档', cm.length === 1 && cm[0].indexOf('margin-left') < 0, cm.join(' '));
  delete global.window;
}
/* v2.13.3 回归：@@ 硬块判据容忍行首缩进（与 <<< 及主循环同口径）。
 * 原先 /^@@/ 不容忍缩进 → 带空格的 @@ begin fill 被当列表延续行吞进 <li>，
 * 标记随之原样泄漏。 */
{
  for (const pre of [' ', '  ', '   ']) {
    const h = p.parseMarkdown('1. 证书：\n' + pre + '@@ begin fill{50|50}\n![](a.png "A"){70}\n\n![](b.png "B"){70}\n@@ end fill\n2. 下一项\n');
    chk('行首缩进 ' + pre.length + ' 空格的 @@ begin fill 仍是硬块（不泄漏 @@）',
      h.indexOf('fill-row') >= 0 && h.indexOf('@@') < 0, h.slice(0, 160));
  }
}

/* v2.13.4 回归：@@ caption 紧贴列表上一行时同样是硬块。
 * 原白名单只有 begin|end|blank → caption 行被当列表延续行吞进 <li>，
 * 题注标记 `@@` 原样泄漏、表格也进不了 tblwrap。 */
{
  const h = p.parseMarkdown('1. 前一页\n@@ caption{表 1}\n| x |\n| --- |\n| 1 |\n2. 后一页\n');
  chk('紧贴列表的 @@ caption 是硬块（不泄漏 @@、表格进 tblwrap）',
    h.indexOf('@@') < 0 && h.indexOf('mde-tblwrap') >= 0 && h.indexOf('<ol start="2">') >= 0,
    h.slice(0, 200));
  const hv = p.parseMarkdown('说明：@@ caption{表 1} 表题\n');
  chk('与文字同行的 @@ caption 仍按字面显示（fail-closed 不变）',
    hv.indexOf('@@') >= 0 && hv.indexOf('mde-tblwrap') < 0, hv.slice(0, 120));
}

console.log('\n' + (fail === 0 ? '✅ ' + total + '/' + total + ' 全过' : '❌ ' + fail + '/' + total + ' FAIL'));
process.exit(fail === 0 ? 0 : 1);
