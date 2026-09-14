# E5 — deferred

What an E5 ticket chose not to fix while it was in the file, with an owner and
the condition that closes it. A PR that defers something adds it here in the same
PR; E5-14 runs the cleanup pass over this file at the epic exit.

A deferral is a decision, not a note. Each entry says what is not enforced, why
it was left, who owns it, and what "done" means — a gap recorded only as a
comment in the file that works around it is `docs/MISTAKES.md` entry 48.

## The design brief still maps the two comparison lines to a colour that fails the contrast floor

**What is not enforced.** `docs/DESIGN_BRIEF.md`'s chart mapping reads
"Benchmark = mist, dashed. University = mist at 50%, dotted", and
`design/PulseTrendChart.dc.html:17-18` draws exactly that. E5-07 ships those two
lines in `--spruce-60` instead, because `--mist` measures 2.58:1 against paper
and WCAG 2.2 SC 1.4.11 asks 3:1 of a graphical object that carries meaning —
mist at 50% over paper is nearer 1.6:1. The reading, and the E4 precedent it
follows (the hero line and the term-week sub-label were corrected the same way
in the E4 boundary round), are written into `instructorReportTrend.css`'s colour
paragraph and pinned by `PulseTrendChart.overlays.test.tsx`. So the code is
measured and the brief is not, and the two now disagree on this one line.

**Why it was left.** The brief is the owner's document and E5-07 is a component
ticket. Shipping a line an instructor with low vision cannot see was not an
option, and editing the owner's brief inside a light-lane build is not this
ticket's to do. Naming the divergence is the honest middle.

**Owner:** the brief's owner; E5-13 is where an E5 ticket next reads this
surface and can carry the edit if it is ruled.

**Done when:** either the brief's mapping names a token that measures at or above
3:1 on paper for both lines, or the ruling is recorded that mist stands and this
ticket's substitution is reverted with the measurement stated as accepted.

## E5-07's stroke pins live beside E5-07's tests rather than in the report's two pin modules

**What is not enforced.** `reportContrastTokens.test.ts` and
`reportMockupFidelity.test.ts` are where the report's stylesheet-only rulings are
pinned, and neither reads the two comparison-line rules E5-07 adds; those pins
are in `PulseTrendChart.overlays.test.tsx` instead. A reader looking for "every
contrast correction on the report" has two places to look rather than one.

**Why it was left.** Three frontend tickets (E5-07, E5-08, E5-09) build in
parallel against the same breakdown, and both pin modules read several
stylesheets each. Adding to a shared module from a parallel branch is the
same-file merge the breakdown's parallel rules exist to avoid, and the pins are
worth more beside the tests that explain them than they are worth being in one
file a week earlier.

**Owner:** E5-13, which already reads every surface E5 ships.

**Done when:** the overlay stroke and contrast pins are in
`reportContrastTokens.test.ts` with the rest of the measured corrections, or the
two-module split is recorded as deliberate with the rule that says which pin goes
where.

## A member that says `suppressed: false` and carries no `points` crashes the panel

**What happens.** `drawnPoints` returns `undefined` for a series whose flag is
exactly `false` but whose `points` key is missing, and the spread in
`axisWeeks` then throws, so the panel render fails. The security re-pass of
the fail-closed fix (`02af6cf`) named it and judged it a robustness note
rather than a finding: the failure withholds a figure rather than disclosing
one, and it needs a payload that sends the flag without the array.

**Why it was left.** The fix round's declared stopping rule covered one
finding; this is not that finding, and the shape that triggers it cannot come
from the fixtures this ticket ships.

**Owner:** E5-10, the ticket that wires the real payload — the place a
malformed first-party payload becomes possible.

**Done when:** a flag-without-points member renders the suppressed treatment
(or another stated treatment) rather than throwing, pinned by a test beside
the malformed-flag pair.

**Resolution, 2026-09-14 (E5-10) — closed.** The reader that returned
`undefined` is gone. E5-10 respelled the overlay props as the wire spells them
(ADR 0171), and the week list a series contributes is now built by one function
that asks whether the payload sent an array at all before reading it: anything
that is not one — a missing `points` key, a `null`, an object, a member that is
itself `null` — yields no drawable week, and a series with no drawable week
renders E5-07's suppression notice. The panel draws its own line and its axis
over the section's whole term either way, which is the half the crash took away.
Pinned in `PulseTrendChart.overlays.test.tsx` under "a member the payload sent
without its weeks": the four malformed shapes, and the axis assertion that says
the panel rendered rather than merely not throwing. The guard was verified by
mutation — removing the array check reds those four and thirteen others.

## The benchmark definer's reach has no pinned equality (E5-03)

`pulse_benchmark_definer` owns the two benchmark set functions and holds
column-grain `SELECT` on `response`, `answer`, `question`, `section`, `term` and
`week`. The other three definer owners each have a test asserting their grants
as an **equality** — `test_the_resolve_definers_privileges_are_exactly_the_point_lookups_it_answers`
and its roster sibling — so a later ticket widening one of those owners is a red
rather than a diff. This owner has no such test: its entry in
`IDENTITY_DEFINER_ROLES` names the gap, and E5-03's own suite asserts what the
functions answer rather than what their owner may read. **Done when** a test
asserts, as an equality in both directions, the exact set of
`(relation, column)` pairs `pulse_benchmark_definer` holds `SELECT` on, with no
column of `user`, `user_identity` or `person` among them. Owner: E5-04, which is
the next ticket to touch this door; a security round on E5-03's pull request may
pull it earlier.

**Resolution, 2026-09-13 (E5-04) — answered and closed.** The missing half was a
record rather than a test: an expected set transcribed from
`benchmark_definer_v001.sql` would assert that the SQL equals itself
(`docs/MISTAKES.md` entry 19), which the sibling equality test refuses in its own
docstring. So ADR 0165 gains an amendment naming the exact eighteen
`(relation, column)` `SELECT` pairs — `response (id, user_id, section_id,
week_id)`, `answer (response_id, question_id, rating, workload_hours)`,
`question (id, kind, stream)`, `section (id, term_id, start_date)`,
`term (id, start_date)`, `week (id, number)` — and states that not one of them is
a column of `user`, `user_identity` or `person`. The list was checked against
both the SQL file and the migrated catalog before it was written down: eighteen
pairs, `SELECT` only, and nothing held at the grain of a whole relation. The
equality is derived from that sentence rather than from the SQL, in
`ROSTER_DEFINER_PRIVILEGES`' shape, and the relation-grain test E5-04's red run
shipped stands beside it.

## The benchmark service spells two statements `views_sql/queries.py` also holds (E5-04)

**What is not enforced.** `app.views_sql.queries` carries typed wrappers for
`benchmark_set_week` and `benchmark_set_rating_week`, written there by E5-03 "so
that E5-04 has no reason to spell a statement of its own".
`app.services.benchmarks` spells them anyway, because
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py` excuses
exactly one importer of that module — `backend/app/services/authz.py` — and reds
every other module under `backend/app/` that imports it. So the same two
statements exist in two files, and a change to one can miss the other. Nothing
about confidentiality rests on the duplication: neither function is a relation
that sweep polices, no exemption was added, and both copies call the same
`SECURITY DEFINER` bodies with the same bound array.

**Why it was left.** The three ways to remove it are each larger than this
ticket. Moving the wrappers out of `queries.py` breaks E5-03's own suite, which
reads them there by name. Widening the import exemption to a second module is a
change to a guard, which CLAUDE.md puts in its own reviewed pull request and
which this file's own doctrine treats as the repair that looks smallest under
time pressure. Routing the call through `authz.py` puts benchmark aggregation in
the authorization chokepoint, where it does not belong. E5-03's comment asserting
the opposite has been corrected in place; the duplication itself is named here.

**Owner:** E5-14 at the epic exit, which is the next pass over this surface.

**Done when** either the two statements have one home that both the service and
the sweep accept, or a record states that two copies is the intended answer and
says which file is authoritative.

## The benchmark views do not filter a response's validity (E5-03)

SPEC §3.3 classifies a submission as valid or not, and `response.is_valid`
records the verdict. Neither `report_rating_distribution` nor `report_workload`
filters on it, and E5-03's four cohort views and two set functions follow them,
so a benchmark counts every stored response exactly as a section's own report
does. That is consistency rather than a decision: nothing in E5-03's ticket, the
E5 breakdown or the ruling on `docs/disputes/E5-03-01.md` says whether a
comparison figure should be computed over valid responses only, and making the
benchmark disagree with the figure it is drawn beside would be a change to what
both numbers mean. **Done when** the question is answered in the open — either
"a comparison figure counts every response, as a section's own figures do,
recorded in a sentence" or a `_v002.sql` per view plus the same filter in both
function bodies. Owner: E5-04, which is where comparison policy lives; E5-08
reads the workload figures and would inherit the answer.

**Resolution, 2026-09-13 (E5-04) — answered in the open and closed.** A benchmark
figure counts **every stored response, exactly as the section's own report
figures do**; `response.is_valid` is not filtered. The reason is the one this
entry names: a comparison figure and the section figure drawn beside it are read
off the same chart, and computing them over different populations would change
what both numbers mean without anybody saying so. The first of the two answers
this entry offered is therefore taken — the sentence, not a `_v002.sql` — and it
is recorded in the module docstring of `backend/app/services/benchmarks.py`,
where the figures are computed. No view or function body changes. E5-08 inherits
the answer, and a later decision to filter validity is a change to both the
benchmark views and the report views together.

## A course week assumes a section starts on one of its term's week boundaries (E5-03)

The course week these views key on is derived as
`week.number - floor((section.start_date - term.start_date) / 7)`. That is exact
for every section §2.2's start-letter map produces, because each start date is a
Monday a whole number of weeks after the term's first, and the seeded worlds and
the property test over all twenty cohorts agree with it. A section whose stored
start date fell mid-week — which no writer produces today and no constraint
forbids — would be keyed to the week its start rounds down to, silently. **Done
when** either a database constraint makes a mid-week section start unstorable,
or a sentence records that the derivation rounds and that this is the intended
answer. Owner: E5-14 at the epic exit, unless a roster ticket writes a start
date from a platform first.

## Three cohort views still pair whole-week counts with subset figures (E5-04)

**What is not enforced.** The contributor-count rule E5-04's fix round
established — a figure is sealed against counts of its own contributors —
is applied everywhere the service reads: the two set functions and
`benchmark_cohort_term_axis`, all in `_v002` bodies. The three sibling
views (`benchmark_cohort_week`, `benchmark_cohort_rating_week`,
`benchmark_cohort_rating_term_axis`) still carry the week's overall
`respondent_count`/`section_count` beside figures computed over a subset
(rating rows per stream; workload rows over hours-carrying responses).
Nothing under `backend/app/` reads any of the three today, so no live path
can seal a figure with the wrong counts.

**Why it was left.** The fix round's declared stopping rule covered the
reviewed findings, all on read paths that exist; widening three unread
views would have been new surface with no consumer and no test to prove it
against.

**Owner:** the first ticket that reads one of the three (E5-05 reads
through the service, so in practice E5-06's preview or E9's dashboards);
E5-14 re-checks at exit. **Done when** any consumer of these views seals
figures only against contributor counts the view itself carries (a `_v002`
per view, the established shape), or the views are retired unread.

## The benchmark-history self-check scopes on section codes without a term filter (E5-12)

**What is not enforced.** `the_cohort_recount(session, section_codes)` counts
rows for the sections whose `lms_section_code` is in the list it is handed,
with no term predicate. Section codes recur across terms by design (§2.2's
letters are per-term data), so a future term reusing one of the prior world's
codes would fold into the recount silently. Today the mock world's codes are
unique across terms, so nothing reachable is wrong — this is an honesty gap
in a development self-check, found by the E5-12 security review and judged a
note rather than a finding.

**Why it was left.** The recount's contract was ruled during the build and
the tests bind to it; narrowing it is a contract change with no wrong answer
it corrects today.

**Owner:** E5-14's cleanup pass; earlier if a ticket seeds a term that reuses
a code. **Done when** the recount resolves sections the way the seeder itself
does — by `(course, term, code)` — or a sentence records that the dev worlds
keep codes unique and why that is acceptable.

## The named-set API's eight refusal sentences sit outside the copy inventory (E5-06)

**What is not enforced.** `backend/app/copy/leadership_sets.py` holds the eight
sentences `app.api.leadership` refuses with — the role gate's, the unknown set's,
the other leader's set, and the five the database's constraints are translated
into — and publishes an **empty** `COPY` mapping, so the shipped-copy inventory
enumerates the module and collects none of its strings. SPEC §4.1 items 4 and 5
are therefore asserted over none of the eight: nothing sweeps them for vocabulary
about a person, and none of them counts toward a surface's confidentiality line.

**Why it was left.** The inventory governs a key by its surface prefix, and
leadership set management is not a governed surface yet. A key published under a
`leadership_sets.` prefix is refused by the inventory's own totality rule — a
prefix no surface claims is a red rather than a silence, which is the rule
working — and the governance row is on the other side of the test wall from this
ticket. This is the position the report API's two refusals sat in until E4-12,
one step further along: the sentences are in the registry package, where the
application reads every user-facing string from one place, rather than written at
their raise sites.

**Owner:** E5-13, whose scope already names "set-management copy". **Done when**
the eight are published as `CopyEntry` values under a prefix the inventory's
governance map claims, with the surface placed in one of its two maps — the one
that carries item 5's line or the one that records why it owes none.

## A deleted comparison set leaves no trace anywhere (E5-06)

**What is not enforced.** E5-06 writes no `audit_log` row (ADR 0174), so what
records a write is the set's own row: the creator and `created_at` on a create,
`updated_at` on an edit. A delete removes the row, and after it nobody can answer
who deleted a named set, or when, from the database. The ticket's fourth
acceptance criterion asks for "the log row for each write"; for the two writes
that leave a row it is met by that row, and for the delete it is not met and is
not faked.

An edit records that the set changed and not what it changed from, which is the
same gap one level down: a set's history is not reconstructible.

**Why it was left.** ADR 0174 has the argument in full. The short version is that
the existing machinery is the Care identity reveal's — one `AuditAction` member,
a `NOT NULL` subject naming the student whose identity was revealed, no privilege
at all for the role every request runs on, and a single `SECURITY DEFINER`
writer. A set write reaching it needs the action family widened, the subject made
nullable, and either an `INSERT` granted to `pulse_app` or a second definer
function. That is a change to the audit guarantee and belongs in a change whose
subject is that guarantee.

**Owner:** E10's audit review surface. **Done when** `audit_log` carries a
non-reveal action family with a nullable subject and a sanctioned writer for it,
and the named-set writes use it — or a record states that set definitions are not
audited events and amends the criterion.

## E5-06's preview reads none of the three unread cohort views (E5-04)

**What is not enforced.** Nothing new. This is a correction to the owner line of
"Three cohort views still pair whole-week counts with subset figures (E5-04)",
which names "E5-06's preview or E9's dashboards" as the likely first reader. The
preview E5-06 shipped answers two counts — the membership rows, and
`len(resolve_named_set(...))` — and reads none of `benchmark_cohort_week`,
`benchmark_cohort_rating_week` or `benchmark_cohort_rating_term_axis`. So that
entry is still open with no reader, and E5-06 is not its owner.

**Why it was left.** The entry belongs to E5-04 and a later ticket does not edit
another's paragraph; the correction is recorded here instead.

**Owner:** unchanged — the first ticket that reads one of the three. **Done
when** that entry's own done-when is met.
