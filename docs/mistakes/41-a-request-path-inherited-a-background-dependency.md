# Entry 41. A request path inherited a background job's dependency, at that dependency's default retry policy

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*1 instance recorded.*

*(E1-11, found by running the whole suite after every one of the ticket's own
suites was green.*

SPEC §7.3 pulls the roster "on schedule and on launch (debounced)", so the launch
door gained one line after its commit: resolve the section, ask
`app.services.roster_sync.request_section_sync` for a sync, which enqueues
`app.jobs.tasks.sync_section_roster` when the section has not been called in the
last five minutes. The enqueue was `task.delay(...)`.

Nothing in the test environment runs Redis. `delay` is `apply_async` with Celery's
defaults, and those defaults are written for a worker rather than for a request:
`send_task` calls `self.backend.on_task_call(...)` before it publishes, the Redis
result backend's retry policy is twenty attempts a second apart, and the broker
publish has a retry policy of its own on top. So every staff launch in the suite
sat for roughly twenty seconds and then raised
`RuntimeError: Retry limit exceeded while trying to reconnect to the Celery result
store backend`, out of a handler that had already verified the launch, already
committed it, and had a landing page ready to return.

**Thirteen tests in `tests/integration/test_launch_time_provisioning.py`, one in
`test_launch_provisioning_defects.py`, one in
`test_provisioning_consults_the_catalog_at_every_write.py` and both of E1-11's own
new provisioning tests failed**, and the full run went from about seven minutes to
fourteen. Every one of E1-11's four roster suites was green throughout, because
none of them goes through the launch door — they call the sync directly. The
ticket's own tests could not see it.

## Root cause

Two mistakes, and the second is the one worth the entry.

The first is ordinary: a new out-of-process dependency was added to a request path
without asking what happens when it is down. Redis is the broker *and* the result
backend (one `REDIS_URL`, ADR 0010), and until this change nothing in a request
touched either — `ping` is a test, and `purge_launch_nonces` is beat's.

The second is that the failure mode was not "it raised" but "it held the request
open first". A client library's defaults are chosen for the context that library
is usually called from, and Celery's are chosen for a worker, where retrying a
broker for twenty seconds is correct. Inherited unexamined on a request path they
turn a dependency that is *down* into a request that is *hanging*, which is the
worse of the two failures: a fast error is a page somebody sees, and twenty
seconds of held connection under a class of thirty launching at once is the door
itself going down.

## Consequence

Caught before the pull request, by running the whole suite rather than the
ticket's own. Had it merged, every launch in a deployment whose Redis was
restarting would have failed after a twenty-second wait — with the launch already
committed, so the person is authenticated, the section is provisioned, and the
platform shows them an error page. The symptom would have read as a launch defect,
which is the one thing `app.services.provisioning` is built never to produce.

## Rule

**A request path may not be able to fail because a background dependency was
unavailable, and it may not wait to find out.** When a handler enqueues work,
publish with retries off, keep the result backend out of it for a task whose
answer nobody reads, and catch broadly — the request has already done its own job
by then, and the scheduled run is what covers the gap. State in the docstring
which of the three is doing what, because each of them looks removable on its own.

**And the corollary, which is how this was found:** a change that adds a call to a
shared entry point is not verified by the suites of the ticket that made it. Run
the whole suite before believing a green, and read the *timing* as well as the
result — the run took twice as long, and that was the same defect saying so.
