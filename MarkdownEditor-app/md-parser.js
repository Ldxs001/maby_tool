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
 *   2. parseMarkdown(src, opts) 增加可选第二参 opts.indents = {p, quote, li}
 *      （容器级缩进档，px）——不传时与原文 100% 一致（默认 {p:0,quote:0,li:0}）。
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
  return '<figure class="mde-fig" data-fig-side="'+(m?m[1]:'b')
    +'" data-fig-gap="'+gap
    +'" data-fig-w="'+(w?w[1]:'auto')
    +'" data-fig-mode="'+(md?md[1]:'')+'" style="'+sty+'">'+h+'</figure>';
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
      var cinner=[],cclosed=false,cj=i+1;
      while(cj<lines.length){
        if(/^[ ]{0,3}@@\s*end\s+color\s*$/.test(lines[cj])){cclosed=true;cj++;break;}
        cinner.push(lines[cj]);cj++;
      }
      if(cval&&cclosed){
        html+='<div class="mde-color" style="color:'+cval+(curInd?';margin-left:'+curInd+'px':'')+'">'+
          parseMarkdown(cinner.join('\n'))+'</div>';
        i=cj;olSeq=0;
        continue;
      }
      if(cclosed){
        html+='<p>'+parseInline(line)+'</p>';
        var ctxt=cinner.join('\n');
        if(ctxt.trim()){html+=parseMarkdown(ctxt);}
        i=cj;olSeq=0;
        continue;
      }
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
                 dsp='<div class="mde-dp mde-dp-block"'+dattrs+'>'+parseMarkdown(_dpTableSrc(dmm[5]))+'</div>';
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
             i=dj;olSeq=0;curInd=0;
             continue;
           }
           /* fail-closed：整块按普通段落（含标记行原文） */
           html+='<p>'+parseInline(dfull.replace(/\n/g,' '))+'</p>';
           i=dj;olSeq=0;curInd=0;
           continue;
         }
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
      var _tb=t[0];
      if(pendCap&&pendCap.at===i){_tb=_wrapTabCap(_tb,pendCap);}
      pendCap=null;
      html+=_tb;i=t[1];olSeq=0;curInd=0;continue;
    }
    if(/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(line)){
      var ind=/^([ ]*)([-+]|[0-9]+\.)/.exec(line)[1].length;
      var lst=parseList(lines,i,ind,olSeq);
      html+=lst[0];i=lst[1];olSeq=lst[2];curInd=IPX.li;continue;
    }
    var para=[];
    while(i<lines.length && !/^[ ]*$/.test(lines[i]) && !/^```/.test(lines[i]) && !/^(#{1,6})[ ]+/.test(lines[i]) && !/^[ ]*>/.test(lines[i]) && !/^[ ]*([-+]|[0-9]+\.)[ ]+/.test(lines[i]) && !/^[ ]{0,3}<<<\s*$/.test(lines[i]) && !(lines[i].indexOf('|')>=0 && i+1<lines.length && /^[ ]*\|?[-|: ]+\|?[ ]*$/.test(lines[i+1]) && lines[i+1].indexOf('-')>=0)
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
