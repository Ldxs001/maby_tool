# -*- coding: utf-8 -*-
"""隐私安全诊断：用用户文档跑结构诊断，输出仅含 ID/页号/布尔值，零正文内容。
内存中完成 doc.md -> parseMarkdown -> build_paged_html -> Paged.js -> 回填诊断。
不写任何用户内容到磁盘（打印版 HTML 落到 runtime 临时目录，诊断完即删）。"""
import io, os, sys, subprocess, zipfile, shutil

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
SMD = r'D:\Users\sm001\onedirve\OneDrive\Desktop\吴王思淼简历2026.smd'
OUT = os.path.join(APP, 'runtime', '_toc_probe')
TMP = os.path.join(OUT, '_priv_doc')

# 1. 解出最新 doc.md（zip 同名多版本，取最后一条）
z = zipfile.ZipFile(SMD)
names = [i for i in z.namelist() if i == 'doc.md']
md = z.read(names[-1]).decode('utf-8')
os.makedirs(TMP, exist_ok=True)
io.open(os.path.join(TMP, 'doc.md'), 'w', encoding='utf-8').write(md)

# 2. 解析（node md-parser.js，与编辑器预览同源）
r = subprocess.run(['node', '-e', '''
const { parseMarkdown } = require(%s);
const fs = require('fs');
const md = fs.readFileSync(process.argv[1], 'utf8');
process.stdout.write(parseMarkdown(md));
''' % repr(os.path.join(APP, 'md-parser.js')), os.path.join(TMP, 'doc.md')],
    capture_output=True, text=True, cwd=APP, encoding='utf-8')
if r.returncode:
    print('PARSE FAIL', r.stderr[:500]); sys.exit(1)
body_html = r.stdout
io.open(os.path.join(TMP, 'body.html'), 'w', encoding='utf-8').write(body_html)

# 3. 打印版
sys.path.insert(0, APP)
import md_server as S
pg = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
      'pn': {'on': 'on', 'pos': 'outer', 'tpl': '{p}', 'size': 9},
      'toc': {'on': 'on', 'solo': True, 'pos': 'top'}, 'img': 'orig'}
html = S.build_paged_html('', body_html, '', pg)
fp = os.path.join(TMP, 'print.html')
io.open(fp, 'w', encoding='utf-8').write(html)

# 4. Playwright 诊断（输出零正文）
diag = r'''
const pages = Array.from(document.querySelectorAll('.pagedjs_page'));
const skipOf = p => !!(p.querySelector('.md-toc-wrap') && !p.querySelector('[id^="md-h-"]'));
const regOf = p => { const e = p.querySelector('.page-region[data-pn]'); return e ? e.getAttribute('data-pn') : ''; };
const pgInfo = pages.map((p,i)=>({i, pn:regOf(p), skip:skipOf(p)}));
const toc = Array.from(document.querySelectorAll('.md-toc a[href^="#md-h-"]')).map(a => {
  const id = a.getAttribute('href').slice(1);
  const dst = document.getElementById(id);
  const pgEl = dst ? dst.closest('.pagedjs_page') : null;
  const idx = pgEl ? pages.indexOf(pgEl) : -1;
  const num = a.querySelector('.md-toc-pg');
  return {id, found:!!dst, page:idx, skip: idx>=0?skipOf(pages[idx]):null,
          pn: idx>=0?regOf(pages[idx]):'', shown: num?num.textContent:null};
});
return {n: pages.length, pgInfo, toc};
'''
driver = os.path.join(TMP, 'diag.py')
io.open(driver, 'w', encoding='utf-8').write('''# -*- coding: utf-8 -*-
import os, json
from playwright.sync_api import sync_playwright
url = 'file:///' + %r
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(url, wait_until='load')
    pg.wait_for_selector('.pagedjs_page', timeout=30000)
    pg.wait_for_timeout(2800)
    r = pg.evaluate("() => { " + %r + " }")
    b.close()
print(json.dumps(r, ensure_ascii=False))
''' % (os.path.join(TMP, 'print.html').replace('\\\\', '/'), diag))
r2 = subprocess.run([sys.executable, driver], capture_output=True, text=True, encoding='utf-8')
if r2.returncode:
    print('DIAG FAIL', r2.stderr[-600:]); sys.exit(1)
import json
d = json.loads(r2.stdout)
print('总页数', d['n'])
print('页: ' + ' '.join('%d:%s%s' % (x['i'], x['pn'] or '-', '(S)' if x['skip'] else '') for x in d['pgInfo']))
bad = 0
for t in d['toc']:
    if t['shown'] is None or t['page'] < 0:
        bad += 1
        print('  无页码: %s found=%s 落页=%s pn=%s skip=%s' % (t['id'], t['found'], t['page'], t['pn'], t['skip']))
print('目录条目 %d, 无页码 %d' % (len(d['toc']), bad))
