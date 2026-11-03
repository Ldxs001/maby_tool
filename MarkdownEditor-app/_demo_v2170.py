# -*- coding: utf-8 -*-
"""v2.17.0 演示：同一份文档、同一套页区，两种页码模板各出一份 PDF

  _v2170_demo_N.pdf —— 模板 {p} / {N}（区内印本区页数）
  _v2170_demo_P.pdf —— 模板 {p} / {P}（始终印全文页数）

封面 noll → 前言 noll → 序 i → 正文 1，肉眼即可对照。
"""
import io, os, subprocess, sys

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
OUT = os.path.join(APP, 'runtime', '_v2170_demo')
PYPACK = os.path.join(APP, 'python', 'python.exe')

MD = '''# 我写故我播

## 前言

这本书讨论的是「写」与「播」之间那条被忽略的缝。它既不是写作教程，也不是播客运营手册，而是一份关于「把想法做成可交付物」的现场记录。前言这几页不编页码，是书籍的通行做法——读者翻开时不必先面对一个数字。

## 前言续一

页码在这里只是一个位置记号，不应该打断阅读的起点，所以整段前言都不编号。注意下面的序会换成罗马数字，正文才从一重新开始：这三段各说各的位置。

## 前言续二

这一段是用来把前言撑到两页的。翻开一本书，书名页、前言、序、正文各有各的编号规则，排得对读者不会注意，排得不对一眼就能看出别扭。

## 序　为什么写这本书

序用罗马数字。这是印刷业沿用了几百年的分层：前言与序属于「书外」，正文才从一重新开始。

## 序续

罗马数字的好处是它一眼就能看出「这不是正文」。坏处是很多人第一次见到会愣一下，以为页码印错了。

## 序续二

这段把序撑到第二页，好让「共 ii 页」这种写法有个真实对象。

## 序续三

序里的页码用 i、ii、iii，一页一个，跨页续算，不会因为中间插图就跳号。

# 第一章　先把稿子写完

正文从 1 重新开始。你的 PDF 阅读器可能显示第 5 页，而页脚印的是 1——这不是 bug，是分册书一直以来的样子。

## 第一节

这一节用来把正文撑过一页，好让页码真的递增，而不是每一区都只有一页。

## 第二节

正文区的页码会连续递增，跨页续算；前面的罗马区有自己的序列，两者互不干扰。

## 第三节

到这里正文应该已经翻过一页，页脚会从 1 变成 2。

## 第四节

第四节的唯一作用是把正文推向第二页，让递增真的发生。

## 第五节

如果这里印出的是 2，说明区内重编与跨页续算两件事都是对的。
'''


def gen():
    sys.path.insert(0, APP)
    import md_server as S
    sys.path.insert(0, os.path.join(APP))

    # 用真实的解析器把 md 转 body（与前端同一份，抽自 md-parser.js 的源）
    body = S.__dict__.get('_render_md_for_demo')
    os.makedirs(OUT, exist_ok=True)

    # 直接手写 body：演示不需要 md→html 全链路，但要保留段落与标题语义
    import re
    lines = MD.strip().split('\n')
    parts = []
    buf = []
    region = None

    def flush(p):
        if not buf:
            return
        txt = ' '.join(x.strip() for x in buf if x.strip())
        if txt:
            parts.append('<p>%s</p>' % txt)
        buf.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            flush(parts)
            continue
        if s.startswith('## '):
            flush(parts)
            parts.append('<h2>%s</h2>' % s[3:])
        elif s.startswith('# '):
            flush(parts)
            parts.append('<h1>%s</h1>' % s[2:])
        else:
            buf.append(s)
    flush(parts)
    body = ''.join(parts)

    # 按标题切片，插入页区标记
    def wrap(html, pn, pid):
        return '<div class="page-region" data-pn="%s" data-pr-id="%s">%s</div>' % (pn, pid, html)

    # 书名页与前言同属 noll 区（封面不印页码）
    i_seq = body.index('<h2>序　为什么写这本书</h2>')
    i_ch1 = body.index('<h1>第一章　先把稿子写完</h1>')
    body = (wrap(body[:i_seq], 'noll', 'pr1')
            + wrap(body[i_seq:i_ch1], 'i', 'pr2')
            + wrap(body[i_ch1:], '1', 'pr3'))

    for name, tpl in (('N', '{p} / {N}'), ('P', '{p} / {P}')):
        pg = {'paper': 'A5', 'mt': 20, 'mr': 18, 'mb': 20, 'ml': 18,
              'pn': {'on': 'on', 'pos': 'outer', 'tpl': tpl, 'size': 9},
              'toc': {'on': 'off'}, 'img': 'orig'}
        html = S.build_paged_html('', '<div class="markdown-body">' + body + '</div>', '', pg)
        fp = os.path.join(OUT, 'demo_%s.html' % name)
        io.open(fp, 'w', encoding='utf-8').write(html)
        print('%s -> %d KB' % (fp, os.path.getsize(fp) // 1024))


def shoot():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for name in ('N', 'P'):
            p = br.new_page()
            url = 'file:///' + os.path.join(OUT, 'demo_%s.html' % name).replace('\\', '/')
            p.goto(url, wait_until='load')
            p.wait_for_selector('.pagedjs_page', timeout=30000)
            p.wait_for_timeout(2200)
            n = p.evaluate("document.querySelectorAll('.pagedjs_page').length")
            feet = p.evaluate("""() => Array.from(document.querySelectorAll('.pagedjs_page')).map(pg => {
              const r = pg.querySelector('.pagedjs_margin-bottom-right .pagedjs_margin-content');
              const l = pg.querySelector('.pagedjs_margin-bottom-left .pagedjs_margin-content');
              return (r&&r.textContent) || (l&&l.textContent) || '(空)';
            })""")
            pdf = p.pdf(prefer_css_page_size=True, print_background=True)
            fp = os.path.join(APP, 'runtime', '_v2170_demo_%s.pdf' % name)
            open(fp, 'wb').write(pdf)
            print('%s  模板=%s  %d 页  %.1f KB' %
                  (os.path.basename(fp), name, n, len(pdf) / 1024.0))
            print('   页脚：', feet)
            p.close()
        br.close()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'gen':
        gen()
    else:
        shoot()
