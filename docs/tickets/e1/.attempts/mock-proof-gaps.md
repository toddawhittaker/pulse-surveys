# e1/mock-proof-gaps (E1 cleanup Batch B, items 2 and 3)

Heavy lane. Items 2 (machine-readable reason marker) and 3 (served defect
vocabulary). Items 1 and 4 are owned by the orchestrator — not touched.

## Finding before writing code (2026-08-28)

Item 2's replay marker test (`test_a_replayed_launch_names_the_replay_guard_in_
the_marker`) expects the marker `["NonceReplayedError"]`. But the launch route
(`api/lti.py:189`) catches `LaunchRefusedError`, and `verified_launch`
(`lti/launch.py:334-337`) re-raises the nonce-ledger replay as a **bare**
`LaunchRefusedError` — so `type(refusal).__name__` at the route is
`"LaunchRefusedError"`, not `"NonceReplayedError"`. The brief's literal
"pass `type(refusal).__name__`" therefore fails the replay case.

Resolution (not a dispute — the test is right, and the refusal path is in
scope): give `LaunchRefusedError` a `guard` property defaulting to
`type(self).__name__`, and have the replay wrapper set it to the wrapped
ledger exception's name. The lti.py sites pass `refusal.guard`; auth.py's
single unwrapped `SessionRefusedError` passes `type(refusal).__name__` as the
brief says. This keeps the guard vocabulary = the class name for every case
except the one wrapper, where the marker and the log now agree.

## Outcome (2026-08-28) — green

Item 2 (`deps.py` marker slot + `_reason_attribute`; `launch.py` `guard`
property + replay wrapper sets it; `lti.py` two sites pass `refusal.guard`;
`auth.py` passes `type(refusal).__name__`; ADR 0103) and item 3
(`mock-lms/app/config.py` `MOCK_DEFECTS_PATH`; `main.py` `GET /mock/defects`
serving `{"selectors": list(ALL_SELECTORS)}`).

All six targeted tests pass. Ran the full affected files (170), the three
shared-page files (34), and the whole unit suite (846) — all green. ruff
format/check clean; all three mypy passes clean. Item 4's spelling test
(`test_the_published_keys_numbers_are_spelled_as_unpadded_base64url`) already
passes with no code change (encoder already correct), closed as a records line.

Records: deferred.md closures for items 3 and 4; carried-from-e1.md closures for
the served-vocabulary and mock-IdP-spelling entries. Item 2 had no deferred.md
entry — it lived only in the cleanup plan as a PR #110 review note — so its
closure is the PR body, not deferred.md.
