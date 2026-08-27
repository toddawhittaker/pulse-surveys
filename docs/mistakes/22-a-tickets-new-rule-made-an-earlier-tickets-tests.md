# Entry 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 6**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*6 instances recorded; the 4 most recent are below, newest first — except the
E0-18 PR 2 one, which sits further down beside the consequence it illustrates.
The 2 earliest are in this file's git history and in the pull requests they cite.*

*(Writing E1-06's tests (2026-08-25), found by this entry's prescribed sweep —
`grep -rn 'auth_token_url' tests/` before anything was written. E1-05 seeded the
mock registration's `auth_token_url` as NULL on purpose, and two merged modules
assert that fact: `test_demo_seed_script.py` requires the column NULL in as many
words, and `test_registration_address_constraints.py` carries the NULL in its
`DEVELOPMENT_REGISTRATION` fixture beside three docstrings calling it
deliberate. E1-06 fills the column with the mock's token endpoint, so the first
module goes red on its assertion and the second quietly stops describing the row
the seed writes — the second is the sharper catch, because nothing would ever
have turned red. Both repairs are inside `tests/`, in modules the ticket does
not otherwise edit, and landed in the ticket's own test round rather than as a
surprise the implementer meets in a runner and cannot repair.)*

*(Found while building E0-39 (Batch I, 2026-08-22; that ticket has not merged),
and it is the largest blast radius this entry has recorded. E0-39 makes five
`oidc_*` settings required and refuses a mock identity provider's address outside
a development environment — a rule about **what `Settings` will accept**, which is
the configuration equivalent of a rule about what the database will store. At
least six merged test modules construct a non-development `Settings` against the
mock's addresses in their own fixtures, for reasons that have nothing to do with
the identity provider: they wanted a non-development environment for something
else and took the defaults for everything they were not testing. Every one of them
goes red inside its own setup, in modules the ticket is not otherwise editing, and
every repair is on the other side of the test wall. It was caught before any
implementation by the test author grepping the read-only suite for the
constructions the new rule would refuse — the sweep this entry prescribes, run at
the moment it is cheap — and it is repaired as a partitioned fixture-only round in
that ticket's own scope rather than as a surprise the implementer meets in a
runner. **A rule that narrows what a configuration object accepts is a
write-time rule**: fixtures build configuration the same way they build rows, and
defaults are what makes the collision wide rather than narrow.)*

*(Writing E0-28's tests, and the collision was found by asking this entry's
question of an *assertion* rather than of a row. E0-28 item 1 makes exactly one
seeded NRPS member carry no enrollment extension at all, and E0-15's
`test_the_enrollment_window_ends_the_dropped_member_and_nobody_else` builds its
`keyless` list as `"end" not in (enrollment_of(member) or {})` — which is true of
a member with no window, so the new seed turns that test red inside its own
reading of the roster, in a module the ticket is not otherwise editing. `grep -n
'enrollment_of' tests/` found it before anything was written. It is amended in the
same change as the seed test that requires the new member, which the implementer
could not have done: the repair is inside `tests/`, and the person who meets the
red is the one agent forbidden to touch it. The amendment is narrow and says so —
a member that carries a window and no `end` key still fails, which is the mutation
the assertion exists for.)*

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

**Instance, 2026-08-26 (E1-10, dispute E1-10-01).** E1-10 added
`course.title_is_fallback`, and E0-11's migration tests went red inside their
own seeding: `seed_row` ends `.returning(*table.columns)` — every column
`Base.metadata` declares — while the test seeds a database pinned eight
revisions back, so no definition of the new column avoided it. The module's own
docstring stated the premise that had expired ("seeding at `RANK_REVISION`
keeps their columns the ones today's models declare"). The repair was on the
other side of the test wall, exactly this entry's shape: the test author moved
seeding to head with a walk back down, closing the class — any table a future
revision touches — rather than the one column. Not counted as a catch; the
entry describes what happened, it did not prevent it.
