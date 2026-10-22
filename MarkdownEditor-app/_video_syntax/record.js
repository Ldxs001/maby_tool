// MDEditor 语法与排版宣传片 · 确定性录制器
//   node record.js
// 产出：raw10/capture.mp4（1600x900 @25fps，无声，纯画面轨）
//        frames/0N-*.png（13 张时间线关键点验收帧，从成片抽取）
//        ../docs/宣传图/0N-*.png（同 13 个场景的配图版，隐去底部字幕条）
//
// 虚拟时钟 + 逐帧 screenshot：第 i 帧严格等于时间线 i/25 秒，与旁白分段起点零漂移。
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const PW = 'D:\\MEILINSOFFICE\\NODEJS\\NODE_GLOBAL\\node_modules\\@playwright\\cli\\node_modules\\playwright-core';
const { chromium } = require(PW);

const EXE = 'C:\\Users\\sm001\\AppData\\Local\\ms-playwright\\chromium-1217\\chrome-win64\\chrome.exe';
const FF = 'C:\\Users\\sm001\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.1-full_build\\bin\\ffmpeg.exe';

const FPS = 25;
const DUR = 105.65;                            // 与旁白实测时长回填一致
const TOTAL = Math.round(FPS * DUR);
const STEP = 1000 / FPS;
const W = 1600, H = 900;
const KEEP_FRAMES = false;

const OUTDIR = path.join(__dirname, 'raw10');
const FDIR = path.join(OUTDIR, 'frames');
const CAP = path.join(OUTDIR, 'capture.mp4');
const DOCS = 'C:\\Users\\sm001\\WorkBuddy\\maby_tool\\MarkdownEditor-app\\docs\\宣传图';
// 时间线关键点（ms）→ 验收帧 / 配图：覆盖 s0..s12 十三场景
const CHECKS = [
  [400,    '01-标题卡.png'], [13000, '02-基础语法.png'], [25000, '03-列表方言.png'],
  [34000,  '04-代码块.png'], [41000, '05-表格对齐.png'], [48000, '06-公式.png'],
  [56000,  '07-图表引擎.png'], [64000, '08-图片宽度.png'], [71000, '09-分栏.png'],
  [78000,  '10-缩进块.png'], [87000, '11-排版面板.png'], [95000, '12-语法速查.png'],
  [101000, '13-收尾.png'],
];

(async () => {
  fs.mkdirSync(FDIR, { recursive: true });

  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.error('  [page error] ' + e.message));

  await page.addInitScript(() => { window.__DRIVE__ = true; });
  await page.clock.install({ time: new Date(2026, 9, 15, 8, 0, 0) });
  const url = 'file:///' + path.join(__dirname, 'demo-syntax.html').split(path.sep).join('/');
  await page.goto(url, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(800);
  const fontStatus = await page.evaluate(() => document.fonts.status);
  await page.clock.pauseAt(new Date(2026, 9, 15, 8, 0, 30));

  if (!await page.evaluate(() => typeof window.__start === 'function'))
    throw new Error('demo-syntax.html 未提供 __start（驱动闸门未生效）');
  await page.evaluate(() => window.__start());

  const t0 = Date.now();
  const frames = [];
  for (let i = 0; i < TOTAL; i++) {
    if (i > 0) await page.clock.runFor(STEP);
    const file = path.join(FDIR, 'f' + String(i).padStart(5, '0') + '.jpg');
    await page.screenshot({ path: file, type: 'jpeg', quality: 92, animations: 'disabled' });
    frames.push(file);
    if (i % 250 === 0) console.log(`  frame ${i}/${TOTAL}  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }

  // 第二遍：同 13 个时间线关键点的文章配图版（隐去底部字幕条）
  fs.mkdirSync(DOCS, { recursive: true });
  const still = await ctx.newPage();
  await still.addInitScript(() => { window.__DRIVE__ = true; });
  await still.clock.install({ time: new Date(2026, 9, 15, 8, 1, 0) });
  await still.goto(url, { waitUntil: 'load' });
  await still.evaluate(() => document.fonts.ready);
  await still.waitForTimeout(500);
  await still.clock.pauseAt(new Date(2026, 9, 15, 8, 1, 30));
  await still.evaluate(() => { const c = document.getElementById('cap'); if (c) c.style.display = 'none'; });
  await still.evaluate(() => window.__start());
  let cur = 0;
  for (const [ms, name] of CHECKS) {
    await still.clock.runFor(ms - cur); cur = ms;
    await still.screenshot({ path: path.join(DOCS, name), animations: 'disabled' });
  }
  await still.close();
  await browser.close();

  const listFile = path.join(OUTDIR, 'frames.txt');
  fs.writeFileSync(listFile, frames.map(f => `file '${f.replace(/\\/g, '/')}'`).join('\n') + '\n');
  const r = spawnSync(FF, ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-r', String(FPS), '-i', listFile,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
    '-r', String(FPS), '-movflags', '+faststart', CAP], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('ffmpeg 编码失败:\n' + (r.stderr || '').slice(-900));

  // 验收帧一律从成片抽取，保证与最终画面同源
  fs.mkdirSync(path.join(__dirname, 'frames'), { recursive: true });
  for (const [ms, name] of CHECKS) {
    const e = spawnSync(FF, ['-y', '-v', 'error', '-ss', String(ms / 1000), '-i', CAP,
      '-frames:v', '1', path.join(__dirname, 'frames', name)], { encoding: 'utf8' });
    if (e.status !== 0) throw new Error('验收帧抽取失败 ' + name + ': ' + (e.stderr || '').slice(-300));
  }
  fs.rmSync(listFile, { force: true });

  console.log(`\n录制完成：${TOTAL} 帧 / ${DUR}s @ ${FPS}fps   耗时 ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  console.log(`字体状态：${fontStatus}`);
  console.log(`画面轨：${CAP}   ${(fs.statSync(CAP).size / 1048576).toFixed(2)} MB`);
  console.log(`配图：${DOCS}   ${CHECKS.length} 张`);
})().catch(e => { console.error('ERR: ' + e.message); process.exit(1); });
