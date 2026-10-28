# -*- coding: utf-8 -*-
"""v2.16.0 实图输出：打印 / HTML 导出 / 预览缩略图 —— 便携版 Python 可跑的部分"""
import io, os, re, sys, urllib.parse

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
sys.path.insert(0, APP)
import md_server as S

SRC = r'C:\Users\sm001\WorkBuddy\2026-10-26-10-54-01\Temp\src_pdf_png.png'
assert os.path.isfile(SRC), SRC
esc = urllib.parse.quote(SRC)

PASS = FAIL = 0
def ck(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print('  PASS  %s' % name)
    else:
        FAIL += 1; print('  FAIL  %s   %s' % (name, extra))

PG = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
      'pn': {'on': 'off'}, 'toc': {'on': 'off'}}

# ---------- 1. _rewrite_img_width ----------
print('[1] 打印链路：按渲染宽补 w')
body = '<p><img src="/img?path=%s" style="width:24%%" alt="t"></p>' % esc
for mode, want in (('orig', None), ('300', 493), ('150', 247)):
    pg = dict(PG); pg['img'] = mode
    out = S.build_paged_html('', body, '', pg)
    m = re.search(r'/img\?path=[^"]*?w=(\d+)', out)
    got = int(m.group(1)) if m else None
    ck('img=%s -> w=%s' % (mode, got), got == want, 'want %s' % want)

# 满页宽的图（无 width 样式）→ 300dpi 该要 2008px，原图 1920 不够，w 仍会写 2008，
# 但 _shrink_image 会因"只缩不放"返回 None，最终由 /img 路由直供原图
FULL = os.path.join(os.path.dirname(SRC), 'src_pdf_jpg2.jpg')
pg = dict(PG); pg['img'] = '300'
out = S.build_paged_html('', '<p><img src="/img?path=%s"></p>'
                         % urllib.parse.quote(FULL), '', pg)
m = re.search(r'w=(\d+)', out)
ck('满页图 -> w=2055（A4 版心 174mm @300dpi）',
   m and int(m.group(1)) == 2055, m.group(1) if m else 'none')

# 预览渲染时带过来的 &w=820 必须被剥掉重算
body2 = '<p><img src="/img?path=%s&w=820" style="width:24%%"></p>' % esc
out = S.build_paged_html('', body2, '', dict(PG, img='300'))
ws = re.findall(r'&w=(\d+)', out)
ck('剥掉预览的旧 w 并重算', ws == ['493'], ws)

# ---------- 2. 长图切片：先缩后切、缓存键带 dpi ----------
print('[2] 长图切片：先缩后切')
tall = S._slice_tall_images(
    '<p><img src="/img?path=%s&w=493"></p>' % esc, 174.0, 245.0, 300)
ck('切片产物走 /static/_slice/', '/static/_slice/' in tall, tall[:120])
ck('切片 src 不再带 w=', '&w=' not in tall, tall[:120])
tall0 = S._slice_tall_images(
    '<p><img src="/img?path=%s"></p>' % esc, 174.0, 245.0, 0)
d300 = re.search(r'/static/_slice/([^/]+)/', tall)
d0 = re.search(r'/static/_slice/([^/]+)/', tall0)
ck('dpi 不同 -> 切片缓存键不同', d300 and d0 and d300.group(1) != d0.group(1),
   '%s vs %s' % (d300.group(1) if d300 else None, d0.group(1) if d0 else None))

# ---------- 3. 导出 HTML ----------
print('[3] 导出 HTML')
for mode, want_out in (('orig', False), ('300', True)):
    pg = dict(PG); pg['img'] = mode
    out = S.build_standalone_html('', '<p><img src="/img?path=%s" style="width:24%%"></p>' % esc, '', pg)
    m = re.search(r'src="file:///([^"]+)"', out)
    src = m.group(1) if m else ''
    ck('img=%s -> 指向%s' % (mode, '_out 派生件' if want_out else '原图'),
       ('_out' in src) == want_out and src.endswith(('.png', '.jpg')),
       src)
    if want_out:
        ck('  派生件真实存在', os.path.isfile(src.replace('/', os.sep)), src)

# ---------- 4. 预览：/img?w= ----------
print('[4] 预览缩略图接口')
u, a = S._shrink_image(SRC, 1600)
ck('_shrink_image(1600) 产出派生件', bool(a) and os.path.isfile(a), a)
ck('派生件体积小于原图', a and os.path.getsize(a) < os.path.getsize(SRC) * 0.85,
   '%s vs %s' % (os.path.getsize(a) if a else 0, os.path.getsize(SRC)))
ck('缓存重复调用同路径', S._shrink_image(SRC, 1600)[0] == u)

print()
print('RESULT  PASS=%d  FAIL=%d' % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
