# -*- coding: utf-8 -*-
"""v2.17.0 端到端：真实 Paged.js 分页下的页区断页与页脚

分两段跑（同一文件双用途）：
  gen  —— 用打包 python import md_server，生成三份打印版 HTML；
  默认 —— 用系统 python + Playwright 打开，断言断页、页脚形态、封尾。

断言不依赖绝对页数（换字体/换纸就变），只依赖相对关系：
每页最多一个区、区首页页脚为该档起始值、区内递增、区外独立计数。
"""
import io, os, sys, json, subprocess

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
PYPACK = os.path.join(APP, 'python', 'python.exe')
OUT = os.path.join(APP, 'runtime', '_v2170_e2e')

PARA = ('页区页码端到端测试用的填充段落，只为把页面填满、让分页真实发生，'
        '本身不承载任何语义。') * 4


def paras(tag, n):
    return ''.join('<p>%s 第 %d 段：%s</p>' % (tag, k, PARA) for k in range(1, n + 1))


def seg(pn, pid, inner):
    return ('<div class="page-region" data-pn="%s" data-pr-id="%s">%s</div>'
            % (pn, pid, inner))


def gen():
    sys.path.insert(0, APP)
    import md_server as S

    pg = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
          'pn': {'on': 'on', 'pos': 'outer', 'tpl': '{p}|{P}|{N}', 'size': 9},
          'toc': {'on': 'off'}, 'img': 'orig'}

    docs = {
        # 全要素：区外 → noll → 罗马 → 阿拉伯 → 区外
        'pg_all': (paras('A', 4)
                   + seg('noll', 'pr1', paras('N', 8))
                   + seg('i', 'pr2', paras('R', 10))
                   + seg('1', 'pr3', paras('D', 10))
                   + paras('B', 4)),
        # 区域垫底：验证末尾不催空白页
        'pg_tail': paras('A', 2) + seg('1', 'pr1', paras('T', 10)),
        # 无页区：回归对照，输出必须与 v2.16.0 一致（1,2,3…）
        'pg_none': paras('C', 3) + paras('C', 3) + paras('C', 3),
    }
    os.makedirs(OUT, exist_ok=True)
    for name, body in docs.items():
        html = S.build_paged_html('', '<div class="markdown-body">' + body + '</div>', '', pg)
        fp = os.path.join(OUT, name + '.html')
        io.open(fp, 'w', encoding='utf-8').write(html)
        print('%s -> %d KB' % (name, os.path.getsize(fp) // 1024))


def main():
    if not os.path.isdir(OUT) or not os.path.isfile(os.path.join(OUT, 'pg_all.html')):
        subprocess.run([PYPACK, os.path.abspath(__file__), 'gen'], check=True)

    from playwright.sync_api import sync_playwright

    def load(pg, name):
        url = 'file:///' + os.path.join(OUT, name + '.html').replace('\\', '/')
        pg.goto(url, wait_until='load')
        pg.wait_for_selector('.pagedjs_page', timeout=30000)
        pg.wait_for_timeout(2200)   # 填充脚本 300ms × 3 次稳定判定
        return pg.evaluate("""() => Array.from(document.querySelectorAll('.pagedjs_page')).map(p => ({
          pns: Array.from(p.querySelectorAll('.page-region[data-pn]'))
                   .map(e => e.getAttribute('data-pn')),
          txt: p.textContent,
          foot: (p.querySelector('.pagedjs_margin-bottom-right .pagedjs_margin-content')||{}).textContent
                || (p.querySelector('.pagedjs_margin-bottom-left .pagedjs_margin-content')||{}).textContent
                || ''
        }))""")

    pass_n = fail_n = 0

    def t(name, fn):
        nonlocal pass_n, fail_n
        try:
            ok = fn() is True
            note = ''
        except Exception as e:
            ok = False
            note = '  ← %r' % (e,)
        print(('PASS' if ok else 'FAIL') + '  ' + name + ('' if ok else note))
        if ok:
            pass_n += 1
        else:
            fail_n += 1

    with sync_playwright() as pw:
        br = pw.chromium.launch()

        print('\n— 全要素文档：断页与档位 —')
        rows = load(br.new_page(), 'pg_all')
        n = len(rows)
        print('   共 %d 张纸：%s' % (n, [r['pns'] for r in rows]))

        def pns(r):
            return set(r['pns'])

        t('每张纸至多属于一个区（页码永不歧义）',
          lambda: all(len(pns(r)) <= 1 for r in rows))
        t('noll 区至少占一页，且这些页页脚全空',
          lambda: any(pns(r) == {'noll'} for r in rows) and all(
              not r['foot'] for r in rows if pns(r) == {'noll'}))
        t('罗马区存在，且页脚以 i 起、递增',
          lambda: [r['foot'].split('|')[0] for r in rows if pns(r) == {'i'}]
          == ['i', 'ii', 'iii', 'iv', 'v'][:sum(1 for r in rows if pns(r) == {'i'})])
        t('阿拉伯区存在，且页脚以 1 起、递增',
          lambda: [r['foot'].split('|')[0] for r in rows if pns(r) == {'1'}]
          == ['1', '2', '3', '4', '5'][:sum(1 for r in rows if pns(r) == {'1'})])
        t('区外页脚是阿拉伯，且与区内序列独立（区外从 1 重新数）',
          lambda: len([r for r in rows if not pns(r)]) >= 2 and
          all(r['foot'].split('|')[0].isdigit() for r in rows if not pns(r)))
        t('{P} 全篇恒定（页脚第二段唯一）',
          lambda: len(set(r['foot'].split('|')[1] for r in rows if r['foot'])) == 1)
        t('罗马区 {N} 跟随区内形态（罗马字母）',
          lambda: all(r['foot'].split('|')[2].isalpha()
                      for r in rows if pns(r) == {'i'}))
        t('区外 {N} 等于 {P}',
          lambda: all(r['foot'].split('|')[2] == r['foot'].split('|')[1]
                      for r in rows if not pns(r)))

        # 断页：区域起点必须是新页 —— 含区域前最后一段（A 第 4 段）的纸
        # 不应同时含 noll 区首段（N 第 1 段）
        t('区域起点强制断页（前区内容不与 noll 区同页）',
          lambda: not any('A 第 4 段' in r['txt'] and 'N 第 1 段' in r['txt'] for r in rows))
        t('区域终点强制断页（noll 区内容不与罗马区同页）',
          lambda: not any('N 第 8 段' in r['txt'] and 'R 第 1 段' in r['txt'] for r in rows))
        t('罗马区不与阿拉伯区同页',
          lambda: not any('R 第 10 段' in r['txt'] and 'D 第 1 段' in r['txt'] for r in rows))
        t('阿拉伯区不与后段区外同页',
          lambda: not any('D 第 10 段' in r['txt'] and 'B 第 1 段' in r['txt'] for r in rows))

        print('\n— 区域垫底：不出空白尾页 —')
        rows2 = load(br.new_page(), 'pg_tail')
        print('   共 %d 张纸' % len(rows2))
        last = rows2[-1]
        t('最后一张纸有正文内容（不催空白页）',
          lambda: 'T 第' in last['txt'] or 'A 第' in last['txt'])
        t('最后一张纸页脚非空', lambda: bool(last['foot']))

        print('\n— 无页区回归（与 v2.16.0 一致） —')
        rows3 = load(br.new_page(), 'pg_none')
        nums = [r['foot'].split('|')[0] for r in rows3]
        print('   页脚：', nums)
        t('每页都是纯阿拉伯 1..n', lambda: nums == [str(i) for i in range(1, len(rows3) + 1)])
        t('无任何 page-region', lambda: all(not r['pns'] for r in rows3))
        t('区外 {N} 等于 {P}', lambda: all(
            r['foot'].split('|')[1] == r['foot'].split('|')[2] for r in rows3))

        br.close()

    print('\n' + ('ALL PASS' if fail_n == 0 else 'FAILED %d' % fail_n) +
          '  (%d/%d)' % (pass_n, pass_n + fail_n))
    sys.exit(0 if fail_n == 0 else 1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'gen':
        gen()
    else:
        main()
