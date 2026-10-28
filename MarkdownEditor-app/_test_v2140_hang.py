# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwProject. Licensed under GNU AGPL v3 (or later).
"""v2.14.0 列表标记外凸（list-style-position 开关）几何测试。

用户场景：手打 □ 的列表项，续行必须与首行方框同 x ——
    1. □首行方框
    □续行方框          ← 现状（inside）续行落到「1.」左下方
开关打开后走 outside + marker 槽：文字块整体右移一槽，marker 站到文字外。

判据：
1. 关态：ol/ul 仍 inside、padding-left=0（存量文档零影响的结构前提）
2. 开态：ol outside + padding=22.5px（1.5em@15px）、ul outside + padding=16.5px
3. 续行对齐：开态下两个 □ 的 x 相等（±1px）；关态下续行明显偏左（复现原缺陷）
4. 文字块右移量 = 槽宽（marker 槽真的让出来了，不是把文字压回去）
5. `- [ ]` 归队：input 左沿 == 兄弟项文字左沿（两态都成立）
6. 嵌套列表：开态下二级文字左沿 > 一级文字左沿（出槽后才有层级缩进）
7. ts-style 携带 --mde-mark-* 与 outside 规则；关态两者都不出现
8. 无 page errors

跑前杀遗留 md_server。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18766  # md_server.py 里写死，测试只能跟
NO_WINDOW = 0x08000000

fails = []


def check(name, cond, detail=""):
    print("%-58s %s %s" % (name, "PASS" if cond else "FAIL", detail))
    if not cond:
        fails.append(name)


def kill_stale():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "($_.CommandLine -like '*md_server.py*' -or $_.CommandLine -like '*_md_run.py*') -and $_.Name -like "
         "'*python*' } | ForEach-Object { Stop-Process -Id $_.ProcessId "
         "-Force }"],
        capture_output=True)


def alive():
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/api/version" % PORT, timeout=0.3).read()
        return True
    except Exception:
        return False


DOC = """1. □首行方框
□续行方框
2. 第二项

- [ ] 待办项
- 普通项

1. 一级
   - 二级
"""

SET_BASE = """()=>{
  document.getElementById('btnTypeset').click();
  document.querySelector('input[data-tssz="p"]').value='14';
  document.querySelector('select[data-ind="li"]').value='block';
  document.querySelector('input[data-indchars="li"]').value='2';
  document.getElementById('tsHangOn').checked=false;
  document.getElementById('tsApply').click();
}"""

SET_HANG = """()=>{
  document.getElementById('btnTypeset').click();
  document.getElementById('tsHangOn').checked=true;
  document.getElementById('tsApply').click();
}"""

MEASURE = """()=>{
  var pv=document.getElementById('preview');
  var pvx=pv.getBoundingClientRect().left;
  function charX(el,ch){
    var tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null);
    var n;
    while((n=tw.nextNode())){
      var i=n.textContent.indexOf(ch);
      if(i>=0){
        var rg=document.createRange();
        rg.setStart(n,i);rg.setEnd(n,i+1);
        return Math.round(rg.getBoundingClientRect().left-pvx);
      }
    }
    return null;
  }
  function textX(el){
    var tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null);
    var n;
    while((n=tw.nextNode())){
      var m=n.textContent.match(/\\S/);
      if(m){
        var rg=document.createRange();
        rg.setStart(n,m.index);rg.setEnd(n,m.index+1);
        return Math.round(rg.getBoundingClientRect().left-pvx);
      }
    }
    return null;
  }
  var out={};
  var ol1=pv.querySelector('ol'), ul1=null;
  pv.querySelectorAll('ul').forEach(function(u){if(!ul1)ul1=u;});
  var liBox=ol1?ol1.querySelector('li'):null;
  out.olPos=ol1?getComputedStyle(ol1).listStylePosition:null;
  out.olPad=ol1?getComputedStyle(ol1).paddingLeft:null;
  out.olMl=ol1?getComputedStyle(ol1).marginLeft:null;
  out.ulPos=ul1?getComputedStyle(ul1).listStylePosition:null;
  out.ulPad=ul1?getComputedStyle(ul1).paddingLeft:null;
  /* 首行 □ 与续行 □ 的 x（同一 li 内的两行） */
  out.box1=liBox?charX(liBox,'□'):null;
  var li2=null;
  if(ol1){
    ol1.querySelectorAll('li').forEach(function(l){
      if((l.textContent||'').indexOf('续行方框')>=0)li2=l;});
  }
  out.box2=li2?charX(li2,'□'):null;
  /* 第二个 □ 实际是续行的那个：charX 取首个，需用 Range 精确取第二处 */
  if(li2){
    var tw=document.createTreeWalker(li2,NodeFilter.SHOW_TEXT,null),n,cnt=0;
    while((n=tw.nextNode())){
      var idx=-1;
      while((idx=n.textContent.indexOf('□',idx+1))>=0){
        cnt++;
        if(cnt===2){
          var rg=document.createRange();
          rg.setStart(n,idx);rg.setEnd(n,idx+1);
          out.box2=Math.round(rg.getBoundingClientRect().left-pvx);
        }
      }
    }
  }
  /* task 项方框 vs 兄弟项文字 */
  var ulTask=null;
  pv.querySelectorAll('ul').forEach(function(u){
    if(u.querySelector('li.task')&&!ulTask)ulTask=u;});
  out.taskInput=null;out.taskPeer=null;out.ulContent=null;
  if(ulTask){
    var inp=ulTask.querySelector('li.task input');
    if(inp)out.taskInput=Math.round(inp.getBoundingClientRect().left-pvx);
    ulTask.querySelectorAll('li').forEach(function(l){
      if(!l.classList.contains('task')&&out.taskPeer===null)out.taskPeer=textX(l);});
    /* ul 内容盒左沿 = 边框盒左沿 + padding（外凸态的 marker 槽即在此之外） */
    out.ulContent=Math.round(
      ulTask.getBoundingClientRect().left
      + parseFloat(getComputedStyle(ulTask).paddingLeft) - pvx);
  }
  /* 嵌套：二级文字 x */
  out.nest1=null;out.nest2=null;
  var ol2=null;
  pv.querySelectorAll('ol').forEach(function(o){
    if(o.querySelector('ul')&&!ol2)ol2=o;});
  if(ol2){
    out.nest1=textX(ol2.querySelector('li'));
    out.nest2=textX(ol2.querySelector('ul>li'));
  }
  var st=document.getElementById('ts-style');
  out.css=st?st.textContent:'';
  return out;
}"""

kill_stale()
time.sleep(0.3)
srv = subprocess.Popen(
    [os.path.join(HERE, "python", "python.exe"), "md_server.py"],
    creationflags=NO_WINDOW)
t0 = time.time()
while not alive() and time.time() - t0 < 20:
    time.sleep(0.1)
assert alive(), "服务未就绪"

tmpdir = tempfile.mkdtemp(prefix="md_v2140_")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/?file=" % PORT)
        pg.wait_for_timeout(800)
        pg.evaluate(SET_BASE)
        pg.wait_for_timeout(300)
        pg.evaluate(
            "d=>{var ed=document.getElementById('editor');"
            "ed.textContent=d;"
            "ed.dispatchEvent(new Event('input',{bubbles:true}));}", DOC)
        pg.wait_for_function(
            "()=>{var pv=document.getElementById('preview');"
            "return pv&&pv.querySelectorAll('ol').length>=1"
            "&&pv.textContent.indexOf('续行方框')>=0;}", timeout=15000)
        pg.wait_for_timeout(500)

        off = pg.evaluate(MEASURE)
        print("关态:", json.dumps(
            {k: off[k] for k in ("olPos", "olPad", "olMl", "ulPos", "ulPad",
                                 "box1", "box2", "taskInput", "taskPeer",
                                 "nest1", "nest2")}, ensure_ascii=False))

        check("关态 ol 仍是 inside", off["olPos"] == "inside",
              "pos=%s" % off["olPos"])
        check("关态 ol padding-left=0（收编归零）", off["olPad"] == "0px",
              "pad=%s" % off["olPad"])
        check("关态档位=37.33px（14pt×2 字符）", off["olMl"] == "37.33px",
              "ml=%s" % off["olMl"])
        check("关态续行偏左（复现原缺陷，差>3px）",
              off["box1"] is not None and off["box2"] is not None
              and off["box2"] - off["box1"] < -3,
              "首行□=%s 续行□=%s" % (off["box1"], off["box2"]))
        check("关态 task 方框贴 ul 内容左沿（checkbox 自带 4px margin，±5px）",
              off["taskInput"] is not None and off["ulContent"] is not None
              and abs(off["taskInput"] - off["ulContent"]) <= 5,
              "input=%s ulContent=%s" % (off["taskInput"], off["ulContent"]))
        check("关态 ts-style 不含外凸规则",
              "--mde-mark-ol" not in off["css"]
              and "list-style-position:outside" not in off["css"])

        pg.evaluate(SET_HANG)
        pg.wait_for_timeout(600)
        on = pg.evaluate(MEASURE)
        print("开态:", json.dumps(
            {k: on[k] for k in ("olPos", "olPad", "olMl", "ulPos", "ulPad",
                                "box1", "box2", "taskInput", "taskPeer",
                                "nest1", "nest2")}, ensure_ascii=False))

        check("开态 ol → outside", on["olPos"] == "outside",
              "pos=%s" % on["olPos"])
        check("开态 ol padding=22.5px（1.5em@15px）", on["olPad"] == "22.5px",
              "pad=%s" % on["olPad"])
        check("开态 ul → outside + 16.5px（1.1em@15px）",
              on["ulPos"] == "outside" and on["ulPad"] == "16.5px",
              "pos=%s pad=%s" % (on["ulPos"], on["ulPad"]))
        check("开态档位不变（37.33px，marker 基准未被槽挤走）",
              on["olMl"] == "37.33px", "ml=%s" % on["olMl"])
        check("开态两行 □ 对齐（±1px）",
              on["box1"] is not None and on["box2"] is not None
              and abs(on["box1"] - on["box2"]) <= 1,
              "首行□=%s 续行□=%s" % (on["box1"], on["box2"]))
        check("开态续行比关态右移=槽宽（22.5px±1）",
              on["box2"] is not None and off["box2"] is not None
              and abs((on["box2"] - off["box2"]) - 22.5) <= 1,
              "关=%s 开=%s" % (off["box2"], on["box2"]))
        check("开态首行位移=槽宽−marker宽（≈6.5px，说明 marker 让进槽里）",
              on["box1"] is not None and off["box1"] is not None
              and 2 <= (on["box1"] - off["box1"]) <= 10,
              "关=%s 开=%s 差=%s" % (off["box1"], on["box1"],
                                     on["box1"] - off["box1"]))
        check("开态 task 方框贴 ul 内容左沿（跟随列表几何，不再离群）",
              on["taskInput"] is not None and on["ulContent"] is not None
              and abs(on["taskInput"] - on["ulContent"]) <= 5,
              "input=%s ulContent=%s" % (on["taskInput"], on["ulContent"]))
        check("开态嵌套：二级文字右于一级（层级缩进成立）",
              on["nest1"] is not None and on["nest2"] is not None
              and on["nest2"] - on["nest1"] >= 20,
              "一级=%s 二级=%s" % (on["nest1"], on["nest2"]))
        check("开态 ts-style 携带 --mde-mark-ol:22.5px",
              "--mde-mark-ol:22.5px" in on["css"])
        check("开态 ts-style 携带 --mde-mark-ul:16.5px",
              "--mde-mark-ul:16.5px" in on["css"])
        check("开态 ts-style 有 outside 规则",
              "list-style-position:outside" in on["css"])

        # 打印链：直接把同一份 bodyHtml + tsCss 交给 /api/export-paged，
        # 确认 outside 规则与槽宽变量随分页产物走（Paged.js 用同一份样式）
        pr = pg.evaluate(
            "()=>({body:document.getElementById('preview').innerHTML,"
            "css:(document.getElementById('ts-style')||{}).textContent||''})")
        rj = pg.request.post(
            "http://127.0.0.1:%d/api/export-paged" % PORT,
            data={"bodyHtml": pr["body"], "tsCss": pr["css"],
                  "cfg": {"paper": "A4", "mt": 25, "mr": 18, "mb": 25,
                          "ml": 18, "pn": {"on": "off"}}})
        j = rj.json()
        check("分页导出 ok", j.get("ok") is True, str(j)[:80])
        paged = ""
        if j.get("ok"):
            paged = open(os.path.join(HERE, "runtime", "document.paged.html"),
                         encoding="utf-8").read()
        check("分页产物含 outside 规则",
              "list-style-position:outside" in paged)
        check("分页产物含槽宽变量 --mde-mark-ol",
              "--mde-mark-ol:22.5px" in paged)
        # 分页产物不含 #preview 容器，规则靠双选择器里的 .markdown-body 副本生效
        check("分页产物有效副本 .markdown-body ol 带 outside",
              ".markdown-body ol{list-style-position:outside" in paged)
        check("分页产物有效副本 .markdown-body ul 带槽宽",
              ".markdown-body ul{list-style-position:outside" in paged
              and "padding-left:16.5px" in paged)

        # 关闭开关必须回到 inside（可逆）
        pg.evaluate(SET_BASE)
        pg.wait_for_timeout(500)
        back = pg.evaluate(MEASURE)
        check("关→开→关 可逆（inside + padding 0 + 几何同初值）",
              back["olPos"] == "inside" and back["olPad"] == "0px"
              and back["box1"] == off["box1"] and back["box2"] == off["box2"],
              "pos=%s pad=%s box1=%s/%s" % (back["olPos"], back["olPad"],
                                            back["box1"], off["box1"]))
        check("no page errors", not errors, "; ".join(errors[:2]))
        b.close()
finally:
    srv.terminate()
    try:
        srv.wait(3)
    except Exception:
        srv.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)

print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
sys.exit(1 if fails else 0)
