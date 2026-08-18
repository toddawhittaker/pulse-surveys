# Entry 8. Prescribing a fix without probing it

**Caught: 5**

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
