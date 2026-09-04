# 0129 — A post's outcome is an enum and a nullable response code

## Context

ADR 0124 settles that `grade_sync` is append-only at the grain of one row per
post and that a failed attempt is a row too. It leaves open what "the outcome"
is made of, and SPEC §8 says only that the row records it.

Three things could reasonably be stored, and they are not the same question.
Whether the post succeeded, which is what E3-06's retry decision and E11's job
dashboard branch on. What the platform answered with, which is what an operator
reads when a gradebook stops updating — a 401 is a credential problem and a 503
is not. And what the platform *said*, its response body, which is what somebody
debugging a specific failure would most like to have.

The table grows with posts all term and nothing purges it until E13, so
whatever is stored per row is stored a great many times.

## Decision

The outcome is **two columns and no more**: a closed enum of two members
(`posted`, `failed`) beside a nullable integer `response_code`.

**`response_code` is nullable and NULL has exactly one meaning: the call never
reached the platform.** That is `nrps_call`'s semantics for the same column
(ADR 0095), carried over deliberately so §6.1's console reads one idea rather
than two.

**The enum has two members and not three**, because "refused with a 401" and
"never got there" are both failures and are told apart by the code beside the
column. A third member would put one fact in two places that can disagree.

**A platform's response body is not stored**, on this table or on `ags_call`.
A failed attempt records the code and never the body.

## Alternatives rejected

**Store the response body, nullable, for failures only.** The tempting one, and
it would genuinely have made an afternoon of integration debugging easier. It
puts an unbounded third-party string on a row written once per post per student
per re-post, on a table nothing trims for years; a misconfigured platform can
echo the request that produced it, which on this path is a score against a
student; and the retention question it creates arrives long after the person who
added the column has moved on. The debugging need it serves is real and belongs
in a log line at the moment of the failure, where it is subject to the log
retention that already exists, rather than in a durable record of what a student
was told.

**The response code alone, with no enum.** Fewer columns, and success is
"2xx". It makes every reader re-derive the outcome from a number, including the
NULL case, which is the re-derivation ADR 0052 warns about in a different
guise: two readers will eventually disagree about whether a 3xx or a 207 was a
success. E11's dashboard and E3-06's retry branch both want a decided answer,
and deciding it once at write time is where it belongs.

**An enum wide enough to carry the failure kinds** — `refused`, `unreachable`,
`timed_out`, `rejected`. Rejected as the outcome column's job. Those are
distinctions the response code already draws for the two that matter, and the
rest are transport details that belong in `ags_call`, which is at the grain of
the HTTP call and is where an operator looks for them.

**Free text rather than an enum.** Nothing in this project stores a closed set
as free text, and the reason is unchanged here: an open column is one a later
writer puts `pending` or `skipped` into, leaving both readers with a case
neither was written against and nothing red anywhere.

## Consequences

**A failure is diagnosable to the level of "which class of thing went wrong"
and no further, from this table alone.** An operator who needs more goes to
`ags_call`, which records one row per HTTP call, and to the log line the caller
wrote at the time. That is a deliberate loss and it is where the boundary is
drawn.

**The two columns can disagree if a writer is careless** — `posted` with a NULL
code, or `failed` with a 200 — and nothing in the schema refuses it. A CHECK
tying them was considered and left out for the reason `Term` and `Section`
leave out their arithmetic constraints: the pairing belongs to the one writer
that makes the call and knows what happened, and a copy of the rule in the
schema is a second place for one rule to live. E3-04 and E3-06 are that writer.

**`grade_sync` and `ags_call` mean the same thing by a NULL response code**, so
E11's console needs one reading of it rather than two, and a reviewer comparing
the two tables finds them consistent rather than merely similar.
