/*! md-parser.js — MDEditor 自研 Markdown 方言解释器（独立抽取版）
 * 来源：MarkdownEditor-app/markdown-editor.html
 *       标记 PARSER_START … PARSER_END 之间（逐字抽取，行号以标记定位）
 * 抽取脚本：_extract_parser.py（重抽后必跑 _test_parser_sync.py 校验）
 * 许可：同项目根 LICENSE（见 MarkdownEditor-app/LICENSE）
 *
 * 用法：
 *   // 浏览器：<script src="md-parser.js"></script> 后
 *   MDParser.parseMarkdown("# 标题\n\n正文");
 *   // Node / CommonJS
 *   const { parseMarkdown } = require('./md-parser.js');
 *   parseMarkdown(src);
 *   // ESM
 *   import { parseMarkdown } from './md-parser.js';
 *
 * 相对原文件的两处增强（仅本抽取版，原文件未动）：
 *   1. 外包 UMD：浏览器全局(MDParser) / CommonJS(require) / ESM(import) 通用；
 *   2. parseMarkdown(src, _lv, opts) 增加可选第三参 opts.indents = {p, quote, li}
 *      （容器级缩进档，px）——不传时与原文 100% 一致（默认 {p:0,quote:0,li:0}）；
 *      第二参 _lv 为 v2.18.0 主链嵌套层级（0=文档流顶层，html 内部递归专用）。
 * 其余解析逻辑逐字复制，未改动。改 html 解析器段后必须重新抽取本文件。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else if (typeof define === 'function' && define.amd) define(factory);
  else { root.MDParser = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  /* ===== 以下自 markdown-editor.html PARSER_START … PARSER_END 原样抽取 ===== */

/*PARSER_START*/
/* v2.17.0 页区实例序号：给 @@ begin page{…} 出的 .page-region 发唯一 id，
   填充脚本靠它区分「同一个区的续页」与「另一个区」（两个相邻 {1} 区各自
   从 1 起）。只增不复位——同一次渲染内唯一即可，多处递归解析也不会撞号。 */
var _pgRegSeq=0;
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
/* mdeParseBody（v2.6 六形式，规范见 docs/low runner 数据形式规范.md）：
   body → {ok, disp, dispSimple, ch, val, kvSingle, singleKey, singleVal}
   ch='kv'   val=object（多对；单对时 kvSingle 带字段）——并入桶 kv
   ch='vals' val=str / list / 嵌套list —— 入桶 vals
   ok=false → fail-closed（调用方按普通文本渲染，不产数据点 span）
   规则：
   - 含 (( )) → 行文抽取：句中 ((v)) 纯值 / ((k == v)) 键值（不可混用、
     须闭合非空）；显示 = 去掉 (( )) 标记的干净句子
   - 无 (( )) 含 == → 键值：按半角 , 分段——单段 = 单键值对（值内逗号
     是文本，向后兼容）；多段 = 键值向量（每段必须含 ==，否则 fail）
   - 无 (( )) 无 == → 纯值：含 , = 向量（list）；否则单值 str（现有行为）
   - 表格型 :N(rxc) 不走此函数（块级收集分支，body 多行） */
function mdeParseBody(body){
  var b=String(body);
  if(b.indexOf('((')>=0||b.indexOf('))')>=0){
    var items=[];
    var rx=/\(\(([^()]*?)\)\)/g,mm;
    var prose=b.replace(/\(\(([^()]*?)\)\)/g,'');
    while((mm=rx.exec(b))){
      if(!mm[1].trim()){return {ok:false};}
      items.push(mm[1]);
    }
    /* 成对括号提取后若正文残留 ( 或 ) 单边（未闭合标记）→ fail */
    if(prose.indexOf('((')>=0||prose.indexOf('))')>=0){return {ok:false};}
    if(!items.length){return {ok:false};}
    /* 直写与行文混用 → fail：行文形式的 (( )) 外是散文（用户例子全是
       全角，），散文出现半角 ,（直写向量分隔符）或 ==（直写键值符）
       即混写（'a, ((b))' / 'x == 1 ((b))'） */
    if(prose.indexOf(',')>=0||prose.indexOf('==')>=0){return {ok:false};}
    var hasKV=items.some(function(it){return it.indexOf('==')>=0;});
    var hasPure=items.some(function(it){return it.indexOf('==')<0;});
    if(hasKV&&hasPure){return {ok:false};}   /* ((v)) 与 ((k==v)) 混用 */
    var disp=b.replace(/\(\(([^()]*?)\)\)/g,'$1');
    if(hasKV){
      var o={};
      for(var i=0;i<items.length;i++){
        var eq=items[i].indexOf('==');
        if(eq<0){return {ok:false};}
        var k=items[i].slice(0,eq).trim(),v=items[i].slice(eq+2).trim();
        if(!k){return {ok:false};}
        o[k]=v;
      }
      var vs=[];for(var kk in o){vs.push(o[kk]);}
      return {ok:true,disp:disp,ch:'kv',val:o,dispSimple:vs.join('、')};
    }
    return {ok:true,disp:disp,ch:'vals',val:items.map(function(s){return s.trim();})};
  }
  if(b.indexOf('==')>=0){
    var parts=b.split(',');
    if(parts.length===1){
      var e1=b.indexOf('==');
      var k1=b.slice(0,e1).trim();
      if(!k1){return {ok:true,disp:b,ch:'vals',val:b};}
      return {ok:true,disp:b.slice(e1+2).trim(),ch:'kv',val:{},kvSingle:true,
        singleKey:k1,singleVal:b.slice(e1+2).trim()};
    }
    var o2={};
    for(var j=0;j<parts.length;j++){
      var e2=parts[j].indexOf('==');
      if(e2<0){return {ok:false};}
      var k2=parts[j].slice(0,e2).trim();
      if(!k2){return {ok:false};}
      o2[k2]=parts[j].slice(e2+2).trim();
    }
    var vs2=[];for(var kk2 in o2){vs2.push(o2[kk2]);}
    return {ok:true,disp:vs2.join('、'),ch:'kv',val:o2};
  }
  if(b.indexOf(',')>=0){
    return {ok:true,disp:b,ch:'vals',val:b.split(',').map(function(s){return s.trim();})};
  }
  return {ok:true,disp:b,ch:'vals',val:b};
}
/* mdeParseTable（v2.6 表格型 :N(rxc)，规范见 docs/low runner 数据形式规范.md）：
   dim='2'|'3'，coord='(2x2)' 或 '()'（空括号=全表），body=表格行文本。
   → {ok,dim,r,c,l,val}；val=二维 [[...]]（:2）/ 三层 [[[...]]]（:3）。
   规则：分隔行（|-|-| 类：仅 |:-与空白构成）是结构行——不计行号、
   不进输出（第 1 行=表头行、第 2 行=第一条数据行）；坐标 1-based，
   数据区 = 第 r 行第 c 列起取到表尾；空单元格=""；\|=字面竖线；
   :3 表格间空行分隔、张数=实际表数；:2 出现空行多表 → fail；
   非表格行/坐标越界/括号缺失 → fail（fail-closed 整块按普通文本） */
function mdeParseTable(dim,coord,body){
  if(!dim||!coord){return {ok:false};}
  var cm=coord.match(/^\(\s*(?:(\d+)\s*[xX×]\s*(\d+)\s*)?\)$/);
  if(!cm){return {ok:false};}
  var r0=cm[1]?parseInt(cm[1],10):1,c0=cm[2]?parseInt(cm[2],10):1;
  if(r0<1||c0<1){return {ok:false};}
  function _isSep(ln){
    return /^[|:\-\s]+$/.test(ln)&&/[-:]/.test(ln)&&ln.indexOf('|')>=0;
  }
  function _splitCells(ln){
    var s=ln.replace(/\\\|/g,'\x00P\x00');
    s=s.replace(/^\s*\|/,'').replace(/\|\s*$/,'');
    var cells=s.split('|').map(function(x){return x.replace(/\x00P\x00/g,'|').trim();});
    return cells;
  }
  /* 分表（空行切分） */
  var blocks=[],cur=[];
  var bl=String(body).split('\n');
  for(var i=0;i<=bl.length;i++){
    var ln=(i<bl.length)?bl[i]:'';
    if(ln.trim()===''||i===bl.length){
      if(cur.length){blocks.push(cur);cur=[];}
    }else{
      if(ln.indexOf('|')<0){return {ok:false};}   /* 非表格行 */
      cur.push(ln);
    }
  }
  if(!blocks.length){return {ok:false};}
  if(dim==='2'&&blocks.length>1){return {ok:false};}   /* 多表是 :3 专属 */
  var out=[],maxR=0,maxC=0;
  for(var bi=0;bi<blocks.length;bi++){
    var rows=[],nrows=0;
    for(var ri=0;ri<blocks[bi].length;ri++){
      var ln2=blocks[bi][ri];
      if(_isSep(ln2)){continue;}   /* 结构行：不计行号不进输出 */
      nrows++;
      rows.push(_splitCells(ln2));
    }
    if(!nrows){return {ok:false};}
    var width=0;
    for(var w=0;w<rows.length;w++){width=Math.max(width,rows[w].length);}
    if(r0>nrows||c0>width){return {ok:false};}   /* 坐标越界 */
    var crop=[];
    for(var rr=r0-1;rr<rows.length;rr++){
      var line=[];
      for(var cc=c0-1;cc<width;cc++){
        line.push((rows[rr][cc]!==undefined)?rows[rr][cc]:'');
      }
      crop.push(line);
    }
    out.push(crop);
    maxR=Math.max(maxR,crop.length);
    maxC=Math.max(maxC,crop[0]?crop[0].length:0);
  }
  /* :2 = 二维 [[行],[行]]（单表去包裹）；:3 = 三层 [[[行],[行]]]（表列表） */
  var val=(dim==='2')?out[0]:out;
  return {ok:true,dim:dim,r:maxR,c:maxC,l:out.length,val:val};
}
/* 显性表格数据点的屏幕呈现（v2.6.12）：body 里的表格原文直接交给块级
   渲染器，渲染成真正的表格——与行内形式「显性 = 看得见内容」同一口径，
   不再造 [数据表 R×C] 这类不可读标签。分表边界与 mdeParseTable 同口径
   （空行分块）；某块缺分隔行（只写数据行也合法）时补一行结构行，
   否则 markdown 不认它是表格、整块会退化成段落文字。补的只是 |---|
   结构行，可见字符一个不动 */
function _dpTableSrc(body){
  var lines=String(body).split('\n'),out=[],cur=[];
  function isSep(ln){return /^[|:\-\s]+$/.test(ln)&&/[-:]/.test(ln)&&ln.indexOf('|')>=0;}
  function flush(){
    if(!cur.length){return;}
    var k;
    if(cur.some(isSep)){
      for(k=0;k<cur.length;k++){out.push(cur[k]);}
    }else{
      var nc=splitRow(cur[0]).length||1;
      out.push(cur[0]);
      out.push('|'+new Array(nc+1).join(' --- |'));
      for(k=1;k<cur.length;k++){out.push(cur[k]);}
    }
    cur=[];
  }
  for(var i=0;i<lines.length;i++){
    if(lines[i].trim()===''){flush();out.push('');}
    else{cur.push(lines[i]);}
  }
  flush();
  return out.join('\n');
}
/* MDE 数据点 span（low runner）：data-dp 存 body 原文（URI 编码），
   data-dp-val 存结构化值 JSON（v2.6 三通道：kv/vals）；fail-closed 时
   调用方不产本 span（按普通文本渲染）。隐性 display:none 不占位 */
/* 外部引用值 → 「打开」按钮的判定（v2.8）：值须是不含换行的相对路径，
   形如 <名>.assets/文件 或 assets/文件。**允许空格**——文档名带空格
   （如「MDEditor 使用指南.assets/x.csv」）是常见情形，早先按 \s 一律
   排除，导致这类文档永远不出按钮。存在性与目录白名单由服务端判定 */
function _dpRefPath(val){
  var v=String(val==null?'':val).trim();
  if(!v||/[\r\n\t]/.test(v))return '';
  if(/^(https?:|data:|file:|\/|[A-Za-z]:)/.test(v))return '';
  if(!/(^|\/)([^\/]+\.assets|assets)\/[^\/]+$/.test(v))return '';
  return v;
}
/* v2.9 @@ color 色值解析（行内与块级共用，口径只此一处）：
   简写 11 个（r/g/b/y/o/p/c/m/k/w/a，不分大小写）→ 固定 hex；
   3 / 6 / 8 位十六进制（规定不带 #，误写 # 也容忍）；8 位末两位为透明度，
   按 CSS #RRGGBBAA 渲染（浏览器原生支持）。
   其余一律返回 ''——调用方 fail-closed 保留原文，不猜颜色。 */
var MDE_COLOR_ABBR={r:'#e53935',g:'#43a047',b:'#1e88e5',y:'#f9a825',
  o:'#fb8c00',p:'#8e24aa',c:'#00acc1',m:'#d81b60',k:'#000000',
  w:'#ffffff',a:'#757575'};
function _colorVal(s){
  s=String(s==null?'':s).trim().replace(/^#+/,'').toLowerCase();
  if(!s)return '';
  if(s.length===1)return MDE_COLOR_ABBR[s]||'';
  if(/^[0-9a-f]{3}$/.test(s))return '#'+s[0]+s[0]+s[1]+s[1]+s[2]+s[2];
  if(/^[0-9a-f]{6}$/.test(s)||/^[0-9a-f]{8}$/.test(s))return '#'+s;
  return '';
}
function mdeDpSpan(body,hidden,alias,parsed){
  var pr=parsed||mdeParseBody(body);
  var disp='';
  if(!hidden){
    disp=pr.ok?(pr.dispSimple!==undefined?pr.dispSimple:pr.disp):(body.indexOf('==')>=0?body.slice(body.indexOf('==')+2).trim():body);
  }
  var valAttr='';
  if(pr.ok){
    var v=pr.kvSingle?function(){var s={};s[pr.singleKey]=pr.singleVal;return s;}():pr.val;
    valAttr=' data-dp-val="'+escAttr(JSON.stringify({ch:pr.ch,val:v}))+'"';
  }
  /* 显性外部引用：挂「打开」按钮（隐性没有渲染位置，故不加） */
  var refBtn='';
  if(!hidden){
    var rp=_dpRefPath(disp);
    if(rp){
      refBtn='<button class="mde-ref-open" type="button" data-ref="'+escAttr(rp)+
        '" title="用系统关联程序打开这份副本">打开</button>';
    }
  }
  return '<span class="mde-dp'+(hidden?' mde-dp-hidden" style="display:none"':'"')+
    ' data-dp="'+encodeURIComponent(body)+'"'+
    ' data-dp-alias="'+escAttr(alias||'')+'"'+valAttr+'>'+escapeHtml(disp)+refBtn+'</span>';
}

/* 图题 / 表题参数组解析（v2.10.0）：一套 token 表同时服务两者。
   l/c/r = 水平对齐　t/b = 题注在图/表之上·之下　w/n = 按宽度裁剪·按宽度换行
   s<n> = 间距，单位是题注字号的 n 倍（字是 t 就落到下间距，b 落到上间距）。
   空格（或逗号）分隔、顺序自由；认不出的 token 忽略。
   参数组整体不闭合时正则不匹配 → 语法原文可见（fail-closed 在语法层）。 */
function _figCap(s){
  var o={al:'',side:'',mode:'',gap:''};
  if(!s)return o;
  var t=String(s).split(/[\s,]+/);
  for(var i=0;i<t.length;i++){
    var x=t[i];
    if(!x)continue;
    var ms=/^s([\d.]+)$/.exec(x);
    if(ms){o.gap=ms[1];continue;}
    if(x==='l'||x==='c'||x==='r'){o.al=x;continue;}
    if(x==='t'||x==='b'){o.side=x;continue;}
    if(x==='w'||x==='n'){o.mode=x;continue;}
  }
  return o;
}
function _alCss(a){return a==='c'?'center':(a==='r'?'right':'left');}
/* 独占段的「图片 + 题注」→ <figure>（<p> 不能合法包含 figure）。
   判据：去掉 figcaption 后段落里只剩一个带 data-fig 的 <img>。 */
function _asFigure(h){
  if(h.indexOf('data-fig="1"')<0)return null;
  var noCap=h.replace(/<figcaption[\s\S]*?<\/figcaption>/g,'');
  if(!/^\s*<img\b[^>]*>\s*$/.test(noCap))return null;
  var m=/data-fig-side="([tb])"/.exec(h);
  var g=/data-fig-gap="([\d.]*)"/.exec(h);
  var w=/data-fig-w="([^"]*)"/.exec(h);
  var md=/data-fig-mode="([wn]?)"/.exec(h);
  var pct=(w&&w[1]&&w[1]!=='auto')?w[1]:'';
  var gap=(g&&g[1])?g[1]:'0.3';
  var sty='--figw:'+(pct?pct+'%':'auto')+';--figgap:'+gap;
  /* v2.11.3 水平对齐上移到 figure：带题注时 {N} 宽度归 figure、img 拿
     width:100% 填满——img 自身 margin:auto 恒等于 0，前缀 l/c/r 对图失效
     （只剩题注还在响应）。对齐从 img 的 data-img-align 读出后落到 figure
     内联 margin（c=双边 auto、r=左 auto 右 0、l=默认不写），img 内联与
     data-img-align 原样保留（docx/打印导出仍按它取对齐）。CSS 侧
     .markdown-body figure.mde-fig{margin:.9em 0} 是 shorthand，内联长手
     属性只覆盖左/右，垂直间距不受影响；fill-col 的 margin:0 !important
     优先级更高，拼版场景照旧。 */
  var al=/data-img-align="(center|left|right)"/.exec(h);
  if(al){
    if(al[1]==='center')sty+=';margin-left:auto;margin-right:auto';
    else if(al[1]==='right')sty+=';margin-left:auto;margin-right:0';
  }
  return '<figure class="mde-fig" data-fig-side="'+(m?m[1]:'b')
    +'" data-fig-gap="'+gap
    +'" data-fig-w="'+(w?w[1]:'auto')
    +'" data-fig-mode="'+(md?md[1]:'')+'" style="'+sty+'">'+h+'</figure>';
}
/* v2.13.2 统一块级规则：「块级语法必须独占一行」（前面可以有缩进/列表内缩进，
   但整行除该语法外不得夹带别的文字）→ 按块渲染，而不是并进段落/列表项的
   行内文本流。反过来，想让它退化成行内文字，多打一个空行即可。
   这里给两个判据，列表延续行与主循环共用（两条路径必须同一口径，否则
   「图片在正文里块级、在列表里行内」这种割裂会重现）：
   _isBlockImgLine  整行只有一个图片语法（含可选 "题注" 与 {参数组}）
   _isHrLine        分隔线：去空格后 ≥3 个同一字符，且该字符限 - * _
                    （CommonMark 口径。历史实现不限制字符集，任何同字符
                     ≥3 的行都变横线——占位符 xxxx、省略号。。。都中招；
                     v2.13.2 收紧，附图/列表共用同一判据） */
function _isBlockImgLine(line){
  var s=String(line).replace(/^[ ]+/,'').replace(/[ ]+$/,'');
  if(s.charAt(0)!=='!')return false;
  return /^!\[[^\]]*\]\([^)]+?(?:\s+"[^"]*")?\)(?:\s*\{[^{}\n]*\})?$/.test(s);
}
function _isHrLine(line){
  var s=String(line).replace(/[ ]/g,'');
  if(s.length<3)return false;
  var c0=s.charAt(0);
  if(c0!=='-'&&c0!=='*'&&c0!=='_')return false;
  for(var z=0;z<s.length;z++){if(s.charAt(z)!==c0)return false;}
  return true;
}
/* v2.10.0 表格题注包裹：题注与表格装进同一个 div，先后由 t/b 定。
   这里按 side 直接拼 DOM 顺序（不用 flex —— 表格变成 flex item 会被
   压宽），docx 侧再按 data-tab-side 独立决定段落先后，两边一致。 */
function _wrapTabCap(tbl,c){
  var o=_figCap(c.tok);
  var side=o.side||'t';
  var gap=o.gap||'0.3';
  var capSty=o.al?(' style="text-align:'+_alCss(o.al)+' !important"'):'';
  var capEl='<div class="mde-tabcap" data-tab-cap="1"'+capSty+'>'
    +parseInline(c.txt)+'</div>';
  return '<div class="mde-tblwrap" data-tab-wrap="1" data-tab-side="'+side
    +'" data-tab-gap="'+gap+'" style="--tabgap:'+gap+';">'
    +(side==='b'?tbl+capEl:capEl+tbl)+'</div>';
}
function parseInline(text,noMde){
  var codes=[];
  text=text.replace(/`([^`]+)`/g,function(m,c){codes.push(c);return '@@C'+(codes.length-1)+'@@';});
  /* 反斜杠转义（CommonMark 口径）：\X（X 为 ASCII 标点）→ 占位符，行内语法全部
     处理完再还原为字面 X。文档里展示 \!\[示例\](路径) 这类语法原文必须走这里，
     否则 \! 原样漏出、且 \[..\](..) 仍会被链接正则吃成真 <a>。
     在代码段提取之后做：代码段内反斜杠保持字面，双保险不冲突。 */
  var escs=[];
  text=text.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/g,function(m,c){escs.push(c);return '\x00E'+(escs.length-1)+'\x00';});
  /* MDE 数据点/执行点（low runner，v2.4→v2.6）：必须在 escapeHtml 之前——
     body 需存原文（含 <>& 已转义就还原不回来了）。
     @@ MDE_{a == 3}        显性公共池（显示 == 后的值，无 == 显示原文）
     @@ MDE__{...}          隐性公共池（不渲染，只为执行点提供数据）
     @@ MDE_甲{a == 3}      显性别名池（v2.4.5：只喂 is 甲 的执行点）
     @@ MDE__甲{...}        隐性别名池
     v2.6 六形式：{文本}/{k==v}/{a,b,c}/{k==v,k==v}/行文((...))抽取——
     解析失败（混用/未闭合/键值段无==）fail-closed：原文保留不产 span。
     @@ MDE import dark [is zzz] [{global p}] / from X import fn [is xxx] [{global p}]
     执行点；{global p} = 全局标记（'''p 实例全文收集进 marks，run 返回
     等长列表逐个替换）；执行点自身渲染不可见。
     行内体不含 {} 与换行；跨行数据点/表格型由块级收集处理（见 parseMarkdown） */
  var toks=[];
  /* noMde：执行点结果上下文专用开关（v2.7）。结果文本里的 @@ MDE… 与 '''
     只当普通文字——否则 run 返回的一段文件内容会在预览区反向生成数据点、
     被 _collectBuckets 收进池子，等于"一个 run 的输出能改另一个 run 的输入"。
     正文渲染不传此参数，行为零变化。 */
  if(!noMde){
  text=text.replace(/@@ MDE(_{1,2})([\w\u4e00-\u9fff.-]*)\{([^\n{}]*)\}/g,function(m,u,alias,body){
    var pr=mdeParseBody(body);
    /* fail-closed：原文保留，但必须先进占位符——否则 body 里的 _{…}
       会被下面 v2.6.10 的下标正则吃成 <sub>（@@ MDE_{a, ((b))} → @@ MDE<sub>…</sub>），
       ** / ~~ 同理。占位后原文不受任何后续行内规则影响 */
    if(!pr.ok){toks.push(escapeHtml(m));return '\x00T'+(toks.length-1)+'\x00';}
    toks.push(mdeDpSpan(body,u==='__',alias,pr));
    return '\x00T'+(toks.length-1)+'\x00';
  });
  text=text.replace(/@@ MDE\s+(?:from\s+([\w\u4e00-\u9fff.-]+?)\s+import\s+([\w\u4e00-\u9fff-]+)|import\s+([\w\u4e00-\u9fff.-]+))(?:\s+is\s+([\w\u4e00-\u9fff.-]+))?(?:\s*\{global\s+([\w\u4e00-\u9fff]+)\})?/g,function(m,f,fn,imp,alias,gmark){
    /* global 执行点不可见性走 CSS 类（.mde-run-global{display:none}、
       [data-done=err]/[data-pending] 时可见）——不写内联 style：内联
       display:none 优先级高于一切 CSS，失败态红字会被永久藏住 */
    toks.push('<span class="mde-run'+(gmark?' mde-run-global':'"')+'" data-run-mod="'+escAttr(f||imp)+'" data-run-fn="'+escAttr(fn||'run')+'" data-run-alias="'+escAttr(alias||'')+'"'+(gmark?' data-run-global="'+escAttr(gmark)+'"':'')+' data-run-orig="'+encodeURIComponent(m)+'">'+(gmark?'':'…')+'</span>');
    return '\x00T'+(toks.length-1)+'\x00';
  });
  /* '''标记（v2.6 全局执行）：'''名称 实例 → mde-mark span（runPass
     按 global 声明收集/替换；未声明未替换的保持原文）。行内代码已被
     @@C 占位保护、代码块走块级分支，不经过这里 */
  text=text.replace(/'''([\w\u4e00-\u9fff-]+)/g,function(m,name){
    toks.push('<span class="mde-mark" data-mark="'+escAttr(name)+'">'+escapeHtml(m)+'</span>');
    return '\x00T'+(toks.length-1)+'\x00';
  });
  }
  text=escapeHtml(text);
  /* v2.9 @@ color x{内容}：行内文字着色，色值口径见 _colorVal。
     位置在 escapeHtml 之后：内容此时已转义，插入的 <span> 不会被二次转义，
     且后面的上下标/加粗/斜体/链接规则仍会作用于内容（@@ color r{价 x^{2}}
     出来的是真上标）。
     花括号用配对计数而非 [^}]*：内容可含 ^{2} / _{1} 这类内嵌花括号，
     深度归零处才是闭合点，否则会在第一个 } 处错切。
     到行尾仍未闭合 → 原文保留；内容不跨行；不支持自嵌套（内层按字面露出）。
     noMde 时整条不生效——run 结果文本不该反向生成语法（与 @@ MDE / ''' 同口径）。 */
  if(!noMde){
  /* 用 exec 游标而非 String.replace：replace 的匹配区间只能到 { 为止，
     内容与闭合 } 落在区间外，返回值里再带内容就会重复一遍。这里手动
     拼接——已定界的一段拼进 _cOut，未定的部分原样留在 text 尾部。 */
  var _cRe=/@@\s*color\s+([\w#]{1,8})\s*\{/g,_cPos=0,_cOut='',_cM;
  while((_cM=_cRe.exec(text))!==null){
    var _cSt=_cM.index+_cM[0].length,_cD=1,_cQ=_cSt;
    while(_cQ<text.length){
      var _cCh=text.charAt(_cQ);
      if(_cCh==='\n')break;
      if(_cCh==='{')_cD++;
      else if(_cCh==='}'){_cD--;if(_cD===0)break;}
      _cQ++;
    }
    /* 未闭合（到行尾/文末没归零）或色值非法 → 不做替换，游标继续往后找 */
    var _cCol=(_cQ<text.length&&text.charAt(_cQ)==='}')?_colorVal(_cM[1]):'';
    if(!_cCol)continue;
    _cOut+=text.slice(_cPos,_cM.index)+
      '<span class="mde-color" style="color:'+_cCol+'">'+text.slice(_cSt,_cQ)+'</span>';
    _cPos=_cQ+1;
    _cRe.lastIndex=_cPos;
  }
  if(_cPos>0)text=_cOut+text.slice(_cPos);
  }
  /* v2.6.10：LaTeX 风格上下标，正文直接写、不加 $：
     ^{任意内容} → <sup>、_{任意内容} → <sub>（^{[1]}、^{1}、^{世界之光} 均可）。
     放在 escapeHtml 之后：花括号里的内容此时已转义，带不进 HTML；再经 toks
     占位，后续强调/斜体/链接规则不会碰到里面的字符（否则 _{a} 与 _{b} 之间
     会被 _.._ 斜体规则吃掉）。只认紧跟 { 的写法，缺右花括号、a^b 一律原样；
     要显示字面 ^{1} 写 \^{1}（反斜杠转义在上面已兜住）。 */
  text=text.replace(/\^\{([^{}\n]+)\}/g,function(m,c){
    toks.push('<sup>'+c+'</sup>');
    return '\x00T'+(toks.length-1)+'\x00';
  });
  text=text.replace(/_\{([^{}\n]+)\}/g,function(m,c){
    toks.push('<sub>'+c+'</sub>');
    return '\x00T'+(toks.length-1)+'\x00';
  });
  /* 生成的标签先进占位符：后续强调/加粗等行内语法绝不能触碰属性值
     （否则下划线文件名 20261015_181923_3419.png 会被 _.._ 改写成 <em>，图片必 404）。
     链接只占位开标签，链接文字仍参与行内格式化。 */

  /* 图片宽度+对齐参数：![alt](src){30} / {30c} / {c} → 版面宽度 30% 等比缩放
     + 可选对齐 c=居中 l=左 r=右（单图覆盖排版面板全局图片档）。
     [1-9]\d{0,2} 捕获，>100 钳到 100；对齐后缀独立可选（仅 {c} 也合法）；
     非法整体不进参数组（后缀原样留在正文可见，fail-closed）。
     参数组在 `)` 之外，保存时的路径改写只动括号内路径，天然不触碰后缀。 */
  text=text.replace(/!\[([^\]]*)\]\(([^)]+?)(?:\s+"([^"]*)")?\)(?:\s*\{([1-9]\d{0,2})?([clr])?(?::([^{}\n]*))?\})?/g,function(m,alt,src,title,wpct,algn,captoks){
    /* 对齐内联进 img 自身 style（display:block + margin auto）而非
       p 的 text-align——ts-style 面板档 !important 按源序后置会盖掉
       主 CSS 的 p:has() 选择器规则；img 自身 margin 与 p text-align
       优先级链独立，语法级天然覆盖全局档 */
    var decls=[];
    /* v2.10.0 有题注（"title" 非空）时宽度归 <figure>，img 填满它——
       否则 figure 宽 N% 里 img 再宽 N%，图只剩 N%×N%。无题注维持原
       语义：{N} 直接落在 img 上 */
    var hasCap=!!title;
    var fc=hasCap?_figCap(captoks):null;
    if(wpct)decls.push(hasCap?'width:100%':'width:'+Math.min(parseInt(wpct,10),100)+'%');
    /* !important：面板全局档规则带 !important（同级按源序），内联不带
       important 会被盖（CSS 规范：作者 important > 内联普通）。
       三值全写覆盖而非叠加——全局档 center 会写 margin-left/right auto，
       语法级只写一侧会被合成为"两边 auto"=居中 */
    if(algn==='c')decls.push('display:block !important;margin-left:auto !important;margin-right:auto !important');
    else if(algn==='r')decls.push('display:block !important;margin-left:auto !important;margin-right:0 !important');
    else if(algn==='l')decls.push('display:block !important;margin-right:auto !important;margin-left:0 !important');
    var st=decls.length?(' style="'+decls.join(';')+'"'):'';
    var a=algn?(' data-img-align="'+(algn==='c'?'center':algn==='l'?'left':'right')+'"'):'';
    /* 题注参数桥接成 data-fig-*（class 会在导出内联样式流程被剥掉，
       figure 容器由块级层按这些属性重建）；题注文字取 "title" */
    var figA=hasCap?(' data-fig="1"'
      +' data-fig-side="'+(fc.side||'b')
      +'" data-fig-gap="'+(fc.gap||'0.3')
      +'" data-fig-mode="'+(fc.mode||'')
      +'" data-fig-w="'+(wpct?Math.min(parseInt(wpct,10),100):'auto')+'"'):'';
    var inner='<img src="'+escAttr(src)+'" alt="'+escAttr(alt)+'"'
      +(title?' title="'+escAttr(title)+'"':'')+st+a+figA+'>';
    if(hasCap){
      /* 题注在框内的对齐：单独给了 l/c/r 就用，否则跟随图的水平位置
         （图居中→题注居中，与出版惯例一致） */
      var cal=fc.al||algn;
      inner+='<figcaption class="mde-figcap"'
        +(cal?' style="text-align:'+_alCss(cal)+' !important"':'')+'>'
        +escapeHtml(title)+'</figcaption>';
    }
    toks.push(inner);
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
     数字仅是语法标记不参与显示；无序项不占编号。
     v2.13 断续规则：编号区域只被空行打断——无空行一律延续，不管什么
     内容：普通文本行并入当前项（<br> 连接，与段落渲染同法）；标题/
     围栏/表格/引用/<<<//@@ 块等硬块物理打断列表但不清编号（外层只在
     空行分支清零，编号跨块延续）。嵌套子列表是独立编号区域（seq 从
     0 起）。 */
  var items=[];
  var i=start;
  var cur=null;
  var listOrdered=null;
  while(i<lines.length){
    var line=lines[i];
    if(/^[ ]*$/.test(line)){break;}
    var m=line.match(/^([ ]*)([-+]|[0-9]+\.)([ ]+)(.*)$/);
    if(!m){
      /* v2.13 延续行：非标记非空行并入当前项；硬块起步行除外（物理
         打断，编号区域由外层延续）；无当前项不吞。
         v2.13.2 整行块级：图片独占一行 / 分隔线 → 不再并进 <br> 文本流，
         作为块直接挂在当前项内（图片走 _asFigure 重建 figure，{N c/l/r}
         与题注参数在列表内同样生效——此前缩进/列表内一律退化成行内图，
         宽度位丢失，这是「图片紧贴列表时 {} 失效」的根因）。 */
      if(cur===null){break;}
      /* 硬块白名单先判：<<< 去空格后是三个同字符，会被 _isHrLine 当分隔线，
         顺序颠倒就会把包围块吞成 li 内的两条横线（实测过） */
      if(/^```/.test(line)||/^(#{1,6})[ ]+/.test(line)||/^[ ]*>/.test(line)||
         /^[ ]{0,3}<<</.test(line)||/^[ ]{0,3}@@\s*(begin|end|blank|caption)\b/.test(line)||
         /^@@ MDE(_{1,2})?[\w\u4e00-\u9fff.-]*(:[23])?(\([^()]*\))?\{/.test(line)||
         (line.indexOf('|')>=0&&i+1<lines.length&&/^[ ]*\|?[-|: ]+\|?[ ]*$/.test(lines[i+1])&&lines[i+1].indexOf('-')>=0)){
        break;
      }
      if(_isBlockImgLine(line)){cur.parts.push({b:'fig',v:line});i++;continue;}
      if(_isHrLine(line)){cur.parts.push({b:'hr',v:line});i++;continue;}
      cur.parts.push({b:'t',v:line});
      i++;
      continue;
    }
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
    cur={raw:m[4],ordered:ordered,mark:m[2],children:'',parts:[]};
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
    /* v2.13.2 项内续接：parts 按源序混排「文本续行 / 整行图片 / 分隔线」。
       文本行之间用 <br> 连接（单回车=换行）；块级元素前不加 <br>（块自带
       间距，多一个 <br> 就是凭空多一行）；块之后的文本同样不加。 */
    var tail='',prevBlk=false;
    for(var pz=0;pz<it.parts.length;pz++){
      var pt=it.parts[pz];
      if(pt.b==='fig'){
        var _fh=_asFigure(parseInline(pt.v));
        tail+=(_fh||('<p>'+parseInline(pt.v)+'</p>'));
        prevBlk=true;
      }else if(pt.b==='hr'){
        tail+='<hr>';prevBlk=true;
      }else{
        tail+=(prevBlk?'':'<br>')+parseInline(pt.v);
        prevBlk=false;
      }
    }
    var contHtml=tail;
    var tm=it.raw.match(/^\[([ xX])\][ ]+(.*)$/);
    if(tm){
      var checked=tm[1].toLowerCase()==='x';
      html+='<li class="task"><input type="checkbox" disabled'+(checked?' checked':'')+'> '+parseInline(tm[2])+contHtml+it.children+'</li>';
    } else {
      /* 仅无序项带 marker 样式类（+ 实心 / - 空心）；有序项无 class */
      var icls=it.ordered?'':(it.mark==='-'?' class="u-hollow"':' class="u-solid"');
      html+='<li'+icls+'>'+parseInline(it.raw)+contHtml+it.children+'</li>';
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
   非法形态（{0}/非数字/多余词）→ 整体视为 lang 原样返回、width=0（fail-closed：字面可见不吞错）。
   v2.10.0 图题：```mermaid "图 1　流程"{40l:c t s0.5} —— "…" 为题注（有题注才包装 figure），
   参数组用 : 分段（前图参 / 后题参），与图片 {图参:题参} 完全同一套口径。无 "…" 时
   维持旧正则（含题注引号则整行走新解析），旧文档零变化。 */
function parseFenceLang(raw){
  /* 新形态先行：lang + 可选 "题注" + 可选 {参数}。认出 " 才按图题口径走 */
  var m2=raw.match(/^([A-Za-z][\w-]*)\s*"([^"\n]*)"\s*(?:\{([^{}\n]*)\})?\s*$/);
  if(m2){
    var o={lang:m2[1],width:0,align:'',title:m2[2],cap:null};
    var seg=(m2[3]||'').split(':');
    /* 图参段：数字 + 对齐单字符（同旧口径；非法 token 忽略——图表侧口径比图片宽，
       题注照常生效，不在围栏行上做字面回显） */
    var pm=seg[0].match(/^\s*([1-9]\d{0,2})?\s*([clr])?\s*$/);
    if(pm){
      if(pm[1])o.width=Math.min(100,parseInt(pm[1],10));
      if(pm[2])o.align=(pm[2]==='c')?'center':(pm[2]==='r')?'right':'left';
    }
    o.cap=_figCap(seg[1]||'');
    return o;
  }
  /* 宽度+对齐参数：```mermaid {30} / mermaid{30} / {30c} / {c}（图 {N} 同规矩）。
     对齐进 data-diagram-align（渲染后应用容器）。lang 与 { 可无空格直连 */
  var m=raw.match(/^([A-Za-z][\w-]*)(?:\s*\{([1-9]\d{0,2})?([clr])?\})?\s*$/);
  if(!m)return {lang:raw.trim(),width:0,align:''};
  return {lang:m[1],
    width:m[2]?Math.min(100,parseInt(m[2],10)):0,
    align:m[3]?(m[3]==='c'?'center':m[3]==='l'?'left':'right'):''};
}
/* ---- v2.18.0 @@ begin 容器的层级与嵌套裁决（四族共用） ----
   主链 rank：page 1 < full 2 < fill 3（外→内）。color 不占主链（透明，
   挂在哪层都不改变层级），所以它「随便组合、放哪都行」。
   规矩一（层级）：主链家族只在 rank > 已进入的最内层级（_lv）时才能开启。
   同族进入后 rank == _lv，必然被拒——「自己套自己」就此自动禁止。实测套
   自己会让外层被内层的 end 提前关掉、内层 begin 与末尾 end 直接印在纸面
   （full 套 full：p2 印 @@ begin full{b}、p3 印 @@ end full，只出 1 个
   full-page）；color 不需要自嵌套，行内 @@ color r{文字} 本来就是就近覆盖。
   规矩二（并写顺序）：三者压在同一个 div 上，顺序不影响渲染结果，锁死
   page→full→color 只为唯一写法（不锁则 full page 与 page full 逐字节相同，
   同一份文档两种写法，diff 出噪音、报错也没法指名）；与规矩一的层级同构。
   越界 / 同族 / 顺序错 → 标记行露出、内容照常渲染（fail-closed）。 */
var _LV={page:1,full:2,fill:3};      /* 嵌套层级（外→内），color 不参与 */
var _MGORD={page:0,full:1,color:2};  /* 并写书写顺序，必须单调递增 */
/* 从 @@ begin 之后那段文字里按出现顺序取家族名。只用于判断「是不是自己套
   自己」，不做参数校验（各家族的参数仍由各自分支严格匹配）。 */
function _beginFams(rest){
  var o=[],re=/(page|full|color|fill)\b/g,m;
  while((m=re.exec(rest))!==null){o.push(m[1]);}
  return o;
}
/* 收集 begin/end 之间的内容。teams = 本块已经声明的家族数组。
   所有 begin 行都压栈（fams=家族数组，z=是否与 teams 交集——交集即「自己
   套自己」或同族混入，整对零宽露出）；end 行只弹「栈顶家族含其名」的栈，
   零宽与否跟随栈顶配对的 begin——这样 teams 之外的内层块（如并写
   full+color 里嵌的 fill）也计入深度，fill 里再写 end full 不会提前关掉
   外层块。栈空时遇到 teams 内的 end → 收尾。返回 {inner, closed, next}。 */
function _scanBeginBlock(lines,startIdx,teams){
  var inner=[],stack=[],closed=false,k=startIdx;
  while(k<lines.length){
    var ln=lines[k];
    var bm=/^[ ]{0,3}@@\s*begin\s+([\s\S]*)$/.exec(ln);
    if(bm){
      var fams=_beginFams(bm[1]),dup=false;
      for(var q=0;q<fams.length;q++){
        if(teams.indexOf(fams[q])>=0){dup=true;break;}
      }
      if(fams.length){
        stack.push({f:fams,z:dup});
        inner.push(dup?('\u200b'+ln):ln);k++;continue;
      }
    }
    var em=/^[ ]{0,3}@@\s*end\s+([A-Za-z]+)[ \t]*$/.exec(ln);
    if(em){
      if(stack.length){
        var top=stack[stack.length-1],zw=top.z;
        if(top.f.indexOf(em[1])>=0){stack.pop();}
        inner.push(zw?('\u200b'+ln):ln);k++;continue;
      }
      if(teams.indexOf(em[1])>=0){closed=true;k++;break;}
    }
    inner.push(ln);k++;
  }
  return {inner:inner,closed:closed,next:k};
}
function parseMarkdown(src, _lv, opts){
  _lv=_lv|0;
  var lines=src.replace(/\r\n/g,'\n').replace(/\r/g,'\n').split('\n');
  var html='';
  var i=0;
  var olSeq=0;   /* 编号区域接力计数：v2.13 起只被空行打断（见 parseList 注释） */
  /* <<< 缩进包围块 · 当前位置状态机（v2.1；档位 v2.2.1 起为 px，正文字号基准）：
     只流容器级缩进（px）——空行/标题/围栏/hr/表格清零；顶层段落=正文首行缩进档、
     列表=列表档、引用=引用档；<<< 冻结当前值为块内左边界（块内封闭不更新），
     闭合时 += 块内容器级子块叠加（列表/引用档，取 max）。段内 text-indent 永不进链。 */
  var IPX=(opts&&opts.indents)||(typeof window!=='undefined'&&window.__IND_PX__)||{p:0,quote:0,li:0};
  var curInd=0;
  var pendCap=null;   /* v2.10.0 @@ caption 暂存：只作用于紧随其后的那一个表格 */
  while(i<lines.length){
    var line=lines[i];
    /* v2.10.0 表格题注：@@ caption{l c t n s0.3} 表 1　标题
       必须先于竖线/表格/段落判断消费掉，否则整行会被当普通段落渲染。
       只认「下一行起就是表格」这一种位置——后面不是表格则整行按普通
       文本露出（fail-closed 可见，不静默吞掉用户的字）。 */
    var _capM=/^[ ]{0,3}@@\s*caption\b[ \t]*(?:\{([^{}\n]*)\})?[ \t]*(.*)$/.exec(line);
    if(_capM){
      var _t1=lines[i+1]||'',_t2=lines[i+2]||'';
      if(_t1.indexOf('|')>=0&&/^[ ]*\|?[-|: ]+\|?[ ]*$/.test(_t2)&&_t2.indexOf('-')>=0){
        pendCap={tok:_capM[1]||'',txt:(_capM[2]||'').trim(),at:i+1};
        i++;continue;
      }
    }
    /* v2.13.2 @@ blank{n}：硬控段间空白。n = 正文行数（1 = 一个正文行高，
       可小数，0.1~50 钳制），输出一个只吃高度的空 div。
       两条规矩：
       ① 必须独占一行——紧贴文字时正则不匹配，整行按普通文本露出
          （fail-closed：不猜意图、不吞字）；
       ② 与前后块的段间距**不叠加**——相邻 margin 由 CSS 清零
          （.mde-blank 规则），实际空白恰为 n 行，也压过排版面板的全局
          段间距。高度写内联 style（克隆到分页导出/HTML 导出时随元素带走），
          calc 里乘 --mde-lh 保证行高口径与正文一致。 */
    var _bm=/^[ ]{0,3}@@\s*blank[ \t]*\{([\d.]+)\}[ \t]*$/.exec(line);
    if(_bm){
      var _bn=parseFloat(_bm[1]);
      if(!isNaN(_bn)&&_bn>0){
        _bn=Math.min(_bn,50);
        html+='<div class="mde-blank" data-blank="'+_bn+'" style="height:calc('+_bn+' * var(--mde-lh,1.7) * 1em)"></div>';
        i++;curInd=0;continue;
      }
      /* n=0 / 非正数：不生效，落到普通段落按原文露出 */
    }
    if(/^```/.test(line)){
      var rawLang=line.slice(3).trim();
       var fl=parseFenceLang(rawLang);   /* 图表围栏支持 ```mermaid {30} 版面百分比宽度 + c/l/r 对齐；v2.10.0 再加 "题注"{图参:题参} */
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
        var dHtml='<div class="diagram" data-diagram="'+kind+'"'+(fA?' data-diagram-align="'+fA+'"':'')+(fW?' style="width:'+fW+'%"':'')+' data-code="'+encodeURIComponent(code)+'"><div class="diagram-pending">图表渲染中…</div></div>';
        /* v2.10.0 图题：围栏带 "题注" 时包成与图片同款 <figure.mde-fig>——
           宽度 {N} 归 figure（diagram 撑满 figure），题参 t/b/w/n/s<n> 与图片
           完全同一套；题注对齐未单独给时跟随图的对齐（fA→l/c/r 映射）。
           无 "题注" 时维持原样输出，旧文档零变化。 */
        if(fl.title){
          var fc=fl.cap||{};
          var _fa2=(fA==='center')?'c':(fA==='right')?'r':(fA==='left')?'l':'';
          var cal=fc.al||_fa2;
          var capSty=cal?(' style="text-align:'+_alCss(cal)+' !important"'):'';
          html+='<figure class="mde-fig" data-fig-side="'+(fc.side||'b')
            +'" data-fig-gap="'+(fc.gap||'0.3')
            +'" data-fig-mode="'+(fc.mode||'')
            +'" data-fig-w="'+(fW?fW:'auto')
            +'" data-fig-chart="1" style="--figw:'+(fW?(fW+'%'):'auto')+';--figgap:'+(fc.gap||'0.3')+'">'
            +'<div class="diagram" data-diagram="'+kind+'"'
            +(fA?' data-diagram-align="'+fA+'"':'')
            +' style="width:100%" data-code="'+encodeURIComponent(code)+'"><div class="diagram-pending">图表渲染中…</div></div>'
            +'<figcaption class="mde-figcap"'+capSty+'>'+escapeHtml(fl.title)+'</figcaption></figure>';
        }else{
          html+=dHtml;
        }
      }else{
        html+='<pre><code'+(rawLang?' class="lang-'+rawLang+'"':'')+'>'+escapeHtml(code).replace(/</g,'&lt;')+'</code></pre>';
      }
      curInd=0;
      continue;
    }
    if(/^[ ]*$/.test(line)){i++;olSeq=0;curInd=0;continue;}
    var hm=line.match(/^(#{1,6})[ ]+(.*)$/);
    if(hm){
      var lvl=hm[1].length;
      html+='<h'+lvl+'>'+parseInline(hm[2].trim())+'</h'+lvl+'>';
      i++;curInd=0;continue;
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
        i++;curInd=0;continue;
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
      html+='<div class="ind-blk" style="margin-left:'+left+'px">'+parseMarkdown(inner.join('\n'),_lv)+'</div>';
      curInd=left+Math.max(hasList?IPX.li:0,hasQuote?IPX.quote:0);
      i=j;
      continue;
    }
    /* @@ fill 分栏（v2.3 图片语法，v2.13 泛化为文字/图片任意组合）：
       @@ begin fill{a|b[|c[|d]]} 或 @@ begin fill（无参 = 栏数等分，2~4 栏）
       … @@ end fill。带参：比例为版面宽度百分比（50|50 各半，与图 {50}
       同口径），各值 1-100、和须=100、段数=栏数。空行分栏（连续非空行
       属同栏）——空行在进入解析器前就被分栏消费，栏内天然无空行，
       「空行打断」规则在栏内不触发；每栏整段走完整 markdown 渲染
       （文字/图片/表格/围栏任意组合）。栏内 {N} 失效（CSS fill-col
       覆盖：width:auto/max-width:100%），图片宽度全权由栏比例决定；
       分栏进 <<< 继承链（容器级 margin-left）。编号区域不清零（空行
       才打断，此处空行已被分栏消费）。
       带参段数≠栏数 / 非法值 / 未闭合 → fail-closed（标记与内容按普通
       文本渲染）。 */
    var fm=line.match(/^[ ]{0,3}@@\s*begin\s+fill\s*(?:\{([\d|]+)\})?\s*$/);
    if(fm){
      if(!(_LV.fill>_lv)){
        /* v2.18.0 越界/同族：fill 是主链最内层（rank 3），_lv>=3 时不可再开
           （fill 套 fill、full/page 区里的 fill——full 2、page 1 都推不进
           _lv=3 的位置）。标记行按原文露出，i++ 推进，内容与结束行交主循环
           照常渲染——end 行走孤 end 兜底按原文露出，begin/end 对称可见
           （fail-closed 不吞字；不做块扫描，否则配对的 end 会被当闭合吃掉）。 */
        html+='<p>'+parseInline(line)+'</p>';
        i++;
        continue;
      }
      var _fr=_scanBeginBlock(lines,i+1,['fill']);
      var finner=_fr.inner,fclosed=_fr.closed,fj=_fr.next;
      if(fclosed){
        /* 空行分栏：连续非空行属同栏（栏内可放文字行/图片行/围栏） */
        var cols=[],cur=[];
        for(var c=0;c<finner.length;c++){
          if(/^[ ]*$/.test(finner[c])){
            if(cur.length){cols.push(cur.join('\n'));cur=[];}
          }else{cur.push(finner[c]);}
        }
        if(cur.length)cols.push(cur.join('\n'));
        var ratios=[],okFill=false;
        if(fm[1]!==undefined){
          var parts=fm[1].split('|');
          okFill=parts.length>=2&&parts.length<=4&&parts.length===cols.length;
          var sumR=0;
          if(okFill){
            for(var r=0;r<parts.length;r++){
              var rv=parseInt(parts[r],10);
              if(isNaN(rv)||rv<1||rv>100){okFill=false;break;}
              ratios.push(rv);sumR+=rv;
            }
            if(sumR!==100)okFill=false;
          }
        }else{
          /* v2.13 无参：2~4 栏等分（100 除不尽的余数给末栏） */
          okFill=cols.length>=2&&cols.length<=4;
          if(okFill){
            var base=Math.floor(100/cols.length),rem=100-base*cols.length;
            for(var r2=0;r2<cols.length;r2++){ratios.push(r2===cols.length-1?base+rem:base);}
          }
        }
        if(okFill){
          /* v2.13.3 包围块不吃兄弟块缩进：curInd 此时可能是「上一个块」遗留的
             列表/引用/正文档（列表分支会写 curInd=IPX.li），紧贴列表的
             @@ begin fill 会因此凭空左缩进一档——实测「只有紧跟列表的那一个
             缩进，下一个包围就恢复」（因为 fill 结束写了 curInd=0）。
             fill 是容器级块：外层 <<< 的缩进由 .ind-blk 的 margin 承担，
             内层 fill 相对容器左边界即 0，故不写 margin-left。 */
          var fh='<div class="fill-row">';
          for(var ci=0;ci<cols.length;ci++){
            fh+='<div class="fill-col" style="width:'+ratios[ci]+'%">'+parseMarkdown(cols[ci],_LV.fill)+'</div>';
          }
          fh+='</div>';
          html+=fh;
          i=fj;curInd=0;
          continue;
        }
      }
      /* fail-closed：整块（含标记行）按普通文本渲染 */
      if(fclosed){
        html+='<p>'+parseInline(line)+'</p>';
        var ftxt=finner.join('\n');
        if(ftxt.trim()){html+=parseMarkdown(ftxt,_lv);}
        i=fj;curInd=0;
        continue;
      }
    }
    /* v2.9 @@ begin color x / @@ begin color {x} … @@ end color：块级整块着色。
       与行内 @@ color 分工——块级管「整段/整节」，内容按完整 markdown 渲染
       （标题/列表/引用/图片/表格/公式都走正常分支），内部可再用行内
       @@ color 做局部覆盖（span 内联色 > 父 div 继承色，CSS 就近）。
       色值口径与行内共用 _colorVal（不另立一套）。
       容器用 div 不用 span：里面装的是 p/ul/h3/table，行内元素包块级是非法嵌套。
       不嵌套、不跨缩进层（内层 parseMarkdown 独立递归，与 @@ begin fill 同口径）；
       curInd 不清零——颜色块不改变缩进语义，清了会打断后续 <<< 继承。
       未闭合 / 色值非法 → 标记行按原文、内容照常渲染，结束行不露出。 */
    var cm=line.match(/^[ ]{0,3}@@\s*begin\s+color\s+(?:\{([^}]*)\}|([\w#]+))\s*$/);
    if(cm){
      var cval=_colorVal(cm[1]!==undefined?cm[1]:cm[2]);
      var _cr=_scanBeginBlock(lines,i+1,['color']);
      var cinner=_cr.inner,cclosed=_cr.closed,cj=_cr.next;
      if(cval&&cclosed){
        /* v2.13.3 同 fill：不继承兄弟块缩进（紧贴列表时会被带出一档），
           容器缩进由外层 .ind-blk 承担。color 不占主链（v2.18.0）：层级
           状态 _lv 原样下传，color 块里的主链层级不变；块内再写
           @@ begin color 由 _scanBeginBlock 整对零宽露出（禁同族，
           行内 @@ color 就是就近覆盖，块级自嵌套无意义）。 */
        html+='<div class="mde-color" style="color:'+cval+'">'+
          parseMarkdown(cinner.join('\n'),_lv)+'</div>';
        i=cj;
        continue;
      }
      if(cclosed){
        html+='<p>'+parseInline(line)+'</p>';
        var ctxt=cinner.join('\n');
        if(ctxt.trim()){html+=parseMarkdown(ctxt,_lv);}
        i=cj;
        continue;
      }
    }
    /* v2.13 @@ begin full{t|m|b} / @@ begin full（缺省 m）… @@ end full：
       独占一页块。t=居上 m=居中 b=居下（页内垂直位置，分页导出生效）；
       左右不参数化——块内元素按排版面板既有对齐档走。内容按完整
       markdown 渲染（可嵌 fill/图表/表格/列表，空行在其中保留普通
       打断语义）。预览与 HTML 导出无页概念，按普通块渲染；分页导出
       由 .full-page CSS 撑满页心并按 data-full-pos 垂直定位。
       curInd 不清零、不写 margin-left（页级块与缩进链解耦，继承语义
       与 color 块同口径）；编号区域不清零（空行才打断）。
       参数非 t/m/b（正则不匹配）或未闭合 → 标记行按原文、内容照常
       渲染（fail-closed，结束行按文本露出）。 */
    var um=line.match(/^[ ]{0,3}@@\s*begin\s+full\s*(?:\{([tmb])\})?\s*$/);
    if(um){
      if(!(_LV.full>_lv)){
        /* v2.18.0 越界/同族：full 是主链中层（rank 2），_lv>=2 时不可再开
           （full 套 full、fill 里的 full）。标记行按原文露出，i++ 推进，
           内容与结束行交主循环照常渲染——end 行走孤 end 兜底按原文露出，
           begin/end 对称可见（fail-closed 不吞字；不做块扫描，否则配对的
           end 会被当闭合吃掉、只露 begin 不露 end）。 */
        html+='<p>'+parseInline(line)+'</p>';
        i++;
        continue;
      }
      var _ur=_scanBeginBlock(lines,i+1,['full']);
      var uinner=_ur.inner,uclosed=_ur.closed,uj=_ur.next;
      if(uclosed){
        html+='<div class="full-page" data-full-pos="'+(um[1]||'m')+'">'+
          parseMarkdown(uinner.join('\n'),_LV.full)+'</div>';
        i=uj;
        continue;
      }
      /* 未闭合 fail-closed：标记行按原文，内容照常渲染 */
      html+='<p>'+parseInline(line)+'</p>';
      i++;
      continue;
    }
    /* v2.17.0 @@ begin page{noll|1|i|I} … @@ end page：页区。
       一个区域内的页共用一个页码体系，只作用于分页导出（打印/PDF）：
         noll  区内不印页码（margin box 留空占位，版面高度不变）
         1     阿拉伯数字，本区从 1 重编
         i / I 小写 / 大写罗马，本区从 i / I 重编
       起止两端都强制断页——页码是页级属性，一页只能有一个数字，所以
       一页只属一个区（边界落在页中必然有一方的号是错的）。
       页码不在这里算：输出 data-pn 交给分页填充脚本按页回写，因为
       "第几页"只有 Paged.js 排完版才知道。data-pr-id 区分**不同区域实例**
       （两个相邻的 {1} 区各自从 1 起），由模块级 _pgRegSeq 单调递增生成，
       永不复位——同一次渲染里唯一即可，多渲染几次值变大无害。
       嵌套不支持：内层 begin/end 两行都原样保留为正文（对称，不吞内容）。
       参数非法或未闭合 → 标记行按原文、内容照常渲染（fail-closed）。 */
    var pgm=line.match(/^[ ]{0,3}@@\s*begin\s+page\s*\{([^{}\n]*)\}[ \t]*$/);
    if(pgm){
      var _pgn=(pgm[1]||'').trim();
      if(_pgn==='noll'||_pgn==='1'||_pgn==='i'||_pgn==='I'){
        if(!(_LV.page>_lv)){
          /* v2.18.0 越界/同族：page 是主链最外层（rank 1），_lv>=1 时不可
             再开（页区套页区、full/fill 里的 page）。标记行按原文露出，
             i++ 推进，内容与结束行交主循环照常渲染——end 行走孤 end 兜底
             按原文露出，begin/end 对称可见（fail-closed 不吞字）。 */
          html+='<p>'+parseInline(line)+'</p>';
          i++;
          continue;
        }
        var _pgr=_scanBeginBlock(lines,i+1,['page']);
        var pginner=_pgr.inner,pgclosed=_pgr.closed,pgj=_pgr.next;
        if(pgclosed){
          _pgRegSeq++;
          html+='<div class="page-region" data-pn="'+_pgn+'" data-pr-id="pr'+_pgRegSeq+'">'+
            parseMarkdown(pginner.join('\n'),_LV.page)+'</div>';
          i=pgj;
          continue;
        }
        html+='<p>'+parseInline(line)+'</p>';
        i++;
        continue;
      }
      /* 参数非法：不接管，落到下面普通段落按原文露出 */
    }
    /* v2.18.0 并写：@@ begin page{noll|1|i|I} full{t|m|b} color{X} … @@ end <声明过的任一>。
       三个家族都只是「给同一个容器加属性」，CSS 完全正交，所以能压在**一个**
       div 上——封面「单独一页 + 不写页码」从此一行搞定，不必套两层：
         page  → class page-region + data-pn / data-pr-id（断页 + 页码体系）
         full  → class full-page + data-full-pos（撑满页心 + 垂直定位）
         color → class mde-color + 内联 color（继承色）
       fill **不参与**并写：它要 display:flex 横向分栏，full 要 display:flex
       纵向居中，两种布局意图压进同一个元素必打架；它自带 begin/end，直接
       嵌套即可（@@ begin full 里套 @@ begin fill），一样清楚。
       书写顺序锁死 page→full→color（_MGORD 单调递增校验）：三者压在同一
       div 上渲染结果与顺序无关，锁死只为唯一写法——同一份文档两种写法会
       制造 diff 噪音，报错也没法指名。各带自己的参数（color 允许裸词）。
       同名重复 / 顺序错 / 参数非法 / 未闭合 → 整行按原文露出（fail-closed，
       与四个单家族分支同口径）。
       结束行认**本块声明过的**家族名之一（@@ end page / full / color 等价）：
       一个块只有一个结束位置，写哪个都指向同一处；没声明过的名字不闭合，
       避免张冠李戴。
       嵌套交给 _scanBeginBlock + 递归 rank：内层与容器同族（teams 交集）
       的 begin/end 整对零宽露出；容器之外的块（fill 等）原样收集、递归
       渲染，其内部再写容器家族由 rank 裁决（fill 里写 page/full 被拒）。
       容器主链层级 = 其中 rank 最高的家族（只 page+color→1，带 full→2）：
       容器内 page/full 不得再开（rank 不大于 _lv），fill 照常可开。
       家族数 < 2 不进本分支：单家族由上面四个分支先命中，输出逐字节不变。 */
    var _mgt=line.match(/^[ ]{0,3}@@\s*begin\s+([\s\S]*?)[ \t]*$/);
    if(_mgt){
      var _mgs=_mgt[1],_mgpos=0,_mgl=[],_mgbad=false,_mgm;
      var _mgone=/[ \t]*(page|full|color)\b[ \t]*(\{[^{}\n]*\})?/g;
      while((_mgm=_mgone.exec(_mgs))!==null){
        if(_mgm.index!==_mgpos){_mgbad=true;break;}
        var _mga=null;
        if(_mgm[2]){_mga=_mgm[2].slice(1,-1);}
        else if(_mgm[1]==='color'){
          /* color 允许裸词色值（@@ begin color r）。裸词只能给 color——
             否则 @@ begin full color r 里的 color 会被当成 full 的参数 */
          var _raw=/^[ \t]*([\w#]+)/.exec(_mgs.slice(_mgone.lastIndex));
          if(_raw&&!/^(page|full|color)$/.test(_raw[1])){
            _mga=_raw[1];_mgone.lastIndex+=_raw[0].length;
          }
        }
        _mgl.push({f:_mgm[1],a:_mga});
        _mgpos=_mgone.lastIndex;
      }
      if(!_mgbad&&/[^ \t]/.test(_mgs.slice(_mgpos))){_mgbad=true;}
      if(!_mgbad&&_mgl.length>=2){
        var _mgA={},_mgOk=true,_mgOrd=-1;
        for(var _mi=0;_mi<_mgl.length;_mi++){
          var _mf=_mgl[_mi].f,_ma=_mgl[_mi].a;
          if(_mgA[_mf]!==undefined){_mgOk=false;break;}   /* 同族重复 */
          if(_MGORD[_mf]<=_mgOrd){_mgOk=false;break;}     /* 顺序锁死 page→full→color */
          _mgOrd=_MGORD[_mf];
          if(_mf==='page'){
            if(!(_ma==='noll'||_ma==='1'||_ma==='i'||_ma==='I')){_mgOk=false;break;}
            _mgA.page=_ma;
          }else if(_mf==='full'){
            if(!(_ma===null||_ma==='t'||_ma==='m'||_ma==='b')){_mgOk=false;break;}
            _mgA.full=(_ma||'m');
          }else{
            var _mcv=_colorVal(_ma);
            if(!_mcv){_mgOk=false;break;}
            _mgA.color=_mcv;
          }
        }
        if(_mgOk){
          var _mgTeams=[];
          for(var _mt=0;_mt<_mgl.length;_mt++){_mgTeams.push(_mgl[_mt].f);}
          var _mgr=_scanBeginBlock(lines,i+1,_mgTeams);
          var _mgIn=_mgr.inner,_mgCl=_mgr.closed,_mgK=_mgr.next;
          if(_mgCl){
            var _mgCls=[],_mgAt='';
            if(_mgA.page!==undefined){
              _pgRegSeq++;
              _mgCls.push('page-region');
              _mgAt+=' data-pn="'+_mgA.page+'" data-pr-id="pr'+_pgRegSeq+'"';
            }
            if(_mgA.full!==undefined){
              _mgCls.push('full-page');
              _mgAt+=' data-full-pos="'+_mgA.full+'"';
            }
            if(_mgA.color!==undefined){_mgCls.push('mde-color');}
            /* 容器主链层级 = 其中 rank 最高的家族：只 page+color → 1，
               带 full → 2。容器内同链 begin 由各分支 rank 裁决。 */
            var _mgLv=(_mgA.full!==undefined)?_LV.full:_LV.page;
            html+='<div class="'+_mgCls.join(' ')+'"'+_mgAt+
              (_mgA.color!==undefined?' style="color:'+_mgA.color+'"':'')+'>'+
              parseMarkdown(_mgIn.join('\n'),_mgLv)+'</div>';
            i=_mgK;
            continue;
          }
        }
      }
      /* 不成立（单家族 / 参数非法 / 顺序错 / 未闭合）→ 落到下面普通段落按原文露出 */
    }
     /* MDE 跨行数据点（@@ MDE_{ 或 :N(rxc){ 后行内未闭合 → 收集到 }）：
        ① 普通跨行 = 长文本（形式 1，解析含 (( )) 行文/向量等形式）
        ② :N(rxc){ = 表格型（v2.6）：行内含 | 的行=表格行，空行=分表
           （:3 专属），坐标裁剪见 mdeParseTable */
     var mdeOpen=line.match(/@@ MDE(_{1,2})([\w\u4e00-\u9fff.-]*)(?::([23]))?(\([^()]*\))?\{/);
     if(mdeOpen && line.indexOf('}',mdeOpen.index)<0){
       var dchunks=[line],dclosed=false,dj=i+1;
       while(dj<lines.length){
         dchunks.push(lines[dj]);
         if(lines[dj].indexOf('}')>=0){dclosed=true;dj++;break;}
         dj++;
       }
       if(dclosed){
         var dfull=dchunks.join('\n');
         var dmm=dfull.match(/@@ MDE(_{1,2})([\w\u4e00-\u9fff.-]*)(?::([23]))?(\([^()]*\))?\{([\s\S]*?)\}/);
         if(dmm){
           var dpre=dfull.slice(0,dmm.index),dpost=dfull.slice(dmm.index+dmm[0].length);
           var dout='';
           var dsp=null,dspBlock=false;
           if(dmm[3]){   /* 表格型 */
             var tbl=mdeParseTable(dmm[3],dmm[4],dmm[5]);
             if(tbl.ok){
               var dattrs=' data-dp="'+encodeURIComponent(dmm[5])+'"'+
                 ' data-dp-alias="'+escAttr(dmm[2]||'')+'"'+
                 ' data-dp-val="'+escAttr(JSON.stringify({ch:'vals',val:tbl.val}))+'"';
               if(dmm[1]==='__'){
                 /* 隐性：整块不渲染，只留一个不占位的收集壳（导出时按
                    .mde-dp-hidden 整块剔除） */
                 dsp='<span class="mde-dp mde-dp-hidden" style="display:none"'+dattrs+'></span>';
               }else{
                 /* 显性（v2.6.12）：表格原文照原样渲染成真表格。行列裁剪
                    (RxC) 只作用于 data-dp-val，屏幕显示整张原表 */
                 dsp='<div class="mde-dp mde-dp-block"'+dattrs+'>'+parseMarkdown(_dpTableSrc(dmm[5]),_lv)+'</div>';
                 dspBlock=true;
               }
             }
           }else{
             var dpr=mdeParseBody(dmm[5]);
             if(dpr.ok){dsp=mdeDpSpan(dmm[5],dmm[1]==='__',dmm[2],dpr);}
           }
           if(dsp!==null){
             if(dspBlock){
               /* 表格是块级元素，塞进 <p> 会被 HTML 解析器提前把 p 闭合，
                  生成串与真实 DOM 对不上——前后残留文本各自成段 */
               if(dpre.trim()){html+='<p>'+parseInline(dpre)+'</p>';}
               html+=dsp;
               if(dpost.trim()){html+='<p>'+parseInline(dpost)+'</p>';}
             }else{
               if(dpre.trim())dout+=parseInline(dpre);
               dout+=dsp;
               if(dpost.trim())dout+=parseInline(dpost);
               html+='<p>'+dout+'</p>';
             }
             i=dj;curInd=0;
             continue;
           }
           /* fail-closed：整块按普通段落（含标记行原文） */
           html+='<p>'+parseInline(dfull.replace(/\n/g,' '))+'</p>';
           i=dj;curInd=0;
           continue;
         }
       }
     }
    /* v2.13.2 分隔线与列表内共用同一判据（_isHrLine），两条路径不得分叉 */
    if(_isHrLine(line)){html+='<hr>';i++;curInd=0;continue;}
    if(/^[ ]*>/.test(line)){
      var quote=[];
      while(i<lines.length && /^[ ]*>/.test(lines[i])){quote.push(lines[i].replace(/^[ ]*>[ ]?/,''));i++;}
      html+='<blockquote>'+parseMarkdown(quote.join('\n'),_lv)+'</blockquote>';
      curInd=IPX.quote;
      continue;
    }
    if(line.indexOf('|')>=0 && i+1<lines.length && /^[ ]*\|?[-|: ]+\|?[ ]*$/.test(lines[i+1]) && lines[i+1].indexOf('-')>=0){
      var t=parseTable(lines,i);
      var _tb=t[0];
      if(pendCap&&pendCap.at===i){_tb=_wrapTabCap(_tb,pendCap);}
      pendCap=null;
      html+=_tb;i=t[1];curInd=0;continue;
    }
    if(/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(line)){
      var ind=/^([ ]*)([-+]|[0-9]+\.)/.exec(line)[1].length;
      var lst=parseList(lines,i,ind,olSeq);
      html+=lst[0];i=lst[1];olSeq=lst[2];curInd=IPX.li;continue;
    }
    var para=[];
    while(i<lines.length && !/^[ ]*$/.test(lines[i]) && !/^```/.test(lines[i]) && !/^(#{1,6})[ ]+/.test(lines[i]) && !/^[ ]*>/.test(lines[i]) && !/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(lines[i]) && !/^[ ]{0,3}<<<\s*$/.test(lines[i])
      /* v2.13.2 @@ 家族块（begin/end/caption/blank）紧贴上一行文字时同样终断
         段落——否则"必须独占一行"的块被段落收集器整条吞进 <p>，标记原样
         露出（@@ blank{1} 紧贴正文即中此招）。行内 @@ color / @@ MDE 不在此列
         （它们是真行内语法，本来就可以混在文字里）。 */
      && !/^[ ]{0,3}@@\s*(begin|end|caption|blank)\b/.test(lines[i])
      && !(lines[i].indexOf('|')>=0 && i+1<lines.length && /^[ ]*\|?[-|: ]+\|?[ ]*$/.test(lines[i+1]) && lines[i+1].indexOf('-')>=0)
      /* v2.6：未闭合的 MDE 表格起始行（@@ MDE_x:2(2x2){ 后无 }）终断
         段落收集——否则连续数据点行把表格语法吞进段落漏成明文 */
      && !(/^@@ MDE(_{1,2})?[\w\u4e00-\u9fff.-]*(:[23])?(\([^()]*\))?\{/.test(lines[i]) && lines[i].indexOf('}')<0)){
      para.push(lines[i]);i++;
    }
    /* 上面守卫可能在首行就把本行判死（未闭合的 @@ MDE…{ 起始行）→ para 为空且 i
       未推进；若照旧输出空 <p> 并回到循环，就会永远停在同一行（主线程死锁 = 打开
       文件即卡死，文末未闭合数据点必中）。这里保证每轮至少吃掉一行，该行按普通
       文本 fail-closed 渲染。 */
    if(!para.length){para.push(lines[i]);i++;}
    var _pd=parseInline(para.join('\n'));
    var _fg=_asFigure(_pd);
    html+=_fg?_fg:('<p>'+_pd.replace(/\n/g,'<br>')+'</p>');
    curInd=IPX.p;
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
