/* 元数据区渲染取数（_metaFromWindow）的自动化断言。

   要钉死的规则：
     ① **渲染 = zero + up 合成后的当前值**（主人 2026-10-31），不是建档那一刻
        的快照；up 把某字段改成空，该行就消失。
     ② v2.26.3 结构：返回 {rows, head, last}——
        head 是置顶的「作者 / 创建」两行（档案元信息，后端 read() 合成好送来），
        last 只回答"什么时候"（不带字段名），rows 是其余键值（作者不重复出）。
     ③ 标签随界面语言（__MDE_LANG__），解析器段自带 _FM_LBL_EN 不依赖宿主词表。

   该函数只读 window.__MDE_META__ / __MDE_LANG__ 与 MDE_META_KEYS，不碰 DOM，
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
const fTxt = extract('_fmTxt');
const fStamp = extract('_fmStamp');
const keysLine = (src.match(/var MDE_META_KEYS=\[[^\n]*\];/) || [null])[0];
const lblLine = (src.match(/var _FM_LBL_EN=\{[^;]*\};/) || [null])[0];
if (!fnSrc || !fTxt || !fStamp || !keysLine || !lblLine) {
  console.log('FAIL 未找到 _metaFromWindow / _fmTxt / _fmStamp / MDE_META_KEYS / _FM_LBL_EN');
  process.exit(1);
}

/* ---------- 用 window 桩驱动真代码 ---------- */
function renderWith(meta, lang, fb) {
  const sandbox = {
    window: { __MDE_META__: meta, __MDE_LANG__: lang || 'zh',
              __MDE_META_FALLBACK__: fb || null },
    String, Array, Object, null: null
  };
  const fn = new Function(
    'window',
    keysLine + '\n' + lblLine + '\n' + fTxt + '\n' + fStamp + '\n' + fnSrc +
    '\nreturn _metaFromWindow();'
  );
  return fn(sandbox.window);
}

const results = [];
function chk(name, cond, extra) { results.push({ name, ok: !!cond, extra }); }
function headOf(r, k) {
  if (!r || !r.head) return null;
  return r.head.filter(function (x) { return x.k === k; })[0] || null;
}
function rowOf(r, k) {
  if (!r || !r.rows) return null;
  return r.rows.filter(function (x) { return x.k === k; })[0] || null;
}

/* T1 只有 zero：作者 + 创建 置顶，其余键值成行（老档案没有 authors 字段也能出） */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲', author: '乙' } },
    up: [],
    fields: { title: '甲', author: '乙' }
  });
  chk('T1 作者/创建置顶成两行', r && r.head && r.head.length === 2,
    r && JSON.stringify(r.head));
  chk('T1b 代称值正确', rowOf(r, '代称') && rowOf(r, '代称').v === '甲');
  chk('T1c 无 up 时无「最近修改」', r && r.last === null, r && String(r.last));
  chk('T1d 创建时间格式化为 YYYY-MM-DD HH:MM',
    headOf(r, '创建') && headOf(r, '创建').v === '2026-10-31 02:15',
    headOf(r, '创建') && headOf(r, '创建').v);
  chk('T1e 作者不出现在 rows（不重复）', r && !rowOf(r, '作者'));
}

/* T2 作者链：后端合成好 authors，前端照用，不自己拼 */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '设置里的标题', author: 'default' } },
    authors: ['default', 'Ldxs', '张三'],
    created: '2026-10-31T02:15:57+0800',
    last: '2026-10-31 02:16',
    up: [{ at: '2026-10-31 02:16', who: 'Ldxs', key: 'author', from: 'default', to: 'Ldxs' }],
    fields: { title: '设置里的标题', author: 'Ldxs' }
  });
  chk('T2 作者链按序逗号连接', headOf(r, '作者') && headOf(r, '作者').v === 'default，Ldxs，张三',
    headOf(r, '作者') && headOf(r, '作者').v);
  chk('T2b 未改字段保持原值', rowOf(r, '代称') && rowOf(r, '代称').v === '设置里的标题');
  chk('T2c 最近修改只报时间不带字段名', r && r.last === '2026-10-31 02:16', r && r.last);
}

/* T2d 老后端不返回 authors / last：兜底仍要正确，不崩不空 */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲', author: '乙' } },
    up: [{ at: '2026-10-31 02:20', key: 'title', from: '旧', to: '甲' }],
    fields: { title: '甲', author: '乙' }
  });
  chk('T2d 无 authors 时用 fields.author 兜底', headOf(r, '作者') && headOf(r, '作者').v === '乙',
    headOf(r, '作者') && headOf(r, '作者').v);
  chk('T2e 无 last 时从 up 末条取时间', r && r.last === '2026-10-31 02:20', r && r.last);
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

/* T4 档案存在但一个字段都没填：**仍要出区**——作者 default + 创建，
   这样用户写 @@ meta 的时候不至于什么都不显示（主人 2026-11-01 裁定）。
   只有"压根没有档案"才返回 null（见 T6b）。 */
{
  const r = renderWith({ zero: { created: 'none', fields: {} }, up: [], fields: {} });
  chk('T4 空档案仍出区（作者/创建）', r && headOf(r, '作者') && headOf(r, '创建'),
    JSON.stringify(r));
  chk('T4b 空档案作者记为 default', headOf(r, '作者') && headOf(r, '作者').v === 'default',
    headOf(r, '作者') && headOf(r, '作者').v);
}

/* T5 只有 up 里新增的字段（zero 里没有）也要出 */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲' } },
    up: [{ at: '2026-10-31 02:22', who: 'Ldxs', key: 'tags', from: '', to: '播客, 写作' }],
    fields: { title: '甲', tags: '播客, 写作' }
  });
  const tags = rowOf(r, '标签');
  chk('T5 up 新增字段参与渲染', tags && tags.v === '播客, 写作', tags && tags.v);
}

/* T6 无 window / 无数据：安全返回 null，不抛 */
{
  let threw = null, r = null;
  try { r = renderWith(null); } catch (e) { threw = e; }
  chk('T6 无档案不抛错', !threw, threw && threw.message);
  chk('T6b 无档案返回 null', r === null);
}

/* T7 接手别人的文件：创建写 none，不许编日期 */
{
  const r = renderWith({
    zero: { created: 'none', fields: { author: 'default' } },
    authors: ['default', 'Ldxs'],
    created: 'none',
    last: '2026-11-01 21:40',
    up: [{ at: '2026-11-01 21:40', who: 'Ldxs', key: null, note: '建档' }],
    fields: { author: 'default' }
  });
  chk('T7 创建为 none 时原样显示', headOf(r, '创建') && headOf(r, '创建').v === 'none',
    headOf(r, '创建') && headOf(r, '创建').v);
}

/* T8 老档案里的 date 仍可读可显示（面板不再能改，但显示不能丢） */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲', date: '2026-10-01' } },
    fields: { title: '甲', date: '2026-10-01' }
  });
  chk('T8 老档案 date 仍渲染', rowOf(r, '日期') && rowOf(r, '日期').v === '2026-10-01',
    rowOf(r, '日期') && rowOf(r, '日期').v);
}

/* T9 切英文：标签全英文（解析器段自带 _FM_LBL_EN，不依赖宿主词表） */
{
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '甲', author: '乙', date: '2026-10-01' } },
    authors: ['乙'], created: '2026-10-31T02:15:57+0800', last: '2026-10-31 02:16',
    fields: { title: '甲', author: '乙', date: '2026-10-01' }
  }, 'en');
  chk('T9 英文标签', headOf(r, 'Author') && headOf(r, 'Created') &&
    rowOf(r, 'Alias') && rowOf(r, 'Date'), r && JSON.stringify(r.head));
  chk('T9b 英文态无中文残留', r && !/[作者创建代称日期]/.test(
    JSON.stringify(r.head) + JSON.stringify(r.rows)), r && JSON.stringify(r));
}

/* T10 SM3 指纹：full 存全长、short 只出前 8 位（渲染层规则，与 up.md 写全长不冲突） */
{
  const full = '9f8e7d6c1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5';
  const r = renderWith({ zero: { fields: { author: '乙' } }, authors: ['乙'],
                         created: 'none', last: '2026-11-01 23:10',
                         fields: { author: '乙' }, hash: full, stale: false });
  chk('T10 指纹 short 取前 8 位', r && r.fp && r.fp.short === full.slice(0, 8),
    r && r.fp && r.fp.short);
  chk('T10b 指纹 full 保存全长', r && r.fp && r.fp.full === full,
    r && r.fp && r.fp.full.length);
  chk('T10c stale=false 不出告警', r && r.warn === false, r && r.warn);
}

/* T11 stale=true 出告警（磁盘正文与末条不符：有未记录的改动） */
{
  const r = renderWith({ zero: { fields: {} }, fields: {}, authors: ['default'],
                         hash: 'a'.repeat(64), stale: true });
  chk('T11 stale=true → warn=true', r && r.warn === true, r && r.warn);
}

/* T12 老档案没有指纹：fp 为 null，stale=null 也不出告警（"不知道"不冒充"正常"也不冒充"有错"） */
{
  const r = renderWith({ zero: { fields: { author: '乙' } }, authors: ['乙'],
                         fields: { author: '乙' }, stale: null });
  chk('T12 无指纹 → fp=null', r && r.fp === null, r && r.fp);
  chk('T12b stale=null 不告警', r && r.warn === false, r && r.warn);
}

/* T13 标签/代称的显示只看履历（主人 2026-11-02 定）：
     覆盖显示 = up（含 zero 建档）里最后一次被记录的值；
     为空为继承 = 本次保存没记就沿用之前的；
     全链没记过 = 留空。
   排版设置只是输入口，**save 之前绝不参与显示**——
   T13c 故意塞一个残留的 __MDE_META_FALLBACK__ 桩，钉死渲染不回读设置。 */
{
  /* 13a zero 记过、up 作者没记 → 继承 zero */
  const r = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800',
            fields: { title: '项目甲', tags: '技术文档', author: '乙' } },
    authors: ['乙', '丙'], created: '2026-10-31T02:15:57+0800',
    last: '2026-11-02 00:10',
    up: [{ at: '2026-11-02 00:10', who: '丙', key: null, note: '保存' }],
    fields: { title: '项目甲', tags: '技术文档', author: '丙' }
  });
  chk('T13a zero 有值、up 没记 → 继承 zero 的代称',
    rowOf(r, '代称') && rowOf(r, '代称').v === '项目甲', rowOf(r, '代称') && rowOf(r, '代称').v);
  chk('T13b zero 有值、up 没记 → 继承 zero 的标签',
    rowOf(r, '标签') && rowOf(r, '标签').v === '技术文档', rowOf(r, '标签') && rowOf(r, '标签').v);

  /* 13c 全链没记过 → 留空，设置兜底桩必须被无视（本质看履历） */
  const r2 = renderWith(
    { zero: { created: 'none', fields: {} }, authors: ['default'],
      created: 'none', fields: {} },
    'zh', { title: '设置值不许显示', tags: '同上' });
  chk('T13c 全链没记 → 不出行，且无视设置桩',
    r2 && !rowOf(r2, '代称') && !rowOf(r2, '标签'), r2 && JSON.stringify(r2.rows));

  /* 13d 前面的作者记过、本次没记 → 继承之前；最后一次记录的值覆盖显示 */
  const r3 = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { author: '乙' } },
    authors: ['乙', '丙', '丁'], created: '2026-10-31T02:15:57+0800',
    last: '2026-11-02 00:12',
    up: [{ at: '2026-11-01 09:00', who: '丙', key: 'tags', from: '', to: '播客, 写作' },
         { at: '2026-11-02 00:12', who: '丁', key: null, note: '保存' }],
    fields: { author: '丁', tags: '播客, 写作' }
  });
  chk('T13d 前面作者记过、本次没记 → 继承显示之前的标签',
    rowOf(r3, '标签') && rowOf(r3, '标签').v === '播客, 写作',
    rowOf(r3, '标签') && rowOf(r3, '标签').v);
  chk('T13e 从没人记过代称 → 代称行不出', r3 && !rowOf(r3, '代称'), JSON.stringify(r3 && r3.rows));

  /* 13f 本次保存记了新值 → 覆盖显示最新的 */
  const r4 = renderWith({
    zero: { created: '2026-10-31T02:15:57+0800', fields: { title: '旧项目' } },
    authors: ['乙', '丙'], created: '2026-10-31T02:15:57+0800',
    last: '2026-11-02 00:14',
    up: [{ at: '2026-11-02 00:14', who: '丙', key: 'title', from: '旧项目', to: '新项目' }],
    fields: { title: '新项目' }
  });
  chk('T13f 最后一次记录的代称覆盖显示', rowOf(r4, '代称') && rowOf(r4, '代称').v === '新项目',
    rowOf(r4, '代称') && rowOf(r4, '代称').v);

  /* 13g 英文态：代称行是 Alias */
  const r5 = renderWith({
    zero: { created: 'none', fields: { title: '项目甲' } },
    authors: ['default'], created: 'none', fields: { title: '项目甲' }
  }, 'en');
  chk('T13g 英文继承行显示 Alias', rowOf(r5, 'Alias') && rowOf(r5, 'Alias').v === '项目甲',
    r5 && JSON.stringify(r5.rows));
}

/* ---------- 输出 ---------- */
let pass = 0, fail = 0;
for (const r of results) {
  if (r.ok) { pass++; console.log('PASS ' + r.name); }
  else { fail++; console.log('FAIL ' + r.name + (r.extra ? '  ← ' + r.extra : '')); }
}
console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
