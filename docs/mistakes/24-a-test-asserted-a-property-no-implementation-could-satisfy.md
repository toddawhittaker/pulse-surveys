# Entry 24. A test asserted a property no implementation could satisfy

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


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
