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

## The bounce names no offending position, so the form coaches every comment it sent — E2-10

Deferred by E2-10, which is the first thing to consume the bounce.

SPEC §3.3's synchronous gate refuses one *comment*, and `app.api.student` answers
it with `{"verdict", "message"}` — the verdict that refused it and
`app.copy.submit`'s coaching sentence for that verdict. Neither member says
**which** comment. A submission can carry two: §3.2's set has a free-text question
after each rating, and a student who writes in both boxes and has one of them
judged `insufficient` gets one 422 that does not distinguish them.

So the form does the only honest thing available to it: the coaching is attached
to **every comment field the submission actually carried**, announced once through
a live region, with focus moved to the first of them and every other value left
exactly as the student typed it. Where one comment was sent that is correct and
precise. Where two were sent it is correct and imprecise — it asks a student to
look again at a sentence that may have been fine.

The alternative available today is worse rather than cheaper: guessing which
comment was judged (the shorter one, the last one) would put a coaching sentence
on a field the classifier never refused, and it would be right most of the time,
which is what makes a guess like that survive review.

**Done when** the 422's detail names the offending position — or positions, since
a submission with two thin comments has two — and the form attaches the coaching
to exactly those fields and to no others, with a test that sends two comments and
requires the untouched one to carry no coaching. The change is on the write path
(`app.services.submissions` raises `SubmissionBouncedError` from inside the loop
over submitted comments, so it has the position) and in `app.api.student`'s
detail, which makes it a heavy-lane ticket rather than this one.

## The week eyebrow cannot say how long the course runs — E2-10

Deferred by E2-10, and it is a gap in the read contract rather than a defect in
the screen.

`docs/DESIGN_BRIEF.md` writes the eyebrow as "WK 07 / 12 · closes Sun 11:59 PM",
and `design/Usage Rules.md` §1 adds the quiet term-week sub-label. E2-09's
`OpenSurvey` carries `course_week`, `term_week` and `closes_at`, and nothing that
says **how many weeks the section runs for** — that number lives on the term
calendar and the section's start letter (SPEC §2.2), neither of which reaches this
answer. So the shipped eyebrow reads "WK 07 · TERM 11 · closes Sun 11:59 PM": the
week a student is in, under both names, and when it shuts.

Deriving the total in the frontend is the option not taken. The section code
carries the start letter and the map from letter to length is the institution's,
so a client-side derivation would be a second copy of `start_letter_map` in
TypeScript — the shape `docs/MISTAKES.md` entry 19 is about, and one that reads
right in review because the arithmetic is simple.

**Done when** `OpenSurvey` carries the section's own week count and `WeekEyebrow`
renders the brief's "WK 07 / 12", with the read path's test asserting the count
against the seeded calendar rather than against the service that computed it. The
member is one field on a schema and one read in `app.services.survey_read`, which
puts it on a heavy-lane path.

## The self-hosted faces: an unrecognized licence and a second copy nobody fetches — E2-10

Deferred by E2-10, whose
[ADR 0116](../../adr/0116-the-three-webfonts-are-self-hosted-in-the-bundle.md)
records both. Neither is fixed there because both sit on paths a light-lane ticket
may not touch — `scripts/ci/` for the first, and the second is a judgement about
that same gate's neighbours.

**The licence gate has no rule for OFL-1.1.** The three `@fontsource` packages
declare the SIL Open Font License, and `scripts/ci/check_licenses.py`'s rule table
does not name it, so all three classify `unknown` and appear in the report's "no
recognizable license" list. That is a printed line rather than a failure — the
gate is not run with `--strict-unknown` — so nothing is red today and nothing
will be until somebody turns that flag on, at which point three permissive font
packages fail the build. The licence is permissive and compatible with
distributing this project under MIT (SPEC §10); it is simply not in the
vocabulary.

**And the OFL asks for something this build does not do.** Its clause 2 requires
the licence and the copyright notice to travel with the font files when they are
redistributed, and `frontend/dist` ships six woff2 files and no notice.

**A second copy of every face ships and no supported browser fetches it.** Each
`@fontsource` stylesheet lists woff2 and woff, so the build emits both: 119,100
bytes of woff2 that browsers use and 147,028 bytes of woff that none of them
does. It costs image size and nothing else — the bundle budget counts neither.

**Done when** `check_licenses.py` classifies `OFL-1.1` and the spelled-out "SIL
Open Font License" as permissive, with the near-miss control the rest of that
table's rules get (a licence the rule must *not* match, run and seen to not
match); **and** the built application ships the OFL text and copyright notices
for the three families, with something asserting they are in `dist`; **and** the
woff duplicates are either dropped — which means hand-writing the six
`@font-face` rules and accepting the copy of the package's own declarations that
ADR 0116 refuses today — or recorded as a deliberate cost in the licence and
image-size sweep. E13's accessibility and licence pass is the natural owner of
the first two.

## A resubmission under a rewound development clock answers 500 — E2-10

Found by E2-10 while driving its own end-to-end spec, and it is a defect in a
development-only path rather than one a student can reach.

[ADR 0109](../../adr/0109-the-dev-clock-is-a-database-offset-not-a-freeze.md)
makes the development clock an **offset** rather than a freeze, so setting it to
the same pretended minute a second time — an hour later in real time — produces
an effective now a little *earlier* than the first run had drifted to. A student
who submits under the first setting and revises under the second writes a
`response` row whose `last_submitted_at` precedes its own `first_submitted_at`,
and `response`'s `ck_response_last_submission_is_not_before_the_first` refuses
it. `app.services.submissions` has no branch for that, so it surfaces as a
`psycopg.errors.CheckViolation` out of the flush and the route answers **500**.

Measured on this branch, on the composed stack: a resubmission after the clock
was re-set to `2026-10-02T19:00` wrote
`first_submitted_at = 2026-10-02 23:00:04.017127+00` against
`last_submitted_at = 2026-10-02 23:00:00.841879+00`, three seconds apart in the
wrong direction, and the API answered 500 with the constraint name in the log.

**What it is not.** Real time does not run backwards, so no deployment reaches
this: the clock override is refused outside development (ADR 0109), and the check
constraint is doing exactly the job it was written for — the row is wrong and the
database says so. Nothing is stored, and the student's answers stay in the form.

**What it is.** A 500 where a refusal belongs, on the surface a developer walks a
section through a term on. It is also the shape that makes a demo look broken:
the person who moved the clock has no way to know that the week they are looking
at was answered under a later reading of the same minute. `tests/e2e/student-survey.spec.ts`
works around it by clearing the week before each of its cases, which is a spec
protecting itself rather than a fix.

**Done when** the write path either refuses this in words — one of
`app.copy.submit`'s sentences, with a status that says the request was
understood — or refuses to move `last_submitted_at` backwards at all, and a test
drives a resubmission under a rewound clock and requires something other than a
500. The fix is in `app.services.submissions`, which is a heavy-lane path.
