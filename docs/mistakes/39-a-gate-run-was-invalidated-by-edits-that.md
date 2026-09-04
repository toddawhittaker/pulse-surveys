# 39. A gate run was invalidated by edits that landed while it ran

## What happened

Building E1-09 (2026-08-26), the implementer started the full unit+integration
suite and, while it ran, used `git checkout` in the same tree to inspect the
branch point. The run reported 30 failed / 26 errors, all `ImportError` — output
that read exactly like a broken change. The errors were read before they were
believed, so nothing shipped from it; the cost was a wasted seven-minute run and
a readout indistinguishable from a real regression. The incident is recorded in
`docs/tickets/e1/.attempts/E1-09.md` §6.

## Root cause

A test run reads the tree lazily, module by module, for as long as it runs. An
edit — or a checkout, which is hundreds of edits — landing mid-run splits the
run across two trees, and the report it prints belongs to neither. Nothing warns:
pytest cannot know the tree moved, and the failure shapes (ImportError, missing
constant, F821) are the same ones a genuinely broken change produces.

## Consequence

A false-red gate readout. The benign outcome is a wasted run and a re-run; the
dangerous one is "diagnosing" the phantom failures — or, mirrored, a mid-run
edit making a red run print green, which is a false report about the system.

## The rule

While a gate runs, the tree it runs in is read-only — no edits, no checkouts, no
restores. A gate's verdict is valid only for the tree it started on; if the tree
moved mid-run, the verdict is void and the run is repeated, whatever it printed.
This is the same discipline the mutation battery already keeps (commit before
mutating, snapshot rather than checkout) applied to every gate, including one's
own.

## Instances

**E1-13, 2026-08-27 — the red baseline, and the file that would have gone green
under it.** The heavy lane opens by confirming the committed reds, and that run
is twelve minutes of wall clock on this suite. Rather than idle, I had drafted
the ticket's new `views_sql` files and its Alembic revision and was about to
write them into the tree while the run was still going. This entry is why they
went to a scratchpad directory instead and were applied afterwards.

What it prevented is specific rather than general. One of the 58 committed reds
is `tests/integration/test_identity_grants.py`, whose `SANCTIONED_VIEW_COLUMNS`
enumeration the test author widened with `permits_launch` and `permits_web_login`
— it is red precisely because the view does not publish them yet, and that red is
the evidence E1-01's guard fires. Writing the migration mid-run would not have
applied it, but the two `.sql` files and the revision landing in the tree is the
kind of change that suite reads, and the run had not yet reached it. A baseline
that printed 57 or 58 over a tree that had moved is a number nobody could
reproduce, and the whole point of the run is that the count is the record the
ticket is built against.

The cheap generalisation, worth having: a twelve-minute gate is not dead time to
be filled with edits. It is dead time for reading, and for drafting somewhere the
gate cannot see.

**E1-11's fix round, 2026-08-27 — the correction I did not make mid-run, and
what the honest re-run then found.** The full suite was twelve minutes into its
run when reading SPEC §14.3 showed that the AGS deferral I had just written
named the wrong owner — E2, copied from the work order, where §14.3 gives grade
passback to E3. The correction touched four records and one source comment, and
the temptation was to make it while the run finished, since "documentation
cannot change a Python result".

It can: `tests/unit` holds sweeps that read `docs/` and the source comments, and
they had already run. A verdict of "2 failed, 1858 passed" over a tree that
gained five edits at minute twelve is a number belonging to neither tree. So the
edits waited, and the affected suites were re-run afterwards — which is how the
one-second race in
`test_mock_lms_client_credentials_grant.py::test_an_assertion_dated_beyond_the_platforms_clock_and_the_stated_skew_is_refused`
was found at all: it fails when more than a second passes between the test
reading `time.time()` and the platform reading its own, and it had passed in the
full run an hour earlier. Had it appeared in a run I had edited under, the
obvious diagnosis would have been my own edit, and the real defect — a test
whose expected boundary is computed before two RSA signatures — would have gone
back to sleep.

**FIX-01, 2026-09-03 — the record corrections that waited four and a half
minutes, and the sweep that named a file.** The green run of
`pytest tests/unit tests/integration -n 4` was under way and the ticket's record
corrections were drafted and ready: a docstring paragraph in
`backend/app/services/survey_read.py`, one in
`frontend/src/components/WeekEyebrow.tsx`, and two stylesheet comments. Prose
only, and the temptation was the same one E1-11 records — documentation cannot
change a Python result.

It could have, in a way specific to what that run found. The run came back with
one failure:
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py::test_no_module_outside_the_sanctioned_locations_runs_sql_naming_a_policed_relation`,
reporting `{'backend/app/schemas/student.py': ['section']}` — a sweep that parses
**every** module under `backend/app/` and reports the offenders **by path**. One
of the queued edits was to a docstring in a module in that sweep's set. Landing
it at minute two would have meant a failure naming a file, listing a relation,
over a tree where one of the parsed modules had moved underneath the parse —
with no way to tell whether the offending string was the schema's `Field`
description or the paragraph I had just written, and the fix for the wrong one
would have looked like it worked. The edits went in after the run, and the
single offender was then unambiguous and one word wide (entry 43).

**E3-03, 2026-09-04 — the attempts file that would have landed at minute two of
the run being reported.** The ticket's whole-suite pass runs four and a half
minutes, and the two things still owed — the mutation battery's results written
into `docs/tickets/e3/.attempts/E3-03.md`, and a counter bump in this file — were
drafted and ready while it ran. Both are prose in `docs/`, and the temptation is
E1-11's exactly: documentation cannot change a Python result.

It can here for a reason this ticket can name. E3-03's own deliverable is swept by
`tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py`, which
parses a file off the disk at test time rather than importing it, and the same
suite holds sweeps that read `docs/`. The run in question is the one vouched for
in the pull request as "2720 passed" — a number whose only value is that it
describes one tree. Landing two files at minute two would have made it describe
neither, and nothing in the output would have said so. The edits waited; this
paragraph is one of them.

**Note for whoever trims this file next.** The rule is the three most recent
instances, and adding this one makes four. Removing the oldest (E1-13) was
refused by the permission classifier as a deletion from a mistakes record, so the
trim is left rather than worked around.
