# Entry 24. A test asserted a property no implementation could satisfy

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*(A fourth instance, E2-05, ruled in [E2-05-01](../disputes/E2-05-01.md) on
2026-09-01, and the first counted catch: the implementer recognised the shape
from this entry, measured it in both directions, and wrote the objection
instead of shipping the one schema change that would have satisfied both tests.
The sub-shape is the E2-02 one wearing a fixture: a control that names one
column of a pair and lets the shared seeding walker complete the row from a
constant chosen for a different table — two days before the named value — so
the control attempts the exact backwards row the sibling ordering test requires
the database to refuse. The naive-datetime test was red with the ordering CHECK
present and its sibling red with it absent; no implementation satisfies both.
What the entry prevented: a nullable `last_submitted_at`, which turns both
tests green and pushes a `None` into every later reader of the pair. The
repair is the control naming both timestamps, equal — the killed mutation is
unchanged because the naive guard sits on the column type and is reached by
whichever column carries the naive value.)*

*(A third instance, E2-02, ruled the same way in
[E2-02-01](../disputes/E2-02-01.md) on 2026-08-31. Third sub-shape, and the one
that hides best: **an assertion about one member of a collection, where a second
and entirely legitimate mechanism puts that same member there.**
`test_a_deployments_stored_roster_host_is_not_exempted_from_the_pin` required the
section's stored roster host to be absent from `roster_sync`'s `unpinned_hosts`
outside development. Two independent entries fill that set — the token endpoint's,
which ADR 0101 settles and which is unconditional in every environment, and the
roster host's, which the ticket narrowed — and the fixture's platform builds both
URLs off one issuer, so both entries are the string `roster-platform.invalid`. The
test therefore failed with the finding fixed exactly as it failed with the finding
unfixed, and the only code change that could satisfy it was one the ticket and the
ADR both forbid. **A test that is red in both states measures nothing**, and that
sentence — not the argument around it — is what settled the dispute. What made it a
measurement rather than a claim was disabling the *other* entry and re-running: the
test then failed earlier and differently (no token, so no page fetched), which
attributes the surviving entry beyond argument. The mutation was reverted before
anything else happened. The repair is the test author's and the ruling names it in
preference order: give the deployment fixture a token endpoint on a host distinct
from the roster host, or make the reader attribute each exemption to its reason.)*

*(A second instance, E0-26 item 1, ruled the same way in
[E0-26-01](../disputes/E0-26-01.md). Same entry, different sub-shape: not a needle
that collides with prose, but **a predicate that read a rendering carrying more
than the property under test**.
`test_the_reveal_takes_the_records_identifier_and_nothing_else` compared
`pg_get_function_identity_arguments(oid)` against `'uuid'` to pin the reveal's
argument type. That function renders the parameter's **name** as well —
`in_reveal_id uuid` — so the assertion refused the exact signature the ticket
settles, the signature its own failure message told the reader to build, and the
signature its own module printed in `THE_INTERFACE`. Only an anonymous parameter
could satisfy it, and nothing anywhere asked for one. The implementer declined the
workaround, wrote the objection, and waited — which is what entry 24's own closing
paragraph says to do and is the opposite of what happened the first time.
The repair is `array_to_string(p.proargtypes::regtype[], ',')`, which carries types
and no names. **Two neighbouring spellings are traps and were measured during the
ruling**: `p.proargtypes::regtype[]::text` renders `[0:0]={uuid}` rather than
`{uuid}`, because `oidvector` is zero-based, so a literal comparison there is the
same false red one layer down; and `p.oid::regprocedure::text` is
`search_path`-dependent, schema-qualifying when the function is not visible on the
current path, which makes it right for a failure message and wrong for a
predicate. The column was also called `arguments` while holding a rendering of
names *and* types, and is now called `argument_types`, because the name is what
invited the comparison.)*


**What happened.** E0-13's leak detector searched every rendering of `Settings`
for any eight-character run of the fake credential
`fake-ai-provider-Qv7ZmXt4Ld9RbNsW`. One of those runs is the word `provider`,
and `Settings` has carried a field called `ai_provider_base_url` since E0-01 —
field names appear in `repr()`, in `model_dump()` and in every other
serialisation by construction. So the assertion was false before the ticket
started, and stayed false with the key correctly masked as `SecretStr`. Seven
parametrised tests, red for every possible implementation, printing "The AI
provider key leaked into repr(settings): ['-provide', 'provider']" — a report
about the word "provider" appearing inside the word "ai_provider_base_url".

The fixture's own comment states the property it needed and did not have: "Long
and unlikely-looking so a fragment appearing in a rendering is unambiguously a
leak rather than a coincidence." The random tail has that property. The four
English words in front of it do not, and one of them names the subsystem being
configured.

**Root cause.** A substring search for a secret, over text that legitimately
contains words *about* the secret. The prefix was added to make the fixture
readable to a person, which is the right instinct for a fixture and the wrong one
for a needle — the needle's only job is to be findable and unmistakable.

**Consequence.** A dispute round ([E0-13-01](../disputes/E0-13-01.md)), because the
implementer cannot edit a test and the only fixes available on the implementation
side were worse than the defect: renaming an E0-01 settings field in an E0-13 pull
request, or editing the `.env.example` placeholder URL, either of which is
removing a substring from a rendering to satisfy a search rather than satisfying
the property the search stands for.

**Ruled on**, outcome 1 — the test is wrong — and the needle is now random
throughout (`ae7518d`). The ruling found one thing this entry did not, and it is
the expensive half: the *same* needle is used in
`tests/integration/test_ai_gateway_validity_roundtrip.py` as a **positive**
detector, to prove the key was really sent before anything is asserted about it
not leaking. There a collision does not go red at all — it satisfies the
non-vacuity guard against a request that never carried the key, and every leak
assertion beneath it then reports a guarantee that was never tested. A search term
shared between a must-find rule and a must-not-find rule fails in both directions
at once, and only one of those directions announces itself.

*(This entry was written and committed in `6771d56`, before the arbitrator ran,
stating an outcome that had not been reached. The rule was right and the ruling
confirms it, which is luck rather than method: writing the record ahead of the
ruling is the thing the dispute loop exists to prevent, and a record that had gone
the other way would have had to be retracted rather than amended. Write the
objection, then wait.)*

**Rule.** **A fixture that will be searched for must share no substring with
anything the assertion legitimately renders.** In practice: make it random-only,
with no word in it. Put the human-readable label in the *constant's name*, where
it helps a reader, not in its value, where it is a needle.

**And the same rule pointing the other way, from the second instance: when a
predicate compares against a value some other system rendered, ask what else that
rendering carries.** A catalog function, a `repr()`, a serialiser and a formatter
are all written to be *read*, so they add names, labels, qualifiers and bounds that
the property under test says nothing about — and an equality against one of those
is an assertion about all of it. Print the readable rendering in the failure
message, where the extra material helps; compare against the narrowest value that
carries the property, and say in a comment which neighbouring spelling you rejected
and what it renders instead. A column named for the property while holding the
rendering is how the next person makes the same comparison.

**And from the third instance, for anything that asserts about a set, a list or a
log: before asserting that a member is absent, ask what else legitimately puts it
there.** If a second mechanism can, the assertion is not about the mechanism under
test — it is about the union, and it will report the same red whether or not the
work was done. Either separate the mechanisms in the fixture so the member can only
have come from one of them, or make the reader carry *why* each member is present
rather than only which. The diagnostic, for whoever meets the red: disable the
other mechanism and re-run. If the failure moves, changes shape, or lands earlier,
the assertion was never reading what its docstring said.

The general form is worth stating because it is entry 3's mirror — and **the two
do not cost the same**, which the objection first argued and the arbitrator
declined to accept. It was right to decline. A permanently red test is loud and
can never ship a false guarantee; a wrongly green one ships one silently, and
nobody is looking. The red one is the cheaper failure, and saying otherwise
weakens a good objection by resting it on what is convenient to implement.

What settled the dispute was narrower and sufficient: **the test reported a leak
against text containing no part of the secret.** That is demonstrable in one line,
with no appeal to cost, to effort, or to what the implementation would prefer. Use
that shape of argument — the assertion is false about the text it was given —
rather than the balance-of-inconvenience one.

So: when a test goes red, the first question is still "what exactly is it
measuring", and the answer "a word in a field name" means the test is the thing to
fix. When the same term also drives a must-find assertion somewhere, check that
one too, because it will have gone green rather than red.
