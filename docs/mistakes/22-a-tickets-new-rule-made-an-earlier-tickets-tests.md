# Entry 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 21**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*24 instances recorded; the 3 most recent are below (E4-06, E4-18, E4-17),
each after the "What happened" section. The overdue trim the previous header
owed was taken on 2026-09-08 with the E4-17 bump, removing the E3-04, E4-01,
E4-05 and E4-04 paragraphs; they are in this file's git history and in the
pull requests they cite. The E0-18 PR 2 paragraph stays where it sits, beside
the consequence it illustrates: it carries a rule sentence of its own — that
any instruction to remove or rename a thing is a claim nothing asserts on it —
rather than only an instance.*

**What happened.** Twice in E0-11, from two unrelated mechanisms, with the same
consequence: the ticket cannot be finished green and the implementer cannot fix
either, because both repairs are edits to `tests/`.

**The first is a rule that changed what is writable.** E0-11's first acceptance
criterion adds a role-rank rule to E0-09's supervision trigger: an edge is legal
only where `rank(child) < rank(parent)` over SPEC §2.1's chain. Its own module goes
from 19 passed and 24 failed to 43 passed. Three of E0-09's tests go red, and not
on their assertions — inside their setup. `test_a_six_assignment_cycle_is_refused`
and both properties in `test_supervision_graph_properties.py` build their graphs out
of `graph.node("CHAIR", reports_to=<another CHAIR>)` and require those writes to
**succeed**, while E0-11's `[chair-chair]` case writes the identical row — same
helper, own person, own department — and requires it **refused**. Two identical rows,
two opposite requirements. E0-09's module docstring even states the choice that
causes it: "one role and one scope grain per graph. Every generated node is a chair
on its own department, so that no uniqueness rule this ticket does not mention can
refuse a row and be read as the cycle guard firing." That was the right call for
E0-09 and it is what a later write-time rule collides with.

**The second is a test pinned to a relative revision.** Three tests in
`tests/integration/test_identity_grants.py` assert what E0-10's `downgrade()`
leaves behind, reaching it with `alembic downgrade -1`. `-1` is relative to head, so
the first revision to land on top of E0-10's — E0-11's — is the one `-1` names, and
all three fail. That is by design and the design is good: the shared guard
`only_the_identity_revision_was_undone` exists precisely so the change is loud
rather than a green test about a downgrade the file is not about, and its message
names the repair. The repair is "point this test at the identity revision
explicitly", inside `tests/`.

Measured, not predicted, and in the cheapest possible order: a throwaway revision
whose entire content was `CREATE VIEW public.probe_view AS SELECT 1` was written
*before* any of E0-11 was designed, and it turned the same three red. The content of
the revision is irrelevant — E0-10's two views are in both the at-head and
after-downgrade sets whenever `-1` names anything else — so no implementation of the
ticket avoids it.

**Root cause.** Two, and they are worth separating.

For the first: a new *write-time* rule was specified without asking which rows in
the existing suite it makes unwritable. A rule that changes what can be stored
changes every fixture that stores it, and a fixture is not a record that quietly
goes stale — it goes red, loudly, in a module nobody is editing. Both tickets'
authors looked at `test_role_assignment_graph.py`: E0-11's new module cites it twice
and correctly predicts which of its tests survive. Neither looked at the *generators*
in the property module, where the role is a constant chosen for an unrelated reason.

For the second: a test whose subject is one specific revision identified it by
position. Nothing declared the dependency, and it holds until the day it does not.

**Consequence.** Two dispute rounds on a ticket whose own 71 tests are green, and a
branch that cannot be merged under `CLAUDE.md`'s "never merge with red CI" until
somebody who may edit `tests/` acts. The expensive part is not the rounds — it is
that both failures look, in a runner, exactly like an implementer having broken
something. The three E0-09 failures print a `CheckViolation` from the new rule, and
the natural reading is that the rule is too strict rather than that two correct
specifications disagree. Six red tests, no defect in any of them, no defect in the
implementation.

*(In E0-18 PR 2 the trigger was a dispatch brief, not a new test rule, and the
sweep caught it before any code changed. The brief said to "remove the `e2e` probe
from the `detect` job" as cleanup, on the true premise that the `e2e` job was its
only consumer. But `tests/unit/test_the_detect_probes_see_the_files_their_jobs_run.py`
(E0-36) executes every `run:` script in the `detect` job over planted trees and
asserts the emitted output **equals** a three-key dict including `e2e` — so dropping
the probe makes `emitted != expected` on every case, and that test is read-only.
The repair is on the other side of the wall: only the test author may drop the
`e2e` key from those expectations. Nothing was removed. The probe stays — harmless,
still emitted, simply no longer read by the `e2e` job — and only the *skip* half of
the ticket's "find-and-skip" went. `grep -rln 'e2e' tests/` and one read of the
module found it before a single edit. This is the entry working the way it should:
not a red-suite surprise and not a dispute, just a brief instruction quietly
declined because a correct test forbids it, and reported as a deviation. The lesson
generalizes past "a ticket's new rule": **any instruction that removes or renames a
thing — a workflow output, a function, a fixture — is a claim that nothing asserts
on it, and the cheap way to check the claim is to grep the read-only suite before
acting, not after the runner goes red.**)*

**Rule.** **Before specifying a rule that changes what the database will store,
grep the existing suite for the rows it forbids.** `grep -rn 'reports_to='
tests/integration/` would have found all three in a minute, and the collision is a
sentence in the ticket rather than a dispute round. The sweep is not the outward
sweep over *records* that entry 1 asks for — this is over executable setup, and the
question is narrower and mechanical: which fixture writes a row this rule now
refuses?

**And when a guard's failure message prescribes a repair, ask who will meet it.**
`only_the_identity_revision_was_undone` is a well-written guard: it fires exactly
when intended and says what to do. It says it to an agent that is forbidden from
doing it. A guard whose remedy lies outside the reach of whoever it fires on is a
guard that produces an escalation rather than a fix, which is sometimes right — it
is right here — but it should be a chosen outcome and written down, not a surprise.
Where a test's subject is a particular revision, **name the revision**; `-1` and
`head` are convenient and neither is a subject.

**And when the partitioned round comes back, count the failures and then look for
what the first one is standing in front of.** Measured on E0-26 item 1 (PR #53,
2026-08-20), whose instance paragraph has since been trimmed from this file: eight
tests failed on one assertion, and a shared helper that raised in setup meant an
exact-set assertion behind it was **never evaluated** — a defect queued behind a
defect, and a round that repaired only the visible one would have reported the
module fixed. An exact-set assertion is the kind whose silence looks like
agreement.

---

**Instance, 2026-09-06 (E4-06, PR #195, dispute E4-06-02's sibling E4-06-01).**
SPEC §5.1 has the weekly summaries "exclude flagged-held content", ADR 0145 puts
the record of what is held in `moderation_state` and nowhere else, and the Monday
walk runs on the `pulse_app` connection — so the filter that sentence requires
cannot execute without a `SELECT` the ticket's own work order had said it would not
take ("`weekly_summary` and nothing wider"). Granting it reddened **three**
inventories at once, all of them read-only to the implementer:
`RUNTIME_BASE_TABLE_PRIVILEGES`'s equality in `test_identity_grants.py`, the
narrowed walk in `test_report_schema.py`, and — the one that is the lesson here —
`STILL_UNGRANTED`, a closed tuple inside a test module **this ticket had just
written**. The first two are the familiar shape: an earlier ticket's rule, a later
ticket's need. The third is the same collision arriving from the ticket's own
tests-first commit, where nobody thinks to look for it, because the reflex is to
grep the *existing* suite for what a new rule forbids and a module written an hour
ago does not feel like the existing suite.

Counted as a catch: the entry is why the grant became dispute E4-06-01 with all
three assertions named and measured up front, rather than a green branch reached by
quietly widening a tuple the same author had written. **The clause it adds:** when a
ticket takes a privilege, a row or a state its own work order said it would not,
grep its own new test modules for closed sets naming the thing — the read-only rule
is about who may edit a test, not about how old the test is, and a set written
earlier in the same branch is as much on the other side of the wall as one written
in E0.

**Instance, 2026-09-07 (E4-18, and the named repair was not the whole repair).**
E4-18's ticket names this entry itself: `tests/fixtures/report_api.py`'s
`instructor_route_objects` fails every E4-07 suite unless the module has exactly
two GET routes, and the prescribed repair is a test-side flip of that count to
three. Reading the fixture whole showed the count is half of it. `instructor_routes`
maps `_shape_of` over every GET route the module mounts, and `_shape_of` fails **by
name** on a route declaring no section parameter — which is exactly what E4-18's
parameterless `GET /instructor/sections` declares. So a count-only flip leaves all
six E4-07 modules red against a correctly built route, in files the implementer may
not edit, one step after the flip was supposed to have fixed them. The prepared diff
therefore also adds a `_names_a_section` predicate and shapes only the two routes
that take a section, and corrects the two "…'s two GET routes…" sentences the third
route makes false (entry 1). Counted as a catch: the entry's rule is to go and look
for what a new rule makes unrunnable rather than to trust the repair a ticket names,
and here the named repair was incomplete in a way that would have surfaced as an
implementer's red run.

**Instance, 2026-09-07 (E4-17, PR #205, caught at planning).** The work plan
assigned a component-test edit to "the implementer", and no agent the hooks
permit could make it: the implementer's hook denies every `*.test.*` file and
the test author's denies reading `frontend/src`, so component tests have no
permitted agent editor at all. The operative fact was mechanical permission,
not ownership — the same wall this entry is about, arriving from the harness
configuration rather than from a test's content. Caught before any edit: the
orchestrating session took the edit itself as scribe and recorded doing so in
the pull request, and the standing fix is the owed process change to the hook
pair. Counted as a catch per the pull request's own wording: without the
entry, the round would have dispatched an agent into a denial and read the
refusal as a defect.
