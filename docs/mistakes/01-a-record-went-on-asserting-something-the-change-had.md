# Entry 1. A record went on asserting something the change had made false

**Caught: 37**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*20 instances recorded; the 4 most recent are below, oldest of the four first — dated from `git log -S"its first phrase"` on this file rather than read off the page order. The earlier 16 are in this file's git history and in the pull requests they cite.*

*(In E0-35, a documentation-only pass over three new sweeps. The brief named
five records to correct and the entry found four more by asking the question
rather than working the list: ADR 0014's own "Until something closes that"
sentence, which the record had written about itself and could not know was now
answered; three index rows in `docs/adr/README.md`, which is the highest-risk
shape this entry names — written once, never re-read; and a signpost in E0-22,
a live ticket, sending a reader to E0-21 for a residue that had moved twice.
None of the four was in the brief, and the branch would have shipped with a
green suite and four records pointing at the wrong owner.)*

*(In E0-36 item 1, where the record that went stale was **the comment attached to
the line being changed**. The brief named one site — ADR 0002's last consequence
bullet, claiming the aggregate `ci` job "stays correct without edits as
individual gates flip from tolerant to enforcing" — and it was right that this is
the only claim in `docs/`. It is not the only claim. The verdict step's own
header comment in `.github/workflows/ci.yml` said the check "fails if any gate
failed or was cancelled; tolerant jobs report success, so this stays honest as
the tree fills in", which is the argument for leaving `skipped` out of the
pattern. Adding `skipped` to that same line would have left a comment three lines
above it explaining why `skipped` is deliberately absent — and the next person to
touch the verdict would have read the comment, believed the exclusion was
considered, and put it back. **The record most likely to be missed is the one you
are looking straight at**, because a comment above the line you are editing reads
as context rather than as a claim. The sweep has to include the diff's own
neighbourhood, not only the rest of the repository.)*

*(In E0-26 item 1, and this one is a catch and a recurrence in the same commit,
which is why it is worth the space. The change replaced the Care reveal, and the
ticket named three records to repair. The sweep found five more that nothing had
pointed at: ADR 0001's rejected-alternative block and its "one transaction"
consequence, ADR 0042's "two connections mean two transactions" consequence —
which named the wrong function once the door was split — and its "what this does
not fix" paragraph, ADR 0043's three-grant decision list, `docker-compose.yml`'s
comment justifying why `CARE_DATABASE_URL` is blanked, and the epic README's
decision row. **The same sweep then missed eight more**, found only when a
coordinator asked what the counter bump was for: the ADR index row still titled
0043 "holding three grants"; two more sentences inside ADR 0043 itself; ADR
0001's numbered decision item, false twice over — "Care's only access is **one**
`SECURITY DEFINER` function that returns identity and writes the audit row **in
the same transaction**"; two sentences in ADR 0040, which 0043 had already
amended once for the role count; the repository's own top-level `README.md`; and
`backend/app/models/__init__.py`, which is source rather than documentation.

Three of the eight were inside the two ADRs being amended at the time, which is
the shape worth naming: **the paragraphs that got repaired were the ones read
while writing, not the file.** And none of the eight surfaces from grepping
`reveal_student_identity`, because none of them names it — they carry the *fact*
("three grants", "in the same transaction"), which is what a record about a
mechanism actually says. The identifier grep found the sites that mention the
function; the fact grep is what finds the sites that describe it. The index row
was the worst of them, and this entry's own rule already says indexes are the
highest risk, so knowing the rule was not enough — the sweep has to be a list of
greps run, not an intention.)*

*(E0-30's second fix round, where the false records were made false by a
**two-name change to a frozenset**. Adding `error` and `error_description` to
`app.config.RESPONSE_PARAMETERS` — so a registered redirect URI can no longer
preset a name a refusal now appends — falsified three sentences the round's brief
did not name: the `ConfigurationError` message and the comment beside the set,
both of which said "the authorization response appends" and now have two
responses to account for; `app.flow.added_to_query`'s docstring, which said
`validate` "refuses only one already holding `code` or `state`"; and ADR 0062's
fifth rule, which said the same thing in the same words. **Grepping the fact
rather than the identifier is the whole of why they were found**: a search for
`RESPONSE_PARAMETERS` finds the first and neither of the others, because neither
mentions the constant — a search for "already carrying" and "already holding"
finds all three. The same search turned up a fourth site, `docs/mistakes/13`'s
account of the E0-16 incident that put the rule there, and that one was
deliberately left alone: a historical instance says what was true then, and
editing one to match today is how an incident record stops being evidence. The
sweep also had to be run twice, because the round's first commit changed
behaviour and its second changed the records — the second sweep is the one that
counts.)*

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
