# 48. A known gap was recorded only in a comment in the file that worked around it, and the next epic planned against it

## What happened

E3-08 is E3's exit ticket, and its acceptance criterion 1 requires every row of
its enrollment table to be driven against the running Compose stack. Two of those
rows — SPEC §3.4's undated tier, and the later-sync tier beside it — have exactly
one seeded case each, and both live in the mock platform's third section,
`NURS-8100-Q2FF`. The ticket names that section's windowless member outright.
The work order scheduled a drive through it, the test author wrote a spec that
launches into it, and the verifier confirmed the red run.

The section could not be launched. A staff launch into it lands the person and
provisions nothing: `_ingest_the_context` refuses a context whose label names a
prefix the institution does not hold, and `scripts/seed.py` seeded MATH, STAT,
MIS, BIOL, PSYC, CSCI and BUSA. The launch is recorded as an `unknown_prefix`
defect, and the API log says that one word and nothing else.

This was already known. E2 hit it, and wrote it down twice:

```
// version of this file staff-launched into `NURS-8100-Q2FF` to stand up a second
// enrollment, and the premise could not be met: `scripts/seed.py` seeds no NURS
// prefix, so the launch records an `unknown_prefix` defect and creates no section
```

Both sentences are comments inside the two E2 specs that worked around it, which
is a place no ticket, work order or manifest is written from.

## The root cause

A limitation discovered while writing a test was recorded where the *workaround*
lived rather than where the *next plan* would be read. This repository has two
places that are read when work is planned — `docs/tickets/eN/carried-from-e<N-1>.md`
and `docs/tickets/eN/deferred.md` — and a spec comment is neither. So the fact
survived perfectly, in prose, in a file nobody planning E3 had a reason to open,
while every artifact the ticket *was* built from (the exit table, the work order's
drive schedule, the test manifest's hand-computed numbers) assumed the opposite.

The second half of the cause is a fixture that looks complete from the outside.
The mock platform publishes three sections, offers all three on its launch page,
and signs a launch from any of them; nothing about that surface says the tool will
refuse one. "The mock seeds it" and "Pulse can provision it" are two facts, and
only the first is visible from the platform.

## The consequence

One drive cycle: the failure surfaced as `section holds 0 rows with
lms_context_id = mock-lms-context-nurs-8100-q2ff` after three launches that all
landed, which reads as a provisioning bug until the log is read. Then a change to
the demo seed — adding the `NURS` prefix — made inside an exit ticket, which is
the worst place to be changing the world every other suite reads.

It could have been worse in the ordinary way: had the drive worked around the
section instead, E3 would have exited with its two hardest §3.4 tiers proven only
in process, and the exit line "the mock-LMS gradebook shows correct percentages
across enrollment edge cases" would have been signed off against a gradebook that
never held those cases.

## The rule

**A limitation you work around goes in the deferral file the next epic reads, in
the same change as the workaround.** A comment in the spec that dodged it records
the fact for whoever edits that spec, which is the one person who already knows.
If it is worth a paragraph explaining why a test takes the long way round, it is
worth a line in `carried-from-eN.md` or `deferred.md` with an owner — those files
are the only ones a breakdown is written from.

**And when a plan names a seeded fixture, check the fixture reaches the product's
own database, not just the mock's.** A platform offering a launch, a page listing
a section and a roster serving members all say the *platform* holds it; whether
the tool will provision it is a different question with a different answer, and
the cheapest way to ask is to drive the launch and read the row rather than the
screen.

## Instances

**2026-09-06, FIX-04 (Python 3.14).** The ticket's Celery drive — three real
tasks called on the rebuilt images — found that `purge_launch_nonces` raises
`InsufficientPrivilege` on every run, and has since E1-08 shipped it on
2026-08-26: Postgres requires `SELECT` on the columns a `DELETE ... WHERE`
reads, and `pulse_app` deliberately holds only `INSERT, DELETE` on
`lti_launch_nonce`. That has nothing to do with the runtime move and nothing in
FIX-04 could fix it — a grant widening carries a test-side record behind the
test wall. The finding was on its way into the pull request body and the
implementer's report and nowhere else, which is this entry's shape exactly. It
went into `docs/tickets/e4/carried-from-e3.md` with an owner and a done-when
instead, in the same change as the drive that found it.
