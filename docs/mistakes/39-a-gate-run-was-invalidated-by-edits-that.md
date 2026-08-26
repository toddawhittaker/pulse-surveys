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
