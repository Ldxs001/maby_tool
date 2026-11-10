/* 一次性探针：验证 KaTeX 0.16.21 对公式面板候选命令的支持度。
   只读，不参与打包；跑完即删亦可。 */
const katex = require('./katex/katex.min.js');
const cases = [
  ['右上角标', 'x^{2}'],
  ['右下角标', 'x_{i}'],
  ['左上角标 prescript', '\\prescript{14}{6}{C}'],
  ['四角标 sideset', '\\sideset{_a^b}{_c^d}\\sum'],
  ['四角标 手工', '{}^{a}_{b}X^{c}_{d}'],
  ['根号', '\\sqrt[3]{x+1}'],
  ['分数', '\\frac{a}{b}'],
  ['方框', '\\boxed{x^2}'],
  ['上方标记 overset', '\\overset{\\triangle}{AB}'],
  ['下方标记 underset', '\\underset{n}{\\max}'],
  ['下括 underbrace', '\\underbrace{a+b}_{n}'],
  ['上括 overbrace', '\\overbrace{a+b}^{n}'],
  ['行列式', '\\begin{vmatrix}a&b\\\\c&d\\end{vmatrix}'],
  ['矩阵', '\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}'],
  ['分段函数', '\\begin{cases}x&x>0\\\\0&x\\le0\\end{cases}'],
  ['化学式 ce', '\\ce{H2O}'],
  ['上划线', '\\overline{AB}'],
  ['向量', '\\vec{a}'],
  ['度数', '90^{\\circ}'],
  ['极限', '\\lim_{x\\to0}\\frac{\\sin x}{x}'],
  ['积分', '\\int_{0}^{1}f(x)\\,dx'],
  ['求和', '\\sum_{i=1}^{n}i^2'],
  ['中文 text', '\\text{当}x>0'],
  ['着色', '\\color{red}{x}'],
  ['空白占位', '\\phantom{xx}'],
  ['下划线字符', '\\underline{x}'],
  ['多行 aligned', '\\begin{aligned}a&=b\\\\c&=d\\end{aligned}'],
  ['期望', '\\mathbb{E}[X]'],
  ['偏导', '\\frac{\\partial f}{\\partial x}'],
  ['物理单位', '9.8\\,\\text{m/s}^2']
];
let pass = 0, fail = 0;
for (const [name, tex] of cases) {
  let ok = true, err = '';
  try { katex.renderToString(tex, { throwOnError: true, displayMode: false }); }
  catch (e) { ok = false; err = String(e.message).slice(0, 90); }
  if (ok) pass++; else fail++;
  console.log((ok ? 'PASS' : 'FAIL') + '  ' + name + '  |  ' + tex + (ok ? '' : '  -> ' + err));
}
console.log('\nTOTAL ' + (pass + fail) + ' / PASS ' + pass + ' / FAIL ' + fail);
