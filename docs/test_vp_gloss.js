/* test_vp_gloss.js — Node.js harness for vp_gloss.js
   Run: node market-analysis/web/test_vp_gloss.js
   Tests:
     (a) annotates first occurrence of a known term
     (b) skips a term already followed by （
     (c) returns text unchanged (but HTML-escaped) when lang is 'en'
     (d) only marks FIRST occurrence (not second)
     (e) XSS: raw HTML in input is escaped, not injected
*/
"use strict";

/* ── shim browser globals so vp_gloss.js can load ─────────────── */
let _lang = "zh";
global.localStorage = {
  getItem(k){ return k==="valpha_lang" ? _lang : null; },
  setItem(){}
};
global.window = global;

/* ── load the module ──────────────────────────────────────────── */
require("./vp_gloss.js");
const vpAnnotate = global.vpAnnotate;

/* ── tiny assertion helper ────────────────────────────────────── */
let passed=0, failed=0;
function assert(label, cond){
  if(cond){ console.log("  ✓", label); passed++; }
  else     { console.error("  ✗ FAIL:", label); failed++; }
}

/* ════════════════════════════════════════════════════════════════ */
console.log("\n── (a) annotates first occurrence ──");
_lang="zh";
{
  const out = vpAnnotate("市场VIX今天很高，说明恐慌。");
  assert("output contains vp-term span", out.includes('class="vp-term"'));
  assert("output contains vp-tip span",  out.includes('class="vp-tip"'));
  assert("VIX term appears inside span",  out.includes('>VIX<'));
  assert("explanation present",           out.includes("恐慌情绪"));
}

console.log("\n── (b) skips term already followed by （ ──");
{
  const out = vpAnnotate("今天VIX（市场已说明）很高，VIX再出现。");
  // First "VIX" is followed by （ → skip; annotation should NOT appear around first occurrence
  assert("no vp-term for self-explained term", !out.includes('class="vp-term"'));
  // The raw "VIX" text should still be present (escaped)
  assert("VIX text still present", out.includes("VIX"));
}

console.log("\n── (b2) skips term followed by ASCII ( ──");
{
  const out = vpAnnotate("VIX(fear gauge) is high.");
  assert("no vp-term when followed by ASCII (", !out.includes('class="vp-term"'));
}

console.log("\n── (c) lang=en → return text unchanged (HTML-escaped) ──");
_lang="en";
{
  const out = vpAnnotate("VIX is high today. 波动率 rose.");
  assert("no vp-term span in en mode", !out.includes('class="vp-term"'));
  assert("text still contains VIX",    out.includes("VIX"));
  assert("text still contains 波动率",  out.includes("波动率"));
}

console.log("\n── (d) only FIRST occurrence is annotated ──");
_lang="zh";
{
  const out = vpAnnotate("VIX上升，VIX很高，VIX继续涨。");
  const count = (out.match(/class="vp-term"/g)||[]).length;
  assert("exactly one vp-term span for three occurrences", count===1);
}

console.log("\n── (e) XSS: HTML in input is escaped ──");
{
  const evil = '<script>alert(1)<\/script> VIX is high';
  const out = vpAnnotate(evil);
  assert("raw <script> tag is escaped",  !out.includes('<script>'));
  assert("&lt;script&gt; present",       out.includes('&lt;script&gt;'));
  assert("VIX tooltip still injected",   out.includes('class="vp-term"'));
}

console.log("\n── (f) empty/null input ──");
{
  assert("empty string returns empty",   vpAnnotate("") === "");
  assert("null returns empty",           vpAnnotate(null) === "");
  assert("undefined returns empty",      vpAnnotate(undefined) === "");
}

console.log("\n── (g) term with 波动率 annotated ──");
_lang="zh";
{
  const out = vpAnnotate("今日波动率明显上升，短期风险加大。");
  assert("波动率 annotated", out.includes('class="vp-term"') && out.includes("波动率"));
}

/* ════════════════════════════════════════════════════════════════ */
console.log(`\n${"─".repeat(48)}`);
console.log(`结果: ${passed} passed, ${failed} failed`);
if(failed>0){ console.error("TESTS FAILED"); process.exit(1); }
else         { console.log("ALL TESTS PASSED"); }
