# Pulse Surveys — Design Brief

## What this is

A weekly course feedback tool that lives inside a university LMS. Every week, students answer five quick questions about each course. Instructors get a Monday report with ratings, workload data, anonymous comments, and an AI summary; they publish a short response; students then see the aggregate results and that response. Academic leadership sees roll-ups across their span. The product's entire value rests on two feelings the UI must produce: **students must feel safe** (responses are confidential) and **instructors must feel fairly treated** (data has context, criticism is handled with dignity).

Tone: institutional but warm. Trustworthy, calm, uncluttered. Not corporate-SaaS glossy, not gamified. Think "well-designed university system people are surprised doesn't suck."

## Hard constraints

- **Runs inside an LMS iframe** for students and instructors: assume a constrained viewport (~1000px wide or less, variable height), no reliance on browser chrome, no top-level nav bar taking vertical space. Leadership and admin views also open as full browser pages.
- **Accessibility: WCAG 2.2 AA.** Everything keyboard-operable; charts need accessible alternatives; the workload slider must be keyboard-adjustable with a visible numeric readout.
- Students on phones are a primary case for the survey itself. Reports and dashboards are desktop-first but must degrade gracefully.

## Roles and their screens

### 1. Student
- **Weekly survey** (the highest-traffic screen in the product; must take under 90 seconds):
  1. Likert 1–5: "This week, my instructor supported my learning."
  2. Free text "why" — becomes **required** when the rating above is 1 or 2 (the field should visibly change state to explain this)
  3. Likert 1–5: "This week, the course materials and activities supported my learning."
  4. Free text "why" — same conditional-required behavior
  5. Hours spent this week: slider, 0–40 in half-hour steps, live numeric readout
- **Inline validation state:** if a comment is too thin ("it was okay") the system bounces it immediately with a friendly explanation that participation credit requires a substantive answer. Design this state; it must feel like coaching, not rejection.
- **Results view** (after the instructor responds): my section's rating distributions, the published comments, and the instructor's response displayed prominently — the response is the emotional payoff of the whole loop. Students see NO comparison lines, NO other sections, NO university data.
- Closed/missed-week and not-yet-open states.

### 2. Instructor
- **Monday report** (the make-or-break screen), per section:
  - Rating trend chart with **three overlaid lines**: this section, "comparable courses" benchmark, university. Must stay legible with three lines; benchmark lines are context, section line is the hero.
  - This-week rating distributions (two 1–5 histograms)
  - Workload: section median + mean vs. benchmark and university
  - Response rate and validity rate
  - Comment list, randomized order, no timestamps, no identities anywhere
  - AI summary block per comment stream (clearly labeled as AI-generated)
  - **Small-N state:** when fewer than 5 responses, raw comments are hidden and replaced by an explanatory note + summary only. Design this state explicitly.
- **Moderation:** AI-flagged comments (harmful / privacy / nonsense) appear collapsed with the flag reason; one click excludes a flagged comment from what students will see. Excluding an *unflagged* comment demands a typed reason and shows a notice that the exclusion is logged and visible to the Lead Faculty. That friction is intentional — design it as deliberate, not punitive.
- **Response composer:** write a response; buttons for "Draft with AI" (generates an editable draft from the week's data) and a coaching pass that annotates the draft with advisory suggestions (tone, defensiveness, singling students out). Suggestions are dismissible; publishing is always a human act. If the course requires a response, show the hold status ("students see nothing until you publish") and the reminder timeline.

### 3. Lead Faculty (also: Chair, Dean, VP — same pattern, widening scope)
- **Roll-up dashboard:** aggregate trends, workload, response rates across their sections/courses/departments; drill-down navigation along the hierarchy (course set → course → section).
- Per-course-set **policy toggle**: response required on/off.
- **Exclusion log** view (which instructors excluded what, with reasons).
- **Respond-on-behalf** flow for a delinquent instructor — visually attributed to the Lead Faculty, never impersonating the instructor.
- Comparison-set management: define named benchmark sets (courses must match term length and level; the UI should make invalid combinations impossible rather than error on them).

### 4. Care staff (Office of Community Standards)
- **Threat/self-harm queue**, deliberately separate in look and feel from everything else — quiet, serious, minimal. List of flagged comments with section and week. Author identity is hidden behind an explicit "re-identify" action that requires a typed reason and warns that access is audit-logged. Disposition tracking (actioned / false positive / resolved).

### 5. Admin
- Observability console: LTI launch health, background job status, AI usage/spend, classifier spot-review panel.
- Configuration: term calendar, survey window timing, thresholds, org hierarchy management, LMS registration. Dense-but-navigable settings design; function over charm.

## Visibility rules the UI must make impossible to violate

- Student identity never appears on any instructor or leadership screen, including exports.
- Students never see benchmark/university lines or other sections' data.
- Comments never display with timestamps or in submission order.
- Below 5 responses: no raw comments, summary only, with an honest explanation of why.
- Threat/self-harm content appears only in the Care queue, nowhere else.

## Component inventory (reusable primitives worth designing once)

Likert input · conditional-required text area with validation states · workload slider with readout · three-line trend chart · 1–5 distribution histogram · comment card (with flag/collapse/exclude states) · AI-content label · AI draft/coaching annotation UI · small-N notice · hold-status banner · hierarchy drill-down navigation · audit-warning modal (re-identify) · policy toggle with consequence text

## Out of scope for design

Backend, LTI mechanics, email templates, MCP. Don't design login screens beyond a simple OIDC redirect page — LMS users arrive already authenticated.

## Suggested prompting order in Claude Design

1. Instructor Monday report (hardest layout; establishes chart language and comment cards)
2. Student survey + validation states (highest traffic; establishes form language)
3. Student results view (reuses chart language minus benchmarks)
4. Response composer with AI draft/coaching
5. Leadership roll-up dashboard (reuses charts at aggregate scale)
6. Care queue (distinct, quiet visual register)
7. Admin console last

## Aesthetic direction

**Concept: the field log.** The Monday report is a naturalist's weekly observation of a living course — measured, patient, term-long. Everything below derives from that: bookish type, botanical-ink palette, instrument-style numerals, and one signature motif (the pulse line) used with discipline. The register is "university press meets lab instrument," not corporate SaaS.

### Anti-slop guardrails (hard rules)

- No Inter, Roboto, Arial, Lato, or system font stacks anywhere. (Canvas chrome is Lato — the type contrast is how the tool reads as its own considered thing inside the host.)
- No cream-and-terracotta, no dark-mode-with-acid-accent, no purple-to-blue gradients, no glassmorphism, no 16px+ blobby border radii, no emoji as iconography, no centered hero card with a big number and a gradient.
- Interactive elements never use Canvas blue (#0374B5) — the host owns that color; borrowing it confuses what belongs to whom.
- One signature motif, everywhere; zero other decoration.

### Palette

Cool paper and botanical ink — deliberately outside both the warm-cream AI cluster and LMS blue.

| Token | Hex | Role |
|---|---|---|
| `--chalk` | `#F6F8F4` | App background (faint green-white; also visually seams the iframe against Canvas's pure white) |
| `--paper` | `#FFFFFF` | Cards and input surfaces |
| `--spruce` | `#1E3932` | Ink: body text, primary buttons, chart axes |
| `--spruce-60` | `#5B7269` | Secondary text, muted labels |
| `--hairline` | `#DCE4DD` | 1px borders, dividers |
| `--marigold` | `#DFA320` | Signature accent: the section pulse line, selected states (never body text on white, never the focus ring — 2.2:1 against paper, under the 3:1 non-text floor) |
| `--marigold-deep` | `#8F6A10` | Text-safe marigold (links, small accents, the focus ring — 4.6:1 on chalk, 5.0:1 on paper) |
| `--madder` | `#A93F32` | Flags, destructive, required-state — reserved so it always means "attend to this" |
| `--mist` | `#93A5A0` | Benchmark + university lines, disabled states |

Semantic mapping in charts: section line = marigold, solid, 2.5px, rounded caps, small dot on current week. Benchmark = mist, dashed. University = mist at 50%, dotted. The hero is unmistakable at a glance; context recedes.

### Typography

Three faces, three jobs (all on Google Fonts, so prototypes and production match):

- **Display — Literata** (600/700): headings, the instructor-response block, report title. A book face designed for long reading; carries academic credibility without costume. Tight leading, modest sizes — think chapter heads, not posters.
- **Body — Schibsted Grotesk** (400/500): all UI text. Humanist, slightly newsy, warm at small sizes, nothing like Inter's neutrality.
- **Data — Spline Sans Mono** (400/500): every number, axis label, week eyebrow ("WK 07 / 12"), timestamps, rates. Tabular figures give charts and stats an instrument feel and quietly signal "this is measurement."

Base 16px body inside the iframe; type scale 13 / 16 / 20 / 25 / 31. Eyebrows in Spline Sans Mono, 13px, letterspaced +0.08em, spruce-60.

### Layout

- **Week-first structure.** Every student/instructor screen opens with the mono eyebrow ("WK 07 / 12 · closes Sun 11:59 PM") — the term's rhythm is the product's spine, so the layout states it before anything else. No decorative numbering elsewhere; the week number is the only number that earns eyebrow treatment.
- Reports: single reading column (~720px) with charts allowed to break out wider; no dashboard-grid-of-cards. Comment list as a quiet single column of cards with hairline borders, 8px radius, no shadows beyond `0 1px 2px rgba(30,57,50,.06)`.
- Leadership dashboards may use a two-pane pattern (hierarchy tree left, content right) — density is fine there; the reading-column rule is for report and survey surfaces.
- Radius scale: 4px inputs, 8px cards. Nothing rounder — the print-adjacent squareness is part of the register.

### Signature motif: the pulse line

A single hand-tuned line with rounded caps and a terminal dot. It appears as: the mark in the header; a short divider under report H1s; the section trend line itself; the loading state (a dot that beats gently); and the empty state ("No responses yet this week" over a flat line that lifts into a pulse when the first response arrives). One motif carrying brand, data, waiting, and emptiness — nothing else decorates.

### Motion

Purposeful, brief, and all disabled under `prefers-reduced-motion`. Micro-interactions 150–220ms ease-out; one 600ms signature moment per screen, never more.

- **Report load:** the marigold section line draws on left-to-right (stroke-dashoffset, 600ms), benchmark lines fade in after — the week's story literally arrives. Once per visit.
- **Likert select:** the chosen dot beats once (scale 1 → 1.12 → 1, 180ms) — the pulse motif at fingertip scale.
- **Conditional-required reveal:** when a 1–2 rating is chosen, the why-field's border warms to marigold and its helper text slides down 4px with fade (180ms). Marigold, not madder — it's an invitation, not an error.
- **Validity bounce:** the too-thin-comment message enters the same way; the field does not shake. Nothing in this product shames.
- **Workload slider:** readout ticks numerically while dragging; on release, settles with a 120ms ease.
- **Publish response:** the composed card rises 8px and settles as the hold banner (if any) dissolves — the loop visibly closes.
- **Flagged-comment expand:** height ease 200ms; the flag reason chip stays fixed so the eye keeps its anchor.
- **Care queue:** no motion at all. Stillness is the design.

### Components and CSS architecture

- All tokens above as CSS custom properties in one `tokens.css`; components consume tokens only — no raw hex in component styles. Spacing on a 4px scale; a `--space-*` and `--text-*` ramp.
- Focus visible everywhere: 2px deep-marigold ring (`--marigold-deep` — the accent marigold fails SC 1.4.11's 3:1 on both grounds), 2px offset, on every interactive element (WCAG 2.2 AA is a floor, not a feature).
- The primitives listed in the component inventory (Likert input, workload slider, trend chart, comment card, AI-content label, small-N notice, hold banner, audit-warning modal, drill-down nav) are each built once as a reusable component with variants — Claude Design should be told explicitly to reuse them across screens rather than redraw per screen, so the eventual handoff maps 1:1 onto `frontend/src/components/`.
- AI-generated content (summaries, drafts, coaching notes) always sits on a chalk-tinted inset panel with a small mono "AI" label in spruce-60 — one consistent treatment, so provenance is legible at a glance and never mistaken for a human voice.
