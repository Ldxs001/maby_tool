# -*- coding: utf-8 -*-
"""探针驱动：Playwright 跑 toc_probe.html，输出页区/页脚/目录回填"""
import os
from playwright.sync_api import sync_playwright

OUT = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app\runtime\_toc_probe'
url = 'file:///' + os.path.join(OUT, 'toc_probe.html').replace('\\', '/')

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(url, wait_until='load')
    pg.wait_for_selector('.pagedjs_page', timeout=30000)
    pg.wait_for_timeout(2600)
    r = pg.evaluate("""() => {
      const pages = Array.from(document.querySelectorAll('.pagedjs_page'));
      const pgInfo = pages.map((p,i) => {
        const rel = p.querySelector('.page-region[data-pn]');
        return {i, pn: rel?rel.getAttribute('data-pn'):'', id: rel?rel.getAttribute('data-pr-id'):'',
                foot: (p.querySelector('.pagedjs_margin-bottom-right .pagedjs_margin-content')||{}).textContent
                     || (p.querySelector('.pagedjs_margin-bottom-left .pagedjs_margin-content')||{}).textContent || ''};
      });
      const toc = Array.from(document.querySelectorAll('.md-toc a[href^="#md-h-"]')).map(a => {
        const href = a.getAttribute('href').slice(1);
        const dst = document.getElementById(href);
        const pgEl = dst ? dst.closest('.pagedjs_page') : null;
        const idx = pgEl ? pages.indexOf(pgEl) : -1;
        const pgnum = a.querySelector('.md-toc-pg');
        return {href, found: !!dst, pageIdx: idx, shown: pgnum?pgnum.textContent:null,
                hasDots: !!a.querySelector('.toc-dots')};
      });
      return {n: pages.length, pgInfo, toc};
    }""")
    b.close()

print('总页数', r['n'])
print('页区/页脚:')
for x in r['pgInfo']:
    print('  页%d pn=%s id=%s 页脚=[%s]' % (x['i'], x['pn'], x['id'], x['foot']))
print('目录回填:')
for t in r['toc']:
    print('  %s found=%s 落页=%s 显示=[%s] 点线=%s' % (t['href'], t['found'], t['pageIdx'], t['shown'], t['hasDots']))
