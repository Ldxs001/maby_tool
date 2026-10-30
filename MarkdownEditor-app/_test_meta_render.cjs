/* 元数据区渲染取数（_metaFromWindow）的自动化断言。
   要钉死的规则（主人 2026-10-31）：**渲染 = zero + up 合成后的当前值**，
   不是建档那一刻的快照；up 把某字段改成空，该行就消失。

   该函数只读 window.__MDE_META__ 与 MDE_META_KEYS，不碰 DOM，
   所以直接抽取源码 + 一个 window 桩即可，不需要 jsdom。
*/
const fs = require('fs');
const path = require('path');

const HTML = path.join(__dirname, 'markdown-editor.html');
const src = fs.readFileSync(HTML, 'utf8');

function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) return null;
  let depth = 0, end = -1;
  for (let i = src.indexOf('{', start); i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
  }
  return end < 0 ? null : src.slice(start, end);
}

const fnSrc = extract('_metaFromWindow');
const keysLine = (src.match(/var MDE_META_KEYS=\[[^\n]*\];/) || [null])[0];
if (!fnSrc || !keysLine) { console.log('FAIL 未找到 _metaFromWindow 或 MDE_META_KEYS'); process.exit(1); }

/* ---------- 用 window 桩驱动真代码 ---------- */
function renderWith(meta) {
  const sandbox = { window: { __MDE_META__: meta }, String, Array, Object, null: null };
  const fn = new Function(
    'window',
    keysLine + '\n' + fnSrc + '\nreturn _metaFromWindow();'
  );
  return fn(sandbox.window);
}

const results = [];
function chk(name, cond, extra) { results.push({ name, ok: !!cond, extra }); }

/* T1 只有 zero：按建档快照渲染 */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲', author: '乙' } },
    up: [],
    fields: { title: '甲', author: '乙' }
  });
  chk('T1 zero 单独成区', r && r.rows.length === 2, r && JSON.stringify(r.rows));
  chk('T1b 标题值正确', r && r.rows[0].v === '甲');
  chk('T1c 无 up 时无「最近修改」', r && r.last === null);
}

/* T2 zero + up：必须渲染 up 之后的当前值（回归：曾只读 zero） */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '设置里的标题', author: '设置里的作者' } },
    up: [{ at: '2026-10-31 02:16', key: 'author', from: '设置里的作者', to: '改过的作者' }],
    fields: { title: '设置里的标题', author: '改过的作者' }
  });
  const author = r && r.rows.filter(function (x) { return x.k === '作者'; })[0];
  chk('T2 作者取 up 后的当前值', author && author.v === '改过的作者', author && author.v);
  chk('T2b 未改字段保持原值',
    r && r.rows.filter(function (x) { return x.k === '标题'; })[0].v === '设置里的标题');
  chk('T2c 仍报最近修改', r && r.last === '2026-10-31 02:16 · author', r && r.last);
}

/* T3 up 把字段改成空：该行消失（不是留一行空值） */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲', note: '备注' } },
    up: [{ at: '2026-10-31 02:20', key: 'note', from: '备注', to: '' }],
    fields: { title: '甲', note: '' }
  });
  chk('T3 清空的字段不出行', r && r.rows.length === 1, r && JSON.stringify(r.rows));
}

/* T4 无任何字段 → null（不占位、不出空区） */
{
  const r = renderWith({ zero: { fields: {} }, up: [], fields: {} });
  chk('T4 空档案返回 null', r === null, JSON.stringify(r));
}

/* T5 只有 up 里新增的字段（zero 里没有）也要出 */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲' } },
    up: [{ at: '2026-10-31 02:22', key: 'tags', from: '', to: '播客, 写作' }],
    fields: { title: '甲', tags: '播客, 写作' }
  });
  const tags = r && r.rows.filter(function (x) { return x.k === '标签'; })[0];
  chk('T5 up 新增字段参与渲染', tags && tags.v === '播客, 写作', tags && tags.v);
}

/* T6 无 window / 无数据：安全返回 null，不抛 */
{
  let threw = null, r = null;
  try { r = renderWith(null); } catch (e) { threw = e; }
  chk('T6 无档案不抛错', !threw, threw && threw.message);
  chk('T6b 无档案返回 null', r === null);
}

/* ---------- 输出 ---------- */
let pass = 0, fail = 0;
for (const r of results) {
  if (r.ok) { pass++; console.log('PASS ' + r.name); }
  else { fail++; console.log('FAIL ' + r.name + (r.extra ? '  ← ' + r.extra : '')); }
}
console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
