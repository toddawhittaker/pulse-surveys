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
