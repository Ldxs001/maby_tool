# -*- coding: utf-8 -*-
"""v2.16.0 前端：预览缩略图参数、懒加载、排版面板图片档位

素材自产（一张 1920x2744 的噪点合成图，体积够大才会触发降采样），
不含任何真实图片，可在任意机器复跑。
"""
import io, os, sys, time, json, shutil, tempfile, subprocess, urllib.request, urllib.parse

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
PORT = 18799
TD = tempfile.mkdtemp(prefix='mde_v2160_ui_')
SRC = os.path.join(TD, 'synth_big.png')
MD = os.path.join(TD, 'ui_img.md')
SHOT = os.path.join(APP, 'runtime', 'v2160_panel.png')

# 合成素材：噪点 + 结构线，PNG 压不动才有足够体积
from PIL import Image, ImageDraw, ImageFilter
_W, _H = 1920, 2744
_im = Image.effect_noise((_W, _H), 60).convert('RGB')
_d = ImageDraw.Draw(_im)
for _i in range(0, _H, 160):
    _d.line([(0, _i), (_W, _i)], fill=(255, 255, 255), width=6)
for _k in range(6):
    _d.rectangle([200 + _k * 40, 900 + _k * 60, _W - 200 - _k * 40, 1000 + _k * 60],
                 outline=(70, 110, 220), width=10)
_im = _im.filter(ImageFilter.GaussianBlur(0.6))
_im.save(SRC, 'PNG', optimize=True)
del _im, _d

io.open(MD, 'w', encoding='utf-8').write(
    '# 图片输出测试\n\n'
    '下面是一张大图，1920x2744。\n\n'
    '![](%s)\n\n' % SRC.replace('\\', '/') +
    '## 第二节\n\n用来确认预览缩略图与懒加载生效。\n')

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


# 面板「应用」会把档位同步进 runtime/ui-settings.json，跨次运行会串味。
# 开跑前记下原值并置 orig，结束时原样写回 —— 测试必须幂等且不留痕。
US = os.path.join(APP, 'runtime', 'ui-settings.json')

def _set_img_in_settings(val):
    if not os.path.isfile(US):
        return None
    try:
        d = json.load(io.open(US, encoding='utf-8'))
        k = 'md-editor-typeset-v3'
        if k not in d:
            return None
        inner = json.loads(d[k])
        old = (inner.get('page') or {}).get('img')
        if val is None:
            cur = old
        else:
            inner.setdefault('page', {})['img'] = val
            d[k] = json.dumps(inner, ensure_ascii=False, separators=(',', ':'))
            io.open(US, 'w', encoding='utf-8').write(
                json.dumps(d, ensure_ascii=False, indent=1))
            cur = val
        return old if val is not None else cur
    except Exception:
        return None

_prev_img = _set_img_in_settings(None)      # 读原值
_set_img_in_settings('orig')                # 归零，保证默认档位断言稳定

srv = subprocess.Popen([os.path.join(APP, 'python', 'python.exe'), RUNNER],
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

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={'width': 1400, 'height': 900})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto('http://127.0.0.1:%d/?file=%s' % (PORT, urllib.parse.quote(MD)),
                wait_until='load')
        pg.wait_for_selector('#preview img', timeout=20000)
        pg.wait_for_timeout(1200)

        print('[1] 预览缩略图')
        info = pg.evaluate("""() => {
          const im = document.querySelector('#preview img');
          return im ? {src: im.getAttribute('src'),
                       loading: im.getAttribute('loading'),
                       decoding: im.getAttribute('decoding'),
                       nat: im.naturalWidth + 'x' + im.naturalHeight} : null;
        }""")
        print('   ', json.dumps(info, ensure_ascii=False))
        ck('src 带 &w= 参数', info and '&w=' in info['src'], info and info['src'][-44:])
        ck('loading=lazy', info and info['loading'] == 'lazy', info and info['loading'])
        ck('decoding=async', info and info['decoding'] == 'async', info and info['decoding'])
        ck('浏览器解码宽度已被限制（远小于 1920）',
           info and int(info['nat'].split('x')[0]) < 1800, info and info['nat'])

        print('[2] 排版面板')
        pg.click('#btnTypeset')
        pg.wait_for_timeout(500)
        ck('面板出现 #tsImgMode', pg.query_selector('#tsImgMode') is not None)
        val = pg.eval_on_selector('#tsImgMode', 'e => e.value')
        ck('默认档位为 orig', val == 'orig', val)
        opts = pg.eval_on_selector('#tsImgMode',
                                   'e => Array.from(e.options).map(o=>o.value)')
        ck('三档齐全', opts == ['orig', '300', '150'], opts)

        print('[3] 切换档位并应用')
        pg.select_option('#tsImgMode', '300')
        pg.wait_for_timeout(300)
        try:
            pg.eval_on_selector('#tsImgMode', "e => e.scrollIntoView({block:'center'})")
            pg.wait_for_timeout(400)
        except Exception:
            pass
        pg.screenshot(path=SHOT)
        pg.click('#tsApply')
        pg.wait_for_timeout(900)
        saved = pg.evaluate("""() => {
          try { return JSON.parse(localStorage.getItem('md-editor-typeset-v3')||'{}').page||{}; }
          catch(e) { return {}; }
        }""")
        ck('localStorage 里 page.img == 300', saved.get('img') == '300', saved.get('img'))

        print('[4] 无 page error')
        ck('no page errors', not errs, errs[:2])

        # 复位，避免测试档位留在浏览器/服务端设置里
        pg.evaluate("""() => {
          try {
            const k='md-editor-typeset-v3';
            const o=JSON.parse(localStorage.getItem(k)||'{}');
            if(o.page) o.page.img='orig';
            localStorage.setItem(k, JSON.stringify(o));
          } catch(e) {}
        }""")
        pg.close(); br.close()
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
    _set_img_in_settings(_prev_img if _prev_img else 'orig')   # 还原到跑之前的值
    shutil.rmtree(TD, ignore_errors=True)

print()
print('截图:', SHOT)
print('RESULT  PASS=%d  FAIL=%d' % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
