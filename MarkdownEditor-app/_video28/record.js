// MDEditor 2.8 宣传片 · 确定性录制器
//   node record.js            全量录制（114s @25fps）
//   LIMIT=14 node record.js   只录前 14 秒（快速验画面）
// 产出：raw28/capture.mp4（1600x900 @25fps，无声，纯画面轨）
//        frames/0N-*.png（成片抽帧验收）
//        stills/*.png（时间线关键点原图，自检用）
// 为何不用 playwright recordVideo：本机 CDP screencast 通道几乎不推帧，
// 改用「虚拟时钟 + 逐帧 screenshot」——第 i 帧严格等于时间线 i/25 秒，
// 与旁白分段起点零漂移。
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const PW = 'D:\\MEILINSOFFICE\\NODEJS\\NODE_GLOBAL\\node_modules\\@playwright\\cli\\node_modules\\playwright-core';
const { chromium } = require(PW);

const EXE = 'C:\\Users\\sm001\\AppData\\Local\\ms-playwright\\chromium-1217\\chrome-win64\\chrome.exe';
const FF = 'C:\\Users\\sm001\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0.1-full_build\\bin\\ffmpeg.exe';

const FPS = 25;
const FULL = 115.03;                              // 与 demo.html 的 __DUR__ 一致
const LIMIT = parseFloat(process.env.LIMIT || '0');
const DUR = LIMIT > 0 ? LIMIT : FULL;
const TOTAL = Math.round(FPS * DUR);
const STEP = 1000 / FPS;
const W = 1600, H = 900;

const OUTDIR = path.join(__dirname, 'raw28');
const FDIR = path.join(OUTDIR, 'frames');
const CAP = path.join(OUTDIR, 'capture.mp4');
const STILLS = path.join(__dirname, 'stills');

// 时间线关键点 → 自检帧（与 demo.html 的 TL 对应）
const CHECKS = [
  [400, '01-标题卡.png'], [14500, '02-问题.png'], [32000, '03-数据点.png'],
  [45000, '04-表格.png'], [60000, '05-图片.png'], [75000, '06-落点命名.png'],
  [86000, '07-解释器与包.png'], [96000, '08-手动运行.png'], [109000, '09-收尾.png'],
];

(async () => {
  fs.mkdirSync(FDIR, { recursive: true });

  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.error('  [page error] ' + e.message));

  await page.addInitScript(() => { window.__DRIVE__ = true; });
  await page.clock.install({ time: new Date(2026, 9, 25, 9, 0, 0) });
  const url = 'file:///' + path.join(__dirname, 'demo.html').split(path.sep).join('/');
  await page.goto(url, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(800);
  const fontStatus = await page.evaluate(() => document.fonts.status);
  await page.clock.pauseAt(new Date(2026, 9, 25, 9, 0, 30));

  if (!await page.evaluate(() => typeof window.__start === 'function'))
    throw new Error('demo.html 未提供 __start（驱动闸门未生效）');
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

  // 关键点原图（自检 / 需要时可作配图）
  fs.mkdirSync(STILLS, { recursive: true });
  const still = await ctx.newPage();
  await still.addInitScript(() => { window.__DRIVE__ = true; });
  await still.clock.install({ time: new Date(2026, 9, 25, 9, 1, 0) });
  await still.goto(url, { waitUntil: 'load' });
  await still.evaluate(() => document.fonts.ready);
  await still.waitForTimeout(500);
  await still.clock.pauseAt(new Date(2026, 9, 25, 9, 1, 30));
  await still.evaluate(() => window.__start());
  let cur = 0;
  for (const [ms, name] of CHECKS) {
    if (ms > DUR * 1000) break;
    await still.clock.runFor(ms - cur); cur = ms;
    await still.screenshot({ path: path.join(STILLS, name), animations: 'disabled' });
  }
  await still.close();
  await browser.close();

  const listFile = path.join(OUTDIR, 'frames.txt');
  fs.writeFileSync(listFile, frames.map(f => `file '${f.replace(/\\/g, '/')}'`).join('\n') + '\n');
  const r = spawnSync(FF, ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-r', String(FPS), '-i', listFile,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
    '-r', String(FPS), '-movflags', '+faststart', CAP], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('ffmpeg 编码失败:\n' + (r.stderr || '').slice(-900));

  fs.mkdirSync(path.join(__dirname, 'frames'), { recursive: true });
  for (const [ms, name] of CHECKS) {
    if (ms > DUR * 1000) break;
    const e = spawnSync(FF, ['-y', '-v', 'error', '-ss', String(ms / 1000), '-i', CAP,
      '-frames:v', '1', path.join(__dirname, 'frames', name)], { encoding: 'utf8' });
    if (e.status !== 0) throw new Error('验收帧抽取失败 ' + name + ': ' + (e.stderr || '').slice(-300));
  }
  fs.rmSync(listFile, { force: true });

  console.log(`\n录制完成：${TOTAL} 帧 / ${DUR}s @ ${FPS}fps   耗时 ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  console.log(`字体状态：${fontStatus}`);
  console.log(`画面轨：${CAP}   ${(fs.statSync(CAP).size / 1048576).toFixed(2)} MB`);
})().catch(e => { console.error('ERR: ' + e.message); process.exit(1); });
