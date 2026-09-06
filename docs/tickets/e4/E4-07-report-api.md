# E4-07 — The report API

**ID:** E4-07
**Branch:** `e4/report-api`
**Depends on:** E4-02, E4-03, E4-04
**Lane:** heavy — `backend/app/api/` is a named row.
**Security-relevant:** the first instructor-facing read routes in the
product. Authorization scope, §4.1 item 7's chokepoint, and the rule that
nothing here widens what E4-03/E4-04 decided to expose.

## Context

`backend/app/api/instructor.py`, thin over a read service (§13's thin-router
rule): the Monday report payload for one of the instructor's own sections
and one published course week, and the published-week list that week
navigation pages across (breakdown decision 6: published = window closed,
clock service currency).

Authorization in E4 is deliberately narrow: **the requesting session's own
taught sections, nothing else.** The `teaching_instructor` view is the
source; leadership's read-only drill-down is E9's, and the chokepoint rule
(a request resolves only its own authenticated subject's scope) is already
the carried law. Any section id outside the session's own teaching set is a
refusal, driven from the session — not a parameter check.

This ticket owns §4.1 item 7's assertion (breakdown decision 4): the payload
carries the `comparison` member from day one, populated only through one
suppression helper enforcing **both** configured minimums —
`benchmark_min_sections_default` and `benchmark_min_respondents_default`
(§11 question 1 names the pair; a helper reading one of two thresholds is
the closed-set defeat the mistakes ledger records). The invariant test
plants figures on both sides of each minimum and proves suppression and
passage at the payload boundary. E5's real benchmarks flow through this
helper or fail their own invariant.

Read first: SPEC §5.1, §4.1 (items 6 and 7), §2.2; breakdown decisions 4, 5
and 6; the payload sketch in this breakdown's README;
`backend/app/api/student.py` and `deps.py` (the session dependency chain);
`backend/app/services/survey_read.py` (the module-header discipline for a
read module's §4.1 predicate).

## Scope

- The read service assembling the payload from E4-03's views, E4-04's
  comment path, and E4-02's summary table — a new module under
  `backend/app/services/` whose ADR says why no existing module fits
  (`survey_read.py`'s own header is the argument's template).
- Routes: the report for (section, course week), and the published-week
  list. Both behind the session dependency; both refusing out-of-scope
  sections identically to nonexistent ones (no existence oracle).
- The Pydantic response schema in `backend/app/schemas/` — the authority
  over the README's sketch from the moment this merges (decision 5).
- The item-7 chokepoint and its invariant assertion, marked `invariant`, in
  the isolated pass.
- The week axis done right: course week with the term-week sub-label value
  (§2.2), derived server-side so every consumer agrees.

## Acceptance criteria

1. An instructor reads her own section's report; a section she does not
   teach — including one that does not exist — refuses with the same status
   and body, asserted as a pair.
2. A student session and a leadership session are both refused these routes
   (leadership's path is E9's drill-down, not this route), driven per role.
3. The published-week list contains exactly the closed weeks, both
   boundaries driven on the dev clock: the week whose window closes tonight
   is absent now and present after.
4. The payload's comment and summary members are exactly what E4-04 and the
   summary table return — a test proves the service adds no field, no
   count, and no ordering information beyond them (no widening at the
   assembly layer, §4.1 item 6's spirit).
5. The item-7 invariant carries its own positive control, because in E4 the
   member is otherwise always empty and an assertion on absence alone would
   survive deleting the helper: a planted figure clearing **both** minimums
   appears in the serialized payload, and the same figure under either
   minimum — sections and respondents each driven separately — is absent.
   The helper is the only way to populate the member, proven structurally
   (the member's type is private to the helper's module, or an equivalent
   the ADR defends).
6. An absent summary row renders as the schema's explicit absent state,
   never an empty string pretending to be a summary.
7. A zero-response published week returns the full shape — zero rates,
   empty distributions, the week in navigation — because a silent 404 there
   would make "nobody responded" unrenderable.
8. The response schema and the README sketch are reconciled: divergences are
   deliberate, listed in the PR body, and the sketch section gets a pointer
   to the schema as authority.

## Decisions this ticket settles

- **The read-service module's name and boundary** — and the ADR must also
  say where E9's drill-down will attach (it renders this same payload
  read-only), so E9 extends rather than forks it.
- **The refusal status pair** (404 for both out-of-scope and nonexistent is
  the recommendation, matching the no-oracle rule the dev routes already
  follow).
- **How the item-7 helper is made structurally unavoidable** (criterion 5's
  "or an equivalent") — the mechanism the invariant relies on, chosen with
  the awareness that closed-set guards get defeated one level out; name the
  catalog, not the concept.

## Known traps

- **This route's session handling is the doors' work, not new work** — the
  Bearer-session behavior and cookieless-iframe realities from E1 are
  settled; nothing here invents session mechanics, and the e2e that proves
  the route rides E4-11.
- **The published-week boundary crosses clock currencies** — ADR 0142's
  family. Window close is the clock service's; tests pin it.
- **An existence oracle by timing or by shape** — the refusal pair must be
  indistinguishable in body, not merely in status.
- **The invariant suite's isolated pass** treats an empty collection as
  failure but not a shrunken one — the carried collection-floor gap. Name
  the new invariant tests in the PR body so the exit ticket's count has a
  baseline.

## Out of scope

- Any leadership or purview read — E9.
- Comparison data itself — E5 fills the guarded member.
- The frontend consuming this — E4-11.
- CSV or any export — no epic has asked for one; §4.1's export language
  becomes real when one exists.
