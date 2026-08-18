# Entry 2. Behaviour shipped with nothing asserting it

**Caught: 29**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*10 instances recorded; the 3 most recent are below. The earlier 7 are in this file's git history and in the pull requests they cite.*

*(In E0-17, and the interesting part is the delay. The
`ENVIRONMENT` guard on `scripts/seed.py` shipped with nothing in the suite
executing it — the module's one run with a deployment name sat behind a condition
that is false — and the implementer noticed, said so in ADR 0063's own
consequences and in the pull request, and shipped anyway because it may not write
under `tests/`. That is this entry working as far as it can reach: **the
behaviour was still unasserted, and what the entry bought was that nobody had to
discover it.** The test author then wrote ten tests against the record's
description, and the tenth failed — the guard is satisfied by `.env` when the
process environment does not supply the variable, which no hand measurement had
asked. So: an entry that turns "shipped unasserted" into "shipped unasserted, in
writing, with an owner" is worth its counter even when it cannot stop the ship,
because the sentence in the record is what got the tests written and the tests
are what found the defect.)*

*(In E0-16, and it is the twenty-fifth's shape one ticket
later: a gap declared by the agent that could not close it. Two malformed-PKCE
500s were found by the implementer reading its own finished code, and both fixes
shipped with nothing asserting them — every PKCE value the suite sends comes from
`secrets.token_urlsafe`, so no test could produce the byte either guard broke on.
Saying "no test covers this" would have been enough to be honest and not enough
to be acted on. What made it actionable was naming the *reason* nothing covered
it, in the commit message, the attempt log and the report alike: the sentence
about `secrets.token_urlsafe` tells a test author what to build, where "this is
untested" tells them only that something is missing. Both tests exist now, one
per entry point, and the coordinator mutated each to prove they fail
independently — which matters here because the second defect was the first one's
mirror image and a single test covering "malformed PKCE" would have gone green
with either half regressed.)*

*(Writing E0-13's tests, and the rule it caught was one nobody
had ever broken. `CLAUDE.md` says "Never add a secret reference to a workflow
without asking first", and E0-13 is the first ticket with a reason to want one —
`ci.yml` already carries a notice saying the eval suite "needs a provider API key
as a repository secret and a `secrets.*` reference in this workflow", marked
proposed and not wired. A rule stated in a document and asserted by nothing is a
convention, and the next person to add one does so with every gate green. So
`test_no_workflow_references_a_repository_secret_beyond_the_permitted_set` now
sweeps the workflows against a permitted set of one — `GITHUB_TOKEN`, which
Actions supplies rather than anyone configuring — and it passes today, which is
the point of it: **a guard for a rule with no incident behind it yet is still a
guard, and it is cheapest to write in the round that first wanted to break it.**
Its own pattern is tested against a reference it must catch, an unspaced variant,
and the prose in `ci.yml` it must *not* catch, per entry 3.)*

**What happened.** Four times. `__repr_args__` was added to keep credentials out
of `repr(settings)` — deleting it left the suite green. The `institution_timezone`
validator could be deleted whole with the suite green. "`DATABASE_URL` must never
point at the superuser" was prose, and repointing it passed all 50 tests and the
`docker` gate. The two Postgres image digests could be set to different values
with every gate green.

**Root cause.** Fixing the defect and stopping there. The fix is visible in the
diff, so it feels done; nothing makes the absence of a guard visible.

**Consequence.** The next person deletes it during an unrelated refactor and
every gate stays green. For the superuser case, the exact defect the pull request
existed to fix was reintroducible without any signal.

**Rule.** After fixing something, try to reintroduce it. If the suite stays
green, you have written a convention, not a guarantee. Prefer asserting the
*forbidden* state over the permitted one — it keeps working when a legitimate
second case arrives.

---
