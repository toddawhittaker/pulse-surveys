"""SPEC §4's small-N comment rules, in one module — ticket E4-04.

This is the one place the product decides whether an instructor may read a
student's words. SPEC §14.3 marks it for line-by-line human review for that
reason, and the whole of §4's comment paragraph is here rather than spread over
a query, a serializer and a template:

> **Small-N handling (n < 5 responses in a reporting week):** instructors see
> rating distributions and the AI summary, but **no raw comments**. Comments
> from under-threshold weeks are not discarded — they feed the summary, and they
> surface as raw text once the section's cumulative comment volume for the term
> crosses the threshold, batched so that timing cannot identify an author.
> Threshold value is configurable (default 5).
>
> Comment display order is randomized; timestamps are never shown with comments.

Three callables and one payload:

* `visible_comments` — the asked week's comments when that week's response count
  reaches the configured threshold, and the empty tuple below it;
* `released_comments` — every comment a release batch has surfaced for one
  section, term and stream, with no week attribution anywhere;
* `cut_due_release_batches` — the weekly pass that evaluates the release gate and
  writes the batch, run by `app.jobs.tasks.cut_release_batches` on Monday at
  02:40;
* `ReportComment` — what a caller may be told about one comment: its text, its
  moderation status, and which of §5.1's two groups it belongs to. Nothing else.

## The release gate is three conditions, not §4's one

SPEC §4's literal trigger is "the section's cumulative comment volume for the term
crosses the threshold", and E4-04's security round found that counting only that
under-protects §4's own goal in two ways. A volume is denominated in comment
*answers* while the threshold is a number of *responses*, and §3.2 gives every
response two comment items — so a volume that reaches the threshold can come from
three students, or from one across three quiet weeks. And a volume condition
stays true once crossed, so every Monday afterwards the same section passes the
same test and the cutter takes whatever is held: exactly the week that just
closed, which is a per-week batch, which is the week attribution ADR 0153 removed
arriving through the report's own delta.

So a batch is cut only when the volume reaches the threshold **and** the distinct
people behind the unreleased held comments reach it **and** those comments span at
least `WEEKS_A_RELEASE_MUST_SPAN` under-threshold closed weeks. When any leg fails
nothing is cut. ADR 0152 carries the argument, records that the respondent leg
subsumes the other two, and states plainly that this is a reading of §4 rather
than §4's own words — the spec question is open and the owner's to settle, and
this build holds the conservative side meanwhile.

## What is deliberately not here

**No week on a released comment, and no instant anywhere.** `ReportComment` is
frozen and carries three fields, which makes both absences structural rather
than remembered. ADR 0153 argues the week: a released under-threshold comment
grouped under its week, read beside the per-week participation ledger SPEC §3.4
posts into the gradebook (ADR 0125), narrows the author to the students who
completed that week's comment item — and in a four-response week that
intersection can be one person.

**No student-facing parameter.** Neither read takes a viewer, a subject or a
user; there is no argument position a launching student's own claim could be
filled into (SPEC §4.1 item 6). §5.4 gives students a different rule over the
same rows — their own section, published comments only, and a notice in place of
comments below the threshold — and E8 writes it in its own module.
`tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`
sweeps the four student-facing modules for an import of this one.

**No moderation write.** The status a comment carries is read from the record
E4-02 shipped; every writer of a moderation decision is E6's, and the runtime
role holds no `INSERT` on that table (`report_comment_grants_v001.sql`).

**And no §6.2 suppression, which is a gap rather than a decision.** SPEC §5.2
ends "threat/self-harm classifications bypass this flow entirely (§6.2) and are
never shown to the instructor", and nothing in this module implements that: a
comment carrying such a verdict is returned by both reads and counted by the
cutter like any other. It is not reachable today, because nothing in the product
writes a safety verdict — E4's classification task has one member — so the gap is
recorded rather than closed here, with an owner and a done-when in
`docs/tickets/e4/deferred.md`. Whoever adds the first such verdict owns closing
it, and the suppression belongs **below** this read path rather than in each
caller.

## The three rules this module reads, and where each is decided

**The threshold is a count of responses, and it is the institution's number.** It
is what all three legs of the release gate compare against as well.
`Settings.n_threshold_default` is read inside each call rather than at import, so
an institution that changes it changes the rule rather than needing a restart —
SPEC §4 makes the value configuration. The count itself is
`public.report_response_counts`, E4-03's view, which is `count(*)` of `response`
rows per section-week. Counting them again here would be a second implementation
of one number, which is the shape `docs/MISTAKES.md` entry 19 is about.

**The moderation status is the latest row, or published.** ADR 0145 makes the
record append-only with the latest row governing and the initial state the
*absence* of a row, and names the consequence: "a reader of a comment's
moderation state has to write a window function, or its equivalent … That is
E4-04's and E6's to write once, in `app.services`, not per call site."
`reported_status_of` below is that once. Both reads go through it, the summary
gather in `app.services.reporting` calls it since E4-07, and it is shaped so E6
can call it too. An inner join here would drop every comment nobody has decided
about, which on today's database is all of them.

**A week's comments are held only once the week has closed.** A window still
taking responses has no final count, so a comment released from it may belong to
a week that turns out to be at or above the threshold and would then be shown
twice — once under its own week and once in a batch with the week stripped off.
The close is read from `survey_window.closes_at` against
`app.services.clock`, never against the process clock, which is ADR 0109's
convention and what lets a developer walk a term forward by hand.

## Why the queries are SQLAlchemy Core rather than SQL text

Every service read path in this tree is written this way — `survey_read.py`,
`survey_windows.py`, `grading.py` — and the four modules holding raw statements
are the exceptions rather than the rule. There is also a guard in the way, and it
is named here rather than left for the next reader to rediscover:
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py` polices every
relation the view catalog creates or reads, which since E4-03 includes `answer`,
`question`, `response` and the report views, and since this ticket includes
`report_comment` — a statement *text* naming one of those outside four exempt
files is an offender. That sweep's SQL half cannot see a Core query and says so
in its own limitations; what stands behind these relations is the grant, which
this ticket issues narrowly and which
`tests/integration/test_the_comment_path_runs_over_the_connection_production_uses.py`
asserts in both directions. E4-07 reads E4-03's three views and meets the same
question; if the project wants statement text here, the repair that file
prescribes is a pinned location exemption, which is an edit inside `tests/`.

**The two views are declared as `table()`/`column()` and not as mapped classes**,
because SPEC §13 ships identity-separated views as migrations and never as an
ORM convention. The declarations are also a statement worth reading on their own:
between them this module can name a section, a week, a stream, an answer key, a
comment's text and a response count, and no instant a comment was written at.

**One place reaches a person, and it counts them rather than naming them.**
`_held_comments` walks `answer.response_id` and then `response.user_id`, because
the release gate's second leg is a number of distinct people and a gate that
could not reach them could not enforce §4's threshold. What that column is used
for is a `count(distinct …)` inside one query and a grouping inside one
subquery; it is not selected by the membership read, it is not returned by
anything, and no `ReportComment` has ever carried it. That is the whole of the
identity surface in this file, and it is stated here so a reviewer can check the
claim against three functions rather than against the module.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Row,
    Select,
    SQLColumnExpression,
    Subquery,
    column,
    distinct,
    func,
    insert,
    select,
    table,
)
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.report import MODERATION_STATES, ModerationState, ReleaseBatch, ReleaseBatchMember
from app.models.survey import Answer, Response
from app.models.term import SurveyWindow, Week
from app.services import clock

# The initial moderation state, and the one a comment carries when nothing has
# been decided about it (ADR 0145). Taken off the model's own vocabulary rather
# than spelled again, so a token renamed in the schema moves this with it
# (`docs/MISTAKES.md` entry 13).
INITIAL_STATE = MODERATION_STATES[0]

# What each stored state means to a caller of this path: SPEC §5.2's lifecycle,
# stored upper case by E4-02's `CHECK` and reported lower case. A mapping rather
# than a `.lower()` at the call site, so a state outside the vocabulary raises
# here instead of arriving as a status nobody defined — the `CHECK` makes that
# unwritable, and this is what says so if it ever stops being true.
REPORTED_STATUS = {stored: stored.lower() for stored in MODERATION_STATES}

# How many distinct under-threshold closed weeks a release must draw from before
# it may be cut — the third leg of the gate. Two rather than one, and it is the
# smallest number that does the job: a batch confined to a single week is the week
# attribution ADR 0153 removed, arriving through the report's own week-to-week
# delta instead of through a field. Named rather than written inline so the
# reviewer meets the rule rather than a literal.
WEEKS_A_RELEASE_MUST_SPAN = 2

# `public.report_comment`, E4-04's view, declared as the relation it is.
#
# **Five columns and no sixth**, which is the same equality
# `tests/integration/test_identity_grants.py` records and the view file argues:
# no `user_id`, no `response_id`, no instant. The declaration is local to this
# module because a view is not a model (SPEC §13), and it doubles as the list of
# things this module is able to say about a comment at all.
COMMENT_VIEW = table(
    "report_comment",
    column("section_id"),
    column("week_id"),
    column("stream"),
    column("answer_id"),
    column("comment_text"),
    schema="public",
)

# `public.report_response_counts`, E4-03's view. Only `responses` is named here —
# SPEC §4's threshold is "n responses in a reporting week", which is that column
# and not the validity figure beside it (§3.3's rate is E4-07's, over both).
RESPONSE_COUNTS_VIEW = table(
    "report_response_counts",
    column("section_id"),
    column("week_id"),
    column("responses"),
    schema="public",
)


@dataclass(frozen=True)
class ReportComment:
    """One comment as the instructor's report may see it: its words, its status, its group.

    **Three fields, frozen, and the absences are the point.** SPEC §4: "timestamps
    are never shown with comments", and held comments surface "batched so that
    timing cannot identify an author". A `week`, a `submitted_at` or a
    `released_at` here would make both statements false at once, and would do it
    in a diff that reads as a convenience — so the rule is that the field does not
    exist rather than that no caller renders it.

    Frozen because a caller that receives one can otherwise set an attribute on
    it, and the attribute a caller reaches for first is the week it looked the
    comment up under — which is exactly what a release drops (ADR 0153).
    """

    # What the student wrote, verbatim. De-identified by construction: the view
    # this comes from selects no column that names a person.
    text: str
    # SPEC §5.2's lifecycle as a caller reads it — `published`, `flagged_collapsed`,
    # `excluded` or `kept`. E4-10 renders each of them differently; the *data*
    # discipline is this module's.
    status: str
    # Which of SPEC §5.1's two groups this comment belongs to, read from
    # `question.stream` and never from a question's ordinal.
    stream: str


def visible_comments(
    session: Session,
    *,
    section_id: UUID,
    week_id: UUID,
    stream: str,
) -> tuple[ReportComment, ...]:
    """One section-week's comments in one stream, or nothing at all below the threshold.

    SPEC §4: below the n-threshold "instructors see rating distributions and the
    AI summary, but **no raw comments**", and §4.1 item 3 makes that an invariant
    rather than a convention. §5.2 adds the half that is easy to ship without
    noticing: below the threshold a flagged comment is hidden "entirely — no chip,
    no count, no flag-type hint", because in a four-response week a held count is
    a statement about one of four identifiable people.

    **A suppressed week and a week nobody commented in answer the same value.**
    The empty tuple is returned before any comment is read, so nothing a caller
    receives says how much was withheld — not a length, not a type, not a
    placeholder.

    Above the threshold every comment comes back, whatever its moderation state:
    a flagged one collapsed with its chip, an excluded one still visible to the
    instructor (§5.2 keeps its text "visible to the instructor, muted, above the
    exclusion notice"), and a kept one published. A read that filtered a state out
    would remove the record of a decision from the report of the person who made
    it, which is what §5.2's anti-cherry-picking argument rests on.
    """
    settings = Settings()

    # SPEC §4's rule is "n < 5 responses in a reporting week", and the boundary is
    # inclusive on the upper side: the threshold value itself is the first size at
    # which comments are shown. A week nobody answered has no row in the count
    # view (ADR 0147: absence rather than a zero row), which is below any
    # threshold and so suppressed.
    responses = session.execute(
        select(RESPONSE_COUNTS_VIEW.c.responses).where(
            RESPONSE_COUNTS_VIEW.c.section_id == section_id,
            RESPONSE_COUNTS_VIEW.c.week_id == week_id,
        )
    ).scalar_one_or_none()
    if (responses or 0) < settings.n_threshold_default:
        return ()

    asked = _comments_with_their_status().where(
        # §4's confidentiality model is per section: an instructor reads their own
        # students' words and nobody else's.
        COMMENT_VIEW.c.section_id == section_id,
        # §4's threshold is counted "in a reporting week", so a read that pooled a
        # section's weeks would test one week's count and return another's text.
        COMMENT_VIEW.c.week_id == week_id,
        # §5.1's two groups, each headed by its own summary and routed differently
        # by §5.2.
        COMMENT_VIEW.c.stream == stream,
    )
    return _shuffled(session.execute(asked).all())


def released_comments(
    session: Session,
    *,
    section_id: UUID,
    term_id: UUID,
    stream: str,
) -> tuple[ReportComment, ...]:
    """Every comment a release batch has surfaced for one section, term and stream.

    SPEC §4: under-threshold comments "surface as raw text once the section's
    cumulative comment volume for the term crosses the threshold, batched so that
    timing cannot identify an author". The crossing is stored rather than
    re-derived here (E4's breakdown decision 7, ADR 0146, ADR 0152), so this read
    walks the batches `cut_due_release_batches` wrote and applies no threshold of
    its own — the batch *is* the decision that these comments may be read.

    **One flat tuple, and no week anywhere.** Not a mapping keyed by week, not a
    tuple of per-week tuples: a container carries the attribution as plainly as a
    field would, and ADR 0153 is why neither may. E4-07 places the result in the
    latest published week's report under a from-earlier-weeks heading.

    **The section comes off the batch row.** `release_batch_member` carries a
    comment and a batch and nothing else (ADR 0146), so a walk that filtered on
    the term alone would hand every section in the institution its neighbours'
    held comments, and one that reached the section through the comment's own
    response would be right today and wrong the first time a batch spanned
    anything.
    """
    asked = (
        _comments_with_their_status()
        .join_from(
            ReleaseBatchMember,
            ReleaseBatch,
            ReleaseBatch.id == ReleaseBatchMember.batch_id,
        )
        .join(COMMENT_VIEW, COMMENT_VIEW.c.answer_id == ReleaseBatchMember.answer_id)
        .where(
            # §4's per-section boundary, read off the batch and not off the comment.
            ReleaseBatch.section_id == section_id,
            # The threshold §4 counts cumulatively is "for the term", so a batch
            # belongs to one and a report of this term reads no other's.
            ReleaseBatch.term_id == term_id,
            # §5.1's two groups again: a release is grouped under the same two
            # headings as everything else.
            COMMENT_VIEW.c.stream == stream,
        )
    )
    return _shuffled(session.execute(asked).all())


def cut_due_release_batches(session: Session) -> int:
    """Cut one release batch for every section and term whose held comments are now due.

    SPEC §4's cumulative rule, evaluated and written once a week rather than at
    read time (ADR 0152). A comment is **held** when its week was below the
    threshold, its window has closed, and it is in no batch yet; `_held_comments`
    is the one definition and both the gate and the batch are built from it.

    **The gate is three legs and every one of them must open** (ADR 0152, after the
    security round):

    a. the section's cumulative comment-answer volume for the term reaches the
       threshold — SPEC §4's literal trigger, counted over every comment the
       section holds in the term whatever its moderation state and whether or not
       it has already gone out;
    b. the **distinct people** behind the unreleased held comments reach the
       threshold;
    c. those comments span at least `WEEKS_A_RELEASE_MUST_SPAN` distinct
       under-threshold closed weeks.

    Leg (b) is the effective floor — it cannot hold where (a) or (c) fails — and
    all three are written out anyway, because they are the reading of §4 this build
    stands on and each survives a change to another's denominator. **When any leg
    fails nothing is cut**, which is the safe direction: a held comment still feeds
    the summary and is released later, and a released one cannot be un-shown.

    **One batch per crossing, and all of the held set in it.** ADR 0146 puts the
    only time in the design on the batch's `cut_at`, so a release split across
    several batches gives its comments several release times, and the difference
    between two of them is the per-comment timing §4 batches the release to
    remove.

    **One transaction per section and term, committed here.** A section's batch
    and its whole membership land together or not at all, and a walk that dies on
    the fifth section keeps the four it has already released — which matters for a
    job that visits every section in the institution once a week.
    `post_participation_scores` in `app/jobs/tasks.py` makes the same call for the
    same reason and its docstring carries the longer argument; the difference is
    that a released comment has not left this system, so what is bought here is
    the walk's progress rather than a record of somebody else's side effect. The
    task above this commits nothing, because by the time this returns there is
    nothing left to commit.

    **A comment released twice is a defect to see, not an error to swallow.** The
    held set is chosen by anti-join against the membership table, so a second run
    finds nothing to do; `release_batch_member.answer_id` is unique (ADR 0146) and
    nothing here catches the integrity error that a broken held query would
    provoke. Answers how many batches were cut, which is what a worker log line
    wants.
    """
    settings = Settings()
    threshold = settings.n_threshold_default
    # ADR 0109's convention: scheduling and visibility read the effective clock,
    # never the process clock, so a development stack walked forward by hand sees
    # the weeks it has been walked past.
    now = clock.now(session, settings=settings)

    held = _held_comments(threshold=threshold, now=now)
    due = _sections_whose_release_is_due(session, held, threshold=threshold)
    answers = _held_answers_by_section_and_term(session, held)

    cut = 0
    # Sorted, so two runs over the same data visit the sections in the same order
    # and a failure part-way through a walk is reproducible. Nothing about the
    # order reaches a caller — this is which section is released first, not which
    # comment is shown first, which is `_shuffled`'s.
    for key in sorted(due):
        section_id, term_id = key
        batch_id = session.execute(
            insert(ReleaseBatch)
            .values(section_id=section_id, term_id=term_id)
            .returning(ReleaseBatch.id)
        ).scalar_one()
        session.execute(
            insert(ReleaseBatchMember),
            [{"batch_id": batch_id, "answer_id": answer_id} for answer_id in answers[key]],
        )
        # The batch and its whole membership, together. ADR 0146 puts the only
        # release time on the batch row, so a membership committed without its
        # batch — or a batch committed without its members — would be a release
        # nobody can read and a `cut_at` about nothing.
        session.commit()
        cut += 1
    return cut


def reported_status_of(answer_id: SQLColumnExpression[Any]) -> ColumnElement[str]:
    """The status one comment carries: its latest moderation decision, or published.

    **ADR 0145's resolution, written once.** That record makes `moderation_state`
    append-only with the latest row governing, and makes the *initial* state the
    absence of a row — so this is a `LEFT JOIN` with a default in scalar-subquery
    form, and never an inner join, which would drop every comment nobody has
    decided about. §5.2's lifecycle has an undo in both directions, so "the state"
    is an ordering question: a reader that took any row would report the first
    decision for ever, and since a flag is usually what puts the first row on the
    table, that shows a collapsed chip on a comment its own instructor
    deliberately published.

    Shaped as a helper over an answer key rather than inlined, so E6's moderation
    surface calls this one resolution rather than writing a second.

    **Public since E4-07, which is what closed that deferral.** E4-06's summary
    gather in `app.services.reporting` had written the same resolution for itself
    while both branches were being built in parallel; it now calls this, and
    `tests/unit/test_the_moderation_state_ordering_has_one_home_under_backend_app.py`
    holds the tree to exactly one module naming the relation in executable code.
    Two copies of "the latest row, or published" disagree the first time somebody
    changes one, and §5.2's whole lifecycle is about which decision is current.

    **`SQLColumnExpression` rather than `ColumnElement`**, because the two callers
    hold the answer key in the two forms SQLAlchemy has: this module reads it off a
    Core view (`report_comment.answer_id`, a `Column`) and the summary gather off
    the mapped class (`Answer.id`, an ORM attribute). Only the wider of the two
    base classes covers both, and narrowing it again would push one caller into a
    cast for no benefit.
    """
    latest = (
        select(ModerationState.state)
        .where(ModerationState.answer_id == answer_id)
        .order_by(ModerationState.decided_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    resolved: ColumnElement[str] = func.coalesce(latest, INITIAL_STATE)
    return resolved


def _comments_with_their_status() -> Select[tuple[str, str, str]]:
    """The three columns a `ReportComment` is built from, before any filter.

    Deliberately unfiltered and deliberately unordered. The scoping predicates
    belong to the caller, where a reviewer reads them beside the rule each one
    carries; the order belongs to `_shuffled`, because SPEC §4 randomizes comment
    display order and **no stored order may reach a caller** — the answer's key,
    the response's key and `submitted_at` are all submission order, which says who
    answered first.
    """
    return select(
        COMMENT_VIEW.c.comment_text,
        reported_status_of(COMMENT_VIEW.c.answer_id),
        COMMENT_VIEW.c.stream,
    )


def _make_rng() -> random.Random:
    """The random source a display order is shuffled with — private, and deliberately so.

    **Not a parameter, because a seed a caller can supply is a seed an attacker
    can fix.** With the seed fixed, two reads of one week produce the same
    permutation, so diffing a shuffled result against a second shuffle of a known
    set re-derives the order the rows arrived in — and with no `ORDER BY`
    underneath, that is heap order, which is insertion order, which is submission
    order, which is who answered first. The same fixed seed a week apart also pins
    a newly released comment by its position: everything that did not move is old.
    SPEC §4 randomizes the display order precisely to remove both, so the source is
    this module's and no caller's.

    A hook rather than an inline `random.SystemRandom()` because the suite has to
    be able to make "the order is random" a deterministic assertion, and replacing
    one private name is the smallest seam that allows it. That is a seam for the
    tests and not an interface for a caller, which is what the leading underscore
    says.

    `SystemRandom` rather than `random.Random`: this shuffle is a confidentiality
    control rather than a convenience, so it draws from the operating system
    instead of from a generator whose state a long-running worker keeps.
    """
    return random.SystemRandom()


def _shuffled(rows: Sequence[Row[tuple[str, str, str]]]) -> tuple[ReportComment, ...]:
    """The rows as `ReportComment`s, in a random order.

    SPEC §4: "Comment display order is randomized; timestamps are never shown with
    comments." The two halves of that sentence are one rule — a list in submission
    order *is* a timestamp, and read beside SPEC §3.4's per-week completion ledger
    in the gradebook (ADR 0125) the first responder is often nameable.

    The shuffle is in Python rather than in SQL so that there is one place it
    happens; the source is `_make_rng`, looked up here on every call so that the
    module's own hook is what decides it.
    """
    comments = [
        ReportComment(text=text, status=REPORTED_STATUS[stored], stream=stream)
        for text, stored, stream in rows
    ]
    _make_rng().shuffle(comments)
    return tuple(comments)


def _comment_volume_by_section_and_term(
    session: Session,
) -> dict[tuple[UUID, UUID], int]:
    """How many comments each section holds in each term — SPEC §4's cumulative volume.

    **Every comment answer carrying text, every week, every moderation state.**
    ADR 0152 argues the reading: §4 says "comment volume", the sentence is about
    how much a section has said rather than about how much survived review, and a
    volume computed after moderation would move when an instructor excluded
    something — so a section could cross the threshold and then un-cross it, and a
    release would be cut on a number that was wrong.

    The term is the one the comment's **week** belongs to. `survey_window` carries
    a term as well, and it is the same term by composite foreign key (ADR 0018);
    the week is used because a week belongs to a term whether or not a window row
    exists for it, and reading one rule in one place is worth the join.
    """
    counted = (
        select(
            COMMENT_VIEW.c.section_id,
            Week.term_id,
            func.count().label("volume"),
        )
        .join_from(COMMENT_VIEW, Week, Week.id == COMMENT_VIEW.c.week_id)
        .group_by(COMMENT_VIEW.c.section_id, Week.term_id)
    )
    return {(row.section_id, row.term_id): row.volume for row in session.execute(counted).all()}


def _held_comments(*, threshold: int, now: datetime) -> Subquery:
    """The comments SPEC §4 has been holding back — the one definition of "held".

    Three conditions, one per concern, and none of them is another's spare. The
    predicate is written once, as a subquery, and `cut_due_release_batches` selects
    from it twice: `_sections_whose_release_is_due` counts it to decide which
    `(section, term)` the gate opens for, and `_held_answers_by_section_and_term`
    reads the answer keys a membership row is written from. One definition, so the
    gate and the batch cannot be about different sets of comments — two copies of
    this predicate that had drifted would gate on one set and release another.

    **Those are two SQL statements, not one, and that is worth being honest about.**
    They run in the same session's transaction under READ COMMITTED, so each takes
    its own snapshot and a row that appeared between them could in principle be
    counted by one and not the other. What makes that a non-event is that nothing in
    the product writes into this set concurrently with the cutter:

      - a comment enters the set only from a **closed** window, and E2-08's write
        path refuses a submission to a window that has closed — so the set this
        cutter reads cannot grow under it through the ordinary path;
      - the two statements run back to back on one connection with no `await` and
        no second writer between them, and the beat entry is a single scheduled job
        per `(section, term)`;
      - and if two statements ever did disagree — a batch counted as due whose
        answers a concurrent cutter had already released — `release_batch_member`'s
        `UNIQUE (answer_id)` (ADR 0146) refuses the second membership rather than
        letting it through. That is the "a second release is a defect to see"
        stance, reached here by the database rather than by a caught error.

    The only way to make the two snapshots diverge is a second, hand-written cutter
    running against the same rows at the same instant, which is a defect somebody
    introduces rather than one this path opens. Collapsing the two reads into one
    materialized statement would remove even that, and it is deliberately **not**
    done here: it is a behaviour change to a reviewed release path for a hazard the
    product cannot reach, and it belongs in the pull request that argues for it.

    A row carries the comment, the section and term it belongs to, the week it was
    submitted in and **who wrote it**. The last two are what the gate counts and
    what nothing here ever returns: `_sections_whose_release_is_due` reduces them to
    two integers, the membership read selects the answer key alone, and no
    `ReportComment` has ever carried either. The walk to a person is
    `answer.response_id` then `response.user_id`, which is a walk the product may
    make to *count* people and may never make to *name* one — SPEC §4's threshold is
    a number of people, so a gate that could not reach them could not enforce it.
    """
    return (
        select(
            COMMENT_VIEW.c.section_id.label("section_id"),
            Week.term_id.label("term_id"),
            COMMENT_VIEW.c.answer_id.label("answer_id"),
            COMMENT_VIEW.c.week_id.label("week_id"),
            Response.user_id.label("respondent"),
        )
        .join_from(COMMENT_VIEW, Week, Week.id == COMMENT_VIEW.c.week_id)
        .join(Answer, Answer.id == COMMENT_VIEW.c.answer_id)
        .join(Response, Response.id == Answer.response_id)
        .join(
            RESPONSE_COUNTS_VIEW,
            (RESPONSE_COUNTS_VIEW.c.section_id == COMMENT_VIEW.c.section_id)
            & (RESPONSE_COUNTS_VIEW.c.week_id == COMMENT_VIEW.c.week_id),
        )
        .join(
            SurveyWindow,
            (SurveyWindow.section_id == COMMENT_VIEW.c.section_id)
            & (SurveyWindow.week_id == COMMENT_VIEW.c.week_id),
        )
        .where(
            # SPEC §4: the week was below the n-threshold, so its comments were
            # never shown under their own week. A week at or above it is the
            # instructor's to read already, and putting one of its comments in a
            # batch too would show the same student's words twice.
            RESPONSE_COUNTS_VIEW.c.responses < threshold,
            # The week has closed, so that count is final. A window still taking
            # responses may yet reach the threshold, and a comment released from
            # it would then be shown twice — once in a batch and once under its
            # own week.
            SurveyWindow.closes_at < now,
            # ADR 0146: a comment is released at most once. An anti-join rather
            # than a caught integrity error, so a second membership is a defect
            # somebody sees rather than one the cutter absorbs.
            ~select(ReleaseBatchMember.answer_id)
            .where(ReleaseBatchMember.answer_id == COMMENT_VIEW.c.answer_id)
            .exists(),
        )
        .subquery()
    )


def _sections_whose_release_is_due(
    session: Session, held: Subquery, *, threshold: int
) -> set[tuple[UUID, UUID]]:
    """The `(section, term)` pairs every leg of the release gate opens for.

    **Three legs, all of which must hold, and nothing is cut when any fails.**
    Held is the safe direction: an under-threshold comment that stays held still
    feeds the summary and is released later, while a comment released early cannot
    be un-shown (ADR 0146 — nothing in this schema deletes a membership row). ADR
    0152 argues each leg and records that leg (b) subsumes the other two, which is
    why they are still written out: the legs are the reading of SPEC §4 that this
    build stands on, and each survives a change to another's denominator.

    Leg (b) is the effective floor and the one the security round added. §4's
    threshold is "n < 5 **responses** in a reporting week" — a number of people —
    while its release trigger names "comment volume", and §3.2 gives every response
    two comment items. So a volume that reaches the threshold can come from three
    students, or from one across three quiet weeks, and a release gated on the
    volume alone goes out over an author set far below what the threshold was
    chosen to protect.
    """
    volumes = _comment_volume_by_section_and_term(session)
    counted = select(
        held.c.section_id,
        held.c.term_id,
        # Distinct **people**, not distinct responses and not a row count: one
        # student answering both of §3.2's comment questions is one person twice
        # over, and the two numbers come apart in exactly the world this leg
        # exists for.
        func.count(distinct(held.c.respondent)).label("respondents"),
        func.count(distinct(held.c.week_id)).label("weeks"),
    ).group_by(held.c.section_id, held.c.term_id)

    due: set[tuple[UUID, UUID]] = set()
    for row in session.execute(counted).all():
        key = (row.section_id, row.term_id)
        # (a) SPEC §4's literal trigger: "the section's cumulative comment volume
        #     for the term crosses the threshold".
        volume_has_crossed = volumes.get(key, 0) >= threshold
        # (b) The people behind the comments this release would carry. §4's
        #     threshold counts responses, so the batch has to stand between a
        #     comment and at least that many candidate authors.
        enough_respondents = row.respondents >= threshold
        # (c) The weeks it would draw from. A batch confined to one week is the
        #     week attribution ADR 0153 removed, arriving through the report's own
        #     week-to-week delta: the release that was not there last Monday came
        #     from the week that closed in between.
        spans_enough_weeks = row.weeks >= WEEKS_A_RELEASE_MUST_SPAN
        if volume_has_crossed and enough_respondents and spans_enough_weeks:
            due.add(key)
    return due


def _held_answers_by_section_and_term(
    session: Session, held: Subquery
) -> dict[tuple[UUID, UUID], list[UUID]]:
    """Which comments each `(section, term)` is holding, by key and nothing else.

    Selected from the same `held` subquery `_sections_whose_release_is_due` counted,
    so the batch is built from the one definition the gate was read from — subject
    to the two-statement snapshot caveat and its backstops, which `_held_comments`
    states in full rather than repeating here. The respondent column is deliberately
    not selected: this is the list a membership row is written from, and a
    membership row carries a batch and a comment and nothing else (ADR 0146).
    """
    asked = select(held.c.section_id, held.c.term_id, held.c.answer_id)
    found: dict[tuple[UUID, UUID], list[UUID]] = {}
    for row in session.execute(asked).all():
        found.setdefault((row.section_id, row.term_id), []).append(row.answer_id)
    return found
