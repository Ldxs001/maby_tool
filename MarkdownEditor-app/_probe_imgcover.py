# -*- coding: utf-8 -*-
"""验证「真实 <img> + 命名页 margin:0」方案：bgOFF 下能否印出整页封面图"""
import os
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/static/_probe_imgcover.html"
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "Temp"))

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(URL, wait_until="networkidle")
    for flag in (True, False):
        f = os.path.join(OUT, "_imgON.pdf" if flag else "_imgOFF.pdf")
        pg.pdf(path=f, print_background=flag, prefer_css_page_size=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        print("写出", os.path.basename(f), os.path.getsize(f))
    b.close()
