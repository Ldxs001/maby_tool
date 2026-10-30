/* 导出剔除（stripMetaZones）的自动化断言。
   该函数只用到 querySelectorAll / getAttribute / querySelector / textContent /
   createElement / replaceChild / removeChild，用最小 DOM 桩即可驱动，
   不需要 jsdom。函数体从 markdown-editor.html 现场抽取，保证测的是真代码。
*/
const fs = require('fs');
const path = require('path');

const HTML = path.join(__dirname, 'markdown-editor.html');
const src = fs.readFileSync(HTML, 'utf8');

/* ---------- 从 HTML 抽出 stripMetaZones 源码 ---------- */
const start = src.indexOf('function stripMetaZones(root, keepYaml){');
if (start < 0) { console.log('FAIL 未找到 stripMetaZones'); process.exit(1); }
let depth = 0, end = -1;
for (let i = src.indexOf('{', start); i < src.length; i++) {
  if (src[i] === '{') depth++;
  else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
}
const fnSrc = src.slice(start, end);

/* ---------- 最小 DOM 桩 ---------- */
class El {
  constructor(tag, attrs) {
    this.tagName = (tag || 'div').toUpperCase();
    this.attrs = attrs || {};
    this.children = [];
    this.parentNode = null;
    this._text = '';
    this.className = this.attrs['class'] || '';
  }
  getAttribute(k) { return k === 'class' ? (this.className || null) : (this.attrs[k] === undefined ? null : this.attrs[k]); }
  setAttribute(k, v) { this.attrs[k] = v; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i >= 0) this.children.splice(i, 1);
    c.parentNode = null;
    return c;
  }
  replaceChild(nw, old) {
    const i = this.children.indexOf(old);
    if (i >= 0) { this.children[i] = nw; nw.parentNode = this; old.parentNode = null; }
    return old;
  }
  get textContent() {
    if (this.children.length) return this.children.map(c => c.textContent).join('');
    return this._text;
  }
  set textContent(v) { this._text = v; this.children = []; }
  /* 只实现本项目用到的选择器：tag.class / .class / [attr] */
  _match(sel) {
    if (sel.startsWith('[')) {
      const k = sel.slice(1, -1);
      return this.attrs[k] !== undefined;
    }
    const m = /^([a-zA-Z]*)((?:\.[\w-]+)*)$/.exec(sel);
    if (!m) return false;
    const tag = m[1].toLowerCase();
    if (tag && this.tagName.toLowerCase() !== tag) return false;
    const cls = m[2].split('.').filter(Boolean);
    const mine = (this.className || '').split(/\s+/).filter(Boolean);
    return cls.every(c => mine.indexOf(c) >= 0);
  }
  querySelectorAll(sel) {
    const out = [];
    const walk = n => {
      for (const c of n.children) {
        if (c._match(sel)) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  querySelector(sel) { const r = this.querySelectorAll(sel); return r.length ? r[0] : null; }
}

const mk = (tag, attrs) => new El(tag, attrs);

/* 造一份预览树：普通正文 + zone=a（front matter）+ zone=x（冲突条） */
function build() {
  const root = mk('div');
  root.appendChild(mk('p')).textContent = '正文';

  const a = mk('div', { 'data-mde-zone': 'a', 'class': 'mde-fm' });
  const h = mk('div', { 'class': 'mde-fm-h' }); h.textContent = '元数据';
  a.appendChild(h);
  const r1 = mk('div', { 'class': 'mde-fm-row' });
  const k1 = mk('span', { 'class': 'mde-fm-k' }); k1.textContent = 'title';
  const v1 = mk('span', { 'class': 'mde-fm-v' }); v1.textContent = '我写故我播';
  r1.appendChild(k1); r1.appendChild(v1); a.appendChild(r1);
  const r2 = mk('div', { 'class': 'mde-fm-row' });
  const k2 = mk('span', { 'class': 'mde-fm-k' }); k2.textContent = 'author';
  const v2 = mk('span', { 'class': 'mde-fm-v' }); v2.textContent = 'wUwproject';
  r2.appendChild(k2); r2.appendChild(v2); a.appendChild(r2);
  root.appendChild(a);

  const b = mk('div', { 'data-mde-zone': 'b', 'class': 'mde-fm' });
  b.appendChild(mk('div', { 'class': 'mde-fm-row' }));
  root.appendChild(b);

  const x = mk('div', { 'data-mde-zone': 'x', 'class': 'mde-fm mde-fm-conflict' });
  x.textContent = '元数据冲突';
  root.appendChild(x);

  return root;
}

/* 把函数注入桩环境执行 */
const factory = new Function('document', fnSrc + '\nreturn stripMetaZones;');
const document = { createElement: t => new El(t) };
const stripMetaZones = factory(document);

const results = [];
function chk(name, cond, extra) { results.push({ name, ok: !!cond, extra }); }

/* T16 docx / paged：三条数据区全删，正文不动 */
{
  const root = build();
  stripMetaZones(root, false);
  const left = root.querySelectorAll('[data-mde-zone]');
  chk('T16 docx 导出删净元数据区', left.length === 0, '残留 ' + left.length);
  chk('T16b 正文保留', root.textContent.indexOf('正文') >= 0);
  chk('T16c 未留 pre', root.querySelectorAll('pre').length === 0);
}

/* T17 HTML 导出：zone=a 还原成 front matter 原文，zone=b/x 删除 */
{
  const root = build();
  stripMetaZones(root, true);
  const pres = root.querySelectorAll('pre');
  chk('T17 HTML 导出只还原一块', pres.length === 1, 'pre=' + pres.length);
  const txt = pres.length ? pres[0].textContent : '';
  const want = '---\ntitle: 我写故我播\nauthor: wUwproject\n---\n';
  chk('T17b 还原内容逐字相符', txt === want, JSON.stringify(txt));
  chk('T17c 还原块带 mde-fm-src 类', pres.length ? pres[0].className === 'mde-fm-src' : false);
  const left = root.querySelectorAll('[data-mde-zone]');
  chk('T17d 其余数据区删净', left.length === 0, '残留 ' + left.length);
}

/* T18 无元数据区：不报错、DOM 原样 */
{
  const root = mk('div');
  root.appendChild(mk('p')).textContent = '只有正文';
  let threw = null;
  try { stripMetaZones(root, true); } catch (e) { threw = e; }
  chk('T18 无元数据区不抛错', !threw, threw && threw.message);
  chk('T18b 正文原样', root.textContent === '只有正文');
}

/* T19 null 入参安全 */
{
  let threw = null;
  try { stripMetaZones(null, false); } catch (e) { threw = e; }
  chk('T19 null 入参安全', !threw, threw && threw.message);
}

/* ---------- 输出 ---------- */
let bad = 0;
for (const r of results) {
  if (!r.ok) bad++;
  console.log((r.ok ? 'PASS  ' : 'FAIL  ') + r.name + (r.extra ? '  [' + r.extra + ']' : ''));
}
console.log('------------------------------------------------------------');
console.log('合计 ' + results.length + ' 条：PASS ' + (results.length - bad) + ' / FAIL ' + bad);
process.exit(bad ? 1 : 0);
