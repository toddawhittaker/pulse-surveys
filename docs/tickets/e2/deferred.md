# E2 — items a ticket deferred rather than fixed

Created by E2-05's PR, per the epic README: a PR that defers something adds it
here in the same PR, and E2-13 runs the cleanup pass over this file. Each entry
names the ticket that owns it and what "done" means, so the deferral is a
scheduled decision rather than a hope.

## Nothing ties an `answer`'s filled column to its question's kind — E2-08

Deferred by E2-05 (PR #140), raised by that PR's security review. The schema
holds exactly one of `rating`, `comment_text`, `workload_hours` per `answer`
row, but nothing pairs *which* one with `question.kind`: a comment question can
hold a rating and a Likert question can hold free text, and the write path is
the only thing that would notice. If the server is to refuse it, the mechanism
E2-05 built for `survey_window` is available and cheap: a `kind` column on
`answer`, `UNIQUE (id, kind)` on `question`, a composite foreign key
`(question_id, kind)`, and a CHECK pairing each kind to its one non-null
column. **Done when** E2-08 either ships that rule or records in its PR body
why write-path validation alone is enough — a decision, not a discovery.

**Answered by E2-08, and the decision is write-path validation.**
`app.services.submissions` reads each submitted answer's value column and refuses
it unless that column is the one the question's `kind` names, before anything is
written; the pairing lives in `VALUE_COLUMN_OF_KIND` beside the range and step
checks ADR 0110 puts on the same path. The composite-key mechanism is not shipped,
for the reason ADR 0110 gives about the same table: `answer` grows by five rows per
student per section per week, and the mechanism costs a carried column on the
largest table in the schema plus a `UNIQUE` on `question` to reference. The trade
is different from `survey_window`'s, where the rule guards rows a job writes
unattended and the table holds one row per section per week. What is given up is
stated rather than implied — a hand-written `INSERT`, a repair script or a backfill
can still put a rating in a comment question's row — and it is the same thing
ADR 0110 already gives up for the ranges, from the same statement, so it is one
exposure rather than two. A later ticket that takes the mechanism should take it
for the bounds and the kind together.

## The launch-path roster enqueue still waits six seconds on a broker that is down — unowned

Deferred by E2-08 (the submit path), found while building its own enqueue against
`docs/MISTAKES.md` entry 41. That entry's three protections — publish with retries
off, keep the result backend out of it, catch broadly — do not bound the call on
their own. `retry=False` governs the publish, and the publish reaches
`kombu.Connection.default_channel`, which runs `_ensure_connection` under kombu's
own defaults before the publish is attempted. Measured on this branch:
`apply_async(retry=False, ignore_result=True)` against a closed loopback port
raises `kombu.exceptions.OperationalError` after **6.04 seconds**.

`app.services.validity.enqueue_reclassification` publishes on a connection made
for the call instead — `transport_options={"max_retries": 0,
"socket_connect_timeout": 1.0, "socket_timeout": 1.0}` with `connect_timeout=1.0`
— which brings the same closed port to **0.037s**, a blackholed address to
**1.04s**, and a broker that answers to **0.046s**.
`app.services.roster_sync.request_section_sync` has the unfixed shape, on the LTI
launch path: a launch whose Redis is restarting holds the request for six seconds
after the launch has already been verified and committed, which is the shape of
the incident entry 41 records rather than the size of it. It is not changed by
E2-08 because `roster_sync` is a shared module that ticket does not otherwise
touch, and because the launch door's own suites should move with it.

**Done when** `request_section_sync` publishes on a bounded connection the way
`enqueue_reclassification` does, and a test times a staff launch against a broker
at a closed port and holds it under a stated budget — the measurement, not the
flags, because the flags read as complete either way.

## The unproven structural battery rows — E2-13's boundary review, if ever

E2-05's mutation battery proved the security-relevant schema rules by
migration-side mutation (uniqueness on `response`, both cross-term limbs, the
exactly-one-value CHECK, the absent server defaults, the ordering CHECK) and
two further spot checks, and recorded the remaining structural rows as residue
by mechanism class: model-side mutation is inert here because the test
database builds from the migration, and repeating the same class of mutation
per row buys no new information. **Done when** nothing — this entry exists so
the residue is findable, not to schedule work; a later battery that touches
these tables should mutate the migration, not the model.
