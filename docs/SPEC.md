# Pulse Surveys — Product & Technical Specification

**Version:** 0.1 (draft)
**License:** MIT
**Deployment model:** Single tenant, self-hosted

---

## 1. Overview

Pulse Surveys is an LTI 1.3 / LTI Advantage tool that runs a brief, standardized weekly feedback cycle in every enrolled course:

1. Students answer five questions each week inside the LMS.
2. Participation credit is passed back to the gradebook automatically.
3. Every Monday, instructors receive a report: rating distributions, workload data, de-identified comments, and an AI-generated summary.
4. Instructors publish a response (with advisory AI coaching); students see aggregate results and that response, closing the loop.
5. Academic leadership (Lead Faculty → Chair → Dean → VPAA) sees roll-up views across their span of oversight.

The design goal is trust: students must believe their responses are confidential, and instructors must believe the data is fair. Most of the non-obvious requirements below exist to protect one of those two beliefs.

## 2. Roles and access

**People are not roles.** A person holds one or more *role assignments*, each scoped to a node in the org hierarchy; every view is resolved from an assignment (or a union of them), never from a person "type." A chair can also lead courses; an assistant dean can hold a lead-faculty assignment while supervising a chair.

| Role | Entry point | Scope attachment |
|---|---|---|
| Student | LTI launch | Own responses; aggregate results + instructor response for own sections |
| Instructor | LTI launch | Section, per term (~95% adjuncts, distinct from full-time leadership); own reports, moderation, response publishing |
| Lead Faculty | LTI launch **or** web login | **Course** — one lead per course; a lead's practical span may cross prefixes and departments. Policy settings; response-on-behalf |
| Department Chair | LTI launch **or** web login | Department (a grouping of prefixes) |
| Assistant Dean | LTI launch **or** web login | College (same node as the dean — authority comes from the supervision graph, not the scope) |
| Dean | LTI launch **or** web login | College |
| VP of Academics | LTI launch **or** web login | Institution |
| Care | Web login | Institution (Office of Community Standards) — threat/self-harm queue and re-identification only; no reporting access |
| Admin | Web login | Observability console, LTI registration, org/people management, configuration |

Notes:

- **Entry doors are a property of the assignment, not the person.** A person holding two assignments uses whichever door fits the one they are acting under. Every *reporting* role — instructor, lead faculty, chair, assistant dean, dean, VP of Academics — can enter through an LTI launch, including leadership. Every role except instructor and student can *also* enter by web login; Care and Admin are web login only (their work has no launch context), and students enter by launch only. The table above is authoritative where this prose and it disagree.
- The launch authenticates the person by their LMS user ID; because the app owns the supervision graph (§2.1), once identified they are shown their full purview — not just the course they happened to launch from. The launch context resolves *which* section a link points at, never caps what a leadership user may see.
- LTI launch requires being an enrolled LMS user in *some* course, so **web login via OIDC is retained** for all leadership and staff roles (Entra ID, Okta, Keycloak, etc.; local accounts as a pilot fallback). Both doors resolve to the same identity and the same views.
- Roles compose: multi-role people get a role/assignment switcher, or a union purview rendered as a multi-root hierarchy nav. **Care is deliberately not composable** with reporting roles — its sole power is the threat queue, kept isolated so safety re-identification never rides alongside routine oversight access.

### 2.1 Org model: containment, supervision, and purview

Two deliberately decoupled structures. Containment alone cannot express real reporting lines (see the assistant-dean case below); neither is derived from the other.

**Containment hierarchy** — what contains what; drives navigation, aggregation, drill-down:

```
Institution
└── College                 (e.g., College of Sciences)
    └── Department          (groups one or more prefixes: Math may hold MATH, STAT, MIS)
        └── Prefix          (e.g., BIOL)
            └── Course      (e.g., BIOL 2150)
                └── Section (term instance, e.g., R3WW in Fall 2026)
```

**Supervision graph** — who answers to whom; drives purview and escalation. `reportsTo` edges connect **role assignments, not people or org nodes**. Canonical chain: `INSTRUCTOR(section) → LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) → VP_ACADEMICS`, with insertions supported without schema change — e.g., some chairs in a college report through an assistant dean (`CHAIR → ASSISTANT_DEAN → DEAN`) while others report straight to the dean. Two-hat people hold two assignments with two edges (a chair's lead-faculty assignment may report to their own chair assignment — legal and expected). The graph is a forest/DAG over assignments; assignment-level cycles are invalid, person-level cycles are fine.

**Purview(assignment) = own grant ∪ purviews of all assignments transitively reporting to it**, with the own grant restricted by role grain: a Lead Faculty's grant is only the courses they lead (never sibling leads' courses, at any point in the union); a chair's is the department subtree; a dean's the college. The assistant dean is the worked example for why purview comes from the graph: own led courses ∪ every supervised chair's department — a set no single containment node holds.

View behavior:

- Lead Faculty get the **hierarchy view only** — never a by-lead-faculty pivot (they must not see peers' courses). Chair and above additionally get a by-lead drill-down over their purview.
- Tree roots are the highest *useful* nodes, never a single all-encompassing root row: VP starts at colleges, dean at departments, chair at prefixes, Lead Faculty at the prefixes of their led courses.
- Display labels: college rows show `N departments · N sections · Dean: {name}`; department rows `N prefixes · N sections · Chair: {name}`; course rows `N sections · Lead: {name}` (lead name omitted in the lead's own view); section rows show the section code and teaching instructor. Course-level pages (instructor report, student results) carry the Lead Faculty name in the header.

**Data sources — who owns what:**

- **LMS-owned (read-only in Pulse; hourly roster sync + launch-time ingestion):** courses, sections, section codes, enrollments, teaching instructors. Course **level** (UG/GR/DR) derives from the course number; section **length and start date** derive from the section code (§2.2). A read-only course-catalog viewer in the admin console shows what synced and when.
- **Pulse-owned — people graph:** person records (name, category) plus reports-to edges. The LMS has no equivalent; purview is computed from this graph. Built top-down in the admin console (a new person's reports-to selector lists only people already in the graph).
- **Pulse-owned — Lead Faculty mapping:** a mapping of individuals to the courses they lead (people and courses are not 1:1), maintained in the admin console with CSV import/export. Imports always show a dry-run diff before applying (e.g., "2 mappings added · 1 changed · BIOL 4410 unmapped, falls to chair"). A course with no mapping falls to its department chair.

### 2.2 Terms, section codes, and course weeks

- The academic calendar is institution configuration, not code. Reference model (Franklin): fall and spring terms are 18 calendar weeks including break; summer is 12. Course lengths in weeks: **3, 6, 8, 10, 12, 15, 16** (plus an 18-week dissertation length). Most sections are 6-week, then 12-week.
- Section codes follow `{startLetter}{ordinal}{modality}` (e.g., `R3WW`, `Q2FF`): the start letter encodes length + start date within the term via a per-term **start-letter map** (admin-configured data; Fall 2026 seed: 12-week U/R/Q starting 8/17, 9/7, 9/28; 6-week E/F/H; 8-week X/Y/Z; 10-week S/T; 15-week V/D; 16-week K; 3-week sections numbered 2–7). Modality: `WW` online, `FF` face-to-face. Section start/end dates derive from the letter + term calendar; nothing is hand-entered per section.
- **Two week axes.** Course-level pages (instructor report, student results) plot **course week** ("WK 01…") with a quiet term-week sub-label ("TERM 04…") from the section's start offset. Aggregate pages plot the **term axis** (TERM 01–18) with one line per start cohort and a cohort selector (e.g., "U sections · started 8/17") — averaging week-3-of-course across cohorts that began five weeks apart would be meaningless.

## 3. The weekly cycle

### 3.1 Survey window

- Default rhythm (institution configuration): **opens Friday 18:00, closes Sunday 23:59:59, reports available after window close Monday morning** in the institution timezone (default `America/New_York`).
- A section's active weeks derive from its section code and the term calendar (§2.2).
- Students see exactly one open survey at a time per section. Missed weeks cannot be back-filled (this keeps the signal weekly and the grading unambiguous).

### 3.2 The five questions (standardized, v1 fixed)

1. **Instructor rating** — Likert 1–5 ("This week, my instructor supported my learning.")
2. **Instructor comment** — free text. *Required if Q1 ≤ 2*, otherwise optional but encouraged.
3. **Course rating** — Likert 1–5 ("This week, the course materials and activities supported my learning.")
4. **Course comment** — free text. *Required if Q3 ≤ 2*, otherwise optional but encouraged.
5. **Workload** — hours spent on this course this week, numeric entry via a slider with a live numeric readout (range 0–40, 0.5-hour steps; keyboard-adjustable and screen-reader-labeled for accessibility). Stored as a decimal so reporting can show true means and medians rather than band midpoints.

Question text is stored in a versioned `question_set` table even though v1 ships one fixed set — this is the extension point for the future feature where each oversight level can append its own questions to the courses in their purview. No schema migration will be needed to add it.

### 3.3 Response validity (participation gating)

Participation credit requires a *complete, reasonable* submission:

- All required fields answered.
- Each submitted comment is classified by the AI provider as **substantive / insufficient / nonsense** ("the pacing in week 3 was too fast" / "it was okay" / "adfasdfa"). The prototype's ≥25-character heuristic is a placeholder only; production substantiveness is the classifier's call, with the character heuristic retained solely as the fail-open floor below.
- **Validation is synchronous at submit time**: a student typing "it was okay" is told immediately that the answer is too brief to count, before submission — never silently penalized after the fact, with coaching copy and one concrete example, never a shame state. Classifier latency budget: p95 < 2s; on provider timeout, the heuristic floor applies and the submission is accepted, then classified async (fail open, never block a student on an outage).
- Optional comments left blank do not affect validity; optional-state helper copy notes that written feedback counts toward full participation credit.
- Validity rate = valid responses ÷ responses (nonsense-flagged responses reduce it); shown on instructor and leadership surfaces only, never to students.

### 3.4 Grade passback

- One AGS line item per section: **"Pulse Participation"**, created by the tool on first launch.
- Score = valid weeks completed ÷ weeks elapsed to date, posted as a percentage of the line item's max score (default 100).
- Recomputed and re-posted after each week closes; fully automatic, no instructor action or override.
- Late adds: denominator starts at the student's first enrolled week (from NRPS enrollment data). Drops: scores stop updating; the LMS owns what happens to the column.

## 4. Confidentiality model

This is the load-bearing wall of the product.

- Responses are stored keyed to the **LMS user ID** (`sub` from the launch). Identity is never displayed to instructors or any leadership role, in any view, including CSV exports.
- **Traceability exists for safety, not oversight.** Re-identification is possible only through the Care queue (§6.2), only by the Care role, and every identity access is automatically audit-logged with actor, timestamp, and case.
- **Small-N handling (n < 5 responses in a reporting week):** instructors see rating distributions and the AI summary, but **no raw comments**. Comments from under-threshold weeks are not discarded — they feed the summary, and they surface as raw text once the section's cumulative comment volume for the term crosses the threshold, batched so that timing cannot identify an author. Threshold value is configurable (default 5).
- Comment display order is randomized; timestamps are never shown with comments.
- Data retention: raw responses retained for a configurable period (default: current term + 1 year), then comments are deleted and only aggregates persist. All retention jobs are logged.

### 4.1 Hard visibility invariants (testable)

Each of these is an automated assertion in the test suite (§9), not a convention:

1. Students never see comparables, benchmarks, university averages, or other sections — in charts, text, tooltips, exports, or aria labels.
2. A Lead Faculty assignment never grants sibling leads' courses, at any point in the purview union computation.
3. Below the n-threshold, raw comments are hidden from instructors and students alike.
4. Aggregate language counts sections, never instructors; "needs attention," never "underperforming"; no ranking, no composite scores, and no score-sorting anywhere.
5. Confidentiality copy appears exactly once per surface (survey: in the submit bar), in plain words, no shield or lock iconography.
6. No view may ever widen a student's visibility relative to these rules.

## 5. Reporting and the feedback loop

### 5.1 Instructor Monday report (per section)

- **Trend charts as a stacked pair** (instructor stream above, course stream below, shared 1–5 y-scale, one legend): each panel carries three lines — this section (hero), the **comparison set**, and **university-wide**. Course-level pages plot course week with the term-week sub-label (§2.2); week navigation pages across published weeks.
- This-week rating distributions for both streams; workload mean/median for the section against comparison-set and university figures (true numeric statistics — §3.2); response rate and validity rate.
- De-identified comments **grouped under "About the instructor" / "About the course," each group led by its own AI summary**; empty groups show a one-line notice, not a hidden heading. Comments carry their moderation status (§5.2), subject to §4 small-N rules.
- AI summaries per stream: preserve clearly critical themes (never sanded off), state the response count they draw from, exclude flagged-held content (above small-N they may note "one comment is held for review" with type only), and are generated **even in small-N weeks** — there, the summary is the only comment signal.

**Comparison sets.** To be comparable, sections must match on **both** length (§2.2's length set) *and* level (UG / GR / DR) — an 8-week graduate course is never averaged against a 12-week undergraduate one. Benchmarks are **past-referencing**: week N of a 12-week section is compared against week N of 12-week sections of the same level in the current *and prior* terms, regardless of start date. The default comparison set is the same Lead Faculty's courses filtered to matching length+level; leadership can define named sets, and set-definition UI makes invalid combinations impossible rather than erroring on them. The university-wide line is all same-length+level sections institution-wide. Benchmark lines have their own minimum (distinct from the per-section n-threshold): computed from fewer than the configured number of sections, the line is suppressed rather than shown thin.

### 5.2 Comment moderation

- The classifier tags each comment: **clear / harmful / privacy** (names third parties or reveals identifying detail) / **nonsense**. "Harmful" is not only abuse aimed at the instructor — it can be a self-harm disclosure; copy and flows never assume the instructor is the target.
- **Routing by harm type:** abuse or attacks on the instructor route to the course's Lead Faculty review queue in addition to the instructor's own moderation view; self-harm or student-welfare signals route to Care (§6.2) immediately, regardless of small-N or anonymity — severe safety escalations bypass the supervision graph and are never gated on response thresholds.
- **Moderation lifecycle:** `published` → `flagged-collapsed` (hidden from students; chip and reason visible to the instructor above small-N) → instructor review → `excluded` (with Undo) or `kept` ("Keep for students" publishes the comment with a quiet logged-decision line; Undo returns it to review). Excluded comments keep their text visible to the instructor, muted, above the exclusion notice.
- **Small-N concealment:** below the threshold, flagged comments are hidden from the instructor entirely — no chip, no count, no flag-type hint — while flags still route immediately to the appropriate reviewer. If the section later crosses the threshold, the comment appears flagged-collapsed carrying any reviewer decision already made. An optional neutral participation trace ("1 response held for review") never reveals category.
- Excluding a comment the AI did *not* flag requires a stated reason. All exclusions are logged (instructor, excerpt, AI-flagged vs unflagged-with-reason, date); the log is visible at the Lead Faculty prefix scope and above — an accountability record, not a feed. This is the anti-cherry-picking mechanism: the escape valve for genuinely harmful comments stays open, but quietly dropping fair criticism leaves a trail. *Open item:* kept decisions are logged but not yet surfaced in the roll-up log; production should show both directions (Kept / Excluded).
- Threat/self-harm classifications bypass this flow entirely (§6.2) and are never shown to the instructor.

### 5.3 Instructor response

- After reviewing the report, the instructor writes a short response to the class ("You said / we heard / here's what changes"). Responses post **non-anonymously under the instructor's name** to all enrolled students; after posting, the instructor sees the as-students-see-it state with an Edit path.
- **AI assistance, two modes, both optional and both advisory:** (a) the model can **draft** a response from the week's actual themes and ratings, editable before posting ("Use draft"), addressing criticism concretely rather than deflecting — never auto-posts; (b) an instructor-initiated **draft check** ("Check draft with AI"), never forced and never blocking, compares the draft against the week's main comment themes and quietly names any theme not yet addressed (with its comment count). Re-runnable; the result clears when the draft changes. Nothing is ever published without a human pressing publish.
- Publishing is **encouraged by default; a Lead Faculty can set "required" per prefix** (read-only with attribution for chair and above). Required holds the student-facing aggregate until a response is published; delinquency surfaces at +48h on the Lead Faculty dashboard.
- **Delinquency handling:** at +96h, respond-on-behalf enables — the Lead Faculty can publish a response themselves (attributed honestly to the Lead Faculty, never impersonation), releasing the held aggregate via the same draft-plus-check flow one level up. Aggregates are never auto-published without a named human author.

### 5.4 Student closing-the-loop view

On next LTI launch (and via the Monday-after notification), students see their own section only: the instructor's response **leading the page** (the page is a reply, not a dashboard), then the two-stream trend chart, distributions, workload median, and the published comments grouped under the same two headings as everywhere else. Page states: `awaiting` (response-required and unpublished — a closed door: no countdown, no teased data, no blame), `published`, `on-behalf` (identical weight, honest attribution, no implication of discipline), and `small-N` (trend and distributions shown; comments replaced by a notice framing suppression as protecting the student, appearing once enough classmates respond). Students page back through published weeks only. Students **never** see comparison-set or university lines, and never other individuals' raw identifiable data — only what §4 and §5.2 permit.

### 5.5 Leadership roll-ups

- One template for all leadership roles; role changes only the tree root and aggregation breadth. Two-pane (hierarchy nav + content), stacking at tablet width. Aggregate pages plot the term axis with per-cohort lines and a cohort selector (§2.2).
- **Tree modes:** hierarchy view for everyone; a by-lead-faculty pivot additionally for chair and above over their purview — never for Lead Faculty (sibling isolation, invariant §4.1.2). Trees default fully collapsed with expand/collapse-all; breadcrumbs are clickable; roots and row labels per §2.1.
- Drill-down terminates at a section, rendering the Instructor Monday Report wholesale, read-only, with a context bar ("Viewing as Dean · read-only").
- Attention surfacing uses the exact predicates of §5.6; raw comments appear up-chain only de-identified and only where the n-threshold is met at the aggregation being viewed. All leadership views are read-only with respect to student data; the only mutating powers are policy settings at the appropriate scope.

### 5.6 Attention rules (exact predicates)

Stream-aware where trends are involved — instructor and course streams are distinct rules:

1. Instructor trend down 2+ consecutive weeks.
2. Course trend down 2+ consecutive weeks.
3. Response rate under 40%.
4. Response required and delinquent 48h+.

Each attention card names its rule and stream and links to that section's Monday report. Empty state is calm ("Nothing needs attention this week"). Non-goals, permanently: no ranking, no composite scores, no "underperforming."

### 5.7 Notifications

- Monday report email to instructors: headline numbers only (response rate, mean deltas) plus a link into the app — no comments or summaries in email, so confidential content never sits in an inbox.
- Student notifications (survey open, results published) delivered as LMS-agnostic email where addresses are available via NRPS; optional and configurable, since some institutions prohibit tool-originated email.

## 6. Admin console and safety

### 6.1 Observability

- LTI health: registration status, recent launches with outcome (success / signature failure / clock skew), NRPS and AGS call logs with response codes.
- Job dashboard: scheduled and background jobs (report generation, grade passback, classification backlog, retention) with status, duration, retry counts.
- AI provider metrics: request volume, latency, error rate, token spend, per-task breakdown (validity / moderation / summary / coaching).
- Classifier drift panel: weekly sample of classifications for human spot-review, with an override control that feeds an eval set (§9.3).

### 6.2 Threat and self-harm queue (Care role)

- This queue belongs to the **Care role** (the Office of Community Standards), and only the Care role: comment content and identity access are visible to no other role, including Admin and the VPAA. Admins run and observe the system; they do not read flagged comments or re-identify authors. This separation is enforced in code, not just convention.
- Comments classified as **threat-of-harm** or **self-harm risk** are routed here immediately and suppressed from all instructor and leadership views.
- **Case flow.** An open case offers exactly two actions:
  - **Mark false positive** — closes the case; author identity is never surfaced, so a misclassified student is never named to anyone. False positives feed the eval set (§9.3).
  - **Reveal student identity** — a plain, one-click procedural action (no confirmation dialog or typed justification; Care staff acting on a real case *is* the reason). The access is automatically audit-logged (actor, timestamp, case).
  - **Mark resolved** becomes available only *after* identity has been revealed — a genuine case cannot be closed without the responsible staff member having established who the student is. Resolution takes an optional short disposition note, recorded with staff name and date. Outreach, conduct process, and CARE protocol happen outside the tool per Office of Community Standards practice; the tool records only the outcome.
- The identity-access audit log (actor, timestamp, case, later disposition) is reviewable by Admin, without comment content, and access records are **reviewed periodically outside the Care office** (reference practice: monthly, by the Dean of Students office) — the accountability check on Care itself.
- **Conflict-of-interest flag.** A Care assignment and a reporting assignment may legitimately sit on the same person — a Care staffer who also teaches a section is unlikely but permitted (§2.1). Where a reveal returns a student enrolled in a section inside that person's own reporting purview, the audit entry is marked as a conflict. Concretely and most importantly: a Care staffer revealing a student in a section they themselves teach. The reveal is **never blocked** — a student at risk must not wait on a governance check, and a preventive control here would cost more than it saves. The flag is detective: it is surfaced distinctly in the Admin access log and to the periodic outside review, so the rare overlap is visible rather than merely permitted. The narrow case (enrollment in a section the revealer teaches) needs only enrollment data; the general case (anywhere in the revealer's purview) depends on the purview computation in §14.3 E9.
- Queue scale assumptions: no search, no filters beyond Open/Resolved, no bulk actions — expected volume is low and the design must not imply triage-at-scale; the Resolved list is collapsed by default and renders in batches.
- **Non-content apertures** (no comment text or identity crosses these):
  - Admin observability console shows open-case count and oldest-case age, so an unworked queue is operationally visible.
  - A configurable escalation notice ("a case has been open more than N hours") can be sent to a designated contact — count and age only.
  - Optionally, a per-term aggregate case count (never a list) may be exposed on a leadership surface for institutional reporting; enabling this is an institutional governance decision.
- Configurable institution-specific guidance text displayed alongside the queue (escalation policy, contacts).

### 6.3 Configuration surface

- Term calendar and per-term **start-letter map** (§2.2); survey window timing and institution timezone; n-threshold and benchmark min-N; retention period; notification toggles; AI provider (base URL, model, masked key); LTI platform registration (issuer, client ID, deployment IDs, JWKS status/last-fetch, copyable tool-side URLs; add-platform is a form, not a wizard); Care stale-case escalation threshold and contact, and the optional leadership aggregate case count (§6.2).
- **People & reporting editor** (Pulse-owned people graph: name, category, reports-to — built top-down, a new person's reports-to selector lists only people already in the graph) and the **Lead Faculty mapping table** (person → courses). Both tables: column sorting (name columns sort by last name, stripping titles; category sorts by hierarchy rank), pagination, and CSV import/export where import always shows a dry-run diff before applying.
- **Course catalog viewer** — read-only, synced from the LMS, with derived length/level shown and last-sync time. Nothing LMS-owned is editable in Pulse.

## 7. Architecture

### 7.1 Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language / runtime | Python 3.13+ | Stated preference; strong LTI and AI library support |
| API framework | FastAPI (latest stable) | Async-native, Pydantic v2 models double as the API contract, OpenAPI for free (useful for the future MCP server) |
| ORM / migrations | SQLAlchemy 2.x + Alembic | Current idioms, typed |
| Database | PostgreSQL 17 | Single store for app data and job queue state |
| Background jobs | Celery + Redis (alternative: Procrastinate for a Postgres-only stack) | Scheduled report generation, grade passback, async classification |
| LTI | `pylti1p3` | Most feature-complete Python LTI 1.3 library: launch validation, Deep Linking, NRPS, AGS |
| AI access | `pydantic-ai` over any OpenAI-compatible endpoint | Provider-agnostic (OpenAI, Anthropic-compatible proxies, LiteLLM, vLLM, Ollama) with typed outputs and instrumentation; §7.4 |
| Frontend | React 19 + TypeScript + Vite, TanStack Router/Query, Tailwind CSS 4 | SPA suits the iframe launch and the interactive leadership dashboards; charts via Recharts |
| Email | SMTP relay (aiosmtplib), Mailpit in dev | Institution-agnostic |
| Auth (web roles) | OIDC via `authlib`; local accounts fallback | IdP-agnostic |

### 7.2 Services (Docker Compose)

```
api        FastAPI (uvicorn) — serves API + built SPA assets
worker     Celery worker — classification, summaries, passback
beat       Celery beat — window open/close, Monday reports, retention
db         postgres:17
redis      redis:7 (broker/result backend)
mailpit    dev-only SMTP capture
mock-lms   dev/test-only LTI 1.3 platform (§9.2)
mock-idp   dev/test-only OIDC identity provider for web-login roles (§9.2)
```

Production deployment follows the same topology; reverse proxy / tunnel (e.g., cloudflared sidecar) is deployment-specific and out of scope for the compose file, but the app must run correctly behind a TLS-terminating proxy with a configurable public base URL (LTI redirect URIs demand it).

### 7.3 LTI specifics (LMS-agnosticism in practice)

- Strict LTI 1.3 core + LTI Advantage (NRPS 2.0, AGS 2.0, Deep Linking 2.0) — no platform-proprietary APIs anywhere in core code.
- **Iframe cookie survival:** third-party cookie blocking is the norm; the tool uses the OIDC state-passing patterns `pylti1p3` supports (platform storage / postMessage) plus its own short-lived launch-session JWT so no third-party cookie is ever required.
- Per-platform quirk isolation: a thin `PlatformProfile` adapter (Canvas, Moodle, D2L, Blackboard) for known deviations in AGS score semantics and NRPS paging — quirks live in one file each, nothing leaks into domain logic.
- Deep Linking supported so the tool can be placed as a graded assignment where the platform prefers that flow; plain resource-link launch is the default.
- Roster sync: NRPS pulled on schedule and on launch (debounced), used for enrollment windows (§3.4) and email addresses where exposed.

### 7.4 AI task inventory

All model calls go through one internal `AIGateway` with per-task prompts, timeouts, retries, and eval hooks:

| Task | Trigger | Output |
|---|---|---|
| Comment validity | Synchronous at submit (async fallback) | substantive / insufficient / nonsense |
| Moderation | Async at window close | clear / harmful / privacy / nonsense / threat / self-harm |
| Weekly summary | Monday report job | Per-stream, per-node themed summaries under the §5.1 contracts |
| Response draft | On instructor/Lead Faculty request | Draft class response from the week's actual themes + ratings |
| Draft check | Instructor-initiated, re-runnable | Names themes the draft hasn't addressed, with comment counts; clears on edit |

**Typed contracts.** Every task declares its output as a Pydantic model rather than parsed JSON. The gateway validates against that model, retries on shape violations, and surfaces persistent failures as errors rather than letting a malformed classification propagate. The same models serve three purposes without duplication: the runtime contract, the API response schema, and the eval fixtures in §9.3 — so an eval case is a typed object, not a string comparison. `pydantic-ai` is the intended implementation (model-agnostic across OpenAI-compatible endpoints, typed outputs, instrumentation that feeds the admin console's per-task metrics); it is young and fast-moving, so pin it and keep the gateway interface thin enough that replacing it is a day's work.

**Single-shot boundary.** Every task in the table above is one call in, one validated object out — no tool use, no planning loop, no iterative retrieval. This is deliberate: the validity check has a p95 < 2s budget that loop variance would break; the CI precision/recall gates need stable execution paths; and the threat/self-harm classifier must be auditable, meaning a specific prompt version and model ID produced a specific classification for a specific comment. "The agent decided to check three things and concluded" is not a defensible record when a participation grade or a safety flag is questioned.

Prompts are versioned in-repo; every classification stores prompt version and model ID for reproducibility.

**Agentic execution** — planning loops with tool use — is a separate module that *consumes* the authz-scoped services (§13 `services/`) rather than living inside the gateway. It is reserved for genuinely open-ended, read-only work where the answer requires multiple scoped queries and synthesis: the leadership MCP server (§7.5) is the first such surface, and term-end synthesis is the second candidate. The safety property that makes autonomy tolerable there is that scoping is enforced server-side in the same services a human hits, so an agent can never widen purview, cross an n-threshold, or reach identity regardless of how it plans. Nothing on the student-facing or grading paths is agentic.

### 7.5 Future: MCP server

Roadmap item, designed-for now: a read-only MCP server exposing leadership-scoped query tools ("summarize workload trends across ITEC 600-level this term") that reuses the API's authorization layer — same role scoping, same n-threshold and de-identification rules enforced server-side, so a model client can never see more than the human it acts for.

### 7.6 Design system (prototype → codebase contract)

The Claude Design prototype is the visual and interaction contract; the frontend implements it, it does not reinterpret it.

- `tokens.css` is the single source for palette, type (Literata / Schibsted Grotesk / Spline Sans Mono), spacing, radii, shadow, focus ring, and the global reduced-motion kill switch. No raw hex in components.
- One React component per prototype primitive, with variants rather than copies: WeekEyebrow, PulseTrendChart (single/three-line, cohort mode, term axis, term offset), TrendPair, TrendDuo, RatingHistogram, StatPair, CommentCard (default / flagged-collapsed / flagged-expanded / excluded; optional stream chip, default off), AiPanel, SmallNNotice (instructor and student audiences), ResponseRateBar, LikertInput, ConditionalTextArea (optional/required/bounce), WorkloadSlider, SubmitBar, StateNotice (flat/beat), ResponseCard (instructor/on-behalf), HierarchyNav, AggregateHeader, AttentionList, ExclusionLogRow, PolicyToggle, CaseCard (open/revealed/resolved/false-positive), GuidancePanel, HealthRow, JobRow, MetricBlock, DriftCard, CarePanel, ConfigSection, RegistrationCard.
- Screens: InstructorMondayReport, StudentWeeklySurvey, StudentResults, LeadershipRollup (one template, role-scoped), CareQueue, AdminConsole (five routed sections, one status strip).
- Motion budget: hero line draws once (600ms); everything else 150–220ms; all motion removed under `prefers-reduced-motion`; the Care queue has no motion at all.
- Chart-family decision rule: **TrendPair** wherever benchmarks are present (instructor report, leadership); **TrendDuo** for the two-stream benchmark-free case (student results); single-line for one-stream contexts.

## 8. Data model (core tables)

`institution, college, department, prefix, course, section, term, week, start_letter_map, lti_platform, lti_deployment, user, person, role_assignment, lead_faculty_mapping, enrollment, question_set, question, survey_window, response, answer, classification, summary, instructor_response, moderation_action, exclusion_log, comparison_set, grade_sync, threat_case, audit_log, notification`

Selected constraints:

- Containment: `college → department → prefix → course → section` per §2.1; a department groups one or more prefixes; courses belong to exactly one prefix; sections to exactly one course and one term. Course `level` (UG/GR/DR) derives from the course number; section `length_weeks` and start/end dates derive from the section code via `start_letter_map` — LMS-owned data is never hand-edited in Pulse.
- `person` and `role_assignment` implement §2.1: an assignment carries `person_id`, `role`, `scope_node_id`, and a nullable `reports_to` referencing another **assignment** (never a person or org node). The graph is a forest/DAG over assignments; assignment-level cycles are rejected at write time. Purview is computed from this graph, not from containment.
- `lead_faculty_mapping` maps a person to the courses they lead (one lead per course); a course with no mapping resolves to its department chair.
- `response` is unique per (student, section, week); `answer` rows link to versioned `question` rows; workload is stored as a decimal.
- `classification` is append-only (re-runs create new rows) with prompt/model versioning; moderation state transitions (`flagged-collapsed` → `excluded`/`kept`, with undo) are recorded as `moderation_action` rows, both directions logged.
- `comparison_set` holds named leadership-defined sets; the default per section (same lead's courses, matched length+level, past-referencing) is computed, not stored.
- `instructor_response` records the author and whether it was Lead-Faculty-on-behalf (§5.3), and whether it was AI-seeded.
- `audit_log` is append-only and includes all re-identifications, exclusions and kept-decisions, policy changes, response-on-behalf actions, imports (with their dry-run diffs), and admin config edits.
- Identity separation: instructor/leadership read paths go through views that structurally cannot join to `user` identity columns — enforced in the database, not just the application. Only the Care role's queue path can reach identity, and only via the audited reveal action. The §4.1 invariants are asserted against these views in CI.

## 9. Testing

### 9.1 Unit / integration

- pytest + pytest-asyncio; factory-based fixtures; testcontainers for Postgres.
- **Invariant suite:** the §4.1 visibility invariants as named, automated assertions run against every read path — including purview property tests (Hypothesis-generated supervision graphs with assistant-dean insertions and two-hat people, asserting sibling-lead isolation and correct transitive unions) and section-code parsing tests across the full start-letter map.
- LTI: signed-launch fixtures against a mock platform (issuer keys generated per test run) covering launch validation, clock skew, replay, NRPS paging, AGS score posting and failure/retry.
- Grade math: property-based tests (Hypothesis) for the participation formula across adds/drops/missed weeks.

### 9.2 End-to-end

- Playwright: full student flow (launch → submit → validity rejection → resubmit), instructor flow (report → moderate → AI-drafted then coached response → publish), leadership roll-up and response-on-behalf, Care threat queue with re-identification audit-log assertions.
- An in-repo **mock LMS platform** (small FastAPI app implementing the platform side of LTI 1.3 + NRPS + AGS) and an in-repo **mock OIDC IdP** (standards-compliant discovery/authorize/token/JWKS with seeded leadership, Care, and admin identities) make e2e runs fully self-contained in Compose — no live LMS or institutional IdP needed for CI, and both entry doors (§2) are exercised in every run.

### 9.3 AI evals

- Versioned eval sets for each classifier task (validity, moderation, threat) seeded from synthetic data and grown from admin overrides (§6.1). Cases are typed objects built from the same Pydantic contracts the tasks return (§7.4), so a contract change breaks its evals at type-check time rather than silently passing.
- CI gate: prompt or model changes must meet per-task precision/recall floors; threat/self-harm recall floor is the strictest in the suite (false negatives are the expensive error).

## 10. Non-functional requirements

- **Accessibility:** WCAG 2.2 AA; full keyboard operability inside the iframe; charts carry data-table equivalents.
- **Privacy/compliance:** FERPA-aligned handling; no student PII in logs; secrets via environment/secret store; encryption at rest is deployment responsibility, in transit mandatory.
- **Performance:** survey submit p95 < 2.5s including synchronous validity check; Monday report generation for 500 sections < 30 min. The 2.5s figure and the p95 < 2s classifier budget in §3.3 and §7.4 measure different spans — the whole submit round-trip versus the model call inside it — and are not in conflict. Do not reconcile them into one number.
- **I18n:** UI strings externalized from day one; English only at v1.
- **Licensing hygiene:** dependencies compatible with MIT distribution.

## 11. Decisions and remaining questions

**Settled** (spec review + design sessions 1–6): MIT license; dual-door entry (LTI launch or OIDC) with full purview either way; Friday 18:00 ET window; required-response holds student aggregates, respond-on-behalf at 96h with honest attribution; isolated Care role with the two-action case flow and no reveal dialog; TrendPair/TrendDuo chart family with students never seeing benchmarks; workload as a numeric slider; AI draft + instructor-initiated draft check; role-assignment model with a supervision graph decoupled from containment; week alignment resolved by cohort-mode term axes and hard length matching (§2.2, §5.1); comment grouping by stream everywhere; comments answered — week navigation, kept/excluded lifecycle, harm-type routing.

**Still open:**

1. **Benchmark minimum-N value.** The mechanism is specced (§5.1, distinct from section small-N); the number isn't. Suggest 3 sections and 15 respondents as starting values.
2. **Numeric workload outliers.** Trim/winsorize the displayed mean, show median as headline, or cap the slider lower? Leaning: median as headline, mean secondary.
3. **Care role sourcing at pilot.** Office of Community Standards owns the queue in production; for a pilot before that office is wired in, who holds Care? (A named pilot owner, not Admin-by-default.)
4. **Production "substantive" definition** (§3.3). The classifier replaces the 25-character prototype heuristic; its eval set and threshold need real seeded data before E2 exits.
5. **Kept-decision surfacing** (§5.2 open item). Kept decisions are logged; production should show both directions (Kept / Excluded) in the roll-up moderation log.

## 12. Delivery phases

Phase boundaries below describe *what ships to users when*; §14 is the operative development plan and decomposes into tickets.

- **Phase 1 (MVP):** Epics E0–E4 and E6–E8 — a student can take the survey, credit posts, the instructor gets the Monday report, responds, and the loop closes.
- **Phase 2:** Epics E5, E9–E12 — benchmarks, leadership roll-ups, Care queue, admin console, notifications; E13 hardening gates release.
- **Phase 3 (roadmap):** Per-level custom questions; MCP server; multi-language.
## 13. Repository layout

A monorepo: Python backend, TypeScript frontend, the in-repo mock LMS, and infra together, so `docker compose up` brings the whole system — including a fake platform to launch from — with one command.

```
pulse-surveys/
├── README.md
├── LICENSE                         # MIT
├── pyproject.toml                  # backend deps + tooling (ruff, mypy, pytest)
├── docker-compose.yml              # api, worker, beat, db, redis, mailpit, mock-lms
├── docker-compose.override.yml     # dev-only wiring (hot reload, exposed ports)
├── .env.example                    # documented config surface (§6.3)
├── Makefile                        # up / test / lint / migrate / seed shortcuts
│
├── backend/
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── migrations/                 # Alembic revisions
│   └── app/
│       ├── main.py                 # FastAPI app factory, router mount, SPA static serve
│       ├── config.py               # Pydantic settings (all env-driven)
│       ├── db.py                   # SQLAlchemy engine/session
│       │
│       ├── models/                 # ORM tables (§8), one module per aggregate
│       │   ├── org.py              # institution, department, course_set, course, section
│       │   ├── term.py             # term, week, survey_window
│       │   ├── identity.py         # user, enrollment, role_assignment
│       │   ├── survey.py           # question_set, question, response, answer
│       │   ├── ai.py               # classification, summary
│       │   ├── loop.py             # instructor_response, moderation_action, exclusion_log
│       │   ├── benchmark.py        # comparison_set
│       │   ├── grades.py           # grade_sync
│       │   ├── safety.py           # threat_case
│       │   └── audit.py            # audit_log, notification
│       │
│       ├── views_sql/              # identity-separated read views (§8) as migrations + query helpers
│       │
│       ├── schemas/                # Pydantic request/response contracts (also feeds OpenAPI + MCP)
│       │
│       ├── api/                    # HTTP routers, thin — delegate to services
│       │   ├── deps.py             # auth context, role scoping, n-threshold guards
│       │   ├── lti.py              # login-init, launch, JWKS, deep-linking endpoints
│       │   ├── student.py          # survey fetch/submit, loop-closure view
│       │   ├── instructor.py       # report, moderation, response draft/coach/publish
│       │   ├── leadership.py       # roll-ups, comparison sets, response-on-behalf
│       │   ├── care.py             # threat queue, audited re-identify
│       │   └── admin.py            # observability, config, hierarchy, roles
│       │
│       ├── services/               # domain logic (the real app lives here)
│       │   ├── validity.py         # synchronous comment gating (§3.3)
│       │   ├── grading.py          # participation formula + AGS passback (§3.4)
│       │   ├── reporting.py        # distributions, trend lines, benchmark assembly (§5.1)
│       │   ├── benchmarks.py       # comparison-set resolution, length/level matching, min-N
│       │   ├── moderation.py       # classification routing, exclusion rules (§5.2)
│       │   ├── response_loop.py    # draft/coach/publish, required-response holds (§5.3)
│       │   ├── safety.py           # threat/self-harm routing to Care queue (§6.2)
│       │   ├── retention.py        # configurable purge jobs (§4)
│       │   └── authz.py            # role → hierarchy-node scoping, enforced server-side
│       │
│       ├── lti/                    # pylti1p3 integration
│       │   ├── registration.py     # platform/deployment config, key management
│       │   ├── launch.py           # launch validation, role/context resolution
│       │   ├── nrps.py             # roster sync (enrollment windows, emails)
│       │   ├── ags.py              # line-item creation + score posting
│       │   └── platforms/          # PlatformProfile adapters (§7.3)
│       │       ├── base.py
│       │       ├── canvas.py
│       │       ├── moodle.py
│       │       ├── d2l.py
│       │       └── blackboard.py
│       │
│       ├── ai/                     # the AIGateway (§7.4) — single-shot, typed
│       │   ├── gateway.py          # provider-agnostic client (OpenAI-compatible base_url)
│       │   ├── contracts.py        # Pydantic output models per task (runtime + API + eval fixtures)
│       │   ├── tasks.py            # validity / moderation / summary / draft / draft-check calls
│       │   └── prompts/            # versioned prompt templates, one file per task+version
│       │
│       ├── agents/                 # agentic loops (§7.4) — read-only, consume services/ + authz
│       │
│       ├── mcp/                    # future read-only leadership MCP server (§7.5), reuses authz
│       │
│       ├── jobs/                   # Celery
│       │   ├── celery_app.py
│       │   ├── schedules.py        # window open/close, Monday reports, retention (beat)
│       │   └── tasks.py            # async classification, summary, passback
│       │
│       └── notifications/          # email rendering + SMTP (link-only Monday mail, §5.7)
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json                # React 19 + TS + Vite
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── router.tsx              # TanStack Router
│       ├── api/                    # generated client from backend OpenAPI + TanStack Query hooks
│       ├── lib/                    # auth context, charts (Recharts), formatting
│       ├── components/             # shared UI (rating input, workload slider, trend chart, comment list)
│       └── routes/
│           ├── student/            # survey form, results + response
│           ├── instructor/         # report, moderation, response editor w/ coaching
│           ├── leadership/         # roll-up dashboards, comparison-set management
│           ├── care/               # threat queue
│           └── admin/              # observability, config, hierarchy, roles
│
├── mock-lms/                       # in-repo LTI 1.3 platform for dev + e2e (§9.2)
│   ├── Dockerfile
│   └── app/                        # login/auth endpoints, JWKS, NRPS + AGS stubs, seed courses
│
├── mock-idp/                       # in-repo OIDC provider for dev + e2e (§9.2)
│   ├── Dockerfile
│   └── app/                        # discovery, authorize, token, JWKS; seeded leadership/care/admin users
│
├── tests/
│   ├── unit/                       # services, grading (Hypothesis), authz scoping
│   ├── integration/                # LTI launch/NRPS/AGS against mock platform, testcontainers PG
│   ├── e2e/                        # Playwright specs (§9.2)
│   └── evals/                      # versioned AI eval sets + runners, CI recall/precision gates (§9.3)
│
├── scripts/
│   ├── seed.py                     # demo institution, hierarchy, term, sample sections
│   └── generate_client.sh          # OpenAPI → frontend client
│
└── .github/workflows/
    └── ci.yml                      # lint, typecheck, unit+integration+e2e, eval gates
```

Two structural choices worth calling out. First, `api/` routers stay thin and all real behavior lives in `services/`, so the same logic backs the HTTP API, the Celery jobs, and the future MCP server without duplication — and the authz scoping in `services/authz.py` is the single chokepoint every entry point passes through. Second, the identity-separated read views (`views_sql/`) are shipped as migrations, not just ORM conventions, so the confidentiality guarantee holds at the database level even against a future careless query.

## 14. Development plan

### 14.1 How the plan is cut

After a single foundations epic (E0), **epics are vertical feature slices**, not functional layers. Each epic delivers a demonstrable capability end-to-end — schema slice, service logic, API, UI, and its own tests — so that at every epic boundary the system does something new that a person can see. Testing and security review are not epics; they are part of every epic's definition of done. The functional layering in §13 describes where code *lives*; this section describes the order work *ships*.

### 14.2 Definition of done (applies to every epic)

1. **Tests land with the feature:** unit tests for new services, integration tests for LTI/OIDC/AGS surfaces touched, and at least one Playwright e2e path through the new capability against the mock LMS/IdP. CI green is a merge condition, not a milestone.
2. **AI evals updated** whenever an epic touches a model task: eval cases added for the new behavior, and CI precision/recall gates still pass.
3. **Security review by a separate agent:** each epic's diff is reviewed by an independent Claude Code agent session running an adversarial checklist — authz bypass across the role hierarchy, identity leakage past the §4/§8 separation, LTI/OIDC token handling, injection, audit-log completeness — with findings triaged before merge. Epics touching confidentiality-critical paths (marked ⚠ below) additionally require line-by-line **human** review of the security-relevant diff; agent review supplements human judgment there, never replaces it.
4. **Accessibility in-slice:** new UI meets keyboard and screen-reader basics at merge; the full WCAG 2.2 AA audit in E13 is a verification pass, not a first pass.
5. **Docs:** README/config-surface updates for anything an operator or developer would need.

### 14.3 Epics

Hours are focused engineering time for one senior engineer, solo vs. maximizing Claude Code, ±20%. Each epic's estimate includes its testing, eval, and review work per §14.2. "Ticket breakdown" indicates how each epic naturally decomposes into scoped tickets.

**E0 — Foundations** (solo 135h / CC 63h)
The only horizontal epic: monorepo scaffold, Compose stack, CI pipeline with test/lint/typecheck/eval gates, Dockerfiles, config surface, core schema and migrations (org, term, identity aggregates), `AIGateway` shell with typed Pydantic contracts and one working task round-trip, authz skeleton, **mock LMS** (LTI 1.3 login/launch, JWKS, NRPS + AGS stubs, seed data), and **mock OIDC IdP** (discovery, authorize, token, JWKS, seeded users). Exit: `docker compose up` yields a launchable-into, loggable-into, testable system that does nothing yet.
*Ticket breakdown:* repo+CI; Compose+Dockerfiles; core schema; mock LMS; mock IdP; AIGateway shell + task contract models; authz skeleton; seed script.

**E1 — Entering the app** ⚠ (solo 100h / CC 60h)
Both doors work end-to-end: LTI launch validation (state/nonce, platform storage for cookieless iframes), automatic section/enrollment provisioning from launch plus the hourly roster sync, section-code parsing against the start-letter map (derived length, start/end dates, modality; §2.2), course-level derivation from course numbers, role resolution from `id_token` claims and the app-owned assignment model, OIDC web login against the mock IdP, unified session model so both doors resolve to the same identity and correct purview. Exit: a student, an instructor, and a Dean each land on the right (empty) view from either door, and a synced section shows correct derived dates.
*Ticket breakdown:* launch flow; cookieless session; section provisioning + code parsing; hourly roster sync; OIDC login; role/purview resolution; dual-door identity merge.

**E2 — Weekly survey & validity** (solo 70h / CC 34h)
The five-question form (Likert, conditional-required text, workload slider), survey-window scheduling from term dates (Friday 18:00 ET open), synchronous AI validity gating with fail-open on provider timeout, one-open-survey rule, resubmission within window. Exit: a student submits a valid response; "it was okay" is bounced with immediate feedback.
*Ticket breakdown:* window scheduler; survey form UI; submit API; validity task + prompts + evals; fail-open path; resubmission rules.

**E3 — Grade passback** (solo 55h / CC 30h)
AGS line-item creation, participation formula (valid weeks ÷ elapsed weeks, enrollment-windowed), weekly recompute job, score posting with retry/failure handling, Hypothesis property tests across adds/drops/missed weeks, `PlatformProfile` seams for AGS quirks. Exit: mock-LMS gradebook shows correct percentages across enrollment edge cases.
*Ticket breakdown:* line-item management; formula service + property tests; posting job + retries; platform adapter seam.

**E4 — Instructor Monday report** (solo 85h / CC 42h)
Report generation job at window close, TrendPair with course-week axis and term-week sub-label, per-stream distributions, workload mean/median, response/validity rates, per-stream AI summaries under the §5.1 contracts (criticism preserved, counts stated, generated even in small-N), grouped comment lists each led by its stream summary, week navigation across published weeks, small-N suppression of raw comments (§4) including cumulative batched release and flag concealment (§5.2). Exit: instructor opens a real Monday report for a seeded section with a diverging two-stream story.
*Ticket breakdown:* report job; distribution + dual-axis queries; summary task + prompts + evals; report UI; week navigation; small-N logic (⚠ human review on the suppression queries).

**E5 — Benchmarks & comparison sets** (solo 70h / CC 36h)
Default comparison-set resolution (same lead's courses, matched length+level from derived attributes), **past-referencing benchmarks** spanning current and prior terms, named-set management UI where invalid length/level combinations are impossible, university-wide line within length+level cohort, benchmark min-N suppression (distinct threshold), overlay rendering in both TrendPair panels, cohort-mode term-axis aggregates, student-view exclusion of all benchmark lines (invariant §4.1.1). Exit: an instructor sees three lines per panel benchmarked against prior terms; a student provably sees two lines and no benchmarks.
*Ticket breakdown:* set resolution service; historical benchmark queries; named-set CRUD; panel overlays + cohort mode; min-N rules; invariant tests.

**E6 — Moderation & exclusions** (solo 65h / CC 33h)
Moderation classification at window close with harm-type routing (§5.2): instructor-abuse to the Lead Faculty review queue, welfare signals to Care regardless of thresholds. Full lifecycle — flagged-collapsed, excluded-with-undo, kept-with-undo (both directions logged), excluded text muted-but-visible to the instructor, reason-required exclusion of unflagged comments, small-N flag concealment with the neutral participation trace, exclusion log at the Lead Faculty prefix scope and above. Exit: the anti-cherry-picking trail is visible up-chain, and a welfare-flagged comment in a 3-response week provably reaches Care with no trace in the instructor view.
*Ticket breakdown:* moderation task + evals; harm-type routing; lifecycle state machine + undo; LF review queue; small-N concealment tests; exclusion/kept log views.

**E7 — Response loop** (solo 70h / CC 36h)
Instructor response editor with non-anonymous posting and as-students-see-it Edit path, AI draft-from-themes, instructor-initiated draft check (re-runnable, clears on edit), publish flow, required-response policy per prefix, aggregate hold with 48h delinquency surfacing, respond-on-behalf enabling at 96h with honest attribution, release of held aggregates. Exit: required-mode section shows nothing to students until a named human publishes.
*Ticket breakdown:* editor UI; draft task; coaching task + evals; publish/hold state machine; reminders; on-behalf flow + attribution.

**E8 — Student loop closure** (solo 35h / CC 16h)
Student results view: own-section aggregates, published comment set, instructor response; next-launch surfacing. Exit: the full weekly loop demos end-to-end from one student's seat.
*Ticket breakdown:* results UI; published-set assembly; launch-time routing.

**E9 — Leadership hierarchy & roll-ups** ⚠ (solo 110h / CC 55h)
The people graph and supervision model in full: People & reporting editor (top-down build), Lead Faculty mapping table with CSV import/export and dry-run diffs, purview computation over the assignment DAG (assistant-dean insertions, two-hat people, sibling-lead isolation), multi-role switcher / union purview with multi-root nav, roll-up dashboards at every level on the term axis with cohort selection, hierarchy and by-lead tree modes (by-lead for chair+ only), read-only section drill-down into the Monday report, n-threshold enforcement at the aggregation being viewed. Exit: the assistant-dean worked example (§2.1) resolves correctly from either door, and Hypothesis-generated graphs prove sibling isolation and transitive unions.
*Ticket breakdown:* people graph editor; LF mapping + CSV dry-run; purview service over the DAG (⚠); role switcher; roll-up queries + cohort mode; tree modes; scope-boundary property tests.

**E10 — Care queue & safety** ⚠ (solo 60h / CC 40h)
Threat/self-harm classification routing, suppression from all instructor/leadership views, Care-only queue UI with the two-action case flow (reveal identity / false positive, resolve-only-after-reveal with disposition note), automatic identity-access audit logging, Admin-visible access log and open-case count/age aperture (without content), configurable stale-case escalation notice, false-positive feed into evals. Highest human-review burden in the plan; the threat-recall eval floor is set and validated here. Exit: a seeded threat comment reaches only Care, a false positive closes without identity ever surfacing, and every reveal leaves an audit row.
*Ticket breakdown:* safety routing; suppression proofs; queue UI + case state machine; reveal + audit (⚠ line-by-line); resolution notes; count/age aperture + escalation notice; recall-floor eval work.

**E11 — Admin console & observability** (solo 70h / CC 32h)
LTI health and launch-outcome log, job dashboard, AI provider metrics and spend, classifier drift panel with override-to-eval feed, full configuration surface (§6.3), LTI platform registration UI. Exit: an operator can diagnose a failed launch and a stuck job without shell access.
*Ticket breakdown:* launch log; job dashboard; AI metrics; drift panel; config UI; registration UI.

**E12 — Notifications** (solo 25h / CC 10h)
Email rendering and SMTP delivery, link-only Monday instructor mail, optional student open/published notices, per-institution toggles, Mailpit-verified e2e. Exit: Monday morning mail arrives with numbers and a link, never content.
*Ticket breakdown:* templates; delivery + toggles; e2e via Mailpit.

**E13 — Hardening & release** ⚠ (solo 60h / CC 35h)
System-level passes that only make sense against the whole: full WCAG 2.2 AA audit, retention job + purge verification, load test (report generation at 500 sections), end-to-end FERPA data-flow review, dependency/license sweep for MIT compatibility, operator documentation, cut v1.0. This epic exists *despite* integrated testing, not instead of it.
*Ticket breakdown:* a11y audit; retention + purge tests; load test; FERPA review (⚠ human-led); license sweep; docs; release.

### 14.4 Totals and sequencing

| | Solo | With Claude Code |
|---|---:|---:|
| Total | **~1,005h** (±20%) | **~518h** (±20%) |

Dependencies are mostly linear through E4 (E0 → E1 → E2 → {E3, E4}), after which E5–E8 can interleave and E9–E12 are parallelizable in any order; E13 is last. The totals rose from the earlier ~935/~480 estimate because the org model deepened materially in design review: a supervision graph decoupled from containment, DAG purview with property testing, dual week axes with cohort aggregation, past-referencing historical benchmarks, and the kept/excluded moderation lifecycle with harm-type routing. The multiplier varies by epic for the reasons in the estimates discussion: generation-heavy slices (UI, notifications, scaffolding) compress ~2.5–3×; slices bounded by external-protocol debugging (E1) or by human security review (E10, E13) compress ~1.4–1.7×. Certifying against real LMS platforms beyond the mock (Canvas first) is additional integration work per platform — roughly 20–30h for the first real platform, less for each subsequent one, in either column.
