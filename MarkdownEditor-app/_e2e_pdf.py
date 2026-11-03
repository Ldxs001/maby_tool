# -*- coding: utf-8 -*-
"""端到端：同一份文档，原图 / 300dpi / 150dpi 打印成 PDF 的体积对比"""
import os, sys, time, subprocess, urllib.request

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
PORT = 18799
RUNNER = os.path.join(APP, 'runtime', '_test_run_server.py')
os.makedirs(os.path.dirname(RUNNER), exist_ok=True)
open(RUNNER, 'w', encoding='utf-8', newline='\n').write(
    "import os, sys\n"
    "sys.path.insert(0, %r)\n"
    "import md_server\n"
    "md_server.PORT = %d\n"
    "md_server.main()\n" % (APP, PORT))

PY = os.path.join(APP, 'python', 'python.exe')
srv = subprocess.Popen([PY, RUNNER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
result = {}
try:
    ok = False
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/' % PORT, timeout=1).read()
            ok = True; break
        except Exception:
            time.sleep(0.3)
    if not ok:
        print('服务未起来'); raise SystemExit(2)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for mode in ('orig', '300', '150'):
            pg = br.new_page()
            pg.goto('http://127.0.0.1:%d/static/_e2e_%s.html' % (PORT, mode),
                    wait_until='load')
            # 等 Paged.js 分页完成
            try:
                pg.wait_for_selector('.pagedjs_page', timeout=25000)
                pg.wait_for_timeout(1500)
            except Exception:
                pg.wait_for_timeout(2500)
            n = pg.evaluate("document.querySelectorAll('.pagedjs_page').length")
            imgs = pg.evaluate(
                "Array.from(document.images).map(i=>i.naturalWidth+'x'+i.naturalHeight)")
            pdf = pg.pdf(prefer_css_page_size=True, print_background=True)
            result[mode] = (len(pdf), n, imgs)
            pg.close()
        br.close()
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
print('%-6s %-12s %-6s %s' % ('档位', 'PDF 体积', '页数', '页面上的图（解码后像素）'))
print('-' * 74)
base = result.get('orig', (1,))[0]
for mode in ('orig', '300', '150'):
    if mode not in result:
        continue
    sz, n, imgs = result[mode]
    print('%-6s %8.1f KB  %-6d %s   (相对原图 %.1f%%)'
          % (mode, sz / 1024.0, n, imgs, sz * 100.0 / base))
print()

os_ok = True
if 'orig' in result and '300' in result:
    o, t = result['orig'][0], result['300'][0]
    print('300dpi 相对原图: %.1f%%' % (t * 100.0 / o))
    print('RESULT', 'PASS' if t < o * 0.5 else 'FAIL',
          '（期望 < 50%，因为 1920px 的图排在 24%% 宽只需 493px）')

for f in ['_e2e_orig.html', '_e2e_300.html', '_e2e_150.html']:
    try:
        os.remove(os.path.join(APP, 'runtime', f))
    except Exception:
        pass
sys.exit(0 if os_ok else 1)
