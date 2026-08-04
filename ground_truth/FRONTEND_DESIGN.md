# Cascade — Frontend Design & Interaction Spec

**Owner:** Ashfaq (Track A). **Implements:** `CASCADE_BUILD_SPEC.md` §9.
**Read before writing any component.**

---

## 1. Design thesis

> **This is an operations console, not a SaaS dashboard.**

The user is an SRE at 3am. The judge is watching a compressed YouTube video.
Both need the same thing: **information density with zero decoration**, where
every pixel of color means something.

Three principles, in priority order:

1. **Color is semantic, never decorative.** Green/amber/red exist *only* to
   carry runbook status. If a color appears anywhere it isn't communicating
   state, delete it. This is what makes the cascade moment land — when cards
   flip red, it reads as *meaning*, not styling.
2. **Identifiers are monospace, prose is sans.** Every rule key, incident ID,
   version number, tool name, and SQL fragment is mono. This single rule does
   more to make the product look like a real ops tool than any other decision.
3. **Only three things animate.** Step rows arriving, the cascade flip, and
   metric numbers counting. Everything else is instant. Restraint *is* the
   aesthetic signal — the absence of motion is why the one moment that moves
   feels important.

---

## 2. Visual system

### 2.1 Color tokens

Status colors are lifted from GitHub Primer's dark palette — battle-tested for
exactly this job (state indication on dark), accessible, and they read as
"engineering tool" rather than "AI product."

```css
:root {
  /* Surfaces — cool near-black, never pure #000 (compresses badly on video) */
  --bg:            #0B0E10;
  --surface:       #14181B;   /* panels */
  --raised:        #1B2024;   /* cards inside panels, inputs */
  --border:        #262C31;
  --border-strong: #333B42;   /* hover, focus rings */

  /* Text */
  --text:          #E8EDF0;
  --text-dim:      #97A3AB;
  --text-faint:    #626E77;   /* never for anything load-bearing */

  /* Accent — the system's own voice: links, focus, active tab, the agent's turn.
     Cyan deliberately: not purple (AI cliché), not green/amber/red (reserved). */
  --accent:        #3ECFD6;
  --accent-dim:    #1F7C82;

  /* Status — SEMANTIC ONLY. Never use these for anything but runbook/task state. */
  --st-candidate:  #7D8590;   /* unproven */
  --st-active:     #3FB950;   /* trusted */
  --st-suspect:    #D29922;   /* quarantined */
  --st-invalid:    #F85149;   /* stale */
  --st-rejected:   #484F58;   /* terminal, + strikethrough */
}
```

### 2.2 Typography

```
Display / UI  →  IBM Plex Sans     (400, 500, 600)
Identifiers   →  IBM Plex Mono     (400, 500)
```

IBM Plex has genuine technical-product heritage and is free via `next/font/google`.
The sans/mono pairing is the identity — do not substitute Inter, Roboto, or
`system-ui` for the display face.

| Use | Size | Weight | Notes |
|---|---|---|---|
| Metric numbers | 48px | 600 | `font-variant-numeric: tabular-nums` — stops jitter during count-up |
| Metric delta | 16px | 500 | |
| Panel title | 13px | 600 | uppercase, `letter-spacing: 0.06em`, `--text-dim` |
| Body | 14px | 400 | |
| Identifiers (mono) | 13px | 400 | rule keys, `INC-1001`, `v2`, tool names |
| Pills / badges | 11px | 500 | uppercase |
| **Absolute minimum** | **12px** | — | YouTube compression destroys anything smaller |

### 2.3 Space, shape, motion

- **Spacing:** 4px base. Use 8 / 12 / 16 / 24 only. Panel padding 16px, internal gaps 12px.
- **Radius:** 6px cards, 4px pills/inputs. **Never ≥12px** — that reads consumer app.
- **Elevation:** borders, not shadows. One shadow allowed, on modals only.
- **Motion:** `140ms ease-out` default. Cascade stagger `60ms`. Count-up `300ms`.
  No spring, no bounce, no scale transforms, no animated gradients.

---

## 3. Layout

```
┌──────────────────────────────────────────────────────────────┬────────┐
│  METRIC BAR   cold │ guided │ Δ% │ hit rate │ counts │ LLM ●  │  [rail]│
├──────────────────────────────────────────────────────────────┤ toggle │
│  ONBOARDING RAIL   ① Run an incident  ② Reuse  ③ Change policy│  (2)   │
├───────────────────────────────┬──────────────────────────────┴────────┤
│  INCIDENT CONSOLE             │  RUNBOOK LIBRARY                      │
│  input + live step stream     │  cards, status, provenance, lineage   │
├───────────────────────────────┼───────────────────────────────────────┤
│  POLICY PANEL                 │  OPS COPILOT                          │
│  rules, params, impact preview│  chat → table + generated SQL         │
└───────────────────────────────┴───────────────────────────────────────┘
```

**The 2×2 grid is sacred.** Every extension goes into the **right rail** (a
320px collapsible drawer holding Approvals + Insights) or into a **modal**
(dry-run preview, postmortem viewer, episode detail). Adding a fifth or sixth
grid cell would destroy the "one feature that shines" clarity the spec's D8
depends on.

- Desktop ≥1280px: as drawn. Panels scroll internally; the page itself never scrolls.
- 768–1280px: 2×1 columns, panels stack in pairs.
- <768px: single column, rail becomes a full-screen overlay.

---

## 4. Onboarding — the rail that is also the demo script

**The single highest-leverage component in the app.** It solves three problems
at once: a first-time user knows what to do, a judge reproduces the README's
5-minute tour without reading it, and you get a rehearsed demo path.

A horizontal strip of three numbered steps directly under the metric bar.

| Step | Label | Sub-label (one line, `--text-dim`) | Action when clicked |
|---|---|---|---|
| ① | **Run an incident** | "Watch the agent solve it from scratch." | Fills console input with `Remediate INC-1001`, focuses it, pulses the Run button once |
| ② | **Reuse what it learned** | "Same class of problem — now it has a runbook." | Unlocks after ① completes. Fills `Remediate INC-1002` |
| ③ | **Change a policy** | "Watch every stale runbook get quarantined." | Unlocks after ②. Scrolls to Policy Panel, highlights the `incident.rollback_window` row |

**States:** `locked` (dim, no pointer) → `available` (accent border, clickable)
→ `running` (accent, animated 2px underline) → `done` (check icon, `--st-active`, dim text).

**Persistence:** completion in `localStorage`. Once all three are done the rail
collapses to a 32px strip: `Tour complete · Replay tour · Reset demo`.
"Reset demo" calls `POST /api/admin/reset` (admin token required) and clears the flag.

**Copy rules:** no exclamation marks, no "Welcome!", no emoji, no confetti.
The tone is a colleague pointing at a screen, not an onboarding wizard.

---

## 5. Component interaction specs

### 5.1 MetricBar (always visible — the demo money-shot)

- **Cold** and **Guided** as two 48px numbers side by side (avg seconds and avg steps), with a `Δ −78%` chip in `--st-active` between them.
- Then, smaller: retrieval hit rate · status counts (5 dots with numbers) · LLM health dot.
- **Behavior:** every value animates with a 300ms count-up when `metrics.tick` arrives. Tabular numerals mandatory.
- **Empty state:** dashes `—`, not zeros. Zeros imply a measurement; dashes imply "not yet."
- **LLM degraded:** the dot turns `--st-suspect` and a one-line strip appears: `LLM degraded — new tasks are queued.` Never a modal, never a red error.

### 5.2 IncidentConsole

- **Input:** single line, mono placeholder `Remediate INC-1001`. Enter submits. Disabled while a task runs, with the button reading `Running…`.
- **Mode badge** (appears the moment the mode is known): `Search` icon + "Exploring" in `--text-dim`, or `Zap` icon + "Runbook · rollback-bad-deploy v1" in `--accent`. **Use lucide icons at 14px, never emoji.**
- **StepStream** — the visual heart of the cold-run segment. One row per tool call:
  ```
  03   check_remediation_eligibility   incident_id=INC-1001, action=rollback   ✓ 142ms
  ```
  index (mono, `--text-faint`) · tool (mono, `--text`) · args summary (mono, `--text-dim`, truncate with ellipsis at container width) · result badge · duration (mono, right-aligned).
  Rows slide in from 8px below over 120ms as SSE events arrive. The container auto-scrolls only if already at the bottom.
- **Interrupt banner:** slides down above the stream, `--st-suspect` left border:
  `Policy changed mid-flight — re-planning under the new rules.` Stays until the task resolves.
- **History:** last 10 tasks, one line each: time · input (truncated) · outcome chip.
  Chips: `remediated` (`--st-active`), `escalated` (`--st-active` **outline** — it is a success, per spec §5.4), `failed` (`--st-invalid`), `interrupted` (`--st-suspect`).

### 5.3 RunbookLibrary

- **Card (collapsed):** name + `v1` (mono pill) · status pill · confidence bar (3px, colored by status) · `12 uses · 10 ✓ · 2 ✗` in mono.
- **Status pill:** colored dot **plus text label** — never color alone (accessibility, and color survives video compression worse than text).
- **Click → expands inline** (not a modal — modals break the cascade view):
  - **Steps** — numbered, mono tool names
  - **Preconditions** — plain sentences
  - **Provenance** — the money detail:
    ```
    ● incident.rollback_window  v1   step 2: eligibility gate
    ```
    The leading dot is `--st-active` when fresh, `--st-invalid` when stale.
    **These dots are what flip during the cascade** — they are the visible proof
    that staleness is derived from provenance, not guessed.
  - **Lineage** — `v1 → v2` chips, clicking scrolls to the other version
  - **Actions** — `Re-learn` (only on invalidated), `View episodes`
- **Suspect cards** carry a tooltip on the amber pill:
  *"Quarantined pending re-check — a related policy changed."*
  This is essential: during the demo, *every* same-domain card goes amber, and
  without this the audience reads it as a bug instead of a feature.
- **Failed compiles:** collapsed section at the bottom, count in the header.

### 5.4 PolicyPanel

- **Rule row:** key (mono, `--text`) · `v1` pill · body text (`--text-dim`) · params form.
- **Param inputs** are typed from the per-rule schema (number input for `hours`, `min_tier`).
- **ImpactPreview** appears inline the moment a param field receives focus:
  `3 active runbooks depend on this policy` — with the names listed beneath in mono.
  Deterministic SQL, no LLM, instant. If zero: `No runbooks depend on this yet.`
- **Save** → **confirmation dialog** (MVP) / **dry-run modal** (extension):
  - Title: `Change incident.rollback_window to 4 hours?`
  - Two columns: **Runbooks that will be quarantined** (list with current status) and **Running tasks that will be interrupted** (list with elapsed time)
  - Buttons: `Cancel` · `Commit change` (accent, not red — this is a normal admin action, not a destructive one)
- **History drawer** per rule: every version with `valid_from`/`valid_to` and who changed it.

### 5.5 OpsCopilot

- Chat input, one exchange at a time (no long history — this is an analytics tool, not a chatbot).
- **Answer layout, in this fixed order:** result table → collapsible `Generated SQL` (mono, open by default the first time so judges see it immediately) → fixed footer in `--text-faint`:
  *"Exploratory — generated SQL shown above; verify before acting."*
- Refusals render as a plain one-line message, never a red error card.
- **Suggested prompts** as three clickable chips when empty:
  `Why did rollback runbooks fail this week?` · `Summarize the last 20 audit events` · `Which policies changed most recently?`

### 5.6 Right rail (extensions)

Toggled from a button in the metric bar carrying a count badge. Two stacked sections:

- **Approvals** — incident context, the action awaiting approval, the confidence score and why it fell below the bar, then `Approve` / `Reject` (reject opens a one-line reason field). Arrives live via `approval.requested`.
- **Insights** — small cards: *"`high_error_rate` on svc-search recurred 4× in 7 days."* CTA `Review policy →` deep-links into the Policy Panel **with the suggested params pre-filled** and the field focused. That deep-link is journey step 7 and the thing that makes the loop feel closed.

---

## 6. The cascade choreography (the wow moment — specify it, don't improvise it)

This is the 50 seconds the whole submission is judged on. Timings from the
moment `Commit change` is clicked:

| t | What happens |
|---|---|
| 0ms | Dialog fades out (100ms) |
| 50ms | Toast, bottom-right: `Policy incident.rollback_window → v2 · cascading…` |
| 100ms | The rule row's version pill flips `v1` → `v2` |
| 150ms | Running task's **interrupt banner** slides down in the console |
| 200–500ms | **Dependent runbook cards flip to invalidated, staggered 60ms apart.** Each: border → `--st-invalid`, pill → `invalidated`, and its provenance dot for that rule turns red with a single 200ms pulse |
| 500–800ms | Same-domain non-dependent cards go **amber (suspect)**, same stagger |
| ~900ms | Metric bar status counts animate to their new values |
| ~2s | Interrupted task resumes and completes under the new policy |
| <60s | **v2 card slides in at the top of the library**, lineage chip `v2 ← v1` |

**The 60ms stagger is the entire trick.** Flipping all cards simultaneously
reads as a page repaint; flipping them in sequence reads as a *cascade
propagating through a dependency graph* — which is literally what is happening.
Keep it subtle: no scale, no bounce, no color-cycling. Border and pill only.

---

## 7. States — specify all three for every panel

| State | Rule |
|---|---|
| **Empty** | A sentence explaining what will appear and how to make it appear. Never an illustration, never a cartoon, never "Nothing here yet 🤷". Console: *"No incidents worked yet. Try `Remediate INC-1001`."* Library: *"No runbooks yet — the agent writes them after it resolves an incident successfully."* |
| **Loading** | Skeleton blocks matching the real content's shape, on first paint only. Never a centered spinner. Subsequent updates arrive via SSE and should never show a loading state. |
| **Error** | Inline, one line, in the panel where it happened. Never a modal, never a toast for a panel-scoped failure. SSE disconnect: a thin strip at the top of the page — *"Live updates disconnected — reconnecting…"* — that removes itself on reconnect. |

---

## 8. Built for video (do not skip this)

The demo will be watched as a compressed 1080p YouTube stream, possibly on a phone.

- Record at **1920×1080** with browser zoom at **110–125%**.
- **Nothing below 12px**, and nothing important in `--text-faint`.
- Status is **never color-only** — every pill has a text label. Compression mangles small color patches; it doesn't mangle words.
- Avoid pure white on pure black — our `#E8EDF0` on `#0B0E10` is chosen for this.
- Metric numbers at 48px are readable on a phone. Keep them that big.
- **Test before the real recording:** export a 30-second clip, upload as unlisted, watch it on your phone. Fix whatever you can't read.

---

## 9. Accessibility floor (cheap, and judges notice)

- Every status conveyed by **color + text**, never color alone.
- Focus rings on all interactive elements: `2px solid var(--accent)`, `outline-offset: 2px`.
- `aria-live="polite"` on the step stream and the toast region.
- Full keyboard path for the demo: Tab to input → Enter → Tab to rail. The whole tour must be completable without a mouse.
- Body text contrast ≥ 4.5:1 (`--text` on `--surface` passes; `--text-faint` does not — use it only for decoration).

---

## 10. Anti-slop checklist — never ship any of these

- ❌ Purple/violet gradients (the single most recognizable AI-generated tell)
- ❌ Inter, Roboto, or `system-ui` as the display face
- ❌ Emoji as UI iconography (lucide icons at 14–16px instead)
- ❌ The words "AI-powered", "Magic", "Smart", "Intelligent" anywhere in the UI
- ❌ Glassmorphism, backdrop blur, animated gradient borders
- ❌ `rounded-2xl` consumer-app card styling
- ❌ Drop shadows for elevation (borders only — one shadow, on modals)
- ❌ Stock illustrations or cartoon empty states
- ❌ Centered hero text with a gradient headline
- ❌ A color that doesn't mean anything

**The test:** screenshot any panel and ask *"could this be a screenshot of
Linear, Sentry, or a Grafana panel?"* If yes, ship it. If it looks like a
landing page, delete the decoration.

---

## 11. Build order (maps to `WORKFLOW.md` §5)

| Week | Ship | Runs on |
|---|---|---|
| 1 | Design tokens, app shell, MetricBar, IncidentConsole + StepStream, SSE hookup, onboarding rail (steps locked) | Stub data (`CASCADE_STUB_MODE=true`) |
| 2 | RunbookLibrary + cards + provenance + lineage; MetricBar wired to real `/api/metrics`; onboarding steps ① and ② live | Real engine |
| 3 | PolicyPanel + impact preview + confirm dialog; **cascade choreography**; interrupt banner; toasts; onboarding step ③ live | Real engine |
| 4 | OpsCopilot; right rail (approvals + insights); dry-run modal; postmortem viewer; deploy to Amplify | Live HTTPS |
| 5 | Empty/loading/error state pass · video-legibility pass · a11y pass · **freeze** | — |

**Week 1 rule:** build the entire shell against stub data before the engine
exists. If the UI can't be demoed on Day 3 with fake data, the stub contract
(`WORKFLOW.md` §2) isn't being used properly.

*End of frontend spec.*
