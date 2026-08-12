# Pulse Surveys — Usage Rules

Decision rules established across sessions 1–6. Companion to `tokens.css` (values + semantic comments) and `Component Gallery.dc.html` (every primitive, every state). SPEC_ADDITIONS.md holds the data model and behavioral spec; this document holds the *design* rules.

## 1. Chart variants — which trend component where

- **PulseTrendChart, three-line** (marigold solid section line with terminal dot, mist dashed comparable benchmark, mist 50% dotted university): instructor and leadership surfaces only. Legend names the comparison honestly ("Comparable 12-week courses" — comparables are same-length, past-referencing).
- **PulseTrendChart, single-line** (`comparables=false` — also hides the legend): any student-visible context. Students never see benchmarks, university averages, or comparison language — in lines, text, or aria labels. This is a hard invariant, not a style choice.
- **TrendPair** (two stacked panels, Instructor above Course, shared 1–5 y-scale, one x-axis and one legend at the bottom): the Instructor Monday Report and leadership aggregates. Panel order matches the survey question order and the comment-group order everywhere.
- **TrendDuo** (one panel, two solid equal-weight lines: Instructor marigold, Course spruce; legend above in mono eyebrow style, Instructor first): Student Results only. One 600ms draw for both lines; terminal dots auto-offset when the ends nearly coincide.
- **Axes**: course-level pages plot course week ("WK 01…") with a quiet term-week sub-label ("TERM 04…") when the section starts mid-term. Aggregates plot the term axis with per-start-cohort lines and a cohort selector (start letters: "U · started 8/17").

## 2. Color reservations

- **Madder** means "attend to this" and nothing else: flag chips on comments, the classification label on Care cases (the only madder on that page), and breached thresholds in the admin status strip. Never decoration, never headings, never emphasis.
- **Marigold** is the single hero accent: the current section's line and dot, focus rings, selected/active states, and validity coaching (a thin answer warms the border marigold — never red, never madder; coaching is not an error).
- **Spruce** is ink; **mist** is de-emphasis (comparison lines, excluded text, flat pulse lines); **hairline** is structure only, never text.
- One hero color per chart. When two streams share a panel (TrendDuo), the second line is spruce — never a new accent.

## 3. Motion budget

- The hero trend line draws on **once, 600ms** per page load or node selection (TrendPair: top panel then bottom; TrendDuo: both lines together). Benchmarks fade in after the draw.
- Everything else lives in **150–220ms**: expand/collapse, helper slide-fades, the Likert beat (180ms), tree expand (150ms).
- **Care Queue exception: no motion at all.** No draw-on, no hover transitions, no expands animating. Stillness is the design; the pulse-line appears only in its empty state, flat.
- Admin Console: nothing beyond 150ms expand/collapse.
- `prefers-reduced-motion` removes **all** motion globally (enforced in tokens.css). Nothing may opt out.
- No shake, ever. Nothing on any surface shames.

## 4. Register shifts between surfaces

- **Student surfaces** (survey, results): second person, plain, warm. Fractions, never percentages ("18 of 24 classmates responded"). Never "users," never "data." Confidentiality copy appears exactly once per surface, in plain words — no shield or lock iconography. Missed weeks state facts and the next window; no guilt language.
- **Instructor Monday Report**: formative and factual. Flagged comments are procedural ("Hidden from students pending your review"), not alarmed.
- **Leadership roll-up**: "needs attention," never "underperforming." Aggregate language counts "sections," never "instructors." No ranking, no composite scores, no sort-by-score.
- **Care Queue**: plain, procedural, unheroic. "Case," "comment," "student" — never "flagged content," never "incidents," no exclamation points. Seriousness is carried by restraint, not alarm color.
- **Admin Console**: operator-plain, mono-dominant. Name things by what they control ("Survey opens," not "cron schedule"); every setting states its consequence in one helper line. Wide-effect changes confirm by stating what will change — never "Are you sure?" No KPI heroes, no gradient tiles.

## 5. Recurring motifs

- **Pulse-line divider**: the small marigold ECG stroke under page titles. Its flat (mist) variant marks empty/closed states; the beat variant marks success (StateNotice). On the Care queue it appears only in the empty state, flat.
- **Mono eyebrow**: uppercase Spline Sans Mono, 0.08em tracking, spruce-60 — week markers, legends, panel labels, section codes.
- **Reading treatment for people's words**: comments, cases, and instructor responses are set in Literata at reading size on paper — a person's words get the dignified treatment, never a data-row excerpt.

## 6. Component inventory note

All 29 requested primitives exist in the prototype and render in the gallery. One additional established primitive not on the requested list is included for completeness: **InstructorResponse** (the instructor's compose-and-post block with the optional "Check draft with AI" step). CommentCard's `kept` state is reached by interaction (Keep for students → Undo), not a variant prop; the gallery shows the flagged-expanded state whose actions lead there.
