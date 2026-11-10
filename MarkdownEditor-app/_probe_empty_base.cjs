const katex = require("./katex/katex.min.js");
const cases = [
  ["{}^3 单独", "{}^{3}"],
  ["{}_4 单独", "{}_{4}"],
  ["{}^{3}_{4} 单独", "{}^{3}_{4}"],
  ["^{3} 裸", "^{3}"],
  ["{}^{3}X", "{}^{3}X"],
  ["{}^{3}\\sum", "{}^{3}\\sum"],
];
for (const [n, t] of cases) {
  let ok = true, e = "", html = "";
  try { html = katex.renderToString(t, { throwOnError: true }); } catch (err) { ok = false; e = err.message.slice(0, 70); }
  console.log((ok ? "PASS" : "FAIL") + "  " + n.padEnd(14) + "  " + (ok ? "len=" + html.length : e));
}
