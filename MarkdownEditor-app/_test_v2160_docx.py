# -*- coding: utf-8 -*-
"""v2.16.0 docx：降采样后体积变小，但显示宽度必须与原图口径完全一致"""
import io, os, re, sys, tempfile, zipfile, urllib.parse

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, 'docxdeps'))   # 与运行期同一套依赖（内置）
import docx_export as D

_TD = tempfile.mkdtemp(prefix='mde_v2160_docx_')
SRC = os.path.join(_TD, 'synth_big.png')
from PIL import Image, ImageDraw, ImageFilter
_im = Image.effect_noise((1920, 2744), 60).convert('RGB')
_d = ImageDraw.Draw(_im)
for _i in range(0, 2744, 160):
    _d.line([(0, _i), (1920, _i)], fill=(255, 255, 255), width=6)
_im = _im.filter(ImageFilter.GaussianBlur(0.6))
_im.save(SRC, 'PNG', optimize=True)
del _im, _d
esc = urllib.parse.quote(SRC)

PASS = FAIL = 0
def ck(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print('  PASS  %s' % name)
    else:
        FAIL += 1; print('  FAIL  %s   %s' % (name, extra))

def build(mode, pct=24):
    body = ('<div class="markdown-body"><p><img src="/img?path=%s" '
            'data-x-pct="%d" alt="t"></p></div>' % (esc, pct))
    pg = {'paper': 'A4', 'img': mode}
    return D.build_docx('', body, '', pg)

def probe(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    media = [(n, z.getinfo(n).file_size) for n in z.namelist()
             if n.startswith('word/media/')]
    size = None
    try:
        from PIL import Image
        name = media[0][0]
        size = Image.open(io.BytesIO(z.read(name))).size
    except Exception:
        pass
    xml = z.read('word/document.xml').decode('utf-8')
    ext = re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml)
    z.close()
    mm = None
    if ext:
        mm = (int(ext[0][0]) / 36000.0, int(ext[0][1]) / 36000.0)
    return len(blob), media, size, mm

a = build('orig')
b = build('300')
c = build('150')

na, ma, sa, mma = probe(a)
nb, mb, sb, mmb = probe(b)
nc, mc, sc, mmc = probe(c)

print('[体积]' )
print('  orig : %8.1f KB  内嵌 %s  %s  显示 %.2f x %.2f mm'
      % (na/1024, [(os.path.basename(n), round(s/1024)) for n, s in ma], sa,
         mma[0] if mma else -1, mma[1] if mma else -1))
print('  300  : %8.1f KB  内嵌 %s  %s  显示 %.2f x %.2f mm'
      % (nb/1024, [(os.path.basename(n), round(s/1024)) for n, s in mb], sb,
         mmb[0] if mmb else -1, mmb[1] if mmb else -1))
print('  150  : %8.1f KB  内嵌 %s  %s  显示 %.2f x %.2f mm'
      % (nc/1024, [(os.path.basename(n), round(s/1024)) for n, s in mc], sc,
         mmc[0] if mmc else -1, mmc[1] if mmc else -1))
print()

ck('300dpi 体积显著小于原图', nb < na * 0.5, '%.1f%%' % (nb * 100.0 / na))
ck('150dpi 体积小于 300dpi', nc < nb, '%.1f%%' % (nc * 100.0 / nb))
ck('300dpi 内嵌图确实变小', sb and sa and sb[0] < sa[0] * 0.5,
   '%s -> %s' % (sa, sb))
ck('300dpi 显示宽与原图一致（容差 0.1mm：像素取整引起的长宽比微差）',
   mma and mmb and abs(mma[0]-mmb[0]) < 0.1 and abs(mma[1]-mmb[1]) < 0.1,
   '%s vs %s' % (mma, mmb))
ck('150dpi 显示宽与原图一致', mma and mmc and abs(mma[0]-mmc[0]) < 0.1
   and abs(mma[1]-mmc[1]) < 0.1, '%s vs %s' % (mma, mmc))

# 只缩不放：拿一张本来就不宽的小图（572x747），满页 300dpi 要 1950px，
# 原图不够 -> 必须原样嵌入，绝不能放大
SMALL_SRC = os.path.join(_TD, 'synth_small.jpg')
_sm = Image.effect_noise((572, 747), 60).convert('RGB')
_sm.save(SMALL_SRC, 'JPEG', quality=92)
del _sm
esc_s = urllib.parse.quote(SMALL_SRC)
_body = ('<div class="markdown-body"><p><img src="/img?path=%s" '
         'data-x-pct="100" alt="t"></p></div>' % esc_s)
ns, ms, ss, mms = probe(D.build_docx('', _body, '', {'paper': 'A4', 'img': '300'}))
ck('原图不够宽时不放大（只缩不放）', ms and ms[0][1] == os.path.getsize(SMALL_SRC),
   '%s vs %s' % ([s for _, s in ms], os.path.getsize(SMALL_SRC)))

print()
print('RESULT  PASS=%d  FAIL=%d' % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
