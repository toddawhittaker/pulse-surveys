# Entry 11. A failure in another process, invisible in the traceback that reported it

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** E0-03's round-trip test timed out after thirty seconds
waiting for a task result. Its traceback pointed at `AsyncResult.get()` and said
nothing else: the worker had started, the broker was the one the test itself
started, and every assertion before the wait had passed. The worker runs in a
thread with `WORKER_LOGLEVEL=error`, so what actually happened was not printed.
Rerunning with `WORKER_LOGLEVEL=info` showed the task had *succeeded* and then
died storing its result — `pyproject.toml`'s `error::DeprecationWarning` turned
redis-py 8.1.0's notice about celery's `setex` call into an exception inside the
task trace, so the result was never written.

**Root cause.** A failure that happens in another thread or another container
does not appear in the traceback of the thing that was waiting for it. What the
waiter reports is the *absence* of an answer, which is the same shape whatever
the cause — a broker that is unreachable, a worker that is not running, and a
worker that ran perfectly and could not save its answer all read as a timeout.

**Consequence.** Half an hour, and a wrong first hypothesis: the obvious reading
of "the result never came back" is that the broker or the backend is
misconfigured. Raising the timeout, changing the result backend, or adding a
retry would each have looked reasonable and fixed nothing.

**Rule.** When something on the other side of a queue, a socket, or a container
boundary does not answer, get *its* log before theorizing about the channel. Turn
its log level up (`WORKER_LOGLEVEL`, `docker compose logs <service>`,
`docker inspect` for a health check's output) and reproduce outside the harness
if the harness is what is hiding it. A timeout is the absence of evidence, not
evidence.

---
