# Entry 52. A module-level engine was bound at import by whichever test imported it first

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

**What happened.** E4-06's five behavioural modules — eighteen tests — passed when
run on their own and failed as a block under `make test`'s `pytest -n 4`, in
whichever worker had drawn a particular earlier file. Every failure raised from
`app/services/reporting.py` through `clock.now` to `session.scalars`, and the
connection in the traceback read
`dbname=e0_04_d38ebd91254b user=pulse_app port=36435` — a database that had been
created inside another test and dropped when it finished.

`backend/app/db.py` builds its engine **when the module is imported**, from a
`Settings()` of its own; ADR 0013 records that deliberately and ADR 0010 does the
same for the Celery application. `sys.modules` then keeps the result for the rest
of the worker, so the environment a fixture lays down governs only if nothing has
imported `app.db` yet. Ordinarily that is harmless, because the first importer ran
under the session container's `DATABASE_URL`.
`tests/integration/test_alembic_baseline.py` is the exception: it monkeypatches the
three database variables at a throwaway `empty_database`, then reaches `from app.db
import Base`. Where that is a worker's first import of `app.db`, `engine`,
`SessionLocal` and every Celery task behind them are bound for the rest of the
session to a database that no longer exists.

The suite's own fixture stated the environment and said so in its docstring,
citing entry 40's rule. What it did not do was import the module under the
environment it had just stated. The one other module that drives a Celery task on
the `pulse_app` connection —
`tests/integration/test_the_launch_replay_purge_runs_as_pulse_app.py` — takes that
step in a fixture whose docstring names the mechanism, and its neighbours are green
under the same ordering.

**Root cause.** Two things that are easy to hold as one. Stating a value in the
environment and *binding* a module to that value are separate acts, and only the
first is what a fixture normally does. The second belongs to whoever imports first,
which is not a property of the test that fails — it is a property of the file
ordering, so the failure lands on whichever suite is newest rather than on the test
that did the binding.

**Consequence.** Eighteen red tests, a dispute round, and a diagnosis that pointed
at the wrong layer for as long as the traceback was read as a defect in the new
code. The three repairs a hurried reading suggests are all wrong: making the task
build its own engine departs from ADR 0013 for a reason that exists only inside the
test process and makes it the one task of eight that opens a session differently;
serialising the suite hides the ordering rather than fixing it; and marking the
tests concedes that the newest suite is at fault. The right repair is one import
step in the fixture chain, and the sibling suite already had it.

**Rule.** A process-global built at import — an engine, a client, a Celery
application, anything a module constructs at the top level from configuration — is
bound by whoever imports it first, and `sys.modules` keeps that binding for the
rest of the worker. A suite whose subject reaches such a global states the value
**and takes the import step under it**, in its own fixture chain.

Three corollaries, all of which were live here:

- **Read the connection out of the traceback before believing the failure.** The
  database name in `psycopg`'s message names the test that did the binding, and a
  throwaway name that no longer exists names it exactly. That one line is the
  difference between a half-hour diagnosis and a wrong repair.
- **Green alone and red under `-n 4` is not a flake.** It is an ordering
  dependency, and the way to make it deterministic is to name two files on one
  `pytest` command with `-p no:randomly` and then reverse them. Both directions
  are the measurement; one direction is an anecdote.
- **The suite that fails is rarely the suite that is wrong.** Before changing the
  newest code, run the same ordering against the nearest neighbour that does the
  same thing. If the neighbour is green, the difference between the two files is
  the defect — here, one import step.
