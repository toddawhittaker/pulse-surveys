# Entry 41. A request path inherited a background job's dependency, at that dependency's default retry policy

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*2 instances recorded; one of them is a catch. Newest first.*

*(**A catch**, and a correction to this entry's own rule, writing E2-08's submit
path, 2026-09-01. §3.3 accepts a submission on the character floor when the
provider is down and classifies it later, so the route enqueues a
re-classification — a call this entry's rule is written about, and the rule is
what put `retry=False`, `ignore_result=True` and a broad `except` into the code
before any test ran. Without the entry the line would have been `task.delay(...)`
bare, which is exactly the first instance below.*

*What the entry additionally saved is the part worth recording. Its corollary
says to read the timing as well as the result, and the timing said the three
protections were not enough: with all three in place, `apply_async(retry=False,
ignore_result=True)` against a closed loopback port raised
`kombu.exceptions.OperationalError` after **6.04 seconds**. `retry=False` governs
the publish; the publish reaches `kombu.Connection.default_channel`, which runs
`_ensure_connection` under kombu's own defaults (`interval_start=2,
interval_step=2`) before the publish is attempted, so a broker that refuses
instantly is retried on a schedule nothing in the three flags touches. Six
seconds is under the twenty this entry was written about and over SPEC §10's
2.5-second budget for the whole submit round trip — the same failure, quieter.*

*The repair is a fourth protection, now in the rule: publish on a connection made
for the call. `celery_app.connection_for_write(transport_options={"max_retries":
0, "socket_connect_timeout": 1.0, "socket_timeout": 1.0}, connect_timeout=1.0)`,
with the connection handed to `apply_async`. Measured: the same closed port
**0.037s**; a blackholed address, where the refusal never arrives, **1.04s**
instead of the operating system's own timeout — `connect_timeout` alone does not
bound that, the redis transport reads `socket_connect_timeout` out of
`transport_options`; a broker that answers publishes in **0.046s**. Scoped to the
connection and never to `celery_app.conf`, because a worker whose broker blips
must reconnect rather than give up. Had the entry not said to time it, the six
seconds would have shipped behind three protections that look complete, and the
budget assertion is the only thing in the suite that would have noticed.*

*`app.services.roster_sync.request_section_sync` — the enqueue the first
instance below fixed — still has the three-protection shape and the same six
seconds on the launch path. It is a shared module outside E2-08, so it is carried
in `docs/tickets/e2/deferred.md` with a done-when rather than changed there.)*

*(Closed by E3-05 on 2026-09-04, the ticket that added a second enqueue to that
door. Both now publish through `app.jobs.celery_app.publish_once`, which is where
the bounded connection and its measurement live, and a launch against a closed
port is timed under SPEC §10's budget with both refusals required — so a door that
publishes nothing cannot pass by being fast.)*

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
answer nobody reads, publish on a connection made for the call with its own
retries off and its socket timeouts bounded, and catch broadly — the request has
already done its own job by then, and the scheduled run is what covers the gap.
State in the docstring which of the four is doing what, because each of them looks
removable on its own.

**And measure the enqueue against a closed port rather than trusting the flags.**
The third protection is here because the other three were shipped, believed, and
then timed: a publish flag governs the publish, and the client library opens the
connection under a retry policy of its own before the publish is attempted. That
is the same failure this entry is about, one layer down, and it survives every
reading of the code.

**And the corollary, which is how this was found:** a change that adds a call to a
shared entry point is not verified by the suites of the ticket that made it. Run
the whole suite before believing a green, and read the *timing* as well as the
result — the run took twice as long, and that was the same defect saying so.
