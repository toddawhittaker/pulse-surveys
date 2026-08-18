# Entry 26. A fallback path swallowed the defect that triggered it

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** E0-13's gateway held one HTTP client, and drove it from an
event loop per thread. A pooled connection belongs to the loop it was opened on,
so the second thread to reuse one got `RuntimeError: ... is bound to a different
event loop` — which the provider library turned into "connection error", which
the gateway turned into `AIProviderUnavailableError`, which the validity task
caught, and answered with SPEC §3.3's character floor.

**With a healthy provider and one shared gateway, every second submission was
classified by counting characters.** Measured in review and reproduced here:
submissions 0, 2 and 4 came back with the model's verdict; 1, 3 and 5 came back
`insufficient` / `character-floor` / `no-model`. The request was sent every time
and the answer discarded, so the comment reached the third party and the model's
verdict was thrown away. The same comment was counted or refused depending on
which threadpool thread served it, which makes §3.3's participation gate a coin
flip.

**Root cause.** A `try/except` around a failure class broad enough to include a
programming error. The defect and the sanctioned failure arrived as the same
exception type, and the handler could not tell them apart — so the code that
exists to keep a student unblocked during somebody else's outage quietly absorbed
a bug in the code above it.

**Consequence.** 654 tests passed. Every one of them drives the gateway from a
single thread, so no test could see it; the reviewer found it by running the
deployment shape the record says E2 will use. Had it shipped, the effect would
have been a participation grade that changed with thread scheduling and no error
anywhere — the failure mode a fail-open is *for* is an outage you can see in a
dashboard, and this was invisible by construction.

**Rule.** **A fail-open handler must catch the narrowest failure the spec
sanctions, and everything else must be loud.** Ask of every `except` on a
fallback path: what is the *widest* thing this class can carry, and is a bug in
my own code one of them? If it is, split the class until it is not.

The narrowing this produced is
[ADR 0056](../adr/0056-only-a-timeout-fails-open.md): a timeout is its own class and
is the only one the validity task falls open on, decided on the exception chain
rather than on a message, and an unrecognised failure answers "not a timeout" so
it surfaces.

Two further rules fall out of the same incident, and they are cheaper than the
first:

**A single-threaded test suite proves nothing about a shared client.** Anything
holding a connection pool, a session, or an event loop needs one exercise from
more than one thread — and the assertion is that the *answers* are right, not
that nothing raised, because this defect never raised anywhere a test could see.

**When a fallback fires, the record has to say which failure caused it.** The
floor's own audit pair (`character-floor` / `no-model`,
[ADR 0054](../adr/0054-a-floored-classification-names-the-floor-in-its-audit-pair.md))
is what made this diagnosable at all: the rows said a floor decided, so the
question became *why*, rather than "why is the model answering `insufficient` so
often".

**The narrowing this entry prescribes was made and did not hold.** Entry 33 below
is what happened next, and anyone acting on the rule above should read it first:
"split the class until it is not" was done against the provider library's own
exception tree, and the tree put a case on the wrong side of the split.
