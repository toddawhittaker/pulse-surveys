"""SPEC §4's small-N comment rules, in one module — ticket E4-04.

This is the one place the product decides whether an instructor may read a
student's words. SPEC §14.3 marks it for line-by-line human review for that
reason, and the whole of §4's comment paragraph is here rather than spread over
a query, a serializer and a template:

> **Small-N handling (fewer than the threshold's number of distinct students
> commenting in a stream in a reporting week):** instructors see rating
> distributions and the AI summary, but **no raw comments** in that stream. The
> suppression is per stream: in one week the instructor stream can be held while
> the course stream is shown. Comments from under-threshold weeks are not
> discarded — they feed the summary, and they surface as raw text once the
> section's cumulative comment volume for the term crosses the threshold, batched
> so that timing cannot identify an author. Held comments surface only in those
> release batches, with no week named, and a comment released in a batch is never
> shown again under its own week. Threshold value is configurable (default 5).
>
> Comment display order is randomized; timestamps are never shown with comments.

Four callables and one payload:

* `stream_is_suppressed` — whether one stream of one section-week is below the
  threshold of distinct commenters; the one definition every reader of the rule
  calls;
* `visible_comments` — the asked stream's comments for the asked week when that
  stream is not suppressed, never a comment that is in a release batch, and the
  empty tuple when it is suppressed;
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
*answers* while the threshold is a number of *people*, and §3.2 gives every
response two comment items — so a volume that reaches the threshold can come from
three students, or from one across three quiet weeks. And a volume condition
stays true once crossed, so every Monday afterwards the same section passes the
same test and the cutter takes whatever is held: exactly the week that just
closed, which is a per-week batch, which is the week attribution ADR 0153 removed
arriving through the report's own delta.

So a batch is cut only when the volume reaches the threshold **and** the distinct
people behind the unreleased held comments reach it **and** those comments span at
least `WEEKS_A_RELEASE_MUST_SPAN` distinct closed weeks. When any leg fails for a
stream, that stream stays held. ADR 0152 carries the argument and states plainly that this is a
reading of §4 rather than §4's own words. Since ADR 0182 every leg is counted per
stream: a released comment carries its stream, so each stream's slice of a batch
must stand on a threshold's worth of its own authors over two weeks of its own,
and a stream whose legs do not open stays held while its sibling is released.

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
E4-02 shipped; a moderation verdict and its route are written only by the
routing definer `public.route_moderation_verdict`, and a person's decision only
by `app.services.moderation`'s decision door (E6-03). That module appends and
never orders: whatever it needs to know about which row is latest it asks this
one, through `latest_decision`, so "the latest row" has one definition.

**The handle, and what the report adds to a comment (E6-03).** `ReportComment`
stays three fields. The instructor's report also needs to name a comment so a
decision can be made on it, to show a flagged comment's chip, and to say
whether the latest decision was the reader's own, so `visible_cards` and
`released_cards` answer `CommentCard`s: the same comments, chosen by the same
rule in the same order, each carrying its `ReportComment`, its answer key, the
class of its flag and its latest decider. `visible_comments` and
`released_comments` are those two reads with everything but the
`ReportComment` dropped, so the rule is written once. The decider is a staff
`person` key, and it goes no further than `app.services.reporting`, which turns
it into a yes or no about the reader (ADR 0189).

**And no §6.2 suppression here, because it is below this module.** SPEC §5.2
ends "threat/self-harm classifications bypass this flow entirely (§6.2) and are
never shown to the instructor". Since E6-01 `report_comment` v004 leaves out
every comment that holds no moderation verdict and every comment any of whose
verdicts, ever, is threat or self-harm, so neither read here, nor the cutter,
nor the summary gather, can reach one (ADR 0187). What this module adds is the
section-week half: `section_week_moderated` keeps a week's comments from any
reader until every comment in it holds a verdict.

## The three rules this module reads, and where each is decided

**The threshold is a count of people per stream, and it is the institution's
number.** Since E5.1-01 (ADR 0182) a stream's raw comments for a week are shown
only when at least the threshold of distinct students commented in that stream
that week, counting only comments in no release batch. Not responses: in a week
of six respondents where one wrote about the instructor, a count of responses
shows that comment, and the per-week completion ledger in the gradebook can name
its author (`docs/MISTAKES.md` entry 50). The count is
`_commenters_by_stream_week`, written once; `stream_is_suppressed` reads it for
the week read, the summary's mode and the report's per-stream notice, and
`_held_comments` joins it to choose what is held. The threshold is also what all
three legs of the release gate compare against. `n_threshold` below is the one
place `Settings.n_threshold_default` is read for §4's rule — by this module's
gate, by the release cut, and by E4-07's report, which *prints* the number beside
the comments this gate hid. It is read inside each call rather than at import, so
an institution that changes it changes the rule rather than needing a restart —
SPEC §4 makes the value configuration.

**A released comment is never shown under its week again.** The week read
anti-joins `release_batch_member`, and the commenter count leaves released
comments out, so lowering the threshold or one late comment cannot bring a
released comment back beside the batch that already showed it with no week
(ADR 0182, ADR 0153).

**The moderation status is the latest row, or published.** ADR 0145 makes the
record append-only with the latest row governing and the initial state the
*absence* of a row, and names the consequence: "a reader of a comment's
moderation state has to write a window function, or its equivalent … That is
E4-04's and E6's to write once, in `app.services`, not per call site."
`reported_status_of` below is that once. Both reads go through it, the summary
gather in `app.services.reporting` calls it since E4-07, and it is shaped so E6
can call it too. An inner join here would drop every comment nobody has decided
about, which is most of them: only a flag or a decision writes a row. "Latest" is
`moderation_state.sequence`, the order of insert (E6-01, ADR 0187).

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

**The view is declared as `table()`/`column()` and not as a mapped class**,
because SPEC §13 ships identity-separated views as migrations and never as an
ORM convention. The declaration is also a statement worth reading on its own:
this module can name a section, a week, a stream, an answer key and a comment's
text, and no instant a comment was written at.

**Two places reach a person, and both count them rather than naming them.**
`_commenters_by_stream_week` and `_held_comments` walk `answer.response_id` and
then `response.user_id`, because §4's threshold and the release gate's second leg
are numbers of distinct people, and a gate that could not reach them could not
enforce either. In the first the column is inside `count(distinct …)` and is
grouped away; in the second it is a grouping inside one subquery that
`_streams_whose_release_is_due` reduces to an integer. It is not selected by the
membership read, it is not returned by anything, and no `ReportComment` has ever
carried it. That is the whole of the identity surface in this file, and it is
stated here so a reviewer can check the claim against four functions rather than
against the module.
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
    case,
    column,
    distinct,
    func,
    insert,
    select,
    table,
    true,
    tuple_,
)
from sqlalchemy.orm import Session

from app.ai.contracts import HeldNoteType
from app.config import Settings
from app.models.ai import Classification, ClassificationTask
from app.models.report import MODERATION_STATES, ModerationState, ReleaseBatch, ReleaseBatchMember
from app.models.survey import Answer, Question, QuestionKind, Response
from app.models.term import SurveyWindow, Week
from app.services import clock
from app.services.moderation import holds_no_verdict, under_the_attempt_cap

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

# How many distinct closed weeks one stream's held comments must draw from before
# that stream may be released — the third leg of the gate, counted per stream
# (ADR 0182). Two rather than one, and it is the
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


@dataclass(frozen=True)
class CommentCard:
    """One comment the instructor's report returns, with what lets it be acted on (E6-03).

    The `ReportComment` itself, and three things beside it, none of them a week,
    an instant or a student:

    * `answer_id`, the comment's `answer` key, which the decision route names.
      Random (`gen_random_uuid()`, ADR 0016), so it says nothing about when the
      comment was written; and safe to hand to an instructor because this read
      never returns a Care-class comment, so they never hold an id the reveal
      door would answer for (ADR 0189);
    * `flag`, the class of the comment's moderation verdict when it is harmful
      or privacy, and `None` otherwise;
    * `decided_by`, the `person` who made the latest decision about the comment,
      and `None` when nobody has (no row, or the router's flag). A staff key, and
      `app.services.reporting` reduces it to whether that person is the reader.

    Frozen, for the reason `ReportComment` gives.
    """

    comment: ReportComment
    answer_id: UUID
    flag: HeldNoteType | None
    decided_by: UUID | None


@dataclass(frozen=True)
class LatestDecision:
    """The latest `moderation_state` row about one comment, and the state before it.

    What the decision door needs to judge an action (E6-03): the state the comment
    is in, who decided it and under which role, whether that row was itself an
    undo, and the state the comment held before it, which is what an undo writes
    back. States are the stored tokens. `state_before` is `INITIAL_STATE` when the
    latest row is the only one, because absence is the published state (ADR 0145).
    """

    state: str
    decided_by: UUID | None
    decided_as: str | None
    is_undo: bool
    state_before: str


def n_threshold() -> int:
    """SPEC §4's configured n-threshold — the one place this number is read.

    "Threshold value is configurable (default 5)", counted in distinct students
    commenting in one stream in one reporting week (`stream_is_suppressed`). Every gate that applies it and every surface that *prints* it
    calls this, and that second half is the reason the function exists rather than
    each caller reaching for `Settings` itself.

    **E4-07's security round is the incident.** The instructor's report printed a
    threshold in its `small_n` member from the application's startup configuration
    while `visible_comments` below built a fresh `Settings()` per call. The two
    agree on every ordinary deployment and come apart the moment they are read at
    different times — a screen telling an instructor that comments appear once five
    students have commented, while the query that hid them applied some other
    number. A promise about confidentiality printed from one source and enforced
    from another is two promises, and the one a person acts on is the printed one.

    **A function rather than a parameter, and that is not the shape it wanted.**
    Handing the report's own `Settings` down to `visible_comments` is the plainer
    answer and it is not available: E4-04's work order settles that read's
    signature at four parameters and
    `tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`
    asserts it as an equality, deliberately, so that no fifth parameter of any kind
    can be added and later filled with something that names a person. That rule is
    worth more than the ergonomics, so the single source is a function both sides
    call instead of a value one side passes.

    Read per call rather than at import, which is the property the module docstring
    already claims: an institution that changes the number changes the rule rather
    than needing a restart.
    """
    return Settings().n_threshold_default


def stream_is_suppressed(
    session: Session,
    *,
    section_id: UUID,
    week_id: UUID,
    stream: str,
) -> bool:
    """Whether SPEC §4 withholds one stream's raw comments for one section-week.

    **True when fewer than `n_threshold()` distinct students commented in that
    stream that week**, counting only comments that are in no release batch. This
    is the one definition of "suppressed": `visible_comments` below asks it before
    reading any text, `app.services.reporting` asks it for the summary's mode and
    for the payload's per-stream notice, and `_held_comments` reads the same count
    through `_commenters_by_stream_week`. A second copy of the count anywhere is
    the shape `docs/MISTAKES.md` entry 19 is about.

    **The unit is people, per stream** (the owner's ruling for E5.1-01, and
    `docs/MISTAKES.md` entry 50). Not responses: in a week of six respondents where
    one student wrote about the instructor, a count of responses shows that one
    comment, and the per-week completion ledger SPEC §3.4 posts into the gradebook
    can name its author. Not comment answers either: one student is one candidate
    author however many comment items they filled in.

    **A stream nobody commented in is suppressed**, because zero is below any
    threshold. A reader is then told the same thing about an empty stream as about
    a thin one, so the notice cannot be used to tell nobody from one person.

    **Released comments do not count** (ADR 0182). Their authors are already
    behind a batch with no week, and counting them here would let a lowered
    threshold, or one late comment, bring a week's stream over the line on the
    strength of comments the instructor has already read elsewhere. Moderation
    state does not matter: a flagged or excluded comment still has an author.
    """
    counts = _commenters_by_stream_week()
    commenters = session.execute(
        select(counts.c.commenters).where(
            counts.c.section_id == section_id,
            counts.c.week_id == week_id,
            counts.c.stream == stream,
        )
    ).scalar_one_or_none()
    # A stream nobody commented in has no row in the grouped count, which is zero
    # commenters and so below any threshold. The boundary is inclusive on the
    # upper side: the threshold itself is the first size at which comments show.
    return (commenters or 0) < n_threshold()


def section_week_moderated(session: Session, *, section_id: UUID, week_id: UUID) -> bool:
    """Whether every comment of one section-week that a reader could see holds a moderation verdict.

    **The one home of this rule** (ADR 0187). Three readers ask it: the week read
    (`visible_comments` shows nothing of a section-week until it is true), the
    release cut (`cut_due_release_batches` skips such a section-week whole, and
    its comments join a later cut) and the summary walk in
    `app.services.reporting` (which does not summarize the week until it is
    true). So a reader sees nothing of a week's comments before its last verdict
    lands and all of them after, and no read shows part of a week: a week shown
    one comment at a time as verdicts arrive would let a reader who keeps each
    report attribute the newest comment by subtraction (`docs/MISTAKES.md`
    entry 51).

    **"A comment a reader could see" is a comment `report_comment` would show if
    the verdict did not matter**: an answer to a comment question with text that
    is not blank. A blank answer is not waited for, because no moderator will
    ever classify it and it would hold its week back for ever. A comment holding a
    threat or self-harm verdict counts as moderated: it holds a verdict, and the
    view leaves it out of every reader.

    True for a section-week with no comments at all, which has nothing to wait
    for. A comment at the moderation attempt cap (ADR 0188) is not waited for
    either: it will never hold a verdict, so it is never shown, and waiting on it
    would hold the rest of its week back for ever.
    """
    return (section_id, week_id) not in _unmoderated_section_weeks(
        session, Response.section_id == section_id, Response.week_id == week_id
    )


def visible_comments(
    session: Session,
    *,
    section_id: UUID,
    week_id: UUID,
    stream: str,
) -> tuple[ReportComment, ...]:
    """One section-week's comments in one stream, or nothing at all below the threshold.

    `visible_cards` with each card's `ReportComment` and nothing else, in the
    order it answered. The rule below is written there, once.

    SPEC §4: below the n-threshold "instructors see rating distributions and the
    AI summary, but **no raw comments**", and §4.1 item 3 makes that an invariant
    rather than a convention. The threshold is counted in distinct students
    commenting in this stream this week, and `stream_is_suppressed` above is the
    one place that count is made. §5.2 adds the half that is easy to ship without
    noticing: below the threshold a flagged comment is hidden "entirely — no chip,
    no count, no flag-type hint", because in a stream of four commenters a held
    count is a statement about one of four identifiable people.

    **A suppressed stream and a stream nobody commented in answer the same value.**
    The empty tuple is returned before any comment is read, so nothing a caller
    receives says how much was withheld — not a length, not a type, not a
    placeholder.

    **A comment in a release batch is never returned here** (ADR 0182). It has
    already been shown with no week, in the from-earlier-weeks list, and returning
    it under its week again would re-attach the week ADR 0153 removed. The rule is
    an anti-join rather than a consequence of the count, so it holds after the
    threshold setting is lowered and after a late comment lifts the stream over it.

    Above the threshold every other comment comes back, whatever its moderation
    state: a flagged one collapsed with its chip, an excluded one still visible to
    the instructor (§5.2 keeps its text "visible to the instructor, muted, above
    the exclusion notice"), and a kept one published. A read that filtered a state
    out would remove the record of a decision from the report of the person who
    made it, which is what §5.2's anti-cherry-picking argument rests on.

    **The threshold comes from `n_threshold` above, and every surface that prints
    a threshold reads the same function.** E4-07's report prints one beside the
    comments this gate hid; that record says why the two may not be separate reads.
    """
    return tuple(
        card.comment
        for card in visible_cards(session, section_id=section_id, week_id=week_id, stream=stream)
    )


def visible_cards(
    session: Session,
    *,
    section_id: UUID,
    week_id: UUID,
    stream: str,
) -> tuple[CommentCard, ...]:
    """`visible_comments`'s rule, answering each comment as a `CommentCard` (E6-03).

    This is where the week read's rule is written, and `visible_comments` is this
    with the cards' extras dropped. The instructor's report and the decision door
    both read here, so the door accepts exactly the comments the report shows.
    """
    # A section-week is shown whole or not at all: until every comment in it
    # holds a moderation verdict, no stream of it shows anything, in the same
    # empty shape a suppressed stream answers (ADR 0187).
    if not section_week_moderated(session, section_id=section_id, week_id=week_id):
        return ()
    if stream_is_suppressed(session, section_id=section_id, week_id=week_id, stream=stream):
        return ()

    asked = _cards_with_their_status().where(
        # §4's confidentiality model is per section: an instructor reads their own
        # students' words and nobody else's.
        COMMENT_VIEW.c.section_id == section_id,
        # §4's threshold is counted "in a reporting week", so a read that pooled a
        # section's weeks would test one week's count and return another's text.
        COMMENT_VIEW.c.week_id == week_id,
        # §5.1's two groups, each headed by its own summary and routed differently
        # by §5.2 — and since E5.1-01 each counted against the threshold on its own.
        COMMENT_VIEW.c.stream == stream,
        # A released comment belongs to the from-earlier-weeks list and to no week.
        _in_no_release_batch(COMMENT_VIEW.c.answer_id),
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

    `released_cards` with each card's `ReportComment` and nothing else; the read
    is written there, once.
    """
    return tuple(
        card.comment
        for card in released_cards(session, section_id=section_id, term_id=term_id, stream=stream)
    )


def released_cards(
    session: Session,
    *,
    section_id: UUID,
    term_id: UUID,
    stream: str,
) -> tuple[CommentCard, ...]:
    """`released_comments`'s read, answering each comment as a `CommentCard` (E6-03)."""
    asked = (
        _cards_with_their_status()
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
    read time (ADR 0152). A comment is **held** when its stream was below the
    threshold of distinct commenters that week (ADR 0182), its window has closed, and it is in no batch yet; `_held_comments`
    is the one definition and both the gate and the batch are built from it.

    **The gate is three legs, evaluated per `(section, term, stream)`, and every
    one of them must open for a stream** (ADR 0152, after the security round; per
    stream since ADR 0182):

    a. that stream's cumulative comment-answer volume for the term reaches the
       threshold — SPEC §4's literal trigger, counted over every comment the
       section holds in that stream in the term whatever its moderation state and
       whether or not it has already gone out;
    b. the **distinct people** behind that stream's unreleased held comments
       reach the threshold;
    c. those comments span at least `WEEKS_A_RELEASE_MUST_SPAN` distinct closed
       weeks.

    **Per stream, because each released card carries its stream** and each week's
    report says which of its streams were held. Pooled across streams, a batch
    could carry one instructor comment from the only week whose instructor stream
    was held, beside four course authors, and the card's stream chip would pin it
    to that week's lone commenter (ADR 0182). Evaluated per stream, each stream's
    slice of a release stands on at least a threshold's worth of its own authors
    and at least two weeks of its own. Leg (b) subsumes the other two again — a
    stream's held set inside one week has fewer than the threshold of authors by
    definition — and all three are written out anyway, as ADR 0152 argues. **When
    any leg fails for a stream, that stream stays held**, which is the safe
    direction: a held comment still feeds the summary and is released later, and a
    released one cannot be un-shown.

    **At most one batch per section and term per run, holding the due streams'
    held comments and no others.** ADR 0146 puts the only time in the design on
    the batch's `cut_at`, so a release split across several batches gives its
    comments several release times, and the difference between two of them is the
    per-comment timing §4 batches the release to remove. A stream whose legs did
    not open stays out of the batch and waits for a later Monday.

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
    # The same one reader the read gate uses. All three legs of the release gate
    # compare against §4's threshold, so a second reading of it here would be the
    # third source of one number.
    threshold = n_threshold()
    # ADR 0109's convention: scheduling and visibility read the effective clock,
    # never the process clock, so a development stack walked forward by hand sees
    # the weeks it has been walked past.
    now = clock.now(session, settings=settings)

    # A section-week whose comments are not all moderated yet is skipped whole;
    # its comments join a later cut once the last verdict lands (ADR 0187).
    held = _held_comments(
        threshold=threshold, now=now, unmoderated=_unmoderated_section_weeks(session)
    )
    due = _streams_whose_release_is_due(session, held, threshold=threshold)
    answers = _held_answers_by_section_term_and_stream(session, held)

    # At most one batch per `(section, term)` per run, holding the held comments of
    # exactly the streams whose three legs all opened. A stream whose legs did not
    # open stays held, even when its sibling is released: pooling the two would let
    # one stream's authors open the gate for the other's comments (ADR 0182).
    due_streams: dict[tuple[UUID, UUID], list[str]] = {}
    for section_id, term_id, stream in due:
        due_streams.setdefault((section_id, term_id), []).append(stream)

    cut = 0
    # Sorted, so two runs over the same data visit the sections in the same order
    # and a failure part-way through a walk is reproducible. Nothing about the
    # order reaches a caller — this is which section is released first, not which
    # comment is shown first, which is `_shuffled`'s.
    for key in sorted(due_streams):
        section_id, term_id = key
        batch_id = session.execute(
            insert(ReleaseBatch)
            .values(section_id=section_id, term_id=term_id)
            .returning(ReleaseBatch.id)
        ).scalar_one()
        session.execute(
            insert(ReleaseBatchMember),
            [
                {"batch_id": batch_id, "answer_id": answer_id}
                for stream in sorted(due_streams[key])
                for answer_id in answers[(section_id, term_id, stream)]
            ],
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

    **The ordering is `moderation_state.sequence`, the order of insert** (E6-01,
    ADR 0187). `decided_at` defaults to `now()`, which is PostgreSQL's
    *transaction* timestamp, so every row written in one transaction carries the
    same instant, and ordering by it let `LIMIT 1` choose between two such rows
    arbitrarily — a comment a moderator excluded could resolve to `published`.
    `sequence` is an identity column the database assigns, so the second of two
    decisions written in one transaction is the later one. It records insert
    order, not commit order: of two concurrent writers, the one that inserted
    first is earlier even if it committed second. Breaking the tie on the row key
    instead would have been a wrong answer: `moderation_state.id` is
    `gen_random_uuid()`, a coin flip rather than an order.

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
        .order_by(ModerationState.sequence.desc())
        .limit(1)
        .scalar_subquery()
    )
    resolved: ColumnElement[str] = func.coalesce(latest, INITIAL_STATE)
    return resolved


def latest_decision(session: Session, answer_id: UUID) -> LatestDecision | None:
    """The latest decision row about one comment and the state before it, or `None` (E6-03).

    The decision door's question, answered here because this module is the one
    home of the ordering (`reported_status_of` above, E4-07's deferral): the
    door appends and never orders. "Latest" is `moderation_state.sequence`, the
    order of insert, as everywhere else. `None` when the comment has no row,
    which is the published state.
    """
    rows = session.execute(
        select(
            ModerationState.state,
            ModerationState.decided_by_person_id,
            ModerationState.decided_as,
            ModerationState.is_undo,
        )
        .where(ModerationState.answer_id == answer_id)
        .order_by(ModerationState.sequence.desc())
        .limit(2)
    ).all()
    if not rows:
        return None
    latest = rows[0]
    return LatestDecision(
        state=latest.state,
        decided_by=latest.decided_by_person_id,
        decided_as=latest.decided_as,
        is_undo=latest.is_undo,
        state_before=rows[1].state if len(rows) > 1 else INITIAL_STATE,
    )


def _flag_of(answer_id: SQLColumnExpression[Any]) -> ColumnElement[str | None]:
    """The class of a comment's flag: `harmful`, else `privacy`, else NULL (E6-03).

    Read from the comment's `MODERATION` verdicts rather than from its state, so
    a flagged comment an instructor kept is still a flagged comment: the reason
    rule (an unflagged exclusion needs a stated reason) and the chip both ask
    what the AI said, not what anybody decided. Harmful first when a comment
    holds both, because it is the stronger of the two. The two tokens are
    `HeldNoteType`'s, the closed set that cannot name a Care class.
    """

    def holds(verdict: HeldNoteType) -> ColumnElement[bool]:
        held: ColumnElement[bool] = (
            select(Classification.id)
            .where(
                Classification.answer_id == answer_id,
                Classification.task == ClassificationTask.MODERATION,
                Classification.verdict == verdict.value,
            )
            .exists()
        )
        return held

    flag: ColumnElement[str | None] = case(
        (holds(HeldNoteType.HARMFUL), HeldNoteType.HARMFUL.value),
        (holds(HeldNoteType.PRIVACY), HeldNoteType.PRIVACY.value),
        else_=None,
    )
    return flag


def _latest_decider_of(answer_id: SQLColumnExpression[Any]) -> ColumnElement[UUID | None]:
    """Who made the latest decision about a comment: the latest row's decider, or NULL.

    The same ordering `reported_status_of` reads, so a card's status and its
    decider come from the same row. NULL when the comment has no row, and when
    the latest row is the routing definer's flag, which nobody decided.
    """
    decider: ColumnElement[UUID | None] = (
        select(ModerationState.decided_by_person_id)
        .where(ModerationState.answer_id == answer_id)
        .order_by(ModerationState.sequence.desc())
        .limit(1)
        .scalar_subquery()
    )
    return decider


def _cards_with_their_status() -> Select[tuple[UUID, str, str, str, str | None, UUID | None]]:
    """The columns a `CommentCard` is built from, before any filter.

    Deliberately unfiltered and deliberately unordered. The scoping predicates
    belong to the caller, where a reviewer reads them beside the rule each one
    carries; the order belongs to `_shuffled`, because SPEC §4 randomizes comment
    display order and **no stored order may reach a caller**: the answer's key,
    the response's key and `submitted_at` are all submission order, which says who
    answered first. The answer key is selected to be carried, never to order by.
    """
    answer_id = COMMENT_VIEW.c.answer_id
    return select(
        answer_id,
        COMMENT_VIEW.c.comment_text,
        reported_status_of(answer_id),
        COMMENT_VIEW.c.stream,
        _flag_of(answer_id),
        _latest_decider_of(answer_id),
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


def _shuffled(
    rows: Sequence[Row[tuple[UUID, str, str, str, str | None, UUID | None]]],
) -> tuple[CommentCard, ...]:
    """The rows as `CommentCard`s, in a random order.

    SPEC §4: "Comment display order is randomized; timestamps are never shown with
    comments." The two halves of that sentence are one rule — a list in submission
    order *is* a timestamp, and read beside SPEC §3.4's per-week completion ledger
    in the gradebook (ADR 0125) the first responder is often nameable.

    The shuffle is in Python rather than in SQL so that there is one place it
    happens; the source is `_make_rng`, looked up here on every call so that the
    module's own hook is what decides it.
    """
    cards = [
        CommentCard(
            comment=ReportComment(text=text, status=REPORTED_STATUS[stored], stream=stream),
            answer_id=answer_id,
            flag=None if flag is None else HeldNoteType(flag),
            decided_by=decided_by,
        )
        for answer_id, text, stored, stream, flag, decided_by in rows
    ]
    _make_rng().shuffle(cards)
    return tuple(cards)


def _comment_volume_by_section_term_and_stream(
    session: Session,
) -> dict[tuple[UUID, UUID, str], int]:
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
            COMMENT_VIEW.c.stream,
            func.count().label("volume"),
        )
        .join_from(COMMENT_VIEW, Week, Week.id == COMMENT_VIEW.c.week_id)
        .group_by(COMMENT_VIEW.c.section_id, Week.term_id, COMMENT_VIEW.c.stream)
    )
    return {
        (row.section_id, row.term_id, row.stream): row.volume
        for row in session.execute(counted).all()
    }


def _in_no_release_batch(answer_id: SQLColumnExpression[Any]) -> ColumnElement[bool]:
    """True for a comment that has no `release_batch_member` row — written once.

    Three readers need it and they must agree: the commenter count (a released
    author no longer counts toward their week), the week read (a released comment
    is never shown under its week), and the held set (ADR 0146: a comment is
    released at most once). An anti-join rather than a caught integrity error, so
    a second membership is a defect somebody sees rather than one the cutter
    absorbs.
    """
    released: ColumnElement[bool] = (
        select(ReleaseBatchMember.answer_id)
        .where(ReleaseBatchMember.answer_id == answer_id)
        .exists()
    )
    return ~released


def _unmoderated_section_weeks(
    session: Session, *scope: ColumnElement[bool]
) -> set[tuple[UUID, UUID]]:
    """The section-weeks holding a comment a reader could see that has no moderation verdict.

    `section_week_moderated` above is the rule in words; this is its one
    implementation, which the release cut reads as a set and the week read and
    the summary walk read one section-week at a time. `scope` narrows the walk
    (to one section-week, for those two).

    **What counts as a comment is `report_comment`'s own test, before its
    moderation conditions**: an answer to a `comment` question whose text is not
    null and not blank. Blank is decided by `str.strip()` on the text, which is
    the write path's test and the definition `report_comment_v003.sql` lists by
    code point (its header says so), so this is the definition the view copies
    rather than a second copy beside it. Only answers with no `MODERATION`
    classification are fetched, and their text is read only to be stripped: it
    is never returned, logged or kept.
    """
    unverdicted = (
        select(Response.section_id, Response.week_id, Answer.comment_text)
        .join_from(Answer, Response, Response.id == Answer.response_id)
        .join(Question, Question.id == Answer.question_id)
        .where(
            Question.kind == QuestionKind.COMMENT,
            Answer.comment_text.is_not(None),
            holds_no_verdict(Answer.id),
            # A comment at the attempt cap is resolved: it is never verdicted, so
            # it is never shown, and the rest of its week stops waiting on it.
            under_the_attempt_cap(Answer.id),
            *scope,
        )
    )
    return {
        (section_id, week_id)
        for section_id, week_id, written in session.execute(unverdicted).all()
        if written.strip()
    }


def _outside(section_weeks: set[tuple[UUID, UUID]]) -> ColumnElement[bool]:
    """True for a `report_comment` row in none of `section_weeks`."""
    if not section_weeks:
        return true()
    return tuple_(COMMENT_VIEW.c.section_id, COMMENT_VIEW.c.week_id).not_in(sorted(section_weeks))


def _commenters_by_stream_week() -> Subquery:
    """How many distinct students commented in each section, week and stream.

    **The one count SPEC §4's threshold is compared with**, as a subquery so that
    `stream_is_suppressed` filters it to one stream-week and `_held_comments`
    joins it to every comment. Two copies of this count that drifted would show a
    stream under its week by one rule and hold it for release by another, and a
    comment could then be shown twice or never.

    Counted over comments in no release batch (ADR 0182), whatever their
    moderation state. The walk to a person is `answer.response_id` then
    `response.user_id`, and the column is used only inside `count(distinct …)`:
    it is grouped away here and nothing selects it.
    """
    return (
        select(
            COMMENT_VIEW.c.section_id.label("section_id"),
            COMMENT_VIEW.c.week_id.label("week_id"),
            COMMENT_VIEW.c.stream.label("stream"),
            # Distinct **people**, not responses and not comment answers
            # (`docs/MISTAKES.md` entry 50).
            func.count(distinct(Response.user_id)).label("commenters"),
        )
        .join_from(COMMENT_VIEW, Answer, Answer.id == COMMENT_VIEW.c.answer_id)
        .join(Response, Response.id == Answer.response_id)
        .where(_in_no_release_batch(COMMENT_VIEW.c.answer_id))
        .group_by(COMMENT_VIEW.c.section_id, COMMENT_VIEW.c.week_id, COMMENT_VIEW.c.stream)
        .subquery()
    )


def _held_comments(
    *, threshold: int, now: datetime, unmoderated: set[tuple[UUID, UUID]]
) -> Subquery:
    """The comments SPEC §4 has been holding back — the one definition of "held".

    Three conditions, one per concern, and none of them is another's spare: the
    comment's **stream** was below the threshold of distinct commenters that week
    (counted by `_commenters_by_stream_week`, the count `stream_is_suppressed`
    reads), its window has closed, and it is in no batch. The
    predicate is written once, as a subquery, and `cut_due_release_batches` selects
    from it twice: `_streams_whose_release_is_due` counts it to decide which
    `(section, term, stream)` the gate opens for, and
    `_held_answers_by_section_term_and_stream`
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
    what nothing here ever returns: `_streams_whose_release_is_due` reduces them to
    two integers, the membership read selects the answer key alone, and no
    `ReportComment` has ever carried either. The walk to a person is
    `answer.response_id` then `response.user_id`, which is a walk the product may
    make to *count* people and may never make to *name* one — SPEC §4's threshold is
    a number of people, so a gate that could not reach them could not enforce it.
    """
    commenters = _commenters_by_stream_week()
    return (
        select(
            COMMENT_VIEW.c.section_id.label("section_id"),
            Week.term_id.label("term_id"),
            COMMENT_VIEW.c.stream.label("stream"),
            COMMENT_VIEW.c.answer_id.label("answer_id"),
            COMMENT_VIEW.c.week_id.label("week_id"),
            Response.user_id.label("respondent"),
        )
        .join_from(COMMENT_VIEW, Week, Week.id == COMMENT_VIEW.c.week_id)
        .join(Answer, Answer.id == COMMENT_VIEW.c.answer_id)
        .join(Response, Response.id == Answer.response_id)
        .join(
            commenters,
            (commenters.c.section_id == COMMENT_VIEW.c.section_id)
            & (commenters.c.week_id == COMMENT_VIEW.c.week_id)
            & (commenters.c.stream == COMMENT_VIEW.c.stream),
        )
        .join(
            SurveyWindow,
            (SurveyWindow.section_id == COMMENT_VIEW.c.section_id)
            & (SurveyWindow.week_id == COMMENT_VIEW.c.week_id),
        )
        .where(
            # SPEC §4: the comment's stream had fewer than the threshold of
            # distinct commenters that week, so its comments were never shown
            # under their own week — the rule `stream_is_suppressed` applies, over
            # the same count. A stream at or above it is the instructor's to read
            # already, and putting one of its comments in a batch too would show
            # the same student's words twice. Per stream (ADR 0182): a thin
            # instructor stream is held beside a course stream that is shown.
            commenters.c.commenters < threshold,
            # The week has closed, so that count is final. A window still taking
            # responses may yet reach the threshold, and a comment released from
            # it would then be shown twice — once in a batch and once under its
            # own week.
            SurveyWindow.closes_at < now,
            # ADR 0146: a comment is released at most once.
            _in_no_release_batch(COMMENT_VIEW.c.answer_id),
            # ADR 0187: a section-week is released only once every comment in it
            # holds a moderation verdict, so a batch never carries part of a week.
            _outside(unmoderated),
        )
        .subquery()
    )


def _streams_whose_release_is_due(
    session: Session, held: Subquery, *, threshold: int
) -> set[tuple[UUID, UUID, str]]:
    """The `(section, term, stream)` triples every leg of the release gate opens for.

    **Three legs, all of which must hold for a stream, and that stream stays held
    when any fails.** Held is the safe direction: an under-threshold comment that
    stays held still feeds the summary and is released later, while a comment
    released early cannot be un-shown (ADR 0146 — nothing in this schema deletes a
    membership row). ADR 0152 argues each leg; ADR 0182 evaluates all three per
    stream, because a released card carries its stream and a pooled gate let one
    stream's authors open the gate for the other's comments.

    Leg (b) is the one the security round added. §4's threshold is a number of
    people — distinct commenters in a stream — while its release trigger names
    "comment volume", and §3.2 gives every response two comment items. So a volume
    that reaches the threshold can come from three students, or from one across
    three quiet weeks, and a release gated on the volume alone goes out over an
    author set far below what the threshold was chosen to protect.
    """
    volumes = _comment_volume_by_section_term_and_stream(session)
    counted = select(
        held.c.section_id,
        held.c.term_id,
        held.c.stream,
        # Distinct **people**, not distinct responses and not a row count: one
        # student answering both of §3.2's comment questions is one person twice
        # over, and the two numbers come apart in exactly the world this leg
        # exists for.
        func.count(distinct(held.c.respondent)).label("respondents"),
        func.count(distinct(held.c.week_id)).label("weeks"),
    ).group_by(held.c.section_id, held.c.term_id, held.c.stream)

    due: set[tuple[UUID, UUID, str]] = set()
    for row in session.execute(counted).all():
        key = (row.section_id, row.term_id, row.stream)
        # (a) SPEC §4's literal trigger, "the section's cumulative comment volume
        #     for the term crosses the threshold", counted in this stream.
        volume_has_crossed = volumes.get(key, 0) >= threshold
        # (b) The people behind this stream's comments this release would carry.
        #     §4's threshold counts people, and a released card names its stream,
        #     so the stream's slice has to stand between a comment and at least
        #     that many candidate authors.
        enough_respondents = row.respondents >= threshold
        # (c) The weeks it would draw from. A batch confined to one week is the
        #     week attribution ADR 0153 removed, arriving through the report's own
        #     week-to-week delta: the release that was not there last Monday came
        #     from the week that closed in between. Counted in this stream.
        spans_enough_weeks = row.weeks >= WEEKS_A_RELEASE_MUST_SPAN
        if volume_has_crossed and enough_respondents and spans_enough_weeks:
            due.add(key)
    return due


def _held_answers_by_section_term_and_stream(
    session: Session, held: Subquery
) -> dict[tuple[UUID, UUID, str], list[UUID]]:
    """Which comments each `(section, term, stream)` is holding, by key and nothing else.

    Selected from the same `held` subquery `_streams_whose_release_is_due` counted,
    so the batch is built from the one definition the gate was read from — subject
    to the two-statement snapshot caveat and its backstops, which `_held_comments`
    states in full rather than repeating here. The respondent column is deliberately
    not selected: this is the list a membership row is written from, and a
    membership row carries a batch and a comment and nothing else (ADR 0146).
    """
    asked = select(held.c.section_id, held.c.term_id, held.c.stream, held.c.answer_id)
    found: dict[tuple[UUID, UUID, str], list[UUID]] = {}
    for row in session.execute(asked).all():
        found.setdefault((row.section_id, row.term_id, row.stream), []).append(row.answer_id)
    return found
