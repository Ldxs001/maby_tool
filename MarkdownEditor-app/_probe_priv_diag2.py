# -*- coding: utf-8 -*-
"""打印全部目录条目回填明细（只输出 ID/页号/数值，零正文）"""
import os, json, subprocess, sys

TMP = os.path.join(r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app',
                   'runtime', '_toc_probe', '_priv_doc')
diag = '''
const pages = Array.from(document.querySelectorAll('.pagedjs_page'));
const skipOf = p => !!(p.querySelector('.md-toc-wrap') && !p.querySelector('[id^="md-h-"]'));
const regOf = p => { const e = p.querySelector('.page-region[data-pn]'); return e ? e.getAttribute('data-pn') : ''; };
const toc = Array.from(document.querySelectorAll('.md-toc a[href^="#md-h-"]')).map(a => {
  const id = a.getAttribute('href').slice(1);
  const dst = document.getElementById(id);
  const pgEl = dst ? dst.closest('.pagedjs_page') : null;
  const idx = pgEl ? pages.indexOf(pgEl) : -1;
  const num = a.querySelector('.md-toc-pg');
  const dots = a.querySelector('.toc-dots');
  return {id, lvl: a.parentNode.className, page:idx, skip: idx>=0?skipOf(pages[idx]):null,
          pn: idx>=0?regOf(pages[idx]):'', shown: num?num.textContent:null, dots: !!dots};
});
return toc;
'''
driver = os.path.join(TMP, 'diag2.py')
open(driver, 'w', encoding='utf-8').write('''# -*- coding: utf-8 -*-
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
''' % (os.path.join(TMP, 'print.html').replace(chr(92), '/'), diag))
r = subprocess.run([sys.executable, driver], capture_output=True, text=True, encoding='utf-8')
if r.returncode:
    print('FAIL', r.stderr[-400:]); sys.exit(1)
for t in json.loads(r.stdout):
    print('%s lvl=%s 落页=%s pn=%s skip=%s 显示=[%s] 点线=%s' % (
        t['id'], t['lvl'], t['page'], t['pn'], t['skip'], t['shown'], t['dots']))
