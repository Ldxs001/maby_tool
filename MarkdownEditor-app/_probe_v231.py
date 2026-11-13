# -*- coding: utf-8 -*-
"""探针：走真实服务端 /api/export-paged，检查
   1) @page 纸色、2) full 命名页背景、3) 是否内嵌 data URI
"""
import json, re, os, sys, urllib.request, urllib.parse

BASE = "http://127.0.0.1:18766"
APP = os.path.dirname(os.path.abspath(__file__))

IMG = os.path.join(APP, "docs", "MDEditor 实操手册.assets",
                   "20261103_010158_8502.png")
print("封面图存在:", os.path.isfile(IMG), os.path.getsize(IMG), "bytes")

url_img = "/img?path=" + urllib.parse.quote(IMG)

body = (
    '<div class="full-page" data-full-pos="m"'
    ' data-bg-img="%s" data-bg-mode="f" data-bg-pos="cc"'
    ' style="background-image:url(\'%s\');background-size:100%% 100%%;'
    'background-position:center center;background-repeat:no-repeat;">'
    '<h1>封面标题</h1></div>'
    '<h1>第一章</h1><p>正文段落。</p>' % (url_img, url_img)
)

cfg = {"paper": "A4", "tone": "dark", "mt": 25, "mr": 18, "mb": 25, "ml": 18,
       "pn": {"on": "on", "size": 9, "pos": "outer", "tpl": "{p}"}}

req = urllib.request.Request(
    BASE + "/api/export-paged",
    data=json.dumps({"bodyHtml": body, "tsCss": "", "cfg": cfg,
                     "mode": "native"}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
print("响应:", resp)

p = os.path.join(APP, "runtime", "document.print.html")
html = open(p, encoding="utf-8").read()
open(os.path.join(APP, "Temp", "_probe_v231.html"), "w",
     encoding="utf-8").write(html)
print("产物大小:", len(html))

print("\n--- @page 主规则 ---")
for m in re.finditer(r"@page[^{]*\{[^}]*\}", html):
    head = m.group(0)[:180]
    if "background" in head or m.group(0).startswith("@page{"):
        print(head.replace("\n", " ")[:180], "\n")

print("--- 命名页 ---", len(re.findall(r"@page\s+mdefbg", html)))
print("--- data URI 数量 ---",
      len(re.findall(r"url\(\s*[\"']?data:image", html)))
print("--- 仍是站内 URL 的背景 ---",
      len(re.findall(r"background-image:url\([\"']?/img\?", html)))
print("--- data-mde-pg 注入 ---", len(re.findall(r'data-mde-pg="', html)))
m = re.search(r"@page\s+mdefbg\d+\{.{0,160}", html, re.S)
print("--- 命名页内容 ---\n", m.group(0)[:200] if m else "无")
