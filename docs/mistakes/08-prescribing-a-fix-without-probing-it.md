# Entry 8. Prescribing a fix without probing it

**Caught: 7**

*7 preventions recorded: the two set out in "What happened" below, and the five
notes above — three from earlier reviews (E0-17, a second E0-10, E0-26) and this
fix round's two, round 2's caught and then unmade when round 3 probed harder,
round 3's the one that stood.*

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(In E0-17's review round, applied to somebody else's prescription
rather than my own. A reviewer reported that the seed adopts a `prefix` row it did
not create and prescribed "refuse rather than adopt". Both halves were probed
before either was believed: a throwaway script stood up the pinned Postgres,
migrated it, planted a real institution holding `MATH` and a real `MATH 210`, and
ran the seed — which moved the prefix to the demo's department, overwrote the
course title, and **exited 0 with its success line**. The same script re-run
against the fix showed exit 2, the real rows untouched, and no partial demo
institution, which is the half a prescription cannot tell you: that the refusal
lands inside the one transaction. Reading the schema would have confirmed the
defect and told me nothing about the repair.)*

*(And it is the second time this entry has caught a prescription
about the same tuple. A review of E0-10 found that the Care-session sweep in
`tests/unit/test_care_session_is_bound_to_the_care_service.py` cannot see
`Settings.care_database_url`, and prescribed widening `SESSION_FRAGMENTS`. Run
before being written down, over the 26 modules under `backend/app` and over the
reviewer's own future module, the widening does close that shape and does not
close a second one: `defined_here` subtracts **any** assigned name, so
`care_database_url = settings.care_database_url` — the exact idiom
`app/services/safety.py` itself uses — masks the attribute read and the sweep
reports nothing with the widened tuple in place. The prescription was necessary
and not sufficient, and reading it would not have shown that.)*

*(In E0-26 item 1, and the third time — on my own design this time rather than a
reviewer's prescription. The reveal had to refuse a record its caller has not
committed, and the ticket ruled out the obvious spelling: comparing the row's
`xmin` against `pg_current_xact_id()` is defeated by a caller who wraps the
recording call in a `SAVEPOINT`, because the row then carries a subtransaction
id. I had settled on a second mechanism that avoids the whole question —
`NOT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'transactionid' AND
transactionid = <the row's xmin>)`, reasoning from the documented behaviour that a
subtransaction acquires a lock on its own xid, so "no lock" means the writer has
ended and a visible row whose writer has ended is committed. Types match, no epoch
arithmetic, one predicate.

Probed before writing. On the pinned image, after `BEGIN; SAVEPOINT s1; INSERT …;
RELEASE SAVEPOINT s1;`, `SELECT count(*) FROM pg_locks WHERE locktype =
'transactionid' AND pid = pg_backend_pid()` answers **1, not 2** — the
subtransaction id is not there to be found. The guard would have reported "the
writer has ended" for the savepoint row and opened the door: the exact defect the
ticket named, reached by a different route than the one it warned about, in the
one `SECURITY DEFINER` function in this codebase. `pg_xact_status` was taken
instead, and measured against all three cases before being written down.

**The mechanism that avoids the trap is the one to probe hardest**, because it is
chosen precisely for not having the known flaw and nobody looks for a second one.
And note the shape: this candidate failed *open*, which is the direction a
confidentiality guard must never take — it decides from the absence of evidence,
so an empty answer is a yes. Probing is what turned that from a review finding
into fifteen minutes.)*

*(In E1's boundary-fix batch A, round 2, and it is the sharpest instance this
entry holds — because the probe **was** run and the fix was still wrong. Round
2's rule 6 had to refuse a fetched address whose judging parser and fetching
client read a different host. The prescription was probed before it was written,
which is this entry working: run against the suite's host shapes, a direct
comparison of the raw parsed host against the client-prepared one *appeared* to
refuse every internationalised domain — `röster.example` parsed,
`xn--rster-jua.example` dialled — and rebuilding the judged URL as
`https://{host}/` *appeared* to refuse every IPv6 literal. So round 2 added a
second preparation of the judged host and a re-bracketing step to sidestep both,
and recorded a catch. Round 3 probed harder and found the catch rested on a
misread: `url_host` already IDNA-encodes, through `canonical_host` and urllib3,
so `röster.example` is punycode on **both** sides with no second preparation —
the IDN refusal round 2 feared could not have happened, and the re-bracketing was
for a problem that was not there. Worse, the re-prepared form round 2 chose was
itself defeated one level out: a backslash inside the host truncated both sides
to the same string, so the rule reported agreement about a name the packet would
not go to. This is the entry's own warning turned on the fix that heeded it — the
mechanism chosen precisely to avoid a known flaw is the one to probe hardest, and
round 2's re-preparation was exactly that mechanism, and exactly the one that
needed the harder probe it did not get until round 3. Counted, because the probe
is what surfaced the whole thing; qualified, because a harder probe unmade its
conclusion.)*

*(And round 3, which is where it was made right — the genuine catch this entry
credits, twice on one round's fixes. The rule 6 rewrite was reduced to one line —
compare the dialled host directly against the judged one, no second preparation,
the step round 2's misread had added — and before it was written the settled
design was run against fifteen host vectors: the five divergences it must refuse
and the ten legal spellings it must accept, each read three ways (parsed,
dialled, and the judged name re-read). It held, and the probe was kept as the
record. The parser's unterminated-quote fix was probed the same way against
sixteen header shapes, which is where "does this still pass every round-1 and
round-2 green" stopped being a hope. And the pin's fail-closed — a guard chosen
precisely because it sits behind rule 6 and is never reached in normal operation
— was proved to fire against the diverged host before it was believed, then
exposed by removing rule 6, exactly entry 9's demand made on a guard that would
otherwise be a comment. The one-line prescription was correct; the probe is what
let it be believed rather than argued, and it is the same fifteen minutes each
time.)*

**What happened.** `hide_input_in_errors=True` was the obvious fix for a
credential appearing in a pydantic validation error. It cleans `str(exc)` and
leaves the credential in `errors()`.

A second, in E0-10's objection file, caught by this entry before it was filed.
The objection proposed a widened identity-column fragment set for the marker
sweep and wrote out the tuple: `"name", "email", "login", "picture", …`. Run
against the schema as it stands, `login` matches
`role_assignment.permits_web_login` — a boolean about which doors a role opens,
carrying no identity — so the proposed fix would have arrived as a new red test
in a module nobody had touched. `login_id` adds nothing on today's schema, which
was measured the same way. The prescription was one word wrong and read
perfectly.

**Root cause.** The fix was plausible and cheap, so it went into the brief
without being run. In the second case the tuple was written by thinking of
claims a roster sync carries, which is the right list to start from and is not
the same question as "what does this substring match in the schema I have".

**Consequence.** Would have shipped green against the one test that existed,
leaving the credential one `json.dumps` from any structured logger. The second
would have handed an arbitrator a fix that breaks a passing test, in the file
whose whole subject is a sweep that fires on the wrong things.

**Rule.** Before naming a mechanism in a brief, run it. If you are asking for a
property, say the property and let the implementer find the mechanism.

---
