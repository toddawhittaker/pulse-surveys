# Entry 33. A class-tree split put a case on the wrong side, and the docstring said otherwise

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** Entry 26's rule was applied. E0-13's fail-open was narrowed to
one class — `httpx.TimeoutException`, decided on the exception chain rather than
on a message, deliberately, because a rule that reads a library's sentence breaks
when the library rewords it. The docstring said the class meant "the request
reached an endpoint and the endpoint did not answer in time".

`httpx.ConnectTimeout` subclasses `httpx.TimeoutException`. So a connect that
never completed — no handshake, nothing sent — was inside the narrowed class and
still fell open. Measured against a blackholed route, **with zero requests
reaching any server**: the comment was classified by counting characters, and the
record said a floor decided, exactly as it had before the narrowing.

The record was worse than the code. [ADR 0056](../adr/0056-only-a-timeout-fails-open.md)
justified the whole change with an availability argument — an attacker who can
force a handshake failure can force no classification indefinitely — and dropping
packets is cheaper than forcing a handshake failure and has the same effect. The
ADR argued for a property the code it described did not have.

**Root cause.** Matching on a base class to express a decision about the world.
The question the fail-open turns on is *did the request reach an endpoint that
could have answered, and was the answer about the endpoint or about the request* —
and that is not what any single node of `httpx`'s tree means. A base class is a
set the library defines and may extend; naming one in an `except` or an
`isinstance` is a decision about every member of it, including the members added
in a minor release after the line was written. Reading the sentence was correctly
rejected as coupling to the library's wording. Reading the type is the same
coupling to the library's taxonomy, and it looks principled rather than fragile,
which is why it was not questioned.

**Consequence.** The narrowing shipped, the ADR claimed the property, and the
suite was green — the tests written for it exercised a refused connection, which
is on the correct side of the line by accident of `httpx` raising `ConnectError`
rather than `ConnectTimeout` for it. One review pass and one measurement apart
from an availability guarantee that did not exist.

**Rule.** **When a check expresses a decision about the world, do not encode it as
a check against a library's class tree.** Write down the question first — here,
"did the request reach an endpoint that could have answered?" — enumerate the
conditions on each side of it, and map each condition to a class explicitly. The
repair was exactly that: four classes of the project's own, one per answer, with
the library's types as inputs to the mapping rather than as the mapping.

**And when you must name a base class, enumerate its subclasses at the moment you
name it, and say in the code which ones you mean.** `ConnectTimeout`,
`ReadTimeout`, `WriteTimeout` and `PoolTimeout` are all `TimeoutException`, and
only two of them mean the thing the docstring claimed. If the list is long enough
that enumerating it is tedious, that is the signal that the base class is not the
line you want.

**A docstring that names a distinction the code does not make is the expensive
half.** The line was reviewed twice with the sentence "the request was accepted"
sitting above a match that included the case where nothing arrived, and the
sentence is what both readings trusted. That is entry 1 arriving through a
comment: the code was wrong and the record explained it away.

## Instances

**2026-08-24 — a module split, and the docstring for one half (caught).** The
6,634-line `tests/conftest.py` was split into `tests/fixtures/`. The dispatch
brief settled the docstring for `fixtures/app_imports.py` in advance: "every
`sys.modules` / `sys.meta_path` manipulation in the suite lives in this one
module". The last half of this entry's rule is what sent the author to grep the
distinction rather than transcribe it, and the sentence was false in two places —
`fixtures/seed.py` registers `scripts/seed.py` in `sys.modules` under a name of
its own, and `tests/unit/test_db_engine_configuration.py` and
`test_care_engine_configuration.py` each drop the backend's `app` modules inside
a test. Only the `sys.meta_path` half and the *shared fixtures* half of the
`sys.modules` half were true. Written as the narrower claim with both exceptions
named, so the next person hunting an import-order defect is not told there is
nowhere else to look. A module split is the same shape as the class-tree split
above: the docstring for one half describes a line the split does not draw.
