# -*- coding: utf-8 -*-
"""v2.16.0 /img 缩略图接口：w 参数、ETag 区分、304 协商

素材自产（1920×2744 噪点合成图），不含任何真实图片，可在任意机器复跑。
"""
import os, sys, time, subprocess, tempfile, urllib.request, urllib.parse

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
_TD = tempfile.mkdtemp(prefix='mde_v2160_http_')
SRC = os.path.join(_TD, 'synth_big.png')
PORT = 18799
ESC = urllib.parse.quote(SRC)

from PIL import Image, ImageDraw, ImageFilter
_im = Image.effect_noise((1920, 2744), 60).convert('RGB')
_d = ImageDraw.Draw(_im)
for _i in range(0, 2744, 160):
    _d.line([(0, _i), (1920, _i)], fill=(255, 255, 255), width=6)
_im = _im.filter(ImageFilter.GaussianBlur(0.6))
_im.save(SRC, 'PNG', optimize=True)
del _im, _d

ORIG = os.path.getsize(SRC)

RUNNER = os.path.join(APP, 'runtime', '_test_run_server.py')
os.makedirs(os.path.dirname(RUNNER), exist_ok=True)
open(RUNNER, 'w', encoding='utf-8', newline='\n').write(
    "import os, sys\n"
    "sys.path.insert(0, %r)\n"
    "import md_server\n"
    "md_server.PORT = %d\n"
    "md_server.main()\n" % (APP, PORT))

PASS = FAIL = 0
def ck(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print('  PASS  %s' % name)
    else:
        FAIL += 1; print('  FAIL  %s   %s' % (name, extra))

def fetch(path, extra_headers=None):
    url = 'http://127.0.0.1:%d%s' % (PORT, path)
    req = urllib.request.Request(url, headers=extra_headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b''

srv = subprocess.Popen([sys.executable, RUNNER],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ok = False
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/' % PORT, timeout=1).read()
            ok = True; break
        except Exception:
            time.sleep(0.3)
    if not ok:
        print('服务未起来'); sys.exit(2)

    print('[1] 无 w：原图直供')
    st, hd, body = fetch('/img?path=' + ESC)
    ck('200 + 字节数与原图相同', st == 200 and len(body) == ORIG,
       '%s / %s vs %s' % (st, len(body), ORIG))

    print('[2] 带 w：返回缩略图')
    st2, hd2, b2 = fetch('/img?path=%s&w=1600' % ESC)
    ck('200 + 体积显著更小', st2 == 200 and len(b2) < ORIG * 0.85,
       '%s / %.1f%%' % (st2, len(b2) * 100.0 / ORIG))
    ck('Content-Type 是图片', 'image/' in (hd2.get('Content-Type') or ''),
       hd2.get('Content-Type'))

    print('[3] 不同 w 不串缓存')
    st3, hd3, b3 = fetch('/img?path=%s&w=800' % ESC)
    e1, e2 = hd2.get('ETag'), hd3.get('ETag')
    ck('w=1600 与 w=800 的 ETag 不同', e1 and e2 and e1 != e2, '%s vs %s' % (e1, e2))
    ck('w=800 体积小于 w=1600', len(b3) < len(b2), '%d vs %d' % (len(b3), len(b2)))

    print('[4] 协商缓存')
    st4, _, b4 = fetch('/img?path=%s&w=1600' % ESC, {'If-None-Match': e1})
    ck('带相同 ETag 回 304 且空体', st4 == 304 and len(b4) == 0, str(st4))

    print('[5] w 大于原宽：不放大')
    st5, _, b5 = fetch('/img?path=%s&w=5000' % ESC)
    ck('原图直供（字节数与原图相同）', st5 == 200 and len(b5) == ORIG,
       '%s / %s' % (st5, len(b5)))
finally:
    srv.terminate()
    try:
        srv.wait(timeout=10)
    except Exception:
        srv.kill()
    try:
        os.remove(RUNNER)
    except Exception:
        pass

print()
print('RESULT  PASS=%d  FAIL=%d' % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
