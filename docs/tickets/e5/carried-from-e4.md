# Carried from E4 into E5

Things E4 decided or deferred that later work has to know, per SPEC §14.1:
one entry per thing, each with an owner and what it looks like to be
finished. This is a hand-off note, not a ticket; the next breakdown
schedules the work, and an entry here is what that breakdown has to have
read first. Created by E4-15. Entries point at the record that owns the
detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e4/carried-from-e3.md` not closed inside E4, plus every entry of
`../e4/deferred.md` still open after E4-15's cleanup pass, plus everything
the E4 boundary reviews found and did not fix inside the epic, appears
here.** The demonstration is the ledger below: every source entry is named
with what happened to it, in the source file's own order. Nothing was
dropped silently.

## The ledger: every `carried-from-e3.md` entry, dispositioned

**Closed inside E4** (each closure recorded in the source file itself, with
what closed it): the credit-rule explanation's instructor half (E4-12); the
comment de-anonymization statement's E4 half (E4-04's ADR 0153, completed
at the boundary — the entry below); the gradebook's two strings (E4-12);
the launch-replay purge (E4-14); the Care landing docstring (E4-13); the
student surface's string convention (E4-12); the copy collector's
symlinked-directory gap (E4-12); the week eyebrow's course length (E4-17,
taken after the 2026-09-07 ruling).

**Carried through unchanged** — the source entry's owner and done-when
govern, and nothing about them moved in E4: the roster sync's unbounded
token-acquisition dial; the `azp`/multi-valued-`aud` launch handling and
the per-launch JWKS fetch (both re-affirmed untouched by the E4 boundary's
protocol sweep); the rewound-clock family; the flaky fail-closed framing
test; `post_score` returning nothing; provisioning's docstring-only
separation; the rehoming of the pinned-resolution adapter and Link parser;
the clock routes' missing origin check; the signing-key runbook (E13);
ruff's `py313` target (the next ruff bump); and everything
`carried-from-e3.md`'s own ledger carried through from E2 — the
registration chokepoint's CSP endpoint, the squatted section binding, the
web-login linkage provisioning, logout and back-channel logout, the
local-account fallback, the two registration-write blind spots, the
generative purview note, the bounced-verdict cap and aggregation halves,
the unproven structural battery rows, the bounce that names no position,
the self-hosted font licences, the rewound-clock resubmission 500, the
model identifier in three untied places, the floor-headroom variance
point, and the bounced-comment-before-harm-screening hook — all owned by
epics E4 never touched, per that file.

**Re-carried below with a new dated fact:** the `PERSON_TABLES` standing
question, the TypeScript 7 pair, the session-read sweep's limits, the
denial-inventory and collection-floor class, and the de-anonymization
statement's E6 half.

`../e4/deferred.md` holds six entries still open after the cleanup pass —
the held-note type, the forged block boundaries, the moderation tie-break,
the §6.2 threat class, the course label's two homes, and the landing
strings — re-listed below with what the boundary added to each.

## The de-anonymization statement — E4's half closed, E6's still owed

E4's half closed at the boundary, and it changed what it suppresses a third
time: the whole-epic privacy pass found the quiet-week summary paraphrasing
the very comments the release later shows verbatim, so prose-matching could
re-attach a released comment to its week beside the gradebook ledger. The
ruling of 2026-09-09: below the threshold a summary names themes only,
enforced by a store-time guard (ADR 0162); ADR 0153's amendment carries the
corrected floor claim and the named residual (theme-level correlation
remains). **Owner:** E6, which still owes the same written statement for
its moderation views — and E6 must also read ADR 0162 before writing the
first moderation view, because a reviewer decision displayed beside a
released comment is a new instance of the same channel.
**Done when:** unchanged from the source entry, for E6's surfaces.

## The held-note type is a free string (`../e4/deferred.md`)

Unchanged; owner E6, in the ticket that writes the moderation states.

## A comment can forge block boundaries in the summary prompt (`../e4/deferred.md`)

Unchanged; owner: whichever ticket next changes the multi-comment rendering
(E7's draft and draft check are the first candidates). The boundary adds
one fact: there are now two live summary prompt versions, and a rendering
change must land in both or say why not.

## `moderation_state` has no tie-breakable ordering (`../e4/deferred.md`)

Re-affirmed accurate by the boundary's data-model review, standing.
**Owner:** E6, before the first writer, not after.

## SPEC §6.2's threat class is suppressed nowhere yet (`../e4/deferred.md`)

Unchanged in substance; the boundary marked its tripwire test into the §4.1
isolated pass, so retiring the alarm now reds a guarded gate. **Owner:** E6.

## The course label is composed in two modules (`../e4/deferred.md`)

Still open, and the owner line aged: E4-17 merged without touching either
copy, so it is no longer a candidate. **Owner:** whichever ticket next
changes the label's form; E4-07's pull request still carries the promotion
proposal, and `app/services/enrollment_windows.py` (ADR 0161) is now the
worked example of exactly that promotion done under review.
**Done when:** unchanged.

## The landing views' sentences sit outside the inventory (`../e4/deferred.md`)

Unchanged; owner: the next epic to touch the landings — E9 first candidate.

## The Monday summary walk is serial, and §10's budget does not fit it

Found by the boundary's data-model review: 500 sections × 2 streams is
about 1000 sequential provider calls ≈ 33 minutes at §7.4's own p95 budget,
against §10's "report generation for 500 sections < 30 min". ADR 0154's
dated amendment carries the arithmetic. **Owner:** E13's load test, which
measures the real per-call latency and decides between fan-out and the
recorded materialization fallback (E4 breakdown decision 1).
**Done when:** the load test has measured it and either the budget holds or
a construction change lands with its own record.

## The reveal door accepts any answer id; the harm-class narrowing waits on E6's vocabulary

From the boundary's data-model review of `reveal_subject_for_answer`: the
definer derives an author for any answer, comment-bearing or not, and the
narrowing to §6.2's threat and self-harm set is argued only in ADR 0144 and
the function's prose. Not a live exposure (the CARE gate and the committed
audit row still stand between the door and a name). **Owner:** E6, with the
verdict vocabulary. **Done when:** the door's predicate refuses an answer
whose classification is not in §6.2's set, proven by a planted verdict.

## Aggregate ordering has no code-level gate (§4.1 item 4's second half)

"No ranking, no score-sorting anywhere" is asserted mechanically over
strings only; E4's one ordered list sorts by label and is pinned, but
nothing structural awaits the first surface that could sort by a score.
**Owner:** E9, whose roll-ups are that surface. **Done when:** E9's
breakdown names the gate (a sweep, an invariant test over its ordering
clauses, or a recorded decision that review suffices there).

## The frontend confidentiality tests have no structural floor

The boundary marked a sweep that refuses skip/todo patterns in frontend
test files; what remains structural is the class the standing
collection-floor entry already owns — a deleted or renamed frontend
confidentiality test vanishes silently, exactly as a backend marker loss
would. **Owner:** the same candidate process ticket as the
denial-inventory/collection-floor entry, which this fact joins.
**Done when:** that entry's, extended to the frontend pass.

## The summary eval floor is a `DEFERRED` slot

ADR 0149 staged the summary task's floors cases-first; the slot is still
`DEFERRED` and `tests/evals/README.md` says what that costs. The boundary
adds: the themes-only family (ruling of 2026-09-09) is graded offline like
the rest, so nothing in CI yet measures a real provider against the
small-N mode. **Owner:** the epic that runs the first real-provider
floor-setting pass (E10 at the latest, with the threat-recall floor work).
**Done when:** the slot holds numbers set from a recorded run.

## A quiet week's summary can be refused for ever, and a commenter can arrange it

From the exit ticket's security round: the themes-only store-time guard
(ADR 0162) refuses and retries with no cap and no alarm, and the trigger is
input-controlled as well as provider-controlled — a student in a
below-threshold week who plants a phrase the summary will inevitably
contain takes that week's summary away permanently, and §5.1 makes the
summary that week's only comment signal. Deterministic on the development
stack (the record names why). The direction is denial, never disclosure,
which is why nothing was built; ADR 0162's dated amendment holds the full
reasoning. **Owner:** E11's job observability surface, which already reads
the walk's written/failed answer — a permanently-refused section-week must
be visible to an operator. **Done when:** an operator can see, without
shell access, that a week's summary was refused and why-shaped (count and
week, never content), proven by driving a refusing week against the dev
stack.

## The `PERSON_TABLES` standing question, re-asked and re-carried

E4's answers are in `../e4/boundary-review.md`: the four report tables
judged with pinned column tuples (two reached-and-carrying-nothing, two not
reached), `question.stream` reaching no person, `PERSON_TABLES` unchanged.
**Owner:** E13 at the latest; every epic boundary re-asks it of the tables
it adds.

## The TypeScript 7 pair waits on typescript-eslint

Checked 2026-09-08 at this boundary: latest 8.70.0, peer range still
`>=4.8.4 <6.1.0`, so 7.x was not admitted during E4 — a re-carry with a
dated fact. Installed pins unchanged and inside the range.
**Owner / done when:** unchanged from the source entry.

## The session-read sweep's two disclosed limits

Re-affirmed at the E4 boundary by planting in the epic's two new
route-serving modules (`../e4/boundary-review.md` holds the run); E4 added
no route-serving package outside `backend/app/`, so the disclosed limits
stand as disclosed. **Owner:** each boundary re-affirms; the structural
close is E13's.

## The denial-module inventory and the collection floor, made expensive

The E4 boundary paid this entry's warning at scale: five new
confidentiality modules sat outside the isolated pass because their names
matched no shape and nothing counts the pass's size. The instances are
closed (marked, with two new tests); the class stays open, now covering
the frontend pass too (the entry above). **Owner:** a candidate process
ticket, unchanged. **Done when:** the source entry's — a collection-count
floor or an equivalent the guarded set cannot shrink, watched failing.
