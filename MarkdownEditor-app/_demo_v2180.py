# -*- coding: utf-8 -*-
"""v2.18.0 演示：并写 @@ begin page{noll} full 出封面

一份文档四个块：
  封面  page{noll} full       → 单独一页、垂直居中、不写页码（并写两家族）
  前言  page{noll}            → 不写页码
  序    page{i} full color    → 单独一页、罗马页码、整页蓝字（并写三家族）
  正文  page{1}               → 从 1 起重编
全文用真实解析器（md-parser.js）处理，与编辑器里走的同一条路。
"""
import io, os, json, subprocess, sys

APP = r'C:\Users\sm001\WorkBuddy\MarkdownEditor-app'
OUT = os.path.join(APP, 'runtime', '_v2180_demo')
PYPACK = os.path.join(APP, 'python', 'python.exe')

MD = '''@@ begin page{noll} full
# 我写故我播

把想法做成可交付物

@@ end page

@@ begin page{noll}
## 前言

这本书讨论的是「写」与「播」之间那条被忽略的缝。它既不是写作教程，也不是播客运营手册，而是一份关于「把想法做成可交付物」的现场记录。

封面与前言都不印页码，是书籍的通行做法——读者翻开时不必先面对一个数字。下面这一页序会换成罗马数字。

@@ end page

@@ begin page{i} full color{1e88e5}
## 序　为什么并写

这一页同时声明了三件事：**单独占一页**、**页脚用罗马数字**、**整页文字是蓝的**。

写起来只有一行 `@@ begin page{i} full color{1e88e5}`，不必套三层。

@@ end page

@@ begin page{1}
# 第一章　先把稿子写完

正文从 1 重新开始。你的 PDF 阅读器可能显示第 4 页，而页脚印的是 1——这不是缺陷，是分册书一直以来的样子。

## 第一节

页码在区内跨页续算，离开区之后回到全文序列；两个体系互不干扰。

## 第二节

若把「单独一页且不编号」写成两层嵌套，效果一模一样，只是多两行标记：

```
@@ begin page{noll}
@@ begin full
...
@@ end full
@@ end page
```

并写只是把这两行合成一行，块还是同一个块。

@@ end page
'''


def gen():
    js = ('const {parseMarkdown}=require("./md-parser.js");'
          'const d=JSON.parse(process.argv[1]);'
          'console.log(JSON.stringify(parseMarkdown(d)));')
    r = subprocess.run(['node', '-e', js, json.dumps(MD, ensure_ascii=False)],
                       cwd=APP, capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print('NODE ERR', r.stderr)
        sys.exit(1)
    body = json.loads(r.stdout)
    print('并写块数：page-region=%d  full-page=%d  mde-color=%d' %
          (body.count('page-region'), body.count('full-page'), body.count('mde-color')))

    sys.path.insert(0, APP)
    import md_server as S
    pg = {'paper': 'A5', 'mt': 20, 'mr': 18, 'mb': 20, 'ml': 18,
          'pn': {'on': 'on', 'pos': 'outer', 'tpl': '{p} / {P}', 'size': 9},
          'toc': {'on': 'off'}, 'img': 'orig'}
    html = S.build_paged_html('', '<div class="markdown-body">' + body + '</div>', '', pg)
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, 'demo.html')
    io.open(fp, 'w', encoding='utf-8').write(html)
    print('%s -> %d KB' % (fp, os.path.getsize(fp) // 1024))


def shoot():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        p = br.new_page()
        p.goto('file:///' + os.path.join(OUT, 'demo.html').replace(os.sep, '/'), wait_until='load')
        p.wait_for_selector('.pagedjs_page', timeout=30000)
        p.wait_for_timeout(2500)
        rows = p.evaluate("""() => Array.from(document.querySelectorAll('.pagedjs_page')).map((el, i) => {
          const c = el.querySelector('.pagedjs_page_content') || el;
          const f = [...el.querySelectorAll('.pagedjs_margin-content')]
                    .map(x => x.textContent.trim()).filter(x => x).join(',');
          const u = c.querySelector('.full-page');
          return {n: i + 1, foot: f || '(空)', full: !!u,
                  color: u ? getComputedStyle(u).color : '',
                  head: c.innerText.trim().slice(0, 12).replace(/\\n/g, ' ')};
        })""")
        pdf = p.pdf(prefer_css_page_size=True, print_background=True)
        fp = os.path.join(APP, 'runtime', '_v2180_demo.pdf')
        open(fp, 'wb').write(pdf)
        print('\n%s  %d 页  %.1f KB' % (os.path.basename(fp), len(rows), len(pdf) / 1024.0))
        for r in rows:
            print('  p%-2d 页脚=%-8s 整页容器=%-5s 色=%-18s %s' %
                  (r['n'], r['foot'], r['full'], r['color'] or '-', r['head']))
        p.close()
        br.close()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'gen':
        gen()
    else:
        if not os.path.isfile(os.path.join(OUT, 'demo.html')):
            subprocess.run([PYPACK, os.path.abspath(__file__), 'gen'], check=True)
        shoot()
