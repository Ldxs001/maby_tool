# -*- coding: utf-8 -*-
"""v2.18.0 端到端：并写 @@ begin page{noll} full 的真实分页效果

分两段跑（同一文件双用途）：
  gen  —— 用打包 python import md_server，生成三份打印版 HTML；
  默认 —— 用系统 python + Playwright 打开，断言断页、页脚、着色。

断言不依赖绝对页数（换字体/换纸就变），只依赖相对关系：
封面页独立成页、noll 区页脚为空、罗马区页脚为罗马、并写与嵌套出纸一致。
"""
import io, os, sys, json, subprocess

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
PYPACK = os.path.join(APP, 'python', 'python.exe')
OUT = os.path.join(APP, 'runtime', '_v2180_e2e')

FILLER = '封面／扉页这一页的正文，只为观察它是否单独起页、页脚是否被写号。' * 2

DOCS = {
    # 并写：封面 = 单独一页 + 不编号
    'm_cover': ('前文一段。\n\n@@ begin page{noll} full{t}\n# 书名\n\n' + FILLER +
                '\n@@ end page\n\n后文一段。'),
    # 嵌套：等价写法（两组 begin/end）
    'n_cover': ('前文一段。\n\n@@ begin page{noll}\n@@ begin full{t}\n# 书名\n\n' + FILLER +
                '\n@@ end full\n@@ end page\n\n后文一段。'),
    # 并写三家族：罗马页区 + 整页 + 着色
    'm_roman': ('前文一段。\n\n@@ begin page{i} full color r\n## 序\n\n' + FILLER +
                '\n@@ end page\n\n后文一段。'),
}


def gen():
    js = ('const {parseMarkdown}=require("./md-parser.js");'
          'const d=JSON.parse(process.argv[1]);const o={};'
          'for(const k in d){o[k]=parseMarkdown(d[k]);}'
          'console.log(JSON.stringify(o));')
    r = subprocess.run(['node', '-e', js, json.dumps(DOCS, ensure_ascii=False)],
                       cwd=APP, capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print('NODE ERR', r.stderr)
        sys.exit(1)
    bodies = json.loads(r.stdout)

    sys.path.insert(0, APP)
    import md_server as S
    pg = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
          'pn': {'on': 'on', 'pos': 'outer', 'tpl': '[{p}]', 'size': 9},
          'toc': {'on': 'off'}, 'img': 'orig'}
    os.makedirs(OUT, exist_ok=True)
    for name, body in bodies.items():
        html = S.build_paged_html('', '<div class="markdown-body">' + body + '</div>', '', pg)
        io.open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8').write(html)
        print('%s -> %d KB' % (name, os.path.getsize(os.path.join(OUT, name + '.html')) // 1024))


def read_page(p):
    return p.evaluate("""() => {const o=[];
      document.querySelectorAll('.pagedjs_page').forEach((el,i)=>{
        const c=el.querySelector('.pagedjs_page_content')||el;
        const t=c.innerText.trim();
        const f=[...el.querySelectorAll('.pagedjs_margin-content')]
                 .map(x=>x.textContent.trim()).filter(x=>x);
        o.push({n:i+1, txt:t, foot:f.join(','),
                colorFull: (()=>{const u=c.querySelector('.full-page');
                                 return u?getComputedStyle(u).color:null;})()});
      });
      return o;}""")


def main():
    from playwright.sync_api import sync_playwright
    import re
    res = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for name in DOCS:
            fp = os.path.join(OUT, name + '.html')
            p = br.new_page()
            p.goto('file:///' + fp.replace(os.sep, '/'))
            p.wait_for_timeout(2600)
            res[name] = read_page(p)
            p.close()
        br.close()

    pass_ = fail = 0

    def t(name, fn):
        nonlocal pass_, fail
        ok = False
        note = ''
        try:
            ok = fn() is True
        except Exception as e:
            note = '  ← %s' % e
        print(('PASS' if ok else 'FAIL') + '  ' + name + ('' if ok else note))
        if ok:
            pass_ += 1
        else:
            fail += 1

    cov = res['m_cover']
    nest = res['n_cover']
    rom = res['m_roman']

    def page_of(rows, kw):
        for r in rows:
            if kw in r['txt']:
                return r
        return None

    print('\n— 并写封面 page{noll} full —')
    t('共 3 页（前文 / 封面 / 后文）', lambda: len(cov) == 3)
    t('封面单独成页（不与前文同页）',
      lambda: page_of(cov, '书名') is not None and '前文一段' not in page_of(cov, '书名')['txt'])
    t('封面页页脚为空（noll 生效）', lambda: page_of(cov, '书名')['foot'] == '')
    t('封面页有 .full-page（整页定位生效）',
      lambda: page_of(cov, '书名')['colorFull'] is not None)
    t('前文页页脚为 [1]', lambda: page_of(cov, '前文一段')['foot'] == '[1]')
    t('后文页页脚为 [2]（封面页不占号）', lambda: page_of(cov, '后文一段')['foot'] == '[2]')

    print('\n— 并写与两层嵌套出纸一致 —')
    t('页数相同', lambda: len(cov) == len(nest))
    t('逐页页脚相同', lambda: [r['foot'] for r in cov] == [r['foot'] for r in nest])
    t('逐页文本相同', lambda: [re.sub(r'\s+', '', r['txt']) for r in cov] ==
      [re.sub(r'\s+', '', r['txt']) for r in nest])

    print('\n— 三家族并写 page{i} full color r —')
    t('共 3 页', lambda: len(rom) == 3)
    t('序页单独成页', lambda: page_of(rom, '序') is not None and
      '前文一段' not in page_of(rom, '序')['txt'])
    t('序页页脚为罗马 [i]', lambda: page_of(rom, '序')['foot'] == '[i]')
    t('序页整页容器为红色', lambda: page_of(rom, '序')['colorFull'] == 'rgb(229, 57, 53)')
    t('后文页页脚为 [2]（区内页自成序列，不占区外号）',
      lambda: page_of(rom, '后文一段')['foot'] == '[2]')

    print('\n' + ('ALL PASS' if fail == 0 else 'FAILED %d' % fail) +
          '  (%d/%d)' % (pass_, pass_ + fail))
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'gen':
        gen()
    else:
        if not os.path.isfile(os.path.join(OUT, 'm_cover.html')):
            subprocess.run([PYPACK, os.path.abspath(__file__), 'gen'], check=True)
        sys.exit(main())
