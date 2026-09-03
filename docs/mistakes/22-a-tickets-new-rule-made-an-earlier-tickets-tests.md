# Entry 22. A ticket's new rule made an earlier ticket's tests unrunnable, and the repair was on the other side of the test wall

**Caught: 11**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*11 instances recorded; the 6 most recent are below, newest first — except the
E0-18 PR 2 one, which sits further down beside the consequence it illustrates.
The 5 earliest are in this file's git history and in the pull requests they cite.
It carries six rather than five because the newest and the E2-05 one are the same
inventory in the same module a ticket apart, and reading either without the other
loses what the pair shows; a trim is due and it should take a pair, not a
paragraph.*

*(**2026-09-03, E2-16 (`e2/data-model-repairs`), disputes E2-16-01 and
E2-16-02.** The ticket gives `response` the term-agreement rule `survey_window`
has had since E2-05: a `term_id` on the row, held by composite foreign keys into
`section (id, term_id)` and `week (id, term_id)`. It reddened two classes of
test the implementer may not touch. The first is the closed inventory in
`test_identity_column_marker.py` expiring on the new column — this entry's
E2-05 instance replayed, and the pin working exactly as built: the repair is a
human re-reading the reason and re-pinning the columns. The second is eighteen
tests across three seeding sites, red **inside their own setup**: each writes a
`response` naming a section and a week explicitly while handing `seed_row` an
empty chain, so the walker — which fills an unnamed NOT NULL foreign key from
the chain and builds the target when the chain has none — invented a section in
a fresh term and took that term, and the composite key refused a row whose
section and week were somebody else's. Fourteen of the eighteen were one
fixture. **Not counted as a catch**: nothing swept for them before the schema
changed, and both classes arrived as a red runner and a dispute round. The sweep
that would have found them is this entry's own and is one line — the callers that
write the table the new rule constrains, read for which of them name only part of
the key.

**What this instance adds is the half the sweep would still have missed.** Of the
four seeding calls in `test_survey_schema.py`, three went red and the fourth went
**green** — the duplicate insert, whose test asks only "was this refused?" through
a helper that accepts any `DatabaseError`. With the term left to the walker it was
refused by the composite foreign key rather than by
`uq_response_user_id_section_id_week_id`, so the test would have gone on passing
while measuring a different constraint entirely (`docs/MISTAKES.md` entry 3, and
it was found by reading the file rather than by the run). So: **when a new write
rule reddens setup, look at the tests around it that stayed green.** A test that
asserts a refusal cannot tell one refusal from another, and a new constraint is a
new way for it to pass.)*

*(**2026-09-02, E2-12 (`e2/eval-floors`).** The ticket's configuration split
strikes the spelling `AI_MODEL_NAME` and gives the mock endpoint a triple of its
own, so assertions naming the old variable, and fixtures that configure a
test-process gateway under the real triple's names, describe spellings the
ruling removed. Acting on this entry, the test author swept for them before
writing anything and repaired nine files in a commit of their own — then
measured the blast radius rather than counting the diff, and found that one of
the nine carries four more with it: the renamed assignment in the submit
fixture reddens four committed integration modules that consume it, thirteen
files rather than nine. Those four are green at HEAD and red only with the
repair, so they were named as must-go-green in the implementer's work order
instead of reading later as an unrelated regression. Counted as a catch: the
sweep turned a class of reds the implementer may not repair into one
attributable commit, and the four-module tail is the half a naive reading of the
diff would have missed.)*

*(**2026-09-01, E2-07 (`e2/mock-ai-provider`).** The ticket's two new
configuration rules — a deployment refuses a plain-http provider URL and
refuses the mock's own host — make `.env.example`'s new dev value refusable,
and every existing test that builds `Settings` as a deployment would have
stopped in its own setup on a rule that is not its subject, with the repair on
the read-only side of the wall. Acting on this entry, the test author routed
the repair through the two shared deployment fixtures in the same tests-first
change, so the implementer never meets a red they may not fix.)*

*(**2026-09-01, E2-06 (`e2/window-scheduling`).** The ticket adds a third Celery
beat entry, and `tests/unit/test_celery_app.py` asserts the schedule's contents
as an *equality* — deliberately, so that a new job cannot land without a
conversation. That equality is on the implementer's side of the test wall in
the heavy lane. Acting on this entry, the test author rewrote it in the same
change: the entry set is now an equality over task names, with the new entry
found by its task rather than by a schedule key the ticket does not settle.
Without it the implementer would have met a red test they may not repair.)*

*(Writing E2-05's tests (2026-09-01), found by asking this entry's question of
a discovery walk's fixed point rather than of a fixture. E2-05's
`response.user_id` puts `response` one foreign-key hop from `user` and
`answer.response_id` puts `answer` two, so the `people_tables` walk in
`test_identity_column_marker.py` reaches both the moment the migration lands —
and the closed inventory `REACHED_TABLES_THAT_CARRY_NOTHING`, asserted by an
`@invariant` test in a module the ticket does not otherwise edit, would go red
with the repair on the read-only side of the wall. The two entries were added
with pinned columns and reasons in the ticket's own tests-first round, and the
two docstrings the change falsifies were corrected in the same pass, so the
implementer never meets a red they are forbidden to fix. Counted as a catch:
without this entry's sweep, the tests would have shipped green-looking and the
red would have surfaced in the implementer's runner as an apparent defect in
the migration.)*

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

**Instance, 2026-08-27 (E1-12, caught before it landed).** E1-12's rule that a
verified web login whose subject has no `web_login_subject` linkage lands on
the no-account page turns roughly fifty merged E1-09 web-door tests into calm
no-account landings inside their own flow — a module the ticket does not
otherwise edit, and one the implementer may not touch. The test author ran
`grep -rn 'oidc_callback' tests/` before writing anything, found the class,
and repaired it at the `provider` fixture in the same tests-first round, so
the reds never existed. Counted as a catch: the entry's rule — go looking for
the earlier ticket's tests your new rule breaks, from the side of the wall
that can fix them — is what found it.
**Instance, 2026-08-27 (E1-11, dispute E1-11-02).** D7 made
`user_identity.identity_name` nullable, and seventeen merged Care-door tests —
eleven of them invariant-marked — errored inside their own seeding:
`seed_row`'s documented rule leaves a nullable column to the database, and the
helpers' non-vacuity guard had been leaning on the NOT NULL constraint to fill
a value they never named. Found by the implementer's full-suite run, repaired
on the test side after a ruling: each helper now states the identity it seeds.
Not counted as a catch; the entry describes what happened, it did not prevent
it — the pre-write sweep that caught E1-12's instance looked for route
consumers, not schema-constraint dependents.