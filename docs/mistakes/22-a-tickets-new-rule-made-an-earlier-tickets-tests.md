# Entry 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 17**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*20 instances recorded; the 3 most recent are below — the E3-04 one before the
"What happened" section, and the E4-01 and E4-05 ones after it, each left where
this file has always kept its instances. The other 17 are in this file's git
history and in the pull requests they cite. The overdue trim was taken on
2026-09-06, and it took the E2-16 and E2-05 pair together as the note asked. The
E0-18 PR 2 paragraph stays where it sits, beside the consequence it illustrates:
it carries a rule sentence of its own — that any instruction to remove or rename
a thing is a claim nothing asserts on it — rather than only an instance.*

*(**2026-09-04, E3-04 (`e3/ags-client-and-mock-enforcement`), caught before
anything was written.** The ticket turns on credential enforcement across the
mock's whole AGS surface, which is the largest instance of this shape the
repository has met: every line-item, score and result call in two merged E0-15
suites is made without a credential and every one of them would answer 401, with
the repair on the read-only side of the wall. The ticket's own known-traps
section names the entry, so the sweep was the first thing done. Nearly all of the
calls funnel through `MockPlatform`, so the repair is one fixture: an
`ags_token(scope)` cache and an `ags_get`/`ags_post` pair that attach the scope
each route takes. **The half a fixture-only repair would have missed is the nine
direct call sites** — `mock_platform.service_get(...)` written out in
`test_mock_lms_paging_and_service_urls.py` and
`test_mock_lms_ags_line_items_and_scores.py`, found by grepping for the method
rather than for the helpers — and one of them is worse than a red: the naive
`/scores` concatenation test asserts `400 <= status < 500`, so a 401 would have
kept it **green while measuring the credential instead of the URL**, which is
entry 3 arriving through this one. Attaching tokens is inert until the
enforcement lands, so the whole repair rides the tests-first commit. Counted as a
catch: without it the implementer's first run would have been two walls of red
E0-15 tests, one of them silently passing for the wrong reason, on modules they
may not edit.)*

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

**Instance, 2026-09-06 (E4-01, caught before any green).** The settled reveal
design needed the Care session to read `answer` and `response`, and the
privilege inventories pin that role to one base-table read and two definer
functions — so any repair mechanism reds a pinned test. The test author
surfaced the collision as the head-of-manifest finding, with the three
candidate mechanisms and which inventory each one reds, instead of letting the
first green run discover it. Counted as a catch: the inventories' pins are
what made the gap a finding rather than a surprise.

**Instance, 2026-09-06 (E4-05, PR #187, dispute E4-05-01).** E4-05's scope
requires a new prompt file, `summary.v1.md`, and E2-18's pin
(`tests/unit/test_the_committed_prompt_files_are_pinned_by_content.py`) refuses
any prompt on disk with no row in `RECORDED_SHA256` — a mapping inside that test
module. So the one action that turns the red green is an edit to `tests/`, which
the implementer may not make: this entry's shape with the epics reversed, an
earlier ticket's rule making a later ticket's file unpinnable from where the
implementer stands. The entry is why that became dispute E4-05-01 rather than an
attempt to satisfy the check another way. The objection names the three
workarounds it declined and why each is worse than the red — adding the row
directly (the gesture the pin exists to refuse, and the mapping cannot tell an
added file from an edited one), naming the prompt something the inventory's walk
does not see, and shipping the ticket without the prompt at all. Ruled the same
day: the test is right, the row lands test-side, and the digest was re-derived
from the committed file before the ruling rather than pasted from the objection.
Counted as a catch: without it the branch's route to green ran through the test
wall, and the record would have been a quiet workaround instead of a ruling.
