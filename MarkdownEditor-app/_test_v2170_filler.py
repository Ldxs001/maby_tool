# -*- coding: utf-8 -*-
"""v2.17.0 页码填充脚本：{p}/{P}/{N} 与页区档位

不启服务、不跑 Paged.js——手搭一份 .pagedjs_page 骨架，直接执行服务端
真正注入的那段 PAGED_FILLER_TMPL（从 md_server.py 源码抽出），断言每页
margin box 落下的字符串。测的是产品代码本身，不是它的复制品。

v2.19.1 起回填入口是 window.__pgFill()（由 PagedConfig.after 触发），
场景一直接调它验证回填逻辑；场景四验证轮询兜底（6s 稳定窗口）仍能触发。
"""
import io, os, sys, json

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
SRC = os.path.join(APP, 'md_server.py')
TPL_TAG = 'PAGED_FILLER_TMPL = """'

_src = io.open(SRC, encoding='utf-8').read()
_i = _src.index(TPL_TAG)
_j = _src.index('\n"""\n', _i)
FILLER = _src[_i + len(TPL_TAG) + 1:_j + 1]
assert '__TPL__' in FILLER and 'toRoman' in FILLER, '模板抽取失败'

SEL = {'odd': '.pagedjs_margin-bottom-right .pagedjs_margin-content',
       'even': '.pagedjs_margin-bottom-left .pagedjs_margin-content'}

BOX = ('<div class="pagedjs_margin-bottom-right"><div class="pagedjs_margin-content"></div></div>'
       '<div class="pagedjs_margin-bottom-left"><div class="pagedjs_margin-content"></div></div>'
       '<div class="pagedjs_margin-bottom-center"><div class="pagedjs_margin-content"></div></div>')

TOC_HTML = ('<div class="md-toc-wrap"><nav class="md-toc">'
            '<div class="toc-l1"><a href="#md-h-a">甲</a></div>'
            '<div class="toc-l1"><a href="#md-h-b">乙</a></div>'
            '<div class="toc-l1"><a href="#md-h-c">丙</a></div>'
            '</nav></div>')


def d(pn=None, pid=None, anchor=None, toc=False):
    return {'pn': pn, 'pid': pid, 'anchor': anchor, 'toc': toc}


def build(pages):
    out = []
    for k, p in enumerate(pages, 1):
        inner = ('<h2 id="%s">锚</h2>' % p['anchor']) if p['anchor'] else ''
        inner += '<p>第 %d 张纸</p>' % k
        if p['pn']:
            inner = ('<div class="page-region" data-pn="%s" data-pr-id="%s">%s</div>'
                     % (p['pn'], p['pid'], inner))
        if p['toc']:
            inner += TOC_HTML
        out.append('<div class="pagedjs_page">%s'
                   '<div class="pagedjs_page_content">%s</div></div>' % (BOX, inner))
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
            + ''.join(out) + '</body></html>')


def run(pw, pages, tpl='{p}|{P}|{N}', wait=200, poke=True):
    script = (FILLER.replace('__TPL__', json.dumps(tpl, ensure_ascii=False))
                    .replace('__SEL__', json.dumps(SEL))
                    .replace('__SIZE__', json.dumps('9')))
    br = pw.chromium.launch()
    pg = br.new_page()
    pg.set_content(build(pages))
    pg.add_script_tag(content=script)
    if poke:
        # v2.19.1：直接触发回填入口（等价于 PagedConfig.after 到达）
        pg.evaluate('window.__pgFill && window.__pgFill()')
    pg.wait_for_timeout(wait)
    got = pg.evaluate("""() => {
      const out = [];
      document.querySelectorAll('.pagedjs_page').forEach(p => {
        out.push({
          r: p.querySelector('.pagedjs_margin-bottom-right .pagedjs_margin-content').textContent,
          l: p.querySelector('.pagedjs_margin-bottom-left .pagedjs_margin-content').textContent,
          c: p.querySelector('.pagedjs_margin-bottom-center .pagedjs_margin-content').textContent
        });
      });
      const toc = [];
      document.querySelectorAll('.md-toc a').forEach(a => {
        const s = a.querySelector('.md-toc-pg');
        toc.push(s ? s.textContent : null);
      });
      return {out, toc};
    }""")
    br.close()
    return got


pass_n = fail_n = 0


def t(name, fn):
    global pass_n, fail_n
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


# 场景一：混合档位 + 目录页。23 张纸里 1 张是纯目录页 → {P}=22
PAGES = [d()]                                     # 1  区外 → 1
PAGES += [d('i', 'pr1') for _ in range(14)]       # 2-15 罗马 i..xiv（区内 1..14）
PAGES += [d('1', 'pr2') for _ in range(2)]        # 16-17 阿拉伯 1,2
PAGES += [d('1', 'pr3')]                          # 18  另一实例 → 1
PAGES += [d('noll', 'pr4')]                       # 19  不印
PAGES += [d(), d()]                               # 20-21 区外 → 2,3
PAGES += [d(toc=True)]                            # 22 纯目录页
PAGES += [d()]                                    # 23 区外 → 4
PAGES[4]['anchor'] = 'md-h-a'                     # 第 5 张：罗马区内第 4 页 → iv
PAGES[18]['anchor'] = 'md-h-b'                    # 第 19 张：noll 区
PAGES[22]['anchor'] = 'md-h-c'                    # 第 23 张：区外 → 4

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    r = run(pw, PAGES)
    rows = r['out']
    toc = r['toc']

    def box(i):
        """第 i 张纸（1-based）的页脚串：奇号进右盒，偶号进左盒。"""
        return rows[i - 1]['r'] or rows[i - 1]['l']

    print('\n— 区域外：全文阿拉伯连续，跳过区域页 —')
    t('第 1 张 = 1|22|22', lambda: box(1) == '1|22|22')
    t('第 20 张 = 2|22|22（接在区外序列上，不因区域页断号）',
      lambda: box(20) == '2|22|22')
    t('第 21 张 = 3|22|22', lambda: box(21) == '3|22|22')
    t('第 23 张 = 4|22|22', lambda: box(23) == '4|22|22')

    print('\n— 区外 {N} 与 {P} 同值（无页区文档零破坏） —')
    t('区外四处 {N} 都等于 {P}', lambda: all(
        box(i).split('|')[1] == box(i).split('|')[2] for i in (1, 20, 21, 23)))

    print('\n— 小写罗马区：区内从 i 重编 —')
    t('第 2 张（区内 1）= i|22|xiv', lambda: box(2) == 'i|22|xiv')
    t('第 5 张（区内 4）= iv|22|xiv', lambda: box(5) == 'iv|22|xiv')
    t('第 9 张（区内 8）= viii|22|xiv', lambda: box(9) == 'viii|22|xiv')
    t('第 10 张（区内 9）= ix|22|xiv', lambda: box(10) == 'ix|22|xiv')
    t('第 15 张（区内 14）= xiv|22|xiv', lambda: box(15) == 'xiv|22|xiv')

    t('罗马区 {N} 跟随区内形态（14 → xiv，即「共 v 页」口径）',
      lambda: box(2).split('|')[2] == 'xiv')

    print('\n— 阿拉伯区与实例重编 —')
    t('第 16 张（区 pr2 第 1）= 1|22|2', lambda: box(16) == '1|22|2')
    t('第 17 张（区 pr2 第 2）= 2|22|2', lambda: box(17) == '2|22|2')
    t('第 18 张（区 pr3 第 1）= 1|22|1（相邻 {1} 区各自从 1 起）',
      lambda: box(18) == '1|22|1')

    print('\n— noll 区与目录页 —')
    t('第 19 张（noll）三个盒全空', lambda: all(not rows[18][k] for k in 'rlc'))
    t('第 22 张（纯目录页）三个盒全空', lambda: all(not rows[21][k] for k in 'rlc'))

    print('\n— {P} 不吃页区影响 —')
    t('{P} 在全部有内容的页上恒为 22', lambda: all(
        box(i).split('|')[1] == '22' for i in (1, 2, 5, 10, 15, 16, 17, 18, 20, 21, 23)))

    print('\n— 奇偶位置（按显示号，不按物理页序） —')
    t('第 2 张显示号 1（奇）落右盒', lambda: rows[1]['r'] == 'i|22|xiv' and not rows[1]['l'])
    t('第 3 张显示号 2（偶）落左盒', lambda: rows[2]['l'] == 'ii|22|xiv' and not rows[2]['r'])
    t('第 16 张显示号 1（区重编后仍奇）落右盒',
      lambda: rows[15]['r'] == '1|22|2' and not rows[15]['l'])

    print('\n— 目录条目页码与页脚同源 —')
    t('目录 甲 → iv（罗马区）', lambda: toc[0] == 'iv')
    t('目录 乙 → 无页码（noll 区）', lambda: toc[1] is None)
    t('目录 丙 → 4（区外）', lambda: toc[2] == '4')

    # 场景二：大写罗马 + 边界 40 → XL（41 张：区内 40 + 区外 1）
    P2 = [d('I', 'pA') for _ in range(40)] + [d()]
    r2 = run(pw, P2)
    rows2 = r2['out']

    def box2(i):
        return rows2[i - 1]['r'] or rows2[i - 1]['l']

    print('\n— 大写罗马区 —')
    t('第 1 张 = I|41|XL', lambda: box2(1) == 'I|41|XL')
    t('第 4 张 = IV|41|XL', lambda: box2(4) == 'IV|41|XL')
    t('第 9 张 = IX|41|XL', lambda: box2(9) == 'IX|41|XL')
    t('第 40 张 = XL|41|XL', lambda: box2(40) == 'XL|41|XL')
    t('第 41 张（区外）= 1|41|41', lambda: box2(41) == '1|41|41')

    # 场景三：默认模板 {p}——未引用的占位符不能残留
    P3 = [d('i', 'pX'), d()]
    r3 = run(pw, P3, tpl='{p}')
    t('模板只写 {p}：输出无花括号残留',
      lambda: not any('{' in (p['r'] + p['l'] + p['c']) for p in r3['out']))
    t('模板只写 {p}：罗马区首张 = i', lambda: r3['out'][0]['r'] == 'i')

    # 场景四：轮询兜底——不 poke，页数不变连续 20 轮（约 6s）后自动回填
    P4 = [d('i', 'pY'), d()]
    r4 = run(pw, P4, tpl='{p}|{P}|{N}', wait=7600, poke=False)
    t('兜底轮询（6s 稳定窗）仍能触发回填', lambda: r4['out'][0]['r'] == 'i|2|i')

print('\n' + ('ALL PASS' if fail_n == 0 else 'FAILED %d' % fail_n) +
      '  (%d/%d)' % (pass_n, pass_n + fail_n))
sys.exit(0 if fail_n == 0 else 1)
