# Entry 49. A test asserted a fail-open return value as if it were a decision

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** E3-08's boundary round added a pair of tests to
`tests/integration/test_the_line_item_trigger_does_not_depend_on_a_roster_address.py`
asserting the value `app.services.grading.request_line_item_creation` returns: true
for a section that should be asked for a gradebook column, falsey for one that
should not.

That function's last four lines are `docs/MISTAKES.md` entry 41's contract and ADR
0135's: it publishes inside a `try`, logs, and answers `False` on **any**
exception, because a request path may not fail because a background dependency was
unavailable. So `False` means "the trigger refused" *or* "the broker was
unreachable", deliberately and permanently.

And in this suite the broker is unreachable by construction. `tests/conftest.py`'s
`documented_environment_baseline` is session-scoped and autouse and lays
`.env.example`'s documented values into every test's environment; the documented
value is `REDIS_URL=redis://redis:6379/0`, a Compose service name that no host-side
test process resolves. Exporting a reachable URL does not help — the autouse
baseline overwrites it.

**Root cause.** The observable was chosen by reading the function's signature
rather than its failure contract. A boolean named for a decision was assumed to
report that decision, when two records had deliberately made it report the
disjunction of that decision and a dependency outage.

**Consequence.** Both halves of the pair were wrong and in opposite directions,
which is what made it expensive to see. The accepting test was **red for the
environment**, and its red was reported as a defect twice — once as a predicted
red-to-green, once as a corrected green — before an implementer measured the
production path in the container and found it answered `True` for exactly the case
posed. The refusing test was **green for the wrong reason**: `False` is what a
failed publish answers whatever the condition under test does, so deleting that
condition from the trigger left the control green. The half whose whole job was to
keep the other honest certified nothing, and the module asserted its rule in
neither direction. Settled in `docs/disputes/E3-08-04.md`; repaired by moving both
onto the `creation_enqueues` interception, which records the enqueue instead of
performing it.

**Rule.** Before asserting a return value, read what the function returns on
failure. Where a contract deliberately collapses "refused" and "the dependency was
down" into one value — every fail-open publish, every `return False` in an `except`,
anything entry 41 or ADR 0135 governs — that value cannot be a test's observable,
because the suite's own environment decides it. Assert the effect instead: the
intercepted enqueue, the row, the call the platform recorded. And when a *pair* is
built on such a value, both halves are compromised and only one of them looks it —
so check the green one by deleting the condition it guards and requiring it to go
red, which is entry 2's reintroduction test applied to the control rather than to
the feature.
