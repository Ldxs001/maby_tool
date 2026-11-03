# -*- coding: utf-8 -*-
"""生成端到端测试用的三份打印版 HTML（原图 / 300dpi / 150dpi）

素材自产（1920×2744 噪点合成图），不含真实图片，可在任意机器复跑。
"""
import io, os, sys, tempfile, urllib.parse
APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
sys.path.insert(0, APP)
import md_server as S

SRC = os.path.join(tempfile.mkdtemp(prefix='mde_e2e_'), 'synth_big.png')
from PIL import Image, ImageDraw, ImageFilter
_im = Image.effect_noise((1920, 2744), 60).convert('RGB')
_d = ImageDraw.Draw(_im)
for _i in range(0, 2744, 160):
    _d.line([(0, _i), (1920, _i)], fill=(255, 255, 255), width=6)
_im = _im.filter(ImageFilter.GaussianBlur(0.6))
_im.save(SRC, 'PNG', optimize=True)
del _im, _d
esc = urllib.parse.quote(SRC)

BODY = ('<div class="markdown-body"><h1>图片输出端到端测试</h1>'
        '<p>下面这张图在版心上按 24%% 宽排版。</p>'
        '<p><img src="/img?path=%s" style="width:24%%" alt="测试图"></p>'
        '<p>结束段落。</p></div>' % esc)

PG = {'paper': 'A4', 'mt': 25, 'mr': 18, 'mb': 25, 'ml': 18,
      'pn': {'on': 'off'}, 'toc': {'on': 'off'}}

for mode in ('orig', '300', '150'):
    pg = dict(PG); pg['img'] = mode
    html = S.build_paged_html('', BODY, '', pg)
    out = os.path.join(APP, 'runtime', '_e2e_%s.html' % mode)
    io.open(out, 'w', encoding='utf-8').write(html)
    print('%-5s -> %s  (%d KB)' % (mode, out, os.path.getsize(out) // 1024))
