const p=require('./md-parser.js');
let fail=0;
function chk(name,cond,detail){
  if(!cond){fail++;console.log('FAIL',name,'|',detail||'');}
  else console.log('ok  ',name);
}
/* ===== 一、列表断续 ===== */
{
  const h=p.parseMarkdown('1. xxxx\nxxxx\n2. xxxx\n');
  chk('无空行:延续为一个 ol', (h.match(/<ol>/g)||[]).length===1 && (h.match(/<li/g)||[]).length===2, h);
  chk('无空行:文字并入第一项', h.indexOf('<li>xxxx<br>xxxx</li>')>=0, h);
  chk('无空行:第二项仍 li 纯文本', h.indexOf('<li>xxxx</li></ol>')>=0, h);
}
{
  const h=p.parseMarkdown('1. xxxx\nxxxx\n\n2. xxxx\n');
  chk('空行:打断为两个 ol', (h.match(/<ol>/g)||[]).length===2, h);
}
{
  const h=p.parseMarkdown('1. a\n说明段落\n2. b\n');
  chk('延续行并入后同列表延续', (h.match(/<ol>/g)||[]).length===1 && h.indexOf('<li>a<br>说明段落</li>')>=0 && h.indexOf('<li>b</li>')>=0, h);
}
{
  const h=p.parseMarkdown('1. a\n## 标题\n2. b\n');
  chk('编号跨标题延续', h.indexOf('<ol start="2">')>=0 && h.indexOf('<h2>标题</h2>')>=0, h);
}
{
  const h=p.parseMarkdown('1. a\n> 引用\n2. b\n');
  chk('编号跨引用延续', h.indexOf('<ol start="2">')>=0, h);
}
{
  const h=p.parseMarkdown('+ 实心\n延续行\n- 空心\n');
  chk('无序列表延续行并入', h.indexOf('<li class="u-solid">实心<br>延续行</li>')>=0, h);
}
{
  const h=p.parseMarkdown('1. 任务\n- [x] 完成\n');
  chk('任务项延续不破坏', h.indexOf('class="task"')>=0, h);
}
/* ===== 二、fill 泛化 ===== */
{
  const h=p.parseMarkdown('@@ begin fill\n![a](a.png)\n\n![b](b.png)\n@@ end fill\n');
  chk('无参两栏等分', h.indexOf('width:50%')>=0 && (h.match(/fill-col/g)||[]).length===2, h);
}
{
  const h=p.parseMarkdown('@@ begin fill\na\n\nb\n\nc\n@@ end fill\n');
  chk('无参三栏 34/33/33', h.indexOf('width:34%')>=0 && h.indexOf('width:33%')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin fill{70|30}\n## 小节\n文字行\n\n![图](x.png)\n@@ end fill\n');
  chk('文字|图片:70/30', h.indexOf('width:70%')>=0 && h.indexOf('width:30%')>=0, h);
  chk('文字栏出 h2 与 p', h.indexOf('<h2>小节</h2>')>=0 && h.indexOf('<p>文字行</p>')>=0, h);
  chk('图片栏出 img', h.indexOf('<img src="x.png"')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin fill{70|30}\na\n\nb\n\nc\n@@ end fill\n');
  chk('带参段数≠栏数 fail-closed', h.indexOf('fill-row')<0 && h.indexOf('@@ begin fill{70|30}')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin fill{50|50}\n文\n\n![x](x.png)\n@@ end fill\n');
  chk('文字|图片 基础用法', h.indexOf('width:50%')>=0 && h.indexOf('<p>文</p>')>=0, h);
}
/* ===== 三、full 独占页 ===== */
{
  const h=p.parseMarkdown('@@ begin full{t}\n# 标\n\n正文\n@@ end full\n');
  chk('full{t}:data-full-pos=t', h.indexOf('data-full-pos="t"')>=0, h);
  chk('full 内容完整渲染', h.indexOf('<h1>标</h1>')>=0 && h.indexOf('<p>正文</p>')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin full\n内容\n@@ end full\n');
  chk('full 无参缺省 m', h.indexOf('data-full-pos="m"')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin full{b}\n内容\n@@ end full\n');
  chk('full{b}', h.indexOf('data-full-pos="b"')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin full{x}\n内容\n@@ end full\n');
  chk('full 非法参 fail-closed', h.indexOf('@@ begin full{x}')>=0 && h.indexOf('full-page')<0, h);
}
{
  const h=p.parseMarkdown('@@ begin full{m}\n内容\n');
  chk('full 未闭合 fail-closed', h.indexOf('@@ begin full{m}')>=0 && h.indexOf('<p>内容</p>')>=0, h);
}
{
  const h=p.parseMarkdown('@@ begin full{m}\n@@ begin fill{50|50}\n![a](a.png)\n\n![b](b.png)\n@@ end fill\n@@ end full\n');
  chk('full 嵌 fill', h.indexOf('data-full-pos="m"')>=0 && h.indexOf('width:50%')>=0, h);
}
{
  const h=p.parseMarkdown('1. a\n@@ begin full{t}\n页内容\n@@ end full\n2. b\n');
  chk('full 不清编号区域', h.indexOf('<ol start="2">')>=0, h);
}
console.log(fail===0?'\n✅ 行为矩阵全过':'\n❌ '+fail+' 条 FAIL');
process.exit(fail===0?0:1);
