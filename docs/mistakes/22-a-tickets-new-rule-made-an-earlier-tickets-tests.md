# Entry 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 3**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(Writing E0-26 item 1's tests, and this time the sweep was run before the tests
were, so the collision is a paragraph in a report rather than a dispute round.
E0-26 splits the reveal into two calls and **drops** the three-argument
`reveal_student_identity`, and `tests/integration/test_identity_grants.py` reaches
its door through `the_reveal_function`, which asserts that `pulse_care` may execute
**exactly one** `SECURITY DEFINER` function. After the split there are two, so that
helper fails inside the setup of the ten tests that reach the door through it, none
of which is about this ticket — and the four that go on to *call* the reveal do it
inside `db_session`, whose transaction is never committed, which the new shape
refuses by design. `grep -rn
'reveal_student_identity' tests/` and one read of the helper found all of it in
about ten minutes. Nothing was repaired: the repair is a migration of E0-10's
module onto the new interface, it is larger than the ticket's own tests, and doing
it half-way inside a ticket about something else is how a green suite stops meaning
what it says. It is reported as a partitioned round for the same agent instead.
The entry's second rule earned its place here too — `the_reveal_function`'s
assertion message prescribes a repair to whoever trips it, and whoever trips it
will be the implementer, who may not edit `tests/`.*

***What the partition was worth, measured after it ran.** Eight tests failed, all
on the same assertion, and the count hid a second failure the way this entry's
first instance did: `REVEAL_DEFINER_PRIVILEGES` is asserted as an exact set and was
**never evaluated**, because the helper raised first — so the ticket's fourth grant
was a defect queued behind a defect, and a round that had fixed only the visible
one would have reported the module repaired. The repair round also found that three
of the four converted tests are now near-duplicates of tests in the new module, and
that the fourth — the `pg_temp` shadow hijack — is the only coverage there that
exists nowhere else and had to be rewritten to aim at both halves of the split
door. **Count the failures, then look for what the first one is standing in front
of**: a helper that raises in setup suppresses every assertion in the test behind
it, and an exact-set assertion is the kind whose silence looks like agreement.)*

*(In E0-15's tests, and it stopped a test being written rather than
repaired one. E0-15's scope says "every seeded course needs a title"; E0-14's scope
requires at least one seeded context carrying `id` alone, no title, so that E1's
ingestion meets the empty case in a test rather than in a deployment — and
`test_mock_lms_launch.py::test_a_seeded_context_carries_no_title` asserts exactly
that today. A test of E0-15's sentence would have turned that one red, on a seed
satisfying both tickets read separately. This entry's rule is about rows a new
write-time rule forbids; the same question asked of an existing *assertion* found
this one in a minute. It is reported as a disagreement between two tickets rather
than resolved in a test file, and the course-number half of the same sentence — which
collides with nothing — is asserted. **The ruling then went the way this entry's title
does not lead you to expect**: rather than the new ticket bending, Todd withdrew the
earlier requirement, `test_a_seeded_context_carries_no_title` was deleted in its own
commit, and E0-14's scope now records what the project gave up — the only fixture in
the repository that exercised a titleless course. Worth keeping, because the entry's
own thesis is that these collisions are repaired on the other side of the test wall,
and this one was repaired on the other side of the *product*: neither test was wrong,
and no amount of care inside `tests/` could have settled which requirement to keep.)*

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

---
