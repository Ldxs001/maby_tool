# -*- coding: utf-8 -*-
"""_test_v2191_filler.py — v2.19.1 页码回填完成信号改造（服务端单测）
运行：py -3.11 _test_v2191_filler.py
背景：回填器旧判定「页数 0.9s 不变即完成并永久停机」在长文档分页途中
卡顿即提前回填，目录后半条目页码截断且不再补。修法 = 回填改为可重入
window.__pgFill，由 PagedConfig.after（polyfill 官方完成回调）触发，
轮询降为 6s 窗口的兜底，目录回填幂等。
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

body = ('<div class="markdown-body">'
        '<h1>篇一</h1><h2>章节甲</h2><p>内容</p>'
        '<h2>章节乙</h2><p>内容</p></div>')
html = S.build_paged_html('', body, '', pg)

# 1. PagedConfig.after 预置在场
t('产物预置 PagedConfig.after（auto+回调）',
  'window.PagedConfig={auto:true,after:function(){' in html)
# 2. 预置先于 polyfill 执行体（polyfill 内部的 PagedConfig||{auto 读取点）
t('PagedConfig 预置先于 polyfill 读取点',
  html.index('window.PagedConfig={auto:true') <
  html.index('PagedConfig||{auto'))
# 3. after 回调调 __pgFill
t('after 回调内调 window.__pgFill',
  'window.__pgFill&&window.__pgFill();' in html)
# 4. 回填函数可重入（不再是一次性 done 标记）
t('回填改为 window.__pgFill 函数定义', 'window.__pgFill = function(){' in html)
t('旧的一次性 done 标记已移除', 'done = true' not in html)
# 5. 兜底轮询窗口 0.9s -> 6s
t('旧 3 轮（0.9s）判定已移除', 'if(stable < 3) return;' not in html)
t('兜底轮询放宽到 20 轮（6s）', 'if(++stable < 20) return;' in html)
# 6. 目录回填幂等：先查已有节点再补建
t('目录页码回填先查已有 .md-toc-pg',
  "links[i].querySelector('.md-toc-pg')" in html)
t('点线回填先查已有 .toc-dots',
  "links[i].querySelector('.toc-dots')" in html)

# 7. 三段 script 顺序：预置 < polyfill < 回填器
i_cfg = html.index('window.PagedConfig={auto:true')
i_poly = html.index('PagedConfig||{auto')
i_fill = html.index('window.__pgFill = function(){')
t('脚本顺序 预置 < polyfill < 回填器', i_cfg < i_poly < i_fill)

# 8. 产物结构不回归：目录条目与锚点仍在（1 个 h1 + 2 个 h2 = 3 条）
t('目录条目仍在（3 条）', len(re.findall(r'class="toc-l\d"', html)) == 3)
t('标题锚点仍在', 'id="md-h-' in html)

print('\nPASS=%d FAIL=%d' % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
