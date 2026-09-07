# 0146 — A cumulative release is a batch row and a membership row, and no comment carries a time

## Context

SPEC §4 holds comments from weeks below the n-threshold and surfaces them later:

> Comments from under-threshold weeks … surface as raw text once the section's
> cumulative comment volume for the term crosses the threshold, batched so that
> timing cannot identify an author.

and one line down: "timestamps are never shown with comments".

E4's breakdown settled that the crossing is stored rather than computed at read
time (decision 7): a release re-derived on each read changes as data changes, so
a comment can appear and disappear, and the moment it first appears is itself a
timing signal. E4-02 builds the storage; E4-04 builds the crossing logic that
writes it.

The ticket states the grain as an open decision with a constraint on either
answer:

> **The release batch's grain** — a batch row that comments reference, or a
> batch label stamped onto comments. The constraint either way: E4-04 must be
> able to release a set atomically, and no per-comment release time may exist
> anywhere, because a stored timestamp nobody exposes today is a leak someone
> ships tomorrow.

The second half of that constraint is what makes this contestable. Both shapes
can satisfy "release a set atomically". Only one of them makes the absence of a
per-comment time structural rather than remembered.

## Decision

**Two tables.** `release_batch` holds one row per release — the section, the
term the cumulative threshold is counted over, and `cut_at`, the time the batch
was cut. `release_batch_member` holds one row per comment in a batch: the batch,
the comment, and **nothing else**.

`answer_id` is unique on the membership table and `batch_id` is not. A comment
is released at most once; a batch is a set. Both halves are load-bearing and
each is the other's near miss — a unique over `batch_id`, or over the pair
where `answer_id` alone was meant, refuses a second release exactly as required
and also makes every batch a single comment, which restores the per-comment
timing the batching removes.

**`cut_at` is the only time in the design.** It is a fact about a set of
comments, so it says nothing about any one of them, which is precisely what §4
asks for. There is no `released_at`, no `created_at`, and no column of any other
spelling on the membership row.

## Alternatives rejected

**A batch label stamped onto the comment** — a `release_batch_id` column on
`answer`, or on a moderation row. It is one table fewer and it satisfies
atomicity: one `UPDATE` releases a set. It loses the batch as a thing that can
carry a time, so `cut_at` has to live either nowhere (and the release is
undatable, which E4-04 needs for its own logic) or on the comment row — at which
point every released comment carries its own timestamp and §4's guarantee is
gone. The shape the ticket names and rejects, rejected for the reason it names.

**A batch row, with `released_at` on the membership row as well** — "for
debugging", or because a row convention adds one. This is the leak, stated as
the thing that would actually be written rather than as a hypothetical: nothing
would expose it on the day it landed, and the ordering of a term's held comments
would be recoverable one row at a time by anyone who could read the table.
`tests/integration/test_report_schema.py` asserts the membership row's whole
column set as an equality rather than searching for a name, so a column called
`surfaced_on` or `first_shown` reds exactly as `released_at` would.

**No membership table at all — recompute the released set from `cut_at` and the
comment's own submission time.** Cheaper, and it re-derives a different answer
whenever a comment is reclassified or a response is resubmitted, which is
decision 7's whole objection. It also makes the release depend on the submission
timestamp, which is the one value §4 is trying to keep out of the answer.

**Put the section on the membership row instead of on the batch.** It would let
one batch span sections. The threshold §4 describes is per section and per term,
so a batch that spanned sections would be several crossings recorded as one, and
its `cut_at` would date a release for a section that had not crossed anything.

**A composite `(section_id, term_id)` foreign key on `release_batch`, matching
`response`'s pattern.** The same trade [0145](0145-the-report-schema-has-its-own-module-and-moderation-starts-by-absence.md)
records for `weekly_summary`, decided the same way and for the same reason: the
only writer is E4-04, which derives both keys from the section it is releasing
for. Named here so that the two tables' identical shape is one decision rather
than two coincidences.

## Consequences

- **Adding any column to `release_batch_member` is a confidentiality change**,
  not a schema tidy-up, and it is asserted from two sides: the column inventory
  in `test_report_schema.py` (marked `invariant`, with the batch's own `cut_at`
  as the control it must find) and the `REACHED_TABLES_THAT_CARRY_NOTHING` entry
  in `test_identity_column_marker.py`. Both go red, which is intended — the
  change belongs in the pull request that argues for it.
- **A comment cannot be un-released**, because a released comment is a row and
  nothing in this schema deletes one. If E4-04 or a later ticket needs to undo a
  release, that is a second decision — a state column, or a reversing row — and
  it is not made here.
- **A re-run of E4-04's release after a partial failure is safe at the
  database**, because the second membership for a comment is refused. What it is
  not is *silent*: the writer meets an integrity error rather than a no-op, and
  E4-04 owns deciding whether that is caught or is a defect to see.
- **`release_batch_member` reaches a person in two hops** — `answer.response_id`
  then `response.user_id` — so the identity walk reaches it and it carries a
  recorded entry saying what it holds and why nothing on it is marked. It holds
  no identity of its own; what protects the person behind those hops is what
  protects them on `answer` itself.
- **Neither table is indexed beyond its constraints.** The read E4-04 will make —
  a section's batches, and a batch's members — is served by no index today, and
  the ticket that measures that read is the one that adds it, as
  `c4a8e51db9f3` did for the passback.
