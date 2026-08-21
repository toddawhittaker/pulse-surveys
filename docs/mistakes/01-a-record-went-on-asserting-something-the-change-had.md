# Entry 1. A record went on asserting something the change had made false

**Caught: 41**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*24 instances recorded; the 3 most recent are below, oldest of the three first — this file's order is oldest-first, unlike entries 3 and 13. The earlier 21 are in this file's git history and in the pull requests they cite.*

*(E0-18 PR 1's second round, and this one is the entry applied **to the shape of
an assertion rather than to a sentence**. The claim-to-Care sweep had to gain a
named exception, and an exception is a record: it says "this module reads a claim
and names Care, and here is why that is allowed". Written as a set the assertion
merely subtracts, that record survives the module being deleted, renamed, or
rewritten until it no longer reads a claim at all — and it goes on excusing
something that is no longer there while the sweep quietly stops sweeping. So the
assertion is an **equality** between the flagged set and the exception set's
keys, and a stale exception fails as loudly as a new offender, with its own half
of the message. The same round widened
`tests/integration/test_identity_grants.py`'s hand-written privilege set by two
entries, and the derivation comment above it was extended in the same edit as the
constant — that constant exists precisely so a widening cannot justify itself, so
an entry added without its paragraph would have made the whole block a record
that no longer accounts for what it guards.)*

*(E0-18 PR 1's third round, where the false records would have been **the "what
is deliberately not here" paragraphs at the top of two test modules**. Both door
suites open by enumerating what they cover and what they leave to E1 — one says
"what *is* here is the set E0-18's own acceptance criteria name" and lists the
seven, the other says "two of the three refusals cannot be posed on the wire" —
and the round adds four sections to each. Appending tests without touching those
paragraphs leaves an index that undercounts its own file, in the highest-risk
shape this entry names: written once, three hundred lines above the tests anyone
opens the file for. The same round's other repair was `tests/conftest.py`'s
per-ticket index, which had to gain a sentence for a fixture that signs tokens,
and the claim-to-Care sweep's exception reason — a record that argued the Care
claim is harmless *from the web door alone*, which stopped being the whole
argument the moment the launch door gained a rule of its own about the same
claim.

The implementer's half of the same round found one the test author could not
see, and it is the more expensive shape: `backend/app/services/landing.py`'s
module docstring still carried three paragraphs of **"UNRESOLVED, and this
module is the whole of the disagreement"** — a dispute that had been arbitrated
one round earlier, in a change to a different file. Nothing in the source
pointed at it: the arbitration was recorded where the ruling belonged, in the
sweep's `EXCEPTIONS` reason, and the module that had been arguing its own case
went on arguing it. A record made false by a change to *another* file is the one
no author's diff-reading catches, because it is not in the diff — only asking
"what else asserts something about this" does.)*

*(E0-28, Batch E, and the three false records were **made false by code in a
different file, a different ticket's guess, and a count in prose**. The batch
made the mock platform's results container page, refused NRPS's own query
parameters, gave every line item id a query string, and seeded one member with no
enrollment window. The dispatch brief named the records for the last of those —
E0-15's criterion, ADR 0048, two module docstrings — and named none of the other
three. `README.md`'s seed section said "Two of them are not ordinary" about
`BIOL-215-R3WW`'s late add and drop, and the new windowless student made it
three: the count-in-prose shape this entry already warns about, found by grepping
the *fact* rather than any identifier the change touched. ADR 0051's closing
paragraph guessed that item 3 would need "a seeded line item shaped differently",
and item 3 landed as every id carrying a query instead — a record that was a
prediction when written and a false statement once the prediction was answered,
which nothing in the diff points at. And `docs/tickets/e1/carried-from-e0.md`'s
preamble said item 6 "adds the last section below" while a later section had been
appended after it by another ticket, so the sentence was already false before this
batch touched the file and would have stayed false through a change that rewrote
the section it describes.)*

**What happened.** Nine times, across three tickets. `.dockerignore`'s header
claimed it made secret leakage "impossible rather than unlikely" while `!backend`
re-included the whole subtree. The `db` health-check comment described
authentication that `pg_isready` never performs. A comment said the application
role held "nothing but CONNECT" when it kept Postgres's `PUBLIC` defaults. ADR
0007 claimed digest drift "is visible in a diff on both sides"; that was
retracted, and then the retraction itself went stale two commits later when the
guard landed. `.env.example` said both readers resolve `${...}` top-down, which
measurement disproved. The ADR index silently omitted three ADRs the same branch
shipped. Pull request #13's description spent a round describing a one-role
database stack that no longer existed.

A tenth, in E0-03, and it is the sharpest because of where it sat. The commit
that removed a false claim from `README.md` — that the worker ran the same code
as the API — put a new one in `docker-compose.override.yml` in the same diff: a
comment saying a stale worker makes `get()` hang, when the measurement in that
same commit's README said it raises `NotRegistered` for an added task and
silently returns the old answer for a changed one. It cited this file for it.

An eleventh and twelfth, in E0-12, in the same pull request, and both are the
variant where the record was **never** true rather than made false by a change.
ADR 0031 said a provider volunteering its own `model_id` "is refused rather than
trusted" because the contracts set `extra="forbid"`. `extra="forbid"` refuses
*undeclared* keys; `model_id` is a declared field, so a provider-supplied value
validates and round-trips, and which one survives depends on a merge order the
next ticket has not written yet. ADR 0030 said the hyphenated `self-harm` "stays
in the spec and in the prompt text" — but the enum's value is `self_harm` and
`"self-harm"` is refused, so a prompt author acting on that sentence would ship
a moderation prompt that fails on the one verdict §9.3 gates hardest. Neither
claim was ever run. Both were reasoned from what a setting is *for*, written down
in a record whose whole audience is the ticket that has to implement against it,
and found by an independent reviewer.

**Root cause.** Changing a mechanism and not asking what else in the repository
makes a claim about it. In the E0-12 pair, a second root cause with the same
consequence: reasoning about what a configuration option does instead of running
it. `extra="forbid"` and "forbid an extra value for a field" are one short step
apart in English and are different rules, and prose is where that step is
invisible — the code was correct in both cases and only the record was wrong. Three of these were *introduced by a fix for this same
class of defect* — the `.env.example` header rewritten to correct one false claim
acquired a different one, that `LOG_LEVEL` is settled by the spec, which the spec
never mentions; and the override comment above was written by a session that had
read this entry, bumped its counter, and used it to find four stale claims in
files it was not editing. The sweep is outward-facing. It asks what *other*
records say about the thing you changed, and a sentence you are writing right
now is not yet a record, so it is not in the set you sweep.

**Consequence.** A reader trusts the record over the code, because reading the
record is cheaper. That is what a record is for, so a false one is worse than
none. The stale pull request body was rated HIGH: it was the artifact the merge
decision rested on.

**Rule.** After changing a thing, ask what else in the repository asserts
something about that thing — comments, ADRs, tickets, indexes, READMEs, the pull
request body, test docstrings. Indexes are the highest risk: written once, never
re-read. "Re-read nearby prose" is not enough; it misses the record that was
never written and the one that drifted out from under you.

**Grep the fact, not the identifier, and re-read the whole record you are
amending.** A record about a mechanism states a property — "three grants", "in
the same transaction", "the only writer" — and a grep for the thing's *name*
finds none of the sentences that carry it. So the sweep is at least two greps:
one for the identifier, one for each fact the change makes false, in its own
wording. And amending a record is not reading it: open the whole file, because
the sentence three sections away from the one you were sent to fix is written by
the same author making the same assumption.

A thirteenth, in E0-15, and it is the sharpest instance of the count rule below
because it happened **inside the commit that bumped this entry's counter for
sweeping outward**. `README.md` and `mock-lms/app/seed.py` both said the seed
holds "twenty people and thirty-two enrollments". Twenty is right. Thirty-two was
never right: the three rosters hold twelve, seven and five, which is twenty-four,
and the number came from adding the same figure up in my head rather than out of
`seeded_platform()`. The table two lines below it in the README gave 12, 7 and 5
correctly, so the document contradicted itself on one screen and neither half was
re-read against the other. It reached three prose sites, a report to the
coordinator, and a commit message that cannot be corrected because history is not
rewritten here; the coordinator found it by counting the enrollments out of the
code. The repair deletes the number in all three places rather than correcting
it — the roster sizes are in the table, and a total is a number nobody will
recount the next time a section is added.

**And read the prose in your own diff as if someone else wrote it.** Every claim
you have just written is a claim nobody has checked, including the ones written
while correcting somebody else's. Where a sentence describes a behaviour, it has
to match what you measured — not what you expected to measure before you ran it.

This paragraph already existed when the E0-12 pair was written, and it is the
rule that would have caught both. It failed because "what you measured" reads as
being about experiments, and neither sentence felt like an experiment: one
described a library setting, the other a spelling. So, stated without the escape
hatch — **a claim about what a setting, a flag or a type refuses is a claim about
behaviour, and costs one line in a REPL to check.** If a record says something is
rejected, reject it before writing the sentence. This is entry 9 arriving through
prose rather than through a guard, and it is worth the two entries agreeing: the
expensive records are the ones a later ticket implements against, where the code
is right and only the sentence is wrong, so nothing goes red.

**A count in prose is a record with a scheduled expiry**, so prefer not writing
one. Three of these were counts — the ADR index that omitted three ADRs, "the
two tests below" in `tests/integration/test_term_calendar_schema.py`, left behind
by the commit that added a third and updated the identical count one docstring
over, and E0-15's thirty-two enrollments. The fix is to delete the number rather
than correct it: "the tests below" cannot go stale, and a sentence that needs the
number usually wants a different sentence.

**And a count is not only a stale-record risk — it is an unverified measurement.**
The E0-15 case was wrong on the day it was written, so no amount of re-reading it
later would have helped; what would have helped is the one thing nobody did,
which is to ask the program. A count of rows, files, tests or enrollments is a
number the code can produce in a line, and writing one from memory is entry 9
arriving through arithmetic: citing a total without executing the thing that
knows it. If a sentence must carry a number, get the number from the system and
say in the commit that you did.

---
