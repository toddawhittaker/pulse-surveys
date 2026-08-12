# Pulse Surveys — SPEC_ADDITIONS

Consolidated spec input covering the data model plus all behavioral, policy, and design decisions made in sessions 1–4. Feed this to the spec AI alongside the design brief. Entity/field names are suggestions.

---

## Part A — Data model: org hierarchy, roles, and reporting

### A1. Core principle

**People are not roles.** A person holds one or more *role assignments*, each scoped to a node in the org hierarchy. Deans and chairs can also be lead faculty; an assistant dean can hold a lead-faculty assignment while supervising a chair. Every view is resolved from an assignment (or a union of them), never from a person "type."

Two deliberately decoupled structures:
1. **Org containment hierarchy** — what contains what. Navigation, aggregation, drill-down.
2. **Supervision graph (reports-to)** — who answers to whom. Purview computation and escalation routing.

Containment alone cannot express the real reporting structure (see A5); do not derive one from the other.

### A2. Org containment hierarchy

```
Institution
└── College                 (e.g., College of Sciences)
    └── Department          (e.g., Biology — a grouping of prefixes)
        └── Prefix          (e.g., BIOL, MARS, MATH, STAT, MIS)
            └── Course      (e.g., BIOL 2150 — Principles of Ecology)
                └── Section (term instance, e.g., R3WW in Fall 2026)
```

- A department groups one or more prefixes (Math may hold MATH, STAT, MIS).
- Courses belong to exactly one prefix; sections to exactly one course and one term.

Section (term instance): `code` = `{startLetter}{ordinal}{modality}` (e.g. `Q1WW`, `F3WW`, `Q2FF`); startLetter encodes length + start date within the term (see Part D); ordinal = Nth section of that start within the course; modality `WW` online / `FF` face-to-face; startDate/endDate derived from startLetter + term calendar; lengthWeeks ∈ {3, 6, 8, 10, 12, 15, 16, 18}; instructorAssignment = the teaching instructor (usually adjunct).

### A2b. Data sources (who owns what)
- **LMS (via LTI Advantage / roster sync):** courses, sections, section codes (length + start derive from them), enrollments, teaching instructors. Read-only in Pulse; the hourly roster-sync job is the ingestion path. Course level derives from the course number.
- **Pulse-owned — people graph:** person records with name, category (VP / Dean / Assistant Dean / Department Chair / Lead Faculty), and a reports-to edge. The LMS has no equivalent; purview is computed from this graph.
- **Pulse-owned — Lead Faculty mapping:** a CSV mapping individuals to the courses they manage as Lead Faculty (people and courses do NOT correspond 1:1). Imports always show a dry-run diff before applying. A course with no mapping falls to its department chair.

### A3. Role assignments

```
RoleAssignment {
  id
  personId
  role        // VP_ACADEMICS | DEAN | ASSISTANT_DEAN | CHAIR | LEAD_FACULTY | INSTRUCTOR | CARE | ADMIN
  scopeNodeId // org node the assignment attaches to
  reportsTo   // RoleAssignment id (nullable only at the top of the graph)
}
```

Scope attachment: VP → institution; DEAN → college; ASSISTANT_DEAN → college (same node as the dean — authority comes from the supervision graph, not the scope); CHAIR → department; LEAD_FACULTY → **course** (one lead per course; a lead's practical scope may span prefixes and departments); INSTRUCTOR → section per term (~95% adjuncts, distinct from full-time leadership); CARE → institution (Office of Community Standards).

A person may hold any combination. Each assignment is its own row with its own `reportsTo`.

### A4. Supervision graph

`reportsTo` edges connect **role assignments, not people or org nodes**. Canonical chain:

```
INSTRUCTOR(section) → LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) → VP_ACADEMICS
```

Must support insertions/exceptions without schema change:
- **Assistant dean insertion:** `CHAIR → ASSISTANT_DEAN → DEAN`, for some chairs in a college while others report straight to the dean.
- Two-hat people have two assignments with two edges (a chair's LEAD_FACULTY assignment may report to their own CHAIR assignment — legal and expected).
- Forest/DAG over assignments; assignment-level cycles invalid; person-level cycles legal.

### A5. Purview computation

**Purview(assignment) = own grant ∪ purviews of all assignments transitively reporting to it.**

- Own grant restricted by role grain: LEAD_FACULTY grants only the courses they lead (never sibling leads' courses); CHAIR the department subtree; DEAN the college subtree.
- Assistant dean worked example: own led courses ∪ every supervised chair's department — a set no single org node contains. This is why purview comes from the supervision graph.

View behavior:
- Multi-role people get a role/assignment switcher, or a union purview with a multi-root hierarchy nav.
- Lead faculty get **hierarchy view only** — never the by-lead-faculty pivot (must not see peers' courses). Chair and above also get the by-lead drill-down over their purview.
- Tree roots are the highest *useful* nodes — never a single all-encompassing root row. VP starts at colleges, dean at departments, chair at prefixes, LF at their prefixes-of-led-courses.

### A6. Display labels per level

- College row: name + `N departments · N sections · Dean: {name}`
- Department row: `N prefixes · N sections · Chair: {name}`
- Course row: `N sections · Lead: {name}` (lead name omitted in the lead's own view)
- Section row: code (`R3WW`) + teaching instructor's name
- Course-level pages (instructor report, student results) carry the Lead Faculty name in the header.

---

## Part B — State machines per surface

### B1. Student Weekly Survey (page states)
- `default` (window open, in progress) → `bounce` (submit attempted with thin required text) → `submitted` → between windows: `closed`.
- Required-text trigger: a Likert rating ≤ 2 makes its paired "why" textarea required (Q1→Q2, Q3→Q4).
- Validity bounce: fires on submit when a required text is under the substantive threshold (prototype heuristic: 25 chars — needs a real definition). Marigold only (never madder/red), coaching copy with one concrete example, no shake, nothing shames.
- Submit button disabled until all Likerts answered and required texts non-empty.
- `submitted`: pulse-line beats once; confirms participation credit recorded; "View previous results" button.
- `closed` (between windows): flat pulse line, states when the next window opens, no guilt language; "View previous results" button. Never shows the survey or teased data.

### B2. Student Results (page states)
- `awaiting` (response-required course, instructor hasn't responded): closed door — flat pulse line, no countdown, no data teased, no blame.
- `published`: instructor's ResponseCard leads, data follows (trend, histograms, workload median, grouped comments). The page is a reply, not a dashboard.
- `on-behalf`: identical except attribution ("Response from {Lead Faculty name}, Lead Faculty" + one neutral line); same visual weight, no implication of discipline.
- `small-n`: trend + histograms shown; comments replaced by a notice framing privacy as protecting the student; they appear once enough classmates respond.
- Week navigation: students page back through published weeks only.

### B3. Instructor Monday Report
- Normal vs small-N (below threshold): small-N hides all comments (no chips, no counts, no flag-type hints — see C2), keeps AI summaries and aggregates.
- Week navigation across published weeks; comments disaggregated into "About the instructor" / "About the course" — each group led by its own AI summary.
- "Your response" section: AI-suggested draft (editable, "Use draft"), posts non-anonymously under the instructor's name to all enrolled students; posting shows the as-students-see-it state with an Edit path.

### B4. Leadership Roll-up
- One template for all roles; role changes only tree root and aggregation breadth. Two-pane; stacks at tablet.
- Drill to a section renders the Instructor Monday Report wholesale, read-only, width-matched to the aggregate article.
- Hierarchy vs by-lead-faculty tree modes (LF: hierarchy only). Trees default fully collapsed; expand/collapse-all controls; clickable breadcrumbs.

### B5. Care Queue (Office of Community Standards)
- Reached only by web login; scoped to `CARE` assignments. Page states: open queue | mid-reveal (audit modal) | post-reveal | empty (the most common state — designed as calm, not absence).
- Register: the quietest surface in the product. NO motion of any kind (no draw-on, hover, or transitions), no charts, trends, stats, or AI summary panels. Palette restricted to chalk/paper/spruce/hairline; madder appears ONLY on the classification label. Pulse-line motif only in the empty state, flat. Nothing urgent-styled — seriousness carried by restraint.
- Case = one routed comment: classification ("Self-harm risk" / "Threat of harm") in madder mono; the comment set in Literata at reading size (a person's words, not a data row); section + week + case ID + status in mono. Identity is ABSENT by default — no name, no placeholder, no redaction bar; the identity area does not exist until revealed.
- Re-identification: a plain procedural action. "Reveal student identity" reveals immediately — no modal, no reason picker, no warning — and the access log records actor, timestamp, and case automatically. Post-reveal, a persistent marker: "Identity visible · this access was logged." No un-reveal; the marker stays for the session.
- Case flow (all states live in CaseCard): open → revealed → resolved, plus open → false-positive. Open cases offer exactly two actions: "Reveal student identity" and "Mark false positive" (closes immediately, identity never shown, one quiet line: "False positives improve detection."). Only after reveal does "Mark resolved" appear, with an optional short disposition note (mono; recorded with staff name and date, shown on the resolved card). Resolved cases keep the revealed identity and marker when access was logged.
- GuidancePanel ("Guidance", not "escalation"): institution-configured contacts/policy prose (5–10 lines), pinned top right and top-aligned with the first open case, present in every state including empty.
- Resolved list scale: collapsed by default; when expanded, renders in batches (prototype: 10 at a time with a "Show N more · N older" control) — hundreds of resolved cases must not render or fetch eagerly.
- No search, no filters beyond Open/Resolved, no bulk actions — low volume expected; the design must not imply triage-at-scale.
- Copy register: plain, procedural, unheroic. "Case," "comment," "student" — never "flagged content," never "incidents," no exclamation points. Seeded excerpts must be sober and non-graphic: concern conveyed through context, never method language or explicit threats.

### B6. Admin Console
- Web login only; five routed sections: Health (LTI launch events with expandable plain-words + raw error details), Jobs (background jobs; failed jobs re-runnable with plain-verb confirmation), AI (per-task provider metrics table — validity/moderation/summary/draft/coaching — with small unadorned trend lines; classifier spot-review with reclassify overrides that feed the evaluation set), Care (counts and ages only), Configuration.
- Persistent status strip: LTI success rate (24h), oldest stuck job, AI error rate, open Care cases — each links to its section; madder text ONLY on defined threshold breach (madder keeps its "attend to this" meaning).
- Admin sees comment text ONLY in classifier spot-review, and only validity/moderation-stream samples — never threat/self-harm content (constraint stated on the panel). Admin Care visibility is count + oldest age + escalation setting; no case content, links, or names; automatic "Escalation notice sent" record when oldest age passes threshold.
- Configuration: term calendar; survey window + timezone; N-threshold and benchmark min-N; retention; notification toggles; AI provider (base URL, model, masked key); Care escalation threshold/contact; LMS registrations (issuer, client ID, deployments, JWKS status/last-fetch, copyable tool URLs; add-platform is a form, not a wizard); course catalog viewer (read-only, synced from LMS; length/level derived, last-sync shown); People & reporting editor (name, category, reports-to — Pulse-owned); Lead Faculty mapping table (person → courses) and People & reporting table, both with: column sorting (name columns sort by last name, stripping titles like Dr./Prof.; category sorts by hierarchy rank), pagination (10 default; 20/50 options; prev/next with range readout), and CSV import/export where import ALWAYS shows a dry-run diff (e.g. "2 mappings added · 1 changed · BIOL 4410 unmapped, falls to chair") before apply. Add-person is an inline form whose reports-to select lists only people already in the graph (built top-down). Layout note: the console forces a persistent scrollbar gutter so section switches never shift the nav.
- Every setting shows its consequence in one helper line; destructive/wide-effect changes confirm with plain language stating exactly what will change (never "Are you sure?"). Register: operator-plain — name things by what they control; errors say what happened and what to do next. Motion: nothing beyond 150ms expand/collapse.

## Part C — Privacy, visibility, and moderation

### C1. Hard visibility invariants (testable)
1. Students never see comparables, benchmarks, university averages, or other sections — in charts, text, or aria labels.
2. A LEAD_FACULTY assignment never grants sibling leads' courses, at any point in the union computation.
3. Below the N-threshold (prototype: 5 responses), raw comments are hidden from instructors and students alike.
4. Aggregate language counts sections, never instructors. "Needs attention," never "underperforming." No ranking or score-sorting anywhere.
5. Confidentiality copy appears exactly once per surface (survey: in the submit bar), in plain words, no shield/lock iconography.
6. No view may ever widen a student's visibility relative to these rules.

### C2. Flag taxonomy and routing
- Flags: `harmful`, `privacy`, `nonsense` (validity).
- "Harmful" is not only abuse aimed at the instructor — it can be a self-harm disclosure. Copy and flows must not assume the instructor is the target.
- Routing by harm type: abuse/attacks on instructor → the course's LEAD_FACULTY review queue; self-harm or student-welfare signals → CARE (Office of Community Standards) immediately, regardless of N or anonymity. Severe safety escalations bypass the graph and are never gated on response thresholds.
- Small-N: flagged comments stay hidden from the instructor entirely (no chip, no count, no flag-type hint); flags still route immediately to the appropriate reviewer. If the section later crosses the threshold, the comment appears flagged-collapsed carrying any reviewer decision. Optional neutral trace: "1 response held for review" in participation, category never revealed.

### C3. Moderation lifecycle (comment)
`published` → `flagged-collapsed` (hidden from students, chip + reason visible to instructor above small-N) → instructor review → `flagged-expanded` → `excluded` (with Undo) or `kept` ("Keep for students": comment publishes; quiet logged-decision line; Undo returns it to review). Excluded comments keep their text visible to the instructor (muted) above the exclusion notice.
- Exclusions are logged: instructor, excerpt, AI-flagged vs unflagged-with-typed-reason, date. Log visible at the lead-faculty prefix scope and above — an accountability record, not a feed. OPEN ITEM: kept decisions are logged but not yet surfaced in the roll-up log; a production moderation log should show both directions (Kept / Excluded).

### C4. Re-identification audit (Care Queue)
- Student identity on a routed case is hidden by default. The single reveal path is the plain "Reveal student identity" action; every access is logged automatically with actor, timestamp, and case (no user-entered reason). Records are kept by the Office of Community Standards and reviewed periodically (seeded: monthly, by the Dean of Students office).
- There is no identity access path that skips the audit log, and no way to remove the visible-access marker within a session.

## Part D — Term calendar and time rules

### D1. Calendar model (Franklin)
- Fall and Spring: 18 calendar weeks (incl. break). Summer: 12.
- Course lengths: 3, 6, 8, 10, 12, 15, 16 weeks (+18-week dissertation).
- Start letters map (length, start) per term — Fall 2026 (begins 8/17/26): 12-week U (8/17), R (9/7), Q (9/28); 6-week E (8/17), F (9/28), H (11/9); 8-week X (term start), Y/Z (late; 2-week gap in 18-week terms, overlap in summer; plus a week-5 start in 18-week terms); 10-week S/T; 15-week V/D; 16-week K; 3-week sections numbered 2–7. Spring/Summer reuse letters. Most sections are 6-week, then 12-week; few 3/15-week.
- Charts: course-level pages plot **course week** ("WK 01…") with a quiet term-week sub-label ("TERM 04…") from the section's start offset. Aggregates plot the **term axis** (TERM 01–18), one line per start cohort, with a cohort selector (e.g. "U sections · started 8/17").
- Comparable benchmarks are past-referencing and same-length: week N of a 12-week course vs week N of 12-week courses in current and past terms, regardless of start date. Comparison sets must make invalid combinations impossible (match term length and level).

### D2. Timing rules
- Survey window: opens Friday 6:00 PM, closes Sunday 11:59:59 PM, institution timezone.
- Monday Report generated after window close.
- Response-required policy (per prefix, set by lead faculty; read-only with attribution for chair+): holds student results until the instructor publishes a response; delinquency surfaces at 48h; respond-on-behalf enables for the lead at 96h (honest attribution as the lead, never impersonation).

## Part E — Attention rules (exact predicates)
Stream-aware where trends are involved (instructor and course streams are distinct rules):
1. Instructor trend down 2+ consecutive weeks.
2. Course trend down 2+ consecutive weeks.
3. Response rate under 40%.
4. Response required and delinquent 48h+.
Each card names its rule and stream, links to that section's Monday report. Empty state is calm ("Nothing needs attention this week"). Non-goals: no ranking, no composite scores, no "underperforming."

## Part F — AI behavior contracts
- Weekly summaries: generated per comment stream (instructor / course) and per aggregation node; must preserve clearly critical themes (never sand them off); exclude flagged-held content (may note "one comment is held for review" with type only above small-N); state the response count they draw from; generate even in small-N (summaries are the only comment signal there).
- Suggested instructor response: drafted from the week's actual themes, editable before posting, never auto-posts; addresses criticism concretely rather than deflecting.
- Optional draft check ("Check draft with AI"): instructor-initiated only, never forced and never blocking — compares the draft against the week's main comment themes and quietly names any theme not yet addressed (with its comment count); re-runnable; result clears when the draft changes.
- Classifier: assigns flag taxonomy (C2) with human review downstream; harm-type classification (instructor-abuse vs self-harm) drives routing; spot-review panel is an admin surface.

## Part G — Copy register
- Students: second person, plain, warm. Fractions, not percentages ("18 of 24 classmates responded"). Never "users," never "data."
- No guilt or shame states anywhere: missed weeks state facts and next opportunity; validity bounce coaches with an example.
- Written-feedback nudge: optional-state helper notes that written feedback counts toward full participation credit; required-state ties the "why" to actionability and credit.
- Formative leadership language per Part E.

## Part H — Participation credit and validity
- Participation credit is recorded on submit; substantive written feedback is tied to full credit when required (Likert ≤ 2) and encouraged when optional.
- "Substantive" needs a real production definition — the prototype uses a ≥25-character heuristic as placeholder.
- Validity rate = valid responses / responses (nonsense-flagged responses reduce it); shown on instructor and leadership surfaces only.

## Part I — Design system seed (for the React/Tailwind handoff)
- `tokens.css` is the single source for palette, type (Literata / Schibsted Grotesk / Spline Sans Mono), spacing, radii, shadow, focus ring, and the global reduced-motion kill switch. No raw hex in components.
- Primitives (one component each, with variants): WeekEyebrow, PulseTrendChart (single/three-line, cohort mode, term axis, termOffset), TrendPair, TrendDuo, RatingHistogram, StatPair, CommentCard (default / flagged-collapsed / flagged-expanded / excluded, optional stream chip), AiPanel, SmallNNotice (instructor/student audiences), ResponseRateBar, InstructorResponse, LikertInput, ConditionalTextArea (optional/required/bounce), WorkloadSlider, SubmitBar, StateNotice (flat/beat), ResponseCard (instructor/on-behalf), HierarchyNav, AggregateHeader, AttentionList, ExclusionLogRow, PolicyToggle, CaseCard (case states folded in: open / revealed / resolved / false-positive), GuidancePanel, HealthRow, JobRow, MetricBlock, DriftCard, CarePanel, ConfigSection, RegistrationCard.
- Screens: InstructorMondayReport, StudentWeeklySurvey, StudentResults, LeadershipRollup (one template, role-scoped), CareQueue, AdminConsole (five routed sections, one status strip).
- Motion: hero line draws once (600ms); everything else 150–220ms; all motion removed under prefers-reduced-motion.
