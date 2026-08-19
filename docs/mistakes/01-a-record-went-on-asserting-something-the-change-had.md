# Entry 1. A record went on asserting something the change had made false

**Caught: 33**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*16 instances recorded; the 3 most recent are below. The earlier 13 are in this file's git history and in the pull requests they cite.*

*(In E0-16, and the sweep started from a list rather than from
a file. Adding a service to the health gate's `REQUIRED_SERVICES` is one line;
what it made false was in six other places, all of which read correctly until you
knew a third service existed. The workflow's own step names and the two comments
above them counted "four services named, six covered". The `Makefile` said "Three
services are named and five are covered" and had been wrong since **E0-14** —
`mock-lms` was never added to its health waits, so the local gate and the workflow
had disagreed for a ticket and a half, which is the drift `CLAUDE.md` means when
it says the workflow is right and that file is the bug. `.dockerignore`'s header
described "the two images this repository builds". ADR 0037 said E0-16 "faces the
same choice and should reach the same answer — or say why not", and ADR 0039 said
"a third `app` package would need a third run", both of which stop being true the
moment the ticket lands and both of which send a reader looking for work that is
finished. The epic README's "How CI tightens" table listed a Compose-health row
per mock and was missing one. And `README.md` introduced the stack as running
"the mock LMS described below" while §9.2 requires two doors. None of the six
fails anything.)*

*(In E0-33, where the stale record was the **ticket**. Its item 3
names two properties that "have no assertion anywhere today" — that no
`SECURITY DEFINER` function in `public` is owned by a superuser, and that the
reveal owner's grants are exactly the three its job needs — because it was written
from E0-20's text, which predates E0-10's later review round. Both landed in that
round, and ADR 0043's closing paragraph says so. Writing the two tests the ticket
asks for would not have produced two duplicates: same module, same subject, and
under a similar name a second `def` at module scope **replaces** the first
silently, so a test that exists today would have been deleted by a change whose
whole purpose was to add one. The item was routed instead at what is genuinely
unasserted — who else is named in an ACL, what the connection roles hold on a base
table, and a membership granted `WITH INHERIT FALSE`. **Before writing a test a
ticket asks for, check what already asserts it; a ticket is a record like any
other, and one written from another ticket's text is a copy that drifted.**)*

*(In E0-31 item 1, where the change was a **decision reversal** and the stale
records were the ones that had argued for the old decision. ADR 0065 said
"`mock-lms` is not registered by this or any other path in the repository" and
handed a reviewer a check built on it — grep for the issuer, find nothing. The
ticket named one record to amend, ADR 0038, and amending only that one would
have left ADR 0065 asserting the opposite of what shipped, in the paragraphs
whose whole purpose is to tell a reviewer the safety argument still holds. Five
further sites the ticket did not name: the ADR index row, the epic README's
dependency-graph line marking the item as the blocker on 18, its "two answers
still want an existing record amended" sentence, E0-17's hazard note, and
E0-18's context — which had to learn both that it was unblocked and what the
unblocking deliberately did not do. **A reversal falsifies more records than a
fix does**, because the records that argued the old way are the ones written
most carefully. The one part to leave standing is the superseded record's
rejected-alternative section: its reasoning is the cost the new decision
accepts, not an argument that turned out to be wrong.)*

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
