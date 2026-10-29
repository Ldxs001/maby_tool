# -*- coding: utf-8 -*-
"""_test_v2201_tocex.py — v2.21.0 目录级别排除（服务端单测）
运行：py -3.11 _test_v2201_tocex.py
背景：排版设置「不计入目录」勾选 #/##/### 后，对应级别标题照常渲染、
只是不收集进目录、不加锚（与 noll 区同口径）。场景=封面大标题用 # 但
不进目录，又不想为它套一个 noll 页区。
"""
import io, os, re, sys

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import md_server as S

PASS = 0
FAIL = 0


def t(name, ok):
    global PASS, FAIL
    print(('PASS  ' if ok else 'FAIL  ') + name)
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)


def cfg(**ex):
    return {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
            'pn': {'on': 'on', 'pos': 'outer', 'tpl': '{p}', 'size': 9},
            'toc': dict({'on': 'on', 'solo': True, 'pos': 'top'}, **ex),
            'img': 'orig'}

body = ('<div class="markdown-body">'
        '<h1>大标题</h1><h2>章节甲</h2><p>内容</p>'
        '<h3>小节乙</h3><p>内容</p></div>')

# 基线：无勾选，三级全进目录
html = S.build_paged_html('', body, '', cfg())
t('基线：h1/h2/h3 全部加锚', len(re.findall(r'<h[123] id="md-h-\d+">', html)) == 3)
t('基线：目录条目 3 条', len(re.findall(r'class="toc-l\d"', html)) == 3)

# 勾 #：h1 排除，h2/h3 照常
html = S.build_paged_html('', body, '', cfg(ex1=True))
t('勾#：h1 无锚', '<h1 id="md-h-' not in html)
t('勾#：h1 照常渲染（无 id）', '<h1>大标题</h1>' in html)
t('勾#：h2/h3 仍加锚', len(re.findall(r'<h[23] id="md-h-\d+">', html)) == 2)
t('勾#：目录条目 2 条且无 toc-l1', len(re.findall(r'class="toc-l\d"', html)) == 2
  and 'class="toc-l1"' not in html)

# 勾 #+###：只余 h2
html = S.build_paged_html('', body, '', cfg(ex1=True, ex3=True))
t('勾#+###：仅 h2 加锚', len(re.findall(r'<h[13] id="md-h-\d+">', html)) == 0
  and '<h2 id="md-h-' in html)
t('勾#+###：目录条目 1 条', len(re.findall(r'class="toc-l\d"', html)) == 1)

# 全勾：目录无条目可收，目录整体不生成
html = S.build_paged_html('', body, '', cfg(ex1=True, ex2=True, ex3=True))
t('全勾：md-toc 整体不生成', '<div class="md-toc-wrap"' not in html)
t('全勾：标题照常渲染', '<h1>大标题</h1>' in html and '<h2>章节甲</h2>' in html)

# 与 noll 区叠加互不干扰
body2 = ('<div class="markdown-body">'
         '<div class="page-region" data-pn="noll" data-pr-id="pr1"><h1>封面</h1></div>'
         '<h1>正文篇</h1><h2>章节</h2></div>')
html = S.build_paged_html('', body2, '', cfg(ex1=True))
t('noll+勾#：两个 h1 都不进目录',
  len(re.findall(r'<h1 id="md-h-\d+">', html)) == 0)
t('noll+勾#：h2 照常进目录', '<h2 id="md-h-' in html)

# afterh1 插入点不受 h1 排除影响（目录仍插在第一个 h1 之后）
html = S.build_paged_html('', body, '', cfg(ex1=True, pos='afterh1'))
i_h1 = html.find('<h1>大标题</h1>')
i_toc = html.find('<div class="md-toc-wrap"')
t('afterh1：h1 排除后目录仍插在第一个 h1 之后', 0 < i_h1 < i_toc)

print('\nPASS=%d FAIL=%d' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
