/* _chk_real_md.cjs —— 真实文档（个人工作简历2026.md）结构级校验：
 * 源码计数 vs 渲染产物计数逐项对齐，确认 v2.13.2 的块级规则没有吞掉/多发
 * 任何一类块。不做像素比对（那是视觉验证的活），只回答"块是否还在"。
 * 用法：node _chk_real_md.cjs "<md 路径>"
 */
const fs = require('fs');
const p = require('./md-parser.js');
const src = fs.readFileSync(process.argv[2], 'utf8').replace(/\r\n/g, '\n');
const lines = src.split('\n');
const h = p.parseMarkdown(src);

const countRe = (s, re) => (s.match(re) || []).length;

/* --- 源码侧 --- */
let fenced = 0, inFence = false;
lines.forEach(l => { if (/^```/.test(l)) { fenced++; inFence = !inFence; } });
const s = {
  img: countRe(src, /!\[[^\]]*\]\([^)]+?\)/g),
  heading: countRe(src, /^#{1,6} [^\n]+$/gm),
  li: countRe(src, /^[ ]*([-+]|[0-9]+\.) /gm),
  hr: countRe(src, /^[ ]*([-*_][ ]*){3,}$/gm),
  fence: fenced / 2,
  table: countRe(src, /^[ ]*\|?[-|: ]*[-][-|: ]*\|?[ ]*$/gm),
};

/* --- 产物侧 --- */
const o = {
  img: countRe(h, /<img /g),
  heading: countRe(h, /<h[1-6]>/g),
  li: countRe(h, /<li[ >]/g),
  hr: countRe(h, /<hr>/g),
  pre: countRe(h, /<pre>/g),
  table: countRe(h, /<table>/g),
  blank: countRe(h, /mde-blank/g),
  fig: countRe(h, /<figure/g),
};

console.log('源码:', JSON.stringify(s));
console.log('产物:', JSON.stringify(o));

let fail = 0;
const cmp = (name, a, b) => {
  const ok = a === b;
  if (!ok) fail++;
  console.log((ok ? 'ok   ' : 'FAIL ') + name + ' 源=' + a + ' 产物=' + b);
};
cmp('图片', s.img, o.img);
cmp('标题', s.heading, o.heading);
cmp('列表项', s.li, o.li);
cmp('围栏代码块', s.fence, o.pre);
/* 分隔线：源里的源行必须一一对应 <hr>（表格分隔行不匹配本正则，已排除） */
cmp('分隔线', s.hr, o.hr);

const leak = h.match(/@@\s*(begin|end|blank)\b/g);
console.log((leak ? 'FAIL ' : 'ok   ') + '无 @@ 标记泄漏' + (leak ? ' → ' + leak.slice(0, 5).join(',') : ''));
if (leak) fail++;

console.log(fail === 0 ? '\n✅ 真实文档结构校验全过' : '\n❌ ' + fail + ' 项 FAIL');
process.exit(fail === 0 ? 0 : 1);
