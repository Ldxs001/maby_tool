/*! md-parser.js — MDEditor 自研 Markdown 方言解释器（独立抽取版）
 * 来源：MarkdownEditor-app/markdown-editor.html
 *       第 490 行 PARSER_START … 第 827 行 PARSER_END （逐字抽取，标记名见原文件）
 * 同步：MDEditor v2.3.0（CHANGELOG 首段 2026-10-22，MD_SERVER_VERSION=66）
 * 许可：同项目根 LICENSE（见 MarkdownEditor-app/LICENSE）
 *
 * 用法：
 *   // 浏览器：<script src="md-parser.js"></script> 后
 *   MDParser.parseMarkdown("# 标题

正文");
 *   // Node / CommonJS
 *   const { parseMarkdown } = require('./md-parser.js');
 *   parseMarkdown(src);
 *   // ESM
 *   import { parseMarkdown } from './md-parser.js';
 *
 * 相对原文件的两处增强（仅本抽取版，原文件未动）：
 *   1. 外包 UMD：浏览器全局(MDParser) / CommonJS(require) / ESM(import) 通用；
 *   2. parseMarkdown(src, opts) 增加可选第二参 opts.indents = {p, quote, li}
 *      （容器级缩进档，px）——不传时与原文 100% 一致（默认 {p:0,quote:0,li:0}）。
 * 其余解析逻辑（escapeHtml / escAttr / sanitizeUrl / parseInline / parseList /
 * splitRow / parseTable / parseFenceLang / parseMarkdown 本体）逐字复制，未改动。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else if (typeof define === 'function' && define.amd) define(factory);
  else { root.MDParser = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  /* ===== 以下自 markdown-editor.html PARSER_START … PARSER_END 原样抽取 ===== */

/*PARSER_START*/
function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s){
  return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function sanitizeUrl(u){
  var t=u.trim();
  if(/^(javascript|vbscript):/i.test(t)) return '#';
  if(/^data:/.test(t) && !/^data:image\//i.test(t)) return '#';
  return t;
}
function parseInline(text){
  var codes=[];
  text=text.replace(/`([^`]+)`/g,function(m,c){codes.push(c);return '@@C'+(codes.length-1)+'@@';});
  /* 反斜杠转义（CommonMark 口径）：\X（X 为 ASCII 标点）→ 占位符，行内语法全部
     处理完再还原为字面 X。文档里展示 \!\[示例\](路径) 这类语法原文必须走这里，
     否则 \! 原样漏出、且 \[..\](..) 仍会被链接正则吃成真 <a>。
     在代码段提取之后做：代码段内反斜杠保持字面，双保险不冲突。 */
  var escs=[];
  text=text.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/g,function(m,c){escs.push(c);return '\x00E'+(escs.length-1)+'\x00';});
  text=escapeHtml(text);
  /* 生成的标签先进占位符：后续强调/加粗等行内语法绝不能触碰属性值
     （否则下划线文件名 20261015_181923_3419.png 会被 _.._ 改写成 <em>，图片必 404）。
     链接只占位开标签，链接文字仍参与行内格式化。 */
  var toks=[];
  /* 图片宽度+对齐参数：![alt](src){30} / {30c} / {c} → 版面宽度 30% 等比缩放
     + 可选对齐 c=居中 l=左 r=右（单图覆盖排版面板全局图片档）。
     [1-9]\d{0,2} 捕获，>100 钳到 100；对齐后缀独立可选（仅 {c} 也合法）；
     非法整体不进参数组（后缀原样留在正文可见，fail-closed）。
     参数组在 `)` 之外，保存时的路径改写只动括号内路径，天然不触碰后缀。 */
  text=text.replace(/!\[([^\]]*)\]\(([^)]+?)(?:\s+"([^"]*)")?\)(?:\s*\{([1-9]\d{0,2})?([clr])?\})?/g,function(m,alt,src,title,wpct,algn){
    /* 对齐内联进 img 自身 style（display:block + margin auto）而非
       p 的 text-align——ts-style 面板档 !important 按源序后置会盖掉
       主 CSS 的 p:has() 选择器规则；img 自身 margin 与 p text-align
       优先级链独立，语法级天然覆盖全局档 */
    var decls=[];
    if(wpct)decls.push('width:'+Math.min(parseInt(wpct,10),100)+'%');
    /* !important：面板全局档规则带 !important（同级按源序），内联不带
       important 会被盖（CSS 规范：作者 important > 内联普通）。
       三值全写覆盖而非叠加——全局档 center 会写 margin-left/right auto，
       语法级只写一侧会被合成为"两边 auto"=居中 */
    if(algn==='c')decls.push('display:block !important;margin-left:auto !important;margin-right:auto !important');
    else if(algn==='r')decls.push('display:block !important;margin-left:auto !important;margin-right:0 !important');
    else if(algn==='l')decls.push('display:block !important;margin-right:auto !important;margin-left:0 !important');
    var st=decls.length?(' style="'+decls.join(';')+'"'):'';
    var a=algn?(' data-img-align="'+(algn==='c'?'center':algn==='l'?'left':'right')+'"'):'';
    toks.push('<img src="'+escAttr(src)+'" alt="'+escAttr(alt)+'"'+(title?' title="'+escAttr(title)+'"':'')+st+a+'>');
    return '\x00T'+(toks.length-1)+'\x00';
  });
  text=text.replace(/\[([^\]]+)\]\(([^)]+?)(?:\s+"([^"]*)")?\)/g,function(m,txt,href,title){
    toks.push('<a href="'+escAttr(sanitizeUrl(href))+'"'+(title?' title="'+escAttr(title)+'"':'')+' target="_blank" rel="noopener">');
    return '\x00T'+(toks.length-1)+'\x00'+txt+'</a>';
  });
  text=text.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/__([^_]+)__/g,'<strong>$1</strong>');
  text=text.replace(/\*([^*]+)\*/g,'<em>$1</em>').replace(/_([^_]+)_/g,'<em>$1</em>');
  text=text.replace(/~~([^~]+)~~/g,'<del>$1</del>');
  text=text.replace(/@@C([0-9]+)@@/g,function(m,i){return '<code>'+escapeHtml(codes[+i])+'</code>';});
  text=text.replace(/\x00T(\d+)\x00/g,function(m,i){return toks[+i];});
  /* 转义还原放最后：逐字符 escapeHtml（如 \< → &lt;），只作用于还原出的单个字符，
     不触碰 toks 已注入的标签。 */
  text=text.replace(/\x00E([0-9]+)\x00/g,function(m,i){return escapeHtml(escs[+i]);});
  return text;
}
 function parseList(lines,start,indent,seq){
  /* seq：本编号区域内已出现的有序项数（跨列表接力，由外层块循环维护）。
     显示编号完全由渲染器决定——区域内第 N 个有序项显示 N，输入的
     数字仅是语法标记不参与显示；无序项不占编号；空行/其他块打断
     区域后由外层清零重计。嵌套子列表是独立编号区域（seq 从 0 起）。 */
  var items=[];
  var i=start;
  var cur=null;
  var listOrdered=null;
  while(i<lines.length){
    var line=lines[i];
    var m=line.match(/^([ ]*)([-+]|[0-9]+\.)([ ]+)(.*)$/);
    if(!m){break;}
    var li=m[1].length;
    if(li<indent){break;}
    if(li>indent){
      if(cur!==null){
        var r=parseList(lines,i,li,0);
        cur.children+=r[0];
        i=r[1];
        continue;
      } else {break;}
    }
    var ordered=/[0-9]+\./.test(m[2]);
    /* 标记语义（本工具方言）：无序 + = 实心点（disc）、- = 空心圈（circle），样式跟标记符走、
       与缩进无关（缩进只管层级归并）；星号不作列表标记（专注行内斜体与加粗强调）。 */
    if(listOrdered===null){
      listOrdered=ordered;
    } else if(ordered!==listOrdered){
      break;
    }
    cur={raw:m[4],ordered:ordered,mark:m[2],children:''};
    items.push(cur);
    i++;
  }
  if(items.length===0){return ['',i,seq];}
  var html='';
  if(listOrdered){
    seq+=items.length;
    /* 接力编号：本列表首项 = 区域内第 seq-items.length+1 个有序项 */
    var first=seq-items.length+1;
    html='<ol'+(first>1?(' start="'+first+'"'):'')+'>';
  } else {
    html='<ul>';
  }
  for(var k=0;k<items.length;k++){
    var it=items[k];
    var tm=it.raw.match(/^\[([ xX])\][ ]+(.*)$/);
    if(tm){
      var checked=tm[1].toLowerCase()==='x';
      html+='<li class="task"><input type="checkbox" disabled'+(checked?' checked':'')+'> '+parseInline(tm[2])+it.children+'</li>';
    } else {
      /* 仅无序项带 marker 样式类（+ 实心 / - 空心）；有序项无 class */
      var icls=it.ordered?'':(it.mark==='-'?' class="u-hollow"':' class="u-solid"');
      html+='<li'+icls+'>'+parseInline(it.raw)+it.children+'</li>';
    }
  }
  html+=listOrdered?'</ol>':'</ul>';
  return [html,i,seq];
}
function splitRow(r){
  /* GFM：表格单元格内 \| 恒为字面竖线（行内代码内也不例外），先占位再切分后还原 */
  var PH='\x01';
  r=r.replace(/\\\|/g,PH);
  var arr=r.split('|').map(function(s){return s.trim().replace(new RegExp(PH,'g'),'|');});
  if(arr.length>0 && arr[0]===''){arr.shift();}
  if(arr.length>0 && arr[arr.length-1]===''){arr.pop();}
  return arr;
}
function parseTable(lines,start){
  var head=splitRow(lines[start]);
  var sep=splitRow(lines[start+1]);
  var aligns=sep.map(function(c){
    var l=c.charAt(0)===':', r=c.charAt(c.length-1)===':';
    if(l&&r){return 'center';}
    if(r){return 'right';}
    if(l){return 'left';}
    return '';
  });
  var i=start+2;
  var body='';
  while(i<lines.length && lines[i].indexOf('|')>=0 && !/^[ ]*$/.test(lines[i])){
    var cells=splitRow(lines[i]);
    /* 列数对齐表头：超出合并进本行前一列（用 | 接回，内容不丢），不足补空格 */
    if(cells.length>head.length){
      cells=cells.slice(0,head.length-1).concat([cells.slice(head.length-1).join('|')]);
    }
    while(cells.length<head.length){cells.push('');}
    body+='<tr>'+cells.map(function(c,ci){
      return '<td'+(aligns[ci]?' style="text-align:'+aligns[ci]+'"':'')+'>'+parseInline(c)+'</td>';
    }).join('')+'</tr>';
    i++;
  }
  var thead='<thead><tr>'+head.map(function(c,ci){
    return '<th'+(aligns[ci]?' style="text-align:'+aligns[ci]+'"':'')+'>'+parseInline(c)+'</th>';
  }).join('')+'</tr></thead>';
  return ['<table>'+thead+'<tbody>'+body+'</tbody></table>',i];
}
/* 围栏语言行解析：```lang {N} —— N=版面百分比，与图片 {N} 同一规矩（空白可选、>100 钳 100）。
   非法形态（{0}/非数字/多余词）→ 整体视为 lang 原样返回、width=0（fail-closed：字面可见不吞错）。 */
function parseFenceLang(raw){
  /* 宽度+对齐参数：```mermaid {30} / mermaid{30} / {30c} / {c}（图 {N} 同规矩）。
     对齐进 data-diagram-align（渲染后应用容器）。lang 与 { 可无空格直连 */
  var m=raw.match(/^([A-Za-z][\w-]*)(?:\s*\{([1-9]\d{0,2})?([clr])?\})?\s*$/);
  if(!m)return {lang:raw.trim(),width:0,align:''};
  return {lang:m[1],
    width:m[2]?Math.min(100,parseInt(m[2],10)):0,
    align:m[3]?(m[3]==='c'?'center':m[3]==='l'?'left':'right'):''};
}
function parseMarkdown(src, opts){
  var lines=src.replace(/\r\n/g,'\n').replace(/\r/g,'\n').split('\n');
  var html='';
  var i=0;
  var olSeq=0;   /* 编号区域接力计数：空行/其他块打断即重置（见 parseList 注释） */
  /* <<< 缩进包围块 · 当前位置状态机（v2.1；档位 v2.2.1 起为 px，正文字号基准）：
     只流容器级缩进（px）——空行/标题/围栏/hr/表格清零；顶层段落=正文首行缩进档、
     列表=列表档、引用=引用档；<<< 冻结当前值为块内左边界（块内封闭不更新），
     闭合时 += 块内容器级子块叠加（列表/引用档，取 max）。段内 text-indent 永不进链。 */
  var IPX=(opts&&opts.indents)||(typeof window!=='undefined'&&window.__IND_PX__)||{p:0,quote:0,li:0};
  var curInd=0;
  while(i<lines.length){
    var line=lines[i];
    if(/^```/.test(line)){
      var rawLang=line.slice(3).trim();
       var fl=parseFenceLang(rawLang);   /* 图表围栏支持 ```mermaid {30} 版面百分比宽度 + c/l/r 对齐 */
       var lang=fl.lang, fW=fl.width, fA=fl.align;
      i++;
      var code='';
      while(i<lines.length && !/^```/.test(lines[i])){code+=lines[i]+'\n';i++;}
      i++;
      code=code.replace(/\n$/,'');
      if(lang==='mermaid'||lang==='dot'||lang==='graphviz'||lang==='viz'||lang==='wavedrom'||lang==='wavejson'||lang==='vega'||lang==='vega-lite'||lang==='vegalite'){
        /* 图容器：源码存 data-code（URI 编码），mountDiagrams 懒加载渲染。
           mermaid→mermaid；dot/graphviz/viz→Graphviz (viz-js WASM)；
           wavedrom/wavejson→WaveDrom 波形图（严格 JSON）；vega/vega-lite/vegalite→Vega-Lite（严格 JSON） */
        var kind='mermaid';
        if(lang==='dot'||lang==='graphviz'||lang==='viz')kind='dot';
        else if(lang==='wavedrom'||lang==='wavejson')kind='wavedrom';
        else if(lang==='vega'||lang==='vega-lite'||lang==='vegalite')kind='vega';
        html+='<div class="diagram" data-diagram="'+kind+'"'+(fA?' data-diagram-align="'+fA+'"':'')+(fW?' style="width:'+fW+'%"':'')+' data-code="'+encodeURIComponent(code)+'"><div class="diagram-pending">图表渲染中…</div></div>';
      }else{
        html+='<pre><code'+(rawLang?' class="lang-'+rawLang+'"':'')+'>'+escapeHtml(code).replace(/</g,'&lt;')+'</code></pre>';
      }
      olSeq=0;curInd=0;
      continue;
    }
    if(/^[ ]*$/.test(line)){i++;olSeq=0;curInd=0;continue;}
    var hm=line.match(/^(#{1,6})[ ]+(.*)$/);
    if(hm){
      var lvl=hm[1].length;
      html+='<h'+lvl+'>'+parseInline(hm[2].trim())+'</h'+lvl+'>';
      i++;olSeq=0;curInd=0;continue;
    }
    /* <<< 缩进包围块（开闭同符号，状态翻转；不支持嵌套）。
       必须在 hr 判定之前：<<< 去空格后为三连字符，会被 hr 规则吃掉。
       冻结 curInd 为块内左边界；块内递归渲染（天然封闭，内层 curInd 独立）；
       闭合后 curInd = 块边界 + 块内容器级子块叠加（列表/引用档取 max）。
       未闭合 fail-closed：标记行按普通文本渲染（字面保留）。 */
    if(/^[ ]{0,3}<<<\s*$/.test(line)){
      var inner=[],closed=false,j=i+1;
      while(j<lines.length){
        if(/^[ ]{0,3}<<<\s*$/.test(lines[j])){closed=true;j++;break;}
        inner.push(lines[j]);j++;
      }
      if(!closed){
        html+='<p>'+parseInline(line)+'</p>';
        i++;olSeq=0;curInd=0;continue;
      }
      var hasList=false,hasQuote=false;
      for(var q=0;q<inner.length;q++){
        if(/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(inner[q]))hasList=true;
        else if(/^[ ]*>/.test(inner[q]))hasQuote=true;
      }
      /* div margin 只冻结当前值；块内列表/引用的缩进由自身 CSS 档位生效（否则与
         overlay 双算）。叠加值只更新 curInd 供下一个包围继承
         （块内列表视觉 = 边界 + 列表档）。px 直写不依赖 ind-blk 字号——
         em 时基准随容器字号漂移（继承链 15px 环境下 2em 渲染 30px，
         与正文首行 37.3px 不齐）。 */
      var left=curInd;
      html+='<div class="ind-blk" style="margin-left:'+left+'px">'+parseMarkdown(inner.join('\n'))+'</div>';
      curInd=left+Math.max(hasList?IPX.li:0,hasQuote?IPX.quote:0);
      i=j;olSeq=0;
      continue;
    }
    /* @@ fill 图片分栏（v2.3）：@@ begin fill {a|b[|c[|d]]} … @@ end fill。
       比例为版面宽度百分比（50|50 各半，与图 {50} 同口径），2~4 栏、
       各值 1-100、和须=100。栏内容按空行分隔（每栏 = 一段：图表围栏块
       或图片行序列）；段数 ≠ 栏数 fail-closed（标记与内容按普通文本渲染）。
       栏内 {N} 失效（CSS fill-col 覆盖：width:auto/max-width:100%），
       宽度全权由栏比例决定；分栏是图片布局语法，进 <<< 继承链（容器级
       margin-left）。 */
    var fm=line.match(/^[ ]{0,3}@@\s*begin\s+fill\s*\{([\d|]+)\}\s*$/);
    if(fm){
      var parts=fm[1].split('|');
      var okFill=parts.length>=2&&parts.length<=4;
      var ratios=[];
      var sumR=0;
      if(okFill){
        for(var r=0;r<parts.length;r++){
          var rv=parseInt(parts[r],10);
          if(isNaN(rv)||rv<1||rv>100){okFill=false;break;}
          ratios.push(rv);sumR+=rv;
        }
        if(sumR!==100)okFill=false;
      }
      var finner=[],fclosed=false,fj=i+1;
      while(fj<lines.length){
        if(/^[ ]{0,3}@@\s*end\s+fill\s*$/.test(lines[fj])){fclosed=true;fj++;break;}
        finner.push(lines[fj]);fj++;
      }
      if(okFill&&fclosed){
        /* 空行分栏：连续非空行属同栏（栏内可放图片行/围栏） */
        var cols=[],cur=[];
        for(var c=0;c<finner.length;c++){
          if(/^[ ]*$/.test(finner[c])){
            if(cur.length){cols.push(cur.join('\n'));cur=[];}
          }else{cur.push(finner[c]);}
        }
        if(cur.length)cols.push(cur.join('\n'));
        if(cols.length===ratios.length){
          var fh='<div class="fill-row" style="margin-left:'+curInd+'px">';
          for(var ci=0;ci<cols.length;ci++){
            fh+='<div class="fill-col" style="width:'+ratios[ci]+'%">'+parseMarkdown(cols[ci])+'</div>';
          }
          fh+='</div>';
          html+=fh;
          i=fj;olSeq=0;curInd=0;
          continue;
        }
      }
      /* fail-closed：整块（含标记行）按普通文本渲染 */
      if(fclosed){
        html+='<p>'+parseInline(line)+'</p>';
        i++;
        var ftxt=finner.join('\n');
        if(ftxt.trim()){html+=parseMarkdown(ftxt);}
        i=fj;olSeq=0;curInd=0;
        continue;
      }
    }
    var stripped=line.replace(/[ ]/g,'');
    if(stripped.length>=3){
      var ch0=stripped.charAt(0);
      var allSame=true;
      for(var z=0;z<stripped.length;z++){if(stripped.charAt(z)!==ch0){allSame=false;break;}}
      if(allSame){html+='<hr>';i++;olSeq=0;curInd=0;continue;}
    }
    if(/^[ ]*>/.test(line)){
      var quote=[];
      while(i<lines.length && /^[ ]*>/.test(lines[i])){quote.push(lines[i].replace(/^[ ]*>[ ]?/,''));i++;}
      html+='<blockquote>'+parseMarkdown(quote.join('\n'))+'</blockquote>';
      olSeq=0;curInd=IPX.quote;
      continue;
    }
    if(line.indexOf('|')>=0 && i+1<lines.length && /^[ ]*\|?[-|: ]+\|?[ ]*$/.test(lines[i+1]) && lines[i+1].indexOf('-')>=0){
      var t=parseTable(lines,i);
      html+=t[0];i=t[1];olSeq=0;curInd=0;continue;
    }
    if(/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(line)){
      var ind=/^([ ]*)([-+]|[0-9]+\.)/.exec(line)[1].length;
      var lst=parseList(lines,i,ind,olSeq);
      html+=lst[0];i=lst[1];olSeq=lst[2];curInd=IPX.li;continue;
    }
    var para=[];
    while(i<lines.length && !/^[ ]*$/.test(lines[i]) && !/^```/.test(lines[i]) && !/^(#{1,6})[ ]+/.test(lines[i]) && !/^[ ]*>/.test(lines[i]) && !/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(lines[i]) && !/^[ ]{0,3}<<<\s*$/.test(lines[i]) && !(lines[i].indexOf('|')>=0 && i+1<lines.length && /^[ ]*\|?[-|: ]+\|?[ ]*$/.test(lines[i+1]) && lines[i+1].indexOf('-')>=0)){
      para.push(lines[i]);i++;
    }
    html+='<p>'+parseInline(para.join('\n')).replace(/\n/g,'<br>')+'</p>';
    olSeq=0;curInd=IPX.p;
  }
  return html;
}
/*PARSER_END*/

  /* ===== 抽取结束 ===== */
  return {
    parseMarkdown: parseMarkdown,
    parseInline: parseInline,
    parseList: parseList,
    parseTable: parseTable,
    parseFenceLang: parseFenceLang,
    splitRow: splitRow,
    escapeHtml: escapeHtml,
    escAttr: escAttr,
    sanitizeUrl: sanitizeUrl
  };
}));
