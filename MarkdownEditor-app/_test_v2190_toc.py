# -*- coding: utf-8 -*-
"""_test_v2190_toc.py — v2.19.0 noll 区标题不进目录（服务端单测）
运行：py -3.11 _test_v2190_toc.py
背景：页区标了 noll 就是不编号，其内标题在目录里无页码可填
（判例：封面 h1 进目录、条目无页码无点线）。修法 = 生成目录时
直接排除 noll page-region 区间内的 h1/h2/h3（按 div 深度配对取区间）。
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


pg = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
      'pn': {'on': 'on', 'pos': 'outer', 'tpl': '{p}', 'size': 9},
      'toc': {'on': 'on', 'solo': True, 'pos': 'top'}, 'img': 'orig'}

# 文档：noll 封面（h1+h2 各一）+ 正文两 h2 + 附录区（page{I}，进目录）
body = (
    '<div class="page-region" data-pn="noll" data-pr-id="pr1">'
    '<div class="full-page" data-full-pos="m"><h1>合成封面标题</h1>'
    '<h2>合成副题</h2></div></div>'
    '<div class="page-region" data-pn="1" data-pr-id="pr2">'
    '<h2>正文章节甲</h2><p>内容</p>'
    '<h2>正文章节乙</h2><p>内容</p></div>'
    '<div class="page-region" data-pn="I" data-pr-id="pr3">'
    '<h2>附录甲</h2><p>内容</p></div>'
)

html = S.build_paged_html('', '<div class="markdown-body">' + body + '</div>', '', pg)

t('封面 h1 不进目录（无 md-h-1 指向封面）', '合成封面标题</h1>' in html and 'id="md-h' not in html.split('合成封面标题</h1>')[0].split('<h1>合成封面标题')[-1])
t('封面 h2 不进目录', re.search(r'<h2 id="md-h-\d+">合成副题</h2>', html) is None)
t('noll 区标题不加锚（h1/h2 无 id）',
  '<h1>合成封面标题</h1>' in html and '<h2>合成副题</h2>' in html)
t('正文 h2 进目录（2 条）', len(re.findall(r'<h2 id="md-h-\d+">正文章节', html)) == 2)
t('附录 h2 进目录', re.search(r'<h2 id="md-h-\d+">附录甲</h2>', html) is not None)
t('目录条目共 3 条（2 正文 + 1 附录）',
  len(re.findall(r'class="toc-l\d"', html)) == 3)

# 嵌套 div 配对：noll 区内标题包在 fill 栏深处也应被排除
body2 = (
    '<div class="page-region" data-pn="noll" data-pr-id="pr4">'
    '<div class="full-page"><div class="fill-row"><div class="fill-col">'
    '<h2>深处标题</h2></div></div></div></div>'
    '<div class="page-region" data-pn="1" data-pr-id="pr5">'
    '<h2>正常标题</h2></div>'
)
html2 = S.build_paged_html('', '<div class="markdown-body">' + body2 + '</div>', '', pg)
t('noll 区 fill 栏深处的 h2 也被排除', re.search(r'<h2 id="md-h-\d+">深处标题</h2>', html2) is None)
t('深处排除后正常标题编号从 1 起', 'id="md-h-1">正常标题' in html2)

print()
print('ALL PASS  (%d/%d)' % (PASS, PASS + FAIL) if FAIL == 0
      else 'FAILED %d  (%d/%d)' % (FAIL, PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
