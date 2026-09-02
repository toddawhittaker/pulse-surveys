# E2 — items a ticket deferred rather than fixed

Created by E2-05's PR, per the epic README: a PR that defers something adds it
here in the same PR, and E2-13 runs the cleanup pass over this file. Each entry
names the ticket that owns it and what "done" means, so the deferral is a
scheduled decision rather than a hope.

## The gateway records no token usage, so no live run can report its own cost — E2-13

Deferred by E2-12, and it became a real need during that ticket rather than a
nicety: a spend ledger is now kept per live eval run, and no run can report
against it. `AIGateway._ask` returns `(result.output, model_id)` and drops
`result.usage()`; `run_task` returns the contract object alone; nothing logs it.
So a run's input tokens, its output tokens, and — the figure that decides most of
the bill — its cached input tokens are all unrecorded and unreconstructable
afterwards.

The data is one attribute away in a dependency already pinned. `pydantic_ai`
2.35.3's `RunUsage` carries `input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_write_tokens`, `requests`, `cost` and a `details` dict, and its OpenAI
model maps the chat API's `prompt_tokens_details.cached_tokens` into
`cache_read_tokens` — exactly the split a ledger prices separately, cached input
billing at a tenth of uncached. `details` carries this model's reasoning tokens,
which are billed and never appear in the answer body.

It matters most on this path, and not only for bookkeeping: every eval request is
the same ~4,175-character prompt with a short comment substituted, so about 99%
of each call is an identical prefix and the cached fraction is likely to be
material. Nothing can say how material without measuring it.

**Done when** a live run can report its own input, output and cached-input token
totals. Whether the gateway returns usage alongside the verdict, records it, or
exposes it another way is the deciding ticket's call — it is application
behaviour rather than test machinery, which is why it is not taken here — and
whatever shape it takes has to keep the credential and the comment out of
whatever it writes (SPEC §10, §4).

## `detect.outputs.evals` is published and read by nothing — E2-13

Deferred by E2-12. That probe asked whether the eval runner module exists, and
the `evals` job's steps waited on it while that file was still to be written.
The file is committed now, so waiting on it is exactly the tolerance ADR 0002
says the ticket landing the code must remove: with the clause in place a deleted
runner switches SPEC §9.3's floors off and the job reports success, where
without it the run fails on the import and says so. The clause went; the output
stayed, because the detect-probe module asserts the whole set of outputs that
job emits and withdrawing one is a change on the other side of the heavy lane's
test wall.

What is left is the shape that job's own comment condemns — a boolean nobody
consults, whose wrongness produces no symptom at all, so nobody finds out it is
wrong and the next gate wired to it inherits an answer nothing has ever checked.
The state is written down at the output itself rather than left to be
rediscovered.

**Done when** the output and the probe line that fills it are removed together
and `PROBES` in that module drops `EVALS` in the same change — or a reason to
keep it is recorded there, and that reason would have to be a reader.

## SPEC §11 open question 4 is answered in its set and not yet in its threshold — E2-13

Deferred by E2-12, and it is a residue with a date on it rather than an open
problem. §11 question 4 asks for the production "substantive" definition and
says "its eval set and threshold need real seeded data before E2 exits". The set
exists: ninety-eight typed cases pinned to `validity.v1`, including the two
families the twenty-five-character heuristic gets wrong by construction, and ADR
0119 settles which class the pair of numbers is about. The threshold is measured
against the live provider by E2-12 and written into the validity floor
declaration, which is behind the heavy lane's test wall — so the measurement
travels back to the test author rather than being written down by the
implementer who took it, which is the separation that keeps a floor from being
chosen to fit a run.

**Done when** the measured floors are in that declaration with the sentence
saying what the run scored and how much headroom they leave, the runner passes
`--enforce-floors` against them, and SPEC §11 question 4 is marked
settled-for-v1 by a spec edit — a change to `docs/SPEC.md`, and so not the
implementer's to make.

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

## A bounced submission's verdict rows are unbounded per attempt — a linkage-or-cap ruling is owed

Deferred by E2-08's security re-pass, which raised it as a MEDIUM and accepted it
as residue on the reasons below rather than as a fix withheld.

Since the fix round, a bounce commits the classification that refused it (SPEC
§7.4's audit pair, [ADR 0114](../../adr/0114-an-unclassifiable-comment-refuses-rather-than-floors.md)),
and nothing limits how many times one student may attempt and be bounced. A
student typing "ok", being coached, and typing "ok." again writes a row each time,
and the count is bounded only by their patience.

**What that is not.** The rows are unlinkable by design: `answer_id` is NULL
because no answer exists, the row carries no user, no section, no week and no
comment text, so the growth is not a set of a person's refused words accumulating
anywhere. It is reachable only with a valid student session and a live enrollment
in the section, both established before the provider is asked, so it is not an
unauthenticated lever. Each row is one provider call the tool has already made and
paid for, so the row is a record of spend rather than a multiplier of it. And a
bounced row can move nothing: `response.is_valid` is computed from verdicts naming
an answer, and the re-classification sweep selects on `answer_id IS NOT NULL`, so
these rows enter neither.

**What it is.** They land in any aggregation over `classification` that does not
exclude them — §6.1's drift panel samples verdicts across tasks and would sample a
population weighted toward whatever students retype most, and a per-model or
per-prompt-version count reads them as classifications that judged something.

**Done when** the owner has ruled between the two available answers — link the
rows to the attempt that produced them (which is a new key, a new grant question
and a new confidentiality question, since ADR 0055 refused even a fingerprint of a
comment) or cap the attempts a window will classify — **and** the epic that owns
the drift surface either filters these rows out of its aggregation or bounds them,
naming this entry where it does.

## Nothing structurally forces the next mutating route onto the CSRF dependency — a sweep is owed

Deferred by E2-08's security re-pass as a LOW, and it is about the shape of the
guard rather than about this route: the submit path carries
`app.api.deps.csrf_verified_student` and is correct.

`require_student` and `csrf_verified_student` sit beside each other in the same
module, and the difference between them is the double-submit check ADR 0089 makes
live because the session cookie is `SameSite=None`. That difference is deliberate
— a read path has nothing for the check to protect, and E2-09's student read path
carries the plain one — but nothing in the tree makes a *writing* route reach for
the checked one. The next mutating route is one import away from being unprotected,
and it would be unprotected in exactly the way that reads as fine in review: a
route with `require_student` on it looks guarded.

This is the closed-set shape twice over. The safe default is not the shorter name,
and the inventory of which routes need the check is currently a thing each author
remembers.

**Done when** a sweep test walks the built application's routes — through
`fixtures.routing.every_route`, since an included router carries no `path` on the
pinned FastAPI — and requires every route whose methods include `POST`, `PUT`,
`PATCH` or `DELETE` either to depend on `csrf_verified_student` or to appear on a
named exemption list with a reason per entry, in the shape
`REACHED_TABLES_THAT_CARRY_NOTHING` already uses: asserted in both directions, so
an exemption for a route that no longer exists fails as loudly as a route that
grew a mutating method without one.

## A bounced comment's text reaches neither moderation nor the Care queue — a ruling is owed

Deferred by E2-08's security fix round, and it is a **question rather than a
finding**: nothing is broken, and both answers to it are safety decisions the spec
does not make.

SPEC §3.3 bounces a comment the classifier calls `insufficient` or `nonsense`
before submission, and the ticket's Scope makes that store nothing. The round
added one exception — the verdict that bounced it is kept, because SPEC §7.4 rests
auditability on "a specific prompt version and model ID produced a specific
classification" and a rolled-back row is the one way to lose an append-only row
that ADR 0055's grant cannot prevent. The comment's **text** is still not stored:
ADR 0055 refused even a fingerprint of one on `classification`, "recoverable by
dictionary in seconds" over strings this short, and
[ADR 0114](../../adr/0114-an-unclassifiable-comment-refuses-rather-than-floors.md)
records the consequence as an open limitation rather than a decision.

The consequence is this. §5.2's moderation pass and §6.2's route to the Care queue
both run over stored comments, so a student whose comment discloses harm and is
bounced for being too brief is a student the Care path never sees, and "the
answers are still in the form" is not the same as anyone having read them. Against
that, §4 and ADR 0055 keep a student's words in one place under one set of rules,
and storing refused text creates a second — with a retention question, a grant
question and a reveal question of its own.

**Done when** the owner has ruled which of those governs a comment the student was
told did not count, and the ticket that implements the ruling is named in the
breakdown. If the ruling is that bounced text must reach §6.2's path, that ticket
owns where it is stored, who may read it and what removes it; if the ruling is
that it must not, ADR 0114's paragraph becomes a decision rather than a limitation
and this entry closes with it.

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
