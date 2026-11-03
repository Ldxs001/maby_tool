# -*- coding: utf-8 -*-
"""v2.13 docx 专项：full-page 透传降级 + fill 文字栏经表格桥落位。
用自带解释器跑：./python/python.exe _test_v213_docx.py"""
import io
import sys

HERE = r"C:\Users\sm001\WorkBuddy\MarkdownEditor-app"
sys.path.insert(0, HERE)
import md_server  # noqa: E402
assert md_server._ensure_docx_deps(), "docx 依赖不可用"
import docx_export  # noqa: E402
from docx import Document  # noqa: E402

fails = 0

def chk(name, cond, detail=''):
    global fails
    if not cond:
        fails += 1
        print('FAIL', name, '|', detail)
    else:
        print('ok  ', name)

# 1) full-page：div 透明透传，内容照常成段
html1 = ('<div class="markdown-body">'
         '<div class="full-page" data-full-pos="m">'
         '<h1>封面标题</h1><p>封面正文</p></div>'
         '<p>后续内容</p></div>')
data = docx_export.build_docx(None, html1)
io.writeFileSync = None
open('_tmp_v213_full.docx', 'wb').write(data)
d = Document('_tmp_v213_full.docx')
texts = [pp.text for pp in d.paragraphs]
chk('full 透传:标题成段', '封面标题' in texts, texts)
chk('full 透传:正文成段', '封面正文' in texts, texts)
chk('full 透传:后续内容不丢', '后续内容' in texts, texts)

# 2) fill 文字栏：表格桥，栏内文字进单元格
html2 = ('<div class="markdown-body">'
         '<div class="fill-row" data-fill-row="1" style="margin-left:0px">'
         '<div class="fill-col" style="width:70%" data-fill="70"><h2>小节</h2><p>文字段落</p></div>'
         '<div class="fill-col" style="width:30%" data-fill="30"><p>另一栏</p></div>'
         '</div></div>')
data2 = docx_export.build_docx(None, html2)
open('_tmp_v213_fill.docx', 'wb').write(data2)
d2 = Document('_tmp_v213_fill.docx')
chk('fill 表格桥:产生 1 张表', len(d2.tables) == 1, len(d2.tables))
if d2.tables:
    t = d2.tables[0]
    cell_texts = []
    for row in t.rows:
        for cell in row.cells:
            cell_texts.append(cell.text)
    joined = ' | '.join(cell_texts)
    chk('fill 文字栏:左栏含标题与段落', '小节' in joined and '文字段落' in joined, joined)
    chk('fill 文字栏:右栏内容在位', '另一栏' in joined, joined)

print('✅ docx 专项全过' if fails == 0 else '❌ %d FAIL' % fails)
sys.exit(0 if fails == 0 else 1)
