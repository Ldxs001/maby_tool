/* _test_splitblocks_wrap.cjs -- v2.13.1 splitBlocks @@ 块感知回归测试
 *
 * 根因回顾：splitBlocks 在每个 #/## 行下刀，@@ begin full|fill|color
 * 块内含标题行（或标记紧贴标题）时 begin/end 被劈进相邻块，逐块
 * parseMarkdown 各自 fail-closed，孤儿标记原样泄漏。
 *
 * 本测试从 markdown-editor.html 现场抽取 splitBlocks 真身执行（防实现
 * 与测试漂移），复刻应用真实渲染路径：splitBlocks → 逐块 parseMarkdown。
 * PASS/FAIL 二元，FAIL 计数非零即退出码 1。 */
const fs = require('fs');
const path = require('path');
const p = require('./md-parser.js');

const html = fs.readFileSync(path.join(__dirname, 'markdown-editor.html'), 'utf8');

/* ---- 从 HTML 抽 splitBlocks 真身 ---- */
const m = html.match(/  function splitBlocks\(src\)\{[\s\S]*?\n  \}\r?\n/);
if (!m) { console.error('FAIL: splitBlocks 未在 markdown-editor.html 中找到'); process.exit(1); }
const splitBlocks = new Function('return (' + m[0].replace(/^  /, '').replace(/\s*$/, '') + ')')();
if (typeof splitBlocks !== 'function') { console.error('FAIL: splitBlocks 抽取后不可调用'); process.exit(1); }

/* ---- 应用真实渲染路径：切块 → 逐块解析 ---- */
function appRender(src) {
  return splitBlocks(src).map(b => p.parseMarkdown(b)).join('');
}

let fail = 0;
function chk(name, ok, detail) {
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + (ok || !detail ? '' : '  -- ' + detail));
  if (!ok) fail++;
}

/* 1. 根因场景：@@ begin full 紧贴 # 标题（用户原文结构） */
{
  const src = '@@ begin full\n# 个人工作简历\n@@ end full\n\n正文\n';
  const h = appRender(src);
  chk('full紧贴h1：标记零泄漏', !h.includes('@@'));
  chk('full紧贴h1：full-page 产出', h.includes('full-page'));
  chk('full紧贴h1：h1 正常渲染', h.includes('<h1>个人工作简历</h1>'));
}

/* 2. 根因场景：@@ begin fill{80|20} 紧贴 ## 标题，块内含 ## 与空行分栏 */
{
  const src = '> 引用\n\n@@ begin fill{80|20}\n## 基本信息\n1. 甲\n\n![](x.png)\n@@ end fill\n\n## 下一节\n\n内容\n';
  const h = appRender(src);
  chk('fill紧贴h2：标记零泄漏', !h.includes('@@'));
  chk('fill紧贴h2：80/20 分栏产出', h.includes('width:80%') && h.includes('width:20%'));
  chk('fill紧贴h2：栏内 h2 正常', h.includes('<h2>基本信息</h2>'));
  chk('fill紧贴h2：块外 h2 正常', h.includes('<h2>下一节</h2>'));
}

/* 3. 三种块全活：color 块内含标题也不再被劈 */
{
  const src = '@@ begin color #900\n## 红色标题\n正文\n@@ end color\n\n## 块外\n';
  const h = appRender(src);
  chk('color块内含h2：标记零泄漏', !h.includes('@@'));
  chk('color块内含h2：着色块产出', h.includes('mde-color'));
}

/* 4. 块外标题切分行为不变（增量渲染粒度回归） */
{
  const src = '# 章\n\n段落一\n\n## 节A\n\n段落二\n\n## 节B\n\n段落三\n';
  const bs = splitBlocks(src);
  chk('块外标题仍按 #/## 下刀', bs.length === 3, '实际块数=' + bs.length);
  chk('块外首块仍以 h1 开头', bs[0].startsWith('# 章'));
}

/* 5. 未闭合块：吞到文末（粒度变粗但渲染结果=fail-closed 同口径） */
{
  const src = '@@ begin full\n# 无闭合\n\n## 后续标题\n\n正文\n';
  const bs = splitBlocks(src);
  chk('未闭合块不无限劈块（吞到文末）', bs.length === 1, '实际块数=' + bs.length);
  const h = appRender(src);
  chk('未闭合块渲染结果：标记行按原文', h.includes('@@'), '输出=' + h.slice(0, 80));
  chk('未闭合块渲染结果：内容照常', h.includes('<h2>后续标题</h2>'));
}

/* 6. fence 内标记不算、fence 内 # 不下刀（原行为保持） */
{
  const src = '```\n@@ begin full\n## 假标题\n```\n\n## 真标题\n\n正文\n';
  const bs = splitBlocks(src);
  chk('fence 内 # 不下刀', bs.length === 2, '实际块数=' + bs.length);
  const h = appRender(src);
  chk('fence 内标记仍按代码原样', h.includes('<code>') && !h.includes('full-page'));
}

/* 7. 错配 end：遇任意 @@ end 恢复切分（防无限吞块） */
{
  const src = '@@ begin full\n# 甲\n@@ end fill\n\n## 乙\n\n正文\n';
  const bs = splitBlocks(src);
  chk('错配 end 也恢复切块', bs.length === 2, '实际块数=' + bs.length);
}

/* 8. 用户真实文件端到端（若存在） */
{
  const f = 'D:/Users/sm001/onedirve/OneDrive/Desktop/个人工作简历2026.md';
  if (fs.existsSync(f)) {
    const src = fs.readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
    const h = appRender(src);
    chk('真实文件：标记零泄漏', !h.includes('@@'));
    chk('真实文件：full-page 产出', h.includes('full-page'));
    chk('真实文件：fill-row 80/20 产出', h.includes('width:80%') && h.includes('width:20%'));
  }
}

console.log(fail === 0 ? '\n✅ 全部通过' : '\n❌ ' + fail + ' 条 FAIL');
process.exit(fail === 0 ? 0 : 1);
