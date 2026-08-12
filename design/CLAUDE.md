# Pulse Surveys — project notes

## SPEC_ADDITIONS.md — keep updated
`SPEC_ADDITIONS.md` at the project root is the consolidated spec-AI input: data model (roles/reports-to/purview), state machines, privacy/moderation rules, term calendar, attention rules, AI contracts, copy register, credit/validity, design-system seed. **Whenever a future session adds pages or changes rules/behavior/data-model decisions, update the relevant SPEC_ADDITIONS.md section in the same turn.** ("Data Model - Roles and Reporting.md" is an earlier standalone copy of Part A; SPEC_ADDITIONS.md is authoritative.)

## Moderation & routing rules (from user, session 1)
- "Harmful" flags are not only abuse aimed at the instructor — they can be self-harm disclosures by the student. Design copy and flows must not assume the instructor is the target.
- Routing depends on harm type:
  - Abuse/attacks on instructor → Lead Faculty review queue.
  - Self-harm or student-welfare signals → the "Care" person in the Office of Community Standards, immediately, regardless of N or survey anonymity.
- Small-N state: flagged comments stay hidden from the instructor (no chip, no count, no flag-type hint). Flags still route immediately to the appropriate reviewer. If the section later crosses the response threshold, the comment appears in flagged-collapsed state carrying any reviewer decision.
- Severe/safety escalations are never gated on response threshold and live outside the Monday Report.
- Optional visible trace in small-N: a neutral "1 response held for review" line in participation, with no category revealed.

## Structure
- Design system, session 1 of ~7. Handoff target: React/Tailwind via Claude Code.
- tokens.css holds all palette/type/spacing/radii/shadow/focus tokens; no raw hex in components.
- Primitives (one file each): WeekEyebrow, PulseTrendChart, RatingHistogram, StatPair, CommentCard, AiPanel, SmallNNotice, ResponseRateBar, InstructorResponse.
- Screen: InstructorMondayReport.dc.html (smallN prop toggles the 3-of-9 state; week nav pages seeded weeks 1–7).
- InstructorResponse has an optional, instructor-initiated "Check draft with AI" (themes prop: label/keywords/count; compares draft to weekly themes, names unaddressed ones; never blocks posting). Themes seeded for week 7 + small-N.

## Session 2
- Student primitives: LikertInput, ConditionalTextArea (optional/required/bounce), WorkloadSlider (0–40h, 0.5 steps), SubmitBar (sole home of confidentiality copy), StateNotice (flat/beat pulse-line).
- Screen: StudentWeeklySurvey.dc.html — 390px-first, pageState prop: default | bounce | submitted | closed. Q2/Q4 become required when their Likert (Q1/Q3) ≤ 2; validity bounce fires on submit when required text < 25 chars, marigold only, coaching copy, no shake.
- States canvas: "Student Survey - States.dc.html" (2a–2e).
- Survey window: opens Friday 6:00 PM (institution timezone, Eastern for BIOL 2150), closes Sunday 11:59:59 PM. Between windows the page shows a StateNotice plus a "View previous results" button (results themselves will be a separate page, TBD). Same button on the submitted state. Student results pages must never show comparables/university benchmarks — dissatisfier.
- Substantive written feedback is tied to participation credit — required-state and bounce copy both say so.
- WorkloadSlider thumb grows (30px) and turns marigold while dragging.

## Session 3
- StudentResults.dc.html — pageState: published | on-behalf | awaiting | small-n. Response leads, data follows. Second person, fractions not percentages, no comparables anywhere.
- New primitive ResponseCard (variant instructor | on-behalf; Literata body, mono attribution, pulse divider, 8px rise on load). Instructor: Dr. M. Ellison; Lead Faculty: Dr. Rivera.
- PulseTrendChart comparables=false now also hides the legend (single-line variant). SmallNNotice gained audience prop (instructor | student — student copy frames privacy as protecting them).
- States canvas: "Student Results - States.dc.html" (3a–3e).

## Amendment (sessions 1+3)
- TrendPair primitive: two stacked PulseTrendChart panels (Instructor above Course — matches survey question and comment-group order), shared 1–5 y-scale, x-ticks and legend once (bottom panel only), mono panel labels. Instructor pages: three-line variant per panel; student: single-line.
- Draw sequence: top 600ms → bottom 600ms (delay 600) → benchmarks fade at 1200ms. PulseTrendChart gained height/showTicks/showLegend/drawDelay/fadeDelay/yMin/yMax props (defaults preserve old behavior).
- Seeded data split into two streams telling different stories: instructor steady-then-dip (3.9→3.6), course declining faster with workload (3.8→3.3→3.4). Both streams equal their week's histogram means.

## Amendment (session 3 only)
- StudentResults now uses TrendDuo, not TrendPair: single panel, two solid lines with terminal dots — Instructor marigold, Course spruce — equal weight, 1–5 y-scale, legend above in mono eyebrow style (Instructor first), both lines draw together in one 600ms pass. Terminal dots auto-offset ±4px when ends nearly coincide. Instructor report keeps TrendPair.

## Session 4
- LeadershipRollup.dc.html — ONE template, role prop: lead-faculty | chair | dean | vp (root/breadth change only). Two-pane flex-wrap layout (stacks at tablet). Drill to a section renders InstructorMondayReport wholesale, read-only (pointer-events:none) under a "Viewing as {role} · read-only" context bar.
- New primitives: HierarchyNav (collapsible tree, mono counts, expand 150ms, default-open two levels), AggregateHeader (name + scope line + three-line TrendPair), AttentionList (rule cards, stream-aware rules named in mono; empty = calm flat pulse line; never ranked), ExclusionLogRow (quiet 4-col table row; AI-flagged vs unflagged-with-reason), PolicyToggle (response-required per course set; editable LF only, read-only + note above).
- Hierarchy revised: College → Department → course prefix (BIOL, MARS, CHEM, BCHM, MATH, STAT, MIS…) → course → section. Departments group prefixes. Course rows/nodes show their Lead Faculty; every course has a seeded lead (BIOL 2150/3200/4410 = Dr. Rivera). Lead Faculty line also added to InstructorMondayReport and StudentResults headers.
- HierarchyNav has an alternate drill-down: "Lead faculty" mode (segmented toggle above the tree) grouping courses under their lead.
- InstructorMondayReport article max-width removed so it matches the roll-up article width when embedded.
- Policy placement: toggle(s) shown at prefix nodes (single) and department nodes (per child prefix); higher nodes show a one-line note. Exclusion log only at LF prefix (BIOL) scope.
- Copy rules: "needs attention" never "underperforming"; "sections" never "instructors" in aggregate language.
- States canvas: "Leadership Rollup - States.dc.html" (4a–4e, incl. 768px stack check).

## Session 5
- Care Queue (Office of Community Standards): CareQueue.dc.html, pageState: open | revealed | resolved | empty. Quietest surface: NO motion at all (no draw-on, no hover, no transitions), no charts/stats/AI panels, madder used ONLY for the classification label. Pulse line only in the empty state, flat.
- Primitives: CaseCard (all case states folded in: open → revealed → resolved, plus open → false-positive; madder mono classification, Literata comment, mono meta; identity area absent until revealed) and GuidancePanel (institution-configured guidance prose — titled "Guidance", top right, top-aligned with first open card). ReidentifyFlow and DispositionControl were removed as separate primitives.
- Case flow: open cases offer exactly two actions — "Reveal student identity" (plain procedural action, NO modal/reason picker/warning; access log records actor, timestamp, case automatically; identity block + persistent "Identity visible · this access was logged." marker) and "Mark false positive" (closes immediately, identity never shown, quiet line "False positives improve detection."). Only after reveal does "Mark resolved" appear, with an optional short disposition note (mono input; recorded with staff name + date and shown on the resolved card).
- Composition: "Care queue" header (no eyebrow, no week framing) → Open list → Resolved (collapsed by default; expands in batches of 10 with "Show more") → GuidancePanel aside. No search/filters/bulk actions. Seeds: 3 open (2 self-harm risk, 1 threat naming a classmate) + 2 resolved (1 referred, 1 false positive "exam is going to kill me lol"), all sober and non-graphic. Staff seed: M. Calloway.
- States canvas: "Care Queue - States.dc.html" (5a–5d).

## Session 6
- Admin Console: AdminConsole.dc.html, pageState: calm | health-alert | drift-override | config-diff. Web-only, 1280 desktop-first, dense, mono-dominant instrument panel; no KPI heroes/gradients; motion only 150ms-class expand. Left nav: Health / Jobs / AI / Care / Configuration. Persistent top status strip (LTI 24h rate, stuck jobs, AI error rate, Care open·oldest) — items link to sections, madder ONLY on threshold breach.
- Primitives: HealthRow (LTI event, expandable plain-words reason + raw error), JobRow (status ok/retrying/failed; failed → "Run again" with plain-verb inline confirm), MetricBlock (per-task AI table: validity/moderation/summary/draft/coaching + small static marigold trend line), DriftCard (validity/moderation samples ONLY — never threat/self-harm, note on card; reclassify → "Save override"; "Overrides feed the evaluation set"), CarePanel (count + oldest age + escalation setting only, no content/links/names; "Escalation notice sent · date" when past threshold), ConfigSection (grouped fields, every setting has a consequence helper; wide-effect changes get inline plain-language confirm — never "Are you sure?"), RegistrationCard (issuer/client/deployments/JWKS status + copyable tool URLs; add-platform is a form).
- Configuration also holds: course catalog (READ-ONLY, synced hourly from LMS; length/level derived from section codes/course numbers), People & reporting editor (name, category, reports-to — Pulse-owned; seeds include the assistant-dean insertion Dr. J. Hale), Lead Faculty mapping CSV (person → courses; mandatory dry-run diff; unmapped course falls to chair), LMS registrations, Care escalation (threshold/contact + CarePanel).
- States canvas: "Admin Console - States.dc.html" (6a–6d).

## Term model (from user, session 4)
- Fall and Spring semesters: 18 weeks. Summer: 12 weeks.
- Course lengths vary: 3, 6, 8, 12, 15 weeks.
- Starts: every 3 weeks for 3/12/15-week sections; every 6 weeks for 6-week sections. 8-week sections start at term start or end at term end (2-week gap in 18-week terms, overlap in summer); in 18-week terms there is also an 8-week section starting week 5.
- Resolved: x-axes show course week ("WK 01…") with a quiet term-week sub-label beneath ("TERM 04…") via termOffset prop on PulseTrendChart/TrendPair/TrendDuo (null = off). BIOL 2150 seeded as a 12-week course starting term week 4 (offset 3). Comparables are past-referencing, same-length courses regardless of start date — instructor legend reads "Comparable 12-week courses" (compLabel prop). Course mix: mostly 6-week, some 12, few 3/15.

## Tree roots per role (revised)
- LF: their prefixes (BIOL + MARS for Dr. Rivera) — policy per prefix, exclusion log at BIOL. LF gets hierarchy view ONLY (no by-lead toggle — must not see other leads’ courses). Chair: prefixes (BIOL, MARS). Dean: departments. VP: colleges. No single useless root rows.

## Franklin calendar & section vocabulary (session 4, from uploads)
- Institution: Franklin University. Colleges seen in tally: COB, CAST. Real prefixes: BUSA, CLOUD, COMP, etc. Locations: Online (WWW rooms) vs Downtown (FF).
- Section code = {start letter}{ordinal within that start}{modality}: e.g. Q1WW, F3WW, Q2FF. WW = online, FF = face-to-face.
- Fall 2026 start letters (from 2026-27 calendar PDF): 16wk K (8/17); 15wk V (8/17), D (9/7?); 12wk U (8/17), R (9/7), Q (9/28); 10wk S (8/17 area), T (later); 8wk X (8/17), Z, Y (11/9); 6wk E (8/17–9/26), F (9/28–11/7), H (11/9–12/19); 3wk sections numbered 2–7; 18wk Dissertation. Spring/Summer reuse letters.
- Terms: Fall 2026 begins 8/17/26; ~18 calendar weeks incl. break. Most sections are 6-week (E/F/H) or 12-week (Q/R/U).
- Tally columns: ID, Subj, Crs No, Sec, first char, credits, title, times/days/room, start/end dates, cap/reg/open/waitlist, instructor + email, location, college.
- Prototype keeps fictional people/courses but should adopt this section vocabulary. Roll-up cohort chips = start letters (U · started 8/17, R · 9/7, Q · 9/28 for 12-week Fall).
- Raw files in uploads/ (course-tally.xlsx is a parse-friendly copy).
- Section codes adopted throughout: BIOL 2150 §3 = R3WW (12-week, started 9/7 — matches termOffset 3; note user first said Q2WW but Q starts 9/28, which wouldn't put the course at week 7). Small-N section = R1WW. Tree sections named {letter}{n}WW.
- Tree section rows carry the teaching instructor's name (95% adjuncts, distinct from full-time lead faculty/chairs/deans). BIOL 2150 R3WW = Dr. M. Ellison; other sections seeded from a fictional adjunct pool.
