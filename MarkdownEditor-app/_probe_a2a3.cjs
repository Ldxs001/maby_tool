const katex = require("./katex/katex.min.js");
const cases = [
  ["binom", "\\binom{n}{k}"],
  ["genfrac", "\\genfrac{(}{)}{0pt}{}{n}{k}"],
  ["dfrac", "\\dfrac{a}{b}"],
  ["tfrac", "\\tfrac{a}{b}"],
  ["left-right", "\\left(\\frac{a}{b}\\right)"],
  ["pmatrix", "\\begin{pmatrix}a&b\\\\c&d\\end{pmatrix}"],
  ["cases", "\\begin{cases}x&x>0\\\\0&x\\le0\\end{cases}"],
  ["overparen", "\\overparen{AB}"],
  ["undertilde", "\\underbar{x}"],
  ["vec", "\\vec{a}"],
  ["dot", "\\dot{x}"],
  ["check", "\\check{x}"],
  ["acute", "\\acute{x}"],
  ["breve", "\\breve{x}"],
];
for (const [n, t] of cases) {
  let ok = true, e = "";
  try { katex.renderToString(t, { throwOnError: true }); } catch (err) { ok = false; e = err.message.slice(0, 70); }
  console.log((ok ? "PASS" : "FAIL") + "  " + n.padEnd(12) + "  " + t + (ok ? "" : "   -> " + e));
}
