# -*- coding: utf-8 -*-
"""目录 × 页区组合探针 v2：等结构复刻用户简历文档的语法骨架
（noll 封面 h1 + page{1} 含 fill{80|20} + 多个 h2/h3 + blank + page{I} 附录）
内容全部为合成文字，不含任何真实信息。
"""
import io, os, sys, re

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
OUT = os.path.join(APP, 'runtime', '_toc_probe')
sys.path.insert(0, APP)
import md_server as S

PARA = ('目录页区组合探针填充段落，只为把页面填满让分页真实发生，'
        '本身不承载任何语义。') * 4


def paras(tag, n):
    return ''.join('<p>%s 第 %d 段：%s</p>' % (tag, k, PARA) for k in range(1, n + 1))


pg = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
      'pn': {'on': 'on', 'pos': 'outer', 'tpl': '{p}', 'size': 9},
      'toc': {'on': 'on', 'solo': True, 'pos': 'top'}, 'img': 'orig'}

# 等结构合成文档：noll 封面(full) + page{1}(fill 两栏 + 多个 h2/h3 跨多页) + page{I} 附录
body = (
    '<div class="page-region" data-pn="noll" data-pr-id="pr1">'
    '<div class="full-page" data-full-pos="m"><h1>合成封面标题甲</h1></div></div>'

    '<div class="page-region" data-pn="1" data-pr-id="pr2">'
    '<p>引言行</p>'
    '<div class="fill-row"><div class="fill-col" style="width:80%">'
    '<h2>栏甲小节</h2><p>甲1</p><p>甲2</p></div>'
    '<div class="fill-col" style="width:20%"><p>右栏</p></div></div>'
    '<h2>概述节</h2>' + paras('B', 6) +
    '<h2>能力节：</h2>' + paras('C', 6) +
    '<h2>管理节：</h2>' + paras('D', 6) +
    '<h2>其他节：</h2>' + paras('E', 8) +
    '<h3>2025.11至今</h3>' + paras('F', 6) +
    '<h3>2021.07-2025.10</h3>' + paras('G', 6) +
    '<h3>2020.03-2020.08 合成单位一</h3>' + paras('H', 6) +
    '<h3>2018.02-2020.02 合成单位二</h3>' + paras('I', 6) +
    '<h2>项目节</h2>' + paras('J', 6) +
    '<h3>项目甲</h3>' + paras('K', 6) +
    '<h3>项目乙</h3>' + paras('L', 6) +
    '</div>'

    '<div class="page-region" data-pn="I" data-pr-id="pr3">'
    '<h2>附录甲 合成仪器表</h2>' + paras('M', 4) +
    '<h2>附录乙 合成说明</h2>' + paras('N', 4) +
    '</div>'
)

os.makedirs(OUT, exist_ok=True)
html = S.build_paged_html('', '<div class="markdown-body">' + body + '</div>', '', pg)
fp = os.path.join(OUT, 'toc_probe.html')
io.open(fp, 'w', encoding='utf-8').write(html)
print('OK', fp, os.path.getsize(fp) // 1024, 'KB')

m = re.search(r'<nav class="md-toc">([\s\S]*?)</nav>', html)
if m:
    items = re.findall(r'<div class="(toc-l\d)"><a href="#(md-h-\d+)">([^<]*)</a>', m.group(1))
    print('目录条目 %d 条:' % len(items))
    for cls, href, txt in items:
        print(' ', cls, href, txt)
