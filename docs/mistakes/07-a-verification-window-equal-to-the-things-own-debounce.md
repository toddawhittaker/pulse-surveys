# Entry 7. A verification window equal to the thing's own debounce

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** Checking that a drifted database password made the container
report unhealthy, the poll ran for exactly 60 seconds. Docker needs `retries: 12`
× `interval: 5s` — 60 seconds of consecutive failures — before it flips.

**Root cause.** Choosing the window from the interval without adding the debounce.

**Consequence.** Nearly reported a working fix as broken. The health log already
said `password authentication failed`; only the status had not caught up.

**Rule.** When verifying a debounced state change, wait past the debounce and
read the underlying log as well as the summary status. A negative result inside
the debounce window is not a result.

---
