# -*- coding: utf-8 -*-
"""对比：printBackground True / False 下的纸色与 full 背景"""
import os, sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18766/static/document.print.html"
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "Temp"))

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(URL, wait_until="networkidle")
    for flag in (True, False):
        f = os.path.join(OUT, "_bgON.pdf" if flag else "_bgOFF.pdf")
        pg.pdf(path=f, print_background=flag, prefer_css_page_size=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        print("写出", f, os.path.getsize(f))
    b.close()
