# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""_patch_lint_core.py -- PARSER core 段埋语法诊断点（v2.22.0）

原则：
  1. 诊断与渲染同源——每个 fail-closed 降级分支在降级的同时上报
     {line, code, msg, sev}，lint 不另立规则引擎，永不与渲染双标；
  2. 渲染路径零变化——opts.diag 不传时（宿主渲染、旧调用）输出逐字节不变；
  3. 行号穿透——parseMarkdown 加 _base 形参，10 处递归调用点按下层内容
     首行的绝对行号下传，诊断行号一律为文档绝对行（1-based）。

每处替换先断言 old 串在全文恰好出现 1 次（count==n 铁律），落盘后回读复校。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "markdown-editor.html")

EDITS = [
    # R1 签名 + 诊断通道
    ("""function parseMarkdown(src,_lv){
  _lv=_lv|0;
  var lines=src.replace(/\\r\\n/g,'\\n').replace(/\\r/g,'\\n').split('\\n');
  var html='';
  var i=0;""",
     """function parseMarkdown(src,_lv,opts,_base){
  _lv=_lv|0;
  _base=_base||0;
  var lines=src.replace(/\\r\\n/g,'\\n').replace(/\\r/g,'\\n').split('\\n');
  var html='';
  var i=0;
  /* v2.22.0 语法诊断：opts.diag 非空才收集（渲染路径不传 → 输出逐字节不变）。
     fail-closed 降级点在降级同时上报 {line,code,msg,sev}；lint=渲染同源，永不双标。
     行号=文档绝对行（1-based），_base 由递归调用点按下层内容首行绝对行号下传。 */
  var _dg=(opts&&opts.diag)||null;
  function _dgE(rel,code,msg,sev){
    if(_dg)_dg.push({line:_base+rel+1,code:code,msg:msg,sev:sev||'err'});
  }"""),

    # R2 IPX 行：opts 优先（与抽取版一致，改后 html/jss 两源逐字节同文）
    ("""  var IPX=(typeof window!=='undefined'&&window.__IND_PX__)||{p:0,quote:0,li:0};""",
     """  var IPX=(opts&&opts.indents)||(typeof window!=='undefined'&&window.__IND_PX__)||{p:0,quote:0,li:0};"""),

    # R3 循环顶：_dgHit 每行复位（行尾兜底防重复上报）
    ("""  var pendCap=null;   /* v2.10.0 @@ caption 暂存：只作用于紧随其后的那一个表格 */
  while(i<lines.length){
    var line=lines[i];""",
     """  var pendCap=null;   /* v2.10.0 @@ caption 暂存：只作用于紧随其后的那一个表格 */
  var _dgHit=false;
  while(i<lines.length){
    var line=lines[i];
    _dgHit=false;"""),

    # R4a fence 起始行号
    ("""    if(/^```/.test(line)){
      var rawLang=line.slice(3).trim();""",
     """    if(/^```/.test(line)){
      var _fenceAt=i;
      var rawLang=line.slice(3).trim();"""),

    # R4b fence 未闭合
    ("""      while(i<lines.length && !/^```/.test(lines[i])){code+=lines[i]+'\\n';i++;}
      i++;""",
     """      while(i<lines.length && !/^```/.test(lines[i])){code+=lines[i]+'\\n';i++;}
      if(i>=lines.length)_dgE(_fenceAt,'D103','代码围栏未闭合：文末缺收尾 ```','warn');
      i++;"""),

    # R5 <<< 未闭合
    ("""      if(!closed){
        html+='<p>'+parseInline(line)+'</p>';
        i++;curInd=0;continue;
      }""",
     """      if(!closed){
        _dgE(i,'D101','<<< 未闭合：到文末没有第二个 <<<（开与闭用同一个符号）');
        html+='<p>'+parseInline(line)+'</p>';
        i++;curInd=0;continue;
      }"""),

    # R6 <<< 非独占一行（插在 <<< 块后、fill 注释前）
    ("""      curInd=left+Math.max(hasList?IPX.li:0,hasQuote?IPX.quote:0);
      i=j;
      continue;
    }
    /* @@ fill 分栏""",
     """      curInd=left+Math.max(hasList?IPX.li:0,hasQuote?IPX.quote:0);
      i=j;
      continue;
    }
    /* v2.22.0 <<< 须独占一行：行尾带内容不构成包围块（fail-closed 按普通文本） */
    if(/^[ ]{0,3}<<</.test(line)&&!/^[ ]{0,3}<<<\\s*$/.test(line)){
      _dgE(i,'D102','<<< 须独占一行：行尾还有内容，本行按普通文本渲染','warn');
    }
    /* @@ fill 分栏"""),

    # R7 fill 越界/同族
    ("""      if(!(_LV.fill>_lv)){
        /* v2.18.0 越界/同族：fill 是主链最内层（rank 3），_lv>=3 时不可再开""",
     """      if(!(_LV.fill>_lv)){
        _dgE(i,'D201','fill 不能在这里再开：fill 套 fill，或 full/page 区里开 fill（主链层级 page＞full＞fill）');
        /* v2.18.0 越界/同族：fill 是主链最内层（rank 3），_lv>=3 时不可再开"""),

    # R8 fill 未闭合（ falls-through → 行尾兜底，需 _dgHit 压重复）
    ("""      var _fr=_scanBeginBlock(lines,i+1,['fill']);
      var finner=_fr.inner,fclosed=_fr.closed,fj=_fr.next;
      if(fclosed){""",
     """      var _fr=_scanBeginBlock(lines,i+1,['fill']);
      var finner=_fr.inner,fclosed=_fr.closed,fj=_fr.next;
      if(!fclosed){_dgE(i,'D203','fill 未闭合：到文末没有 @@ end fill，整块按普通文本渲染');_dgHit=true;}
      if(fclosed){"""),

    # R9 分栏列起始行跟踪（cols 内容逐字节不变，仅加 colAt 记账）
    ("""        var cols=[],cur=[];
        for(var c=0;c<finner.length;c++){
          if(/^[ ]*$/.test(finner[c])){
            if(cur.length){cols.push(cur.join('\\n'));cur=[];}
          }else{cur.push(finner[c]);}
        }
        if(cur.length)cols.push(cur.join('\\n'));""",
     """        var cols=[],cur=[],colAt=[],cAt=0;
        for(var c=0;c<finner.length;c++){
          if(/^[ ]*$/.test(finner[c])){
            if(cur.length){cols.push(cur.join('\\n'));colAt.push(cAt);cur=[];}
            cAt=c+1;
          }else{if(!cur.length)cAt=c;cur.push(finner[c]);}
        }
        if(cur.length){cols.push(cur.join('\\n'));colAt.push(cAt);}"""),

    # R10 fill 栏递归基点
    ("""            fh+='<div class="fill-col" style="width:'+ratios[ci]+'%">'+parseMarkdown(cols[ci],_LV.fill)+'</div>';""",
     """            fh+='<div class="fill-col" style="width:'+ratios[ci]+'%">'+parseMarkdown(cols[ci],_LV.fill,opts,_base+i+1+colAt[ci])+'</div>';"""),

    # R11 fill 失败内容递归基点
    ("""        if(ftxt.trim()){html+=parseMarkdown(ftxt,_lv);}""",
     """        if(ftxt.trim()){html+=parseMarkdown(ftxt,_lv,opts,_base+i+1);}"""),

    # R12 fill 参数不匹配：给出具体原因
    ("""      /* fail-closed：整块（含标记行）按普通文本渲染 */
      if(fclosed){
        html+='<p>'+parseInline(line)+'</p>';""",
     """      /* fail-closed：整块（含标记行）按普通文本渲染 */
      if(fclosed){
        if(_dg){
          var _rsn='';
          if(fm[1]!==undefined){
            var _pp=fm[1].split('|');
            if(_pp.length!==cols.length)_rsn='比例段数 '+_pp.length+' ≠ 栏数 '+cols.length;
            else{
              var _ssum=0,_badv=false;
              for(var _pr=0;_pr<_pp.length;_pr++){
                var _pv=parseInt(_pp[_pr],10);
                if(isNaN(_pv)||_pv<1||_pv>100){_badv=true;break;}
                _ssum+=_pv;
              }
              if(_badv)_rsn='比例值须为 1~100 的整数';
              else if(_ssum!==100)_rsn='比例之和须为 100（当前 '+_ssum+'）';
            }
          }else if(cols.length<2||cols.length>4)_rsn='无参 fill 须 2~4 栏（当前 '+cols.length+' 栏）';
          _dgE(i,'D202','fill 参数不匹配'+(_rsn?('：'+_rsn):''));
        }
        html+='<p>'+parseInline(line)+'</p>';"""),

    # R13 color 未闭合
    ("""      var _cr=_scanBeginBlock(lines,i+1,['color']);
      var cinner=_cr.inner,cclosed=_cr.closed,cj=_cr.next;
      if(cval&&cclosed){""",
     """      var _cr=_scanBeginBlock(lines,i+1,['color']);
      var cinner=_cr.inner,cclosed=_cr.closed,cj=_cr.next;
      if(!cclosed){_dgE(i,'D212','color 未闭合：缺 @@ end color，内容照常渲染');_dgHit=true;}
      if(cval&&cclosed){"""),

    # R14 color 内容递归基点
    ("""        html+='<div class="mde-color" style="color:'+cval+'">'+
          parseMarkdown(cinner.join('\\n'),_lv)+'</div>';""",
     """        html+='<div class="mde-color" style="color:'+cval+'">'+
          parseMarkdown(cinner.join('\\n'),_lv,opts,_base+i+1)+'</div>';"""),

    # R15 color 色值非法
    ("""      if(cclosed){
        html+='<p>'+parseInline(line)+'</p>';
        var ctxt=cinner.join('\\n');""",
     """      if(cclosed){
        if(!cval)_dgE(i,'D211','color 色值非法：{X} 须为颜色名或 #rgb / #rrggbb');
        html+='<p>'+parseInline(line)+'</p>';
        var ctxt=cinner.join('\\n');"""),

    # R16 color 失败内容递归基点
    ("""        if(ctxt.trim()){html+=parseMarkdown(ctxt,_lv);}""",
     """        if(ctxt.trim()){html+=parseMarkdown(ctxt,_lv,opts,_base+i+1);}"""),

    # R17 full 越界/同族
    ("""      if(!(_LV.full>_lv)){
        /* v2.18.0 越界/同族：full 是主链中层（rank 2），_lv>=2 时不可再开""",
     """      if(!(_LV.full>_lv)){
        _dgE(i,'D221','full 不能在这里再开：full 套 full，或 fill 区里开 full（主链层级 page＞full＞fill）');
        /* v2.18.0 越界/同族：full 是主链中层（rank 2），_lv>=2 时不可再开"""),

    # R18 full 内容递归基点
    ("""        html+='<div class="full-page" data-full-pos="'+(um[1]||'m')+'">'+
          parseMarkdown(uinner.join('\\n'),_LV.full)+'</div>';""",
     """        html+='<div class="full-page" data-full-pos="'+(um[1]||'m')+'">'+
          parseMarkdown(uinner.join('\\n'),_LV.full,opts,_base+i+1)+'</div>';"""),

    # R19 full 未闭合（消费路径）
    ("""      /* 未闭合 fail-closed：标记行按原文，内容照常渲染 */
      html+='<p>'+parseInline(line)+'</p>';
      i++;
      continue;""",
     """      /* 未闭合 fail-closed：标记行按原文，内容照常渲染 */
      _dgE(i,'D222','full 未闭合：缺 @@ end full，内容照常渲染');
      html+='<p>'+parseInline(line)+'</p>';
      i++;
      continue;"""),

    # R20 page 越界/同族
    ("""        if(!(_LV.page>_lv)){
          /* v2.18.0 越界/同族：page 是主链最外层（rank 1），_lv>=1 时不可""",
     """        if(!(_LV.page>_lv)){
          _dgE(i,'D231','page 不能在这里再开：页区套页区，或 full/fill 区里开 page（主链层级 page＞full＞fill）');
          /* v2.18.0 越界/同族：page 是主链最外层（rank 1），_lv>=1 时不可"""),

    # R21 page 内容递归基点
    ("""          html+='<div class="page-region" data-pn="'+_pgn+'" data-pr-id="pr'+_pgRegSeq+'">'+
            parseMarkdown(pginner.join('\\n'),_LV.page)+'</div>';""",
     """          html+='<div class="page-region" data-pn="'+_pgn+'" data-pr-id="pr'+_pgRegSeq+'">'+
            parseMarkdown(pginner.join('\\n'),_LV.page,opts,_base+i+1)+'</div>';"""),

    # R22 page 未闭合（消费路径）
    ("""        html+='<p>'+parseInline(line)+'</p>';
        i++;
        continue;
      }
      /* 参数非法：不接管，落到下面普通段落按原文露出 */""",
     """        _dgE(i,'D233','page 未闭合：缺 @@ end page，内容照常渲染');
        html+='<p>'+parseInline(line)+'</p>';
        i++;
        continue;
      }
      /* 参数非法：不接管，落到下面普通段落按原文露出 */"""),

    # R23 page 参数非法（falls-through → _dgHit 压重复）
    ("""      /* 参数非法：不接管，落到下面普通段落按原文露出 */
    }""",
     """      /* 参数非法：不接管，落到下面普通段落按原文露出 */
      _dgE(i,'D232','page 参数非法：{...} 里须为 noll / 1 / i / I');_dgHit=true;
    }"""),

    # R24 mg 段起始行记账
    ("""          var _mgSegs=[],_mgBuf=[],_mgOpen={},_mgDepth={page:0,full:0,fill:0,color:0},_mgOpenN=_mgl.length,_mgOk2=true,_mgK2=i+1;""",
     """          var _mgSegs=[],_mgBuf=[],_mgOpen={},_mgDepth={page:0,full:0,fill:0,color:0},_mgOpenN=_mgl.length,_mgOk2=true,_mgK2=i+1,_mgSegAt=i+1;"""),

    # R25 mg 段记录起始行
    ("""                _mgSegs.push({c:_mgBuf,o:_oarr});""",
     """                _mgSegs.push({c:_mgBuf,o:_oarr,at:_mgSegAt});"""),

    # R26 mg 分段后更新段起点
    ("""                _mgOpenN-=_mgClose.length;
                _mgK2++;
                if(_mgOpenN===0){break;}   /* 集合清空 → 块闭合 */""",
     """                _mgOpenN-=_mgClose.length;
                _mgK2++;
                _mgSegAt=_mgK2;
                if(_mgOpenN===0){break;}   /* 集合清空 → 块闭合 */"""),

    # R27 mg 段递归基点
    ("""              if(_mgSegs[_ms].c.length){_mgHtml+=parseMarkdown(_mgSegs[_ms].c.join('\\n'),_mgLv);}""",
     """              if(_mgSegs[_ms].c.length){_mgHtml+=parseMarkdown(_mgSegs[_ms].c.join('\\n'),_mgLv,opts,_base+_mgSegs[_ms].at);}"""),

    # R28 mg 失败诊断（D241/D242/D243）
    ("""            html+=_mgHtml;
            i=_mgK2;
            continue;
          }
        }
      }""",
     """            html+=_mgHtml;
            i=_mgK2;
            continue;
          }
          if(!_mgOk2){_dgE(_mgK2,'D242','并写块：@@ end 关闭了未打开的家族');_dgHit=true;}
          else{_dgE(i,'D243','并写块未闭合：文末仍有开着的 page/full/color 层');_dgHit=true;}
        }else{
          _dgE(i,'D241','并写 begin 不成立：家族顺序须 page→full→color、同族不重复、参数合法');_dgHit=true;
        }
      }"""),

    # R29 MDE 数据点未闭合
    ("""       if(dclosed){
         var dfull=dchunks.join('\\n');""",
     """       if(!dclosed){_dgE(i,'D301','@@ MDE 数据点未闭合：到文末没有 }');_dgHit=true;}
       if(dclosed){
         var dfull=dchunks.join('\\n');"""),

    # R30 表格型数据点：合成源抑制内部诊断
    ("""                 dsp='<div class="mde-dp mde-dp-block"'+dattrs+'>'+parseMarkdown(_dpTableSrc(dmm[5]),_lv)+'</div>';""",
     """                 dsp='<div class="mde-dp mde-dp-block"'+dattrs+'>'+parseMarkdown(_dpTableSrc(dmm[5]),_lv,null,0)+'</div>';"""),

    # R31 MDE 数据点内容不合规范（该块整体多一空格缩进）
    ("""           /* fail-closed：整块按普通段落（含标记行原文） */
           html+='<p>'+parseInline(dfull.replace(/\\n/g,' '))+'</p>';""",
     """           /* fail-closed：整块按普通段落（含标记行原文） */
           _dgE(i,'D302','@@ MDE 数据点内容不合规范：(( )) 混用／键值段缺 ==／表格行列或坐标错——按普通文本渲染');
           html+='<p>'+parseInline(dfull.replace(/\\n/g,' '))+'</p>';"""),

    # R32 引用块递归基点（quote 首行 = 当前 i）
    ("""    if(/^[ ]*>/.test(line)){
      var quote=[];
      while(i<lines.length && /^[ ]*>/.test(lines[i])){quote.push(lines[i].replace(/^[ ]*>[ ]?/,''));i++;}
      html+='<blockquote>'+parseMarkdown(quote.join('\\n'),_lv)+'</blockquote>';""",
     """    if(/^[ ]*>/.test(line)){
      var _qAt=i;
      var quote=[];
      while(i<lines.length && /^[ ]*>/.test(lines[i])){quote.push(lines[i].replace(/^[ ]*>[ ]?/,''));i++;}
      html+='<blockquote>'+parseMarkdown(quote.join('\\n'),_lv,opts,_base+_qAt)+'</blockquote>';"""),

    # R33 <<< 内容递归基点
    ("""      html+='<div class="ind-blk" style="margin-left:'+left+'px">'+parseMarkdown(inner.join('\\n'),_lv)+'</div>';""",
     """      html+='<div class="ind-blk" style="margin-left:'+left+'px">'+parseMarkdown(inner.join('\\n'),_lv,opts,_base+i+1)+'</div>';"""),

    # R34 行尾兜底：方言前缀行未被接管＝未生效
    ("""    if(!para.length){para.push(lines[i]);i++;}""",
     """    if(!para.length){
      para.push(lines[i]);i++;
      /* v2.22.0 行尾兜底：@@ 方言前缀行没被任何分支接管＝未生效（fail-closed
         按普通文本渲染）。分支内已上报过的行（_dgHit）不重复报。 */
      if(!_dgHit&&/^[ ]{0,3}@@/.test(para[0])){
        var _dgT=(para[0].match(/^[ ]{0,3}@@\\s*(begin|end|caption|blank|MDE)/)||[])[1]||'';
        if(_dgT==='end')_dgE(i-1,'D401','孤 @@ end：前面没有打开的对应 begin 块（检查家族名与配对）');
        else if(_dgT==='begin')_dgE(i-1,'D402','@@ begin 未生效：家族名／参数／嵌套位置有误（fill 分栏／full 独占页／page 页区／color 着色）');
        else if(_dgT==='caption')_dgE(i-1,'D403','@@ caption 未生效：其后必须紧跟表格（下一行表体、再下一行分隔行）');
        else if(_dgT==='blank')_dgE(i-1,'D404','@@ blank 未生效：须独占一行，n 为正数（0.1~50）');
        else _dgE(i-1,'D405','以 @@ 开头但不是有效方言指令，按普通文本渲染','warn');
      }
    }"""),
]


def main():
    s = io.open(P, encoding="utf-8").read()
    bad = []
    for n, (old, new) in enumerate(EDITS, 1):
        c = s.count(old)
        if c != 1:
            bad.append("R%d count=%d" % (n, c))
            continue
        s = s.replace(old, new)
    if bad:
        print("FAILED: " + "; ".join(bad))
        return 1
    io.open(P, "w", encoding="utf-8", newline="").write(s)

    # 回读复校：每个新串必须恰好出现 1 次
    s2 = io.open(P, encoding="utf-8").read()
    bad2 = []
    for n, (old, new) in enumerate(EDITS, 1):
        c = s2.count(new)
        if c != 1:
            bad2.append("R%d new-count=%d" % (n, c))
    if bad2:
        print("WRITE OK but VERIFY FAILED: " + "; ".join(bad2))
        return 1
    print("PATCH OK: %d 处替换全部落盘且回读校验通过" % len(EDITS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
