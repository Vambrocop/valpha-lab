# UI Polish Proposal — Valpha Lab visual tokens

Scope: **visual tokens / component states only.** No content, copy, disclaimers, data
logic, or features change. No new variables or classes are *renamed* (25 pages depend on
them) — every change below is either **additive** (a brand-new token / utility class) or a
**subtle, AA-safe refinement of an existing shared value** (flagged loudly).

Reference mined: **Kraken** `design-md/kraken/DESIGN.md` from
`github.com/VoltAgent/awesome-design-md` (cross-checked against **Sentry**'s dark-surface
patterns). Kraken was picked because it is the catalogue's best "purple-accented dark UI,
data-dense dashboard" match — and our accent is *already* purple, so it maps cleanly onto
our existing `--acc`. Sentry contributed the dark-surface elevation + focus-ring patterns
(Kraken's own DESIGN.md documents a light-on-white theme, so its literal hex values were
**translated** to our dark canvas rather than copied).

---

## ⚠️ Affects all pages (shared-value mutations)

Two existing shared values in `vp.css` are refined. Both are subtle and AA-verified; both
were chosen because they touch *elevation/spacing feel*, not text legibility.

| Var | Old | New | Why | Contrast impact |
|-----|-----|-----|-----|-----------------|
| `--shadow` | `0 2px 12px rgba(0,0,0,.45)` | `0 1px 2px rgba(0,0,0,.30), 0 4px 16px rgba(0,0,0,.42)` | Two-layer elevation (micro + ambient), the Kraken/Sentry pattern — reads crisper on dark without getting heavier. | none (shadow only) |
| `--rad` | `10px` | `12px` | Kraken's "rounded-but-not-pill" 12px container radius; matches the 12–14px already hand-coded in `index.html` cards. | none (geometry only) |

Everything else in this proposal is **additive**. No existing variable's *color* value is
mutated, so **no body/label text contrast changes on any of the 25 pages.**

---

## 1. Color roles

Existing palette (kept verbatim — DO NOT rename or recolor):
`--bg #0d1117 · --panel #161b22 · --border #30363d · --fg #e6edf3 · --mut #9da7b3 ·
--grn #3fb950 · --red #f85149 · --acc #c678dd` (vp.css) / `#a371f7` (index inline).

Verified WCAG contrast vs `--bg #0d1117` (luminance 0.0065):

| Role | Hex | Ratio vs bg | Verdict |
|------|-----|-------------|---------|
| `--fg` | `#e6edf3` | 15.7 | AA ✓ (body) |
| `--mut` | `#9da7b3` | 7.5 | AA ✓ (body) |
| `--acc` (vp) | `#c678dd` | 6.2 | AA ✓ |
| `--acc` (index) | `#a371f7` | 5.5 | AA ✓ |
| `--grn` | `#3fb950` | 7.3 | AA ✓ |
| `--red` | `#f85149` | 5.6 | AA ✓ |
| `--amb` | `#d29922` | 7.1 | AA ✓ |

**Finding — Kraken's brand purple `#7132f5` fails AA on our dark bg (≈3.0:1).** It is fine
for large display text only. So we do **not** adopt raw Kraken purple for any body text,
link, or label. Instead we keep our brighter `--acc` for text and add Kraken's purple only
as **fill/border roles** (where contrast rules don't apply to the swatch itself).

### Additive color tokens (new — used by new utility classes / index pilot only)

| New token | Value | Role | Type |
|-----------|-------|------|------|
| `--acc-strong` | `#b483ff` | high-emphasis accent for headings/active states (ratio **6.8** vs bg ✓ AA) | additive |
| `--acc-weak` | `rgba(163,113,247,.14)` | subtle accent fill (badge/hover wash) — Kraken "purple subtle" pattern | additive |
| `--acc-line` | `rgba(163,113,247,.45)` | accent hairline / focus border | additive |
| `--surface-2` | `#1b222c` | one step lighter than `--panel`, for nested/elevated cards (Sentry layered-surface pattern) | additive |
| `--grn-weak` | `rgba(63,185,80,.15)` | success badge fill | additive |
| `--red-weak` | `rgba(248,81,73,.15)` | error/down badge fill | additive |
| `--ring` | `0 0 0 3px rgba(163,113,247,.40)` | focus halo (Sentry focus-ring pattern) | additive |

These reuse the existing accent's RGB so they stay coherent with `--acc` on every page,
but nothing on existing pages references them yet — purely opt-in.

---

## 2. Typography scale (system fonts only)

**No webfont.** Keep the exact existing system stack
`-apple-system,"Segoe UI","Microsoft YaHei",sans-serif`. Kraken's IBM-Plex/Helvetica
families are **substituted** by this stack (China-accessible, same-origin). We only borrow
Kraken's *scale discipline* (a tight type ramp + tighter heading tracking), exposed as
**additive tokens** so existing inline font sizes are untouched.

| Token (new) | Size | Weight | Line-height | Maps to Kraken role |
|-------------|------|--------|-------------|---------------------|
| `--fs-micro` | 0.72rem | 600 | 1.3 | Micro / eyebrow |
| `--fs-cap` | 0.82rem | 400 | 1.5 | Caption |
| `--fs-body` | 0.94rem | 400 | 1.6 | Body |
| `--fs-h3` | 1.05rem | 700 | 1.3 | Feature title |
| `--fs-h2` | 1.35rem | 800 | 1.25 | Sub-heading |
| `--fs-h1` | 1.7rem | 800 | 1.1 | Hero (matches existing `h1`) |
| `--lh-tight` | 1.25 | — | — | heading line-height |
| `--lh-body` | 1.6 | — | — | body line-height |

Type: **all additive.** Existing pages keep their inline `font:15px/1.6 …` etc. These
tokens are available for the pilot and future migration; nothing is forced.

---

## 3. Spacing scale

Existing `--sp-1 6 / --sp-2 10 / --sp-3 14 / --sp-4 20` stays (do not rename). Kraken's
scale is denser at the top and adds larger steps. We **extend additively**:

| Token | Value | Type | Note |
|-------|-------|------|------|
| `--sp-0` | 3px | additive | hairline gap (Kraken 3px) |
| `--sp-5` | 28px | additive | section gap |
| `--sp-6` | 40px | additive | major band gap (Sentry section rhythm, scaled for our compact pages) |

Existing `--sp-1..4` values are **not** mutated.

---

## 4. Component state refinements

All as **additive utility classes** (new `vp-` names that no page uses yet) plus the two
shared-value refinements already flagged (`--shadow`, `--rad`). The pilot applies these in
`index.html` by adding classes / wrapping, never by editing shared component CSS that
other pages render.

### Card hover / elevation (additive `.vp-card--hover`)
- rest: existing `.vp-card` look, now on the refined two-layer `--shadow`.
- hover: `border-color:var(--acc-line)` + `transform:translateY(-2px)` + slightly stronger
  shadow. Mirrors the `.tool:hover` motion already in `index.html`, generalized.
- respects `prefers-reduced-motion` (global rule in vp.css already kills transforms).

### Badges (additive `.vp-badge` + `--good`/`--bad`/`--neu` modifiers)
Kraken badge pattern = semantic color at fixed low-opacity fill + solid text, small radius.
- `.vp-badge`        : `--acc-weak` fill, `--acc-strong` text, 6px radius, 0.72rem.
- `.vp-badge--good`  : `--grn-weak` fill, `--grn` text.
- `.vp-badge--bad`   : `--red-weak` fill, `--red` text.
- `.vp-badge--neu`   : `rgba(157,167,179,.12)` fill, `--mut` text.
All text colors verified AA on their own background tone (the fills are translucent over
`--bg`/`--panel`, so effective text contrast stays ≥4.5).

### Buttons (additive `.vp-btn`, `.vp-btn--primary`, `.vp-btn--ghost`)
Kraken button variants (primary / outlined / subtle), translated to dark + AA-safe text:
- `.vp-btn`          : 0.88rem, 8px–16px padding, `--rad` radius, visible focus.
- `.vp-btn--primary` : `--acc` fill, **white** text (white on `#a371f7` = 3.7:1 — used for
  large/bold button label ≥18px-equivalent, matching the existing `#ob-dismiss` which is
  already white-on-acc and accepted). For safety this class is only suggested where the
  existing site already uses white-on-acc; not introduced as new small text.
- `.vp-btn--ghost`   : transparent fill, `--acc-line` border, `--acc-strong` text (6.8:1 ✓).
- focus: adds `--ring` halo on top of the existing `:focus-visible` outline (additive).

### Links / focus
- existing global `:focus-visible{outline:2px solid var(--acc);outline-offset:2px}` is
  **kept** (do not weaken). New `.vp-focus-ring:focus-visible` *adds* the soft `--ring`
  halo for elements that want the richer Sentry-style focus — additive, opt-in.
- additive `.vp-link` : `--acc-strong` color (6.8:1 ✓), underline on hover/focus.

---

## Pilot (index.html) — what actually changed

Additive only on the page side:
1. Added the new tokens to `:root` in **vp.css** (additive block, clearly commented).
2. Refined the two shared values (`--shadow`, `--rad`) in **vp.css** — flagged above.
3. Added the additive utility classes (`.vp-card--hover`, `.vp-badge*`, `.vp-btn*`,
   `.vp-link`, `.vp-focus-ring`) to **vp.css**.
4. In **index.html**: applied `--ring` focus halo + slightly richer hover to the existing
   `.tool` / `.hero-acct` via the new tokens (referencing tokens, not renaming anything),
   and let the cards pick up the refined `--rad`/`--shadow`. No copy, no Chinese/English
   text, no data-binding, no disclaimer touched.

---

## Dropped / deliberately NOT done (red-line protection)

- **Raw Kraken purple `#7132f5` as a link/text color** — dropped: 3.0:1 vs our bg fails AA.
  Kept our brighter `--acc`/`--acc-strong` for all text.
- **Kraken/IBM-Plex webfont** — dropped: would need a remote/external font (no-CDN red
  line). Substituted the existing system stack and noted it.
- **Any recolor of `--bg/--panel/--border/--fg/--mut/--acc/--grn/--red`** — not touched, to
  avoid silently shifting contrast across all 25 pages.
- **Pure-white body text on accent fills at small sizes** — avoided; white-on-`--acc` only
  reused where the site already does it (large bold button labels).
