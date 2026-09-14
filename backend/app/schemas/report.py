"""The instructor's Monday report as it goes over the wire (SPEC §5.1, §2.2, §4.1).

`docs/tickets/e4/README.md` carries a payload sketch that E4-08 through E4-11
build their component fixtures against, and E4's breakdown decision 5 makes
**this module the authority over that sketch** from the moment it merges. The
sketch section names this file for that reason, and
`tests/unit/test_the_payload_sketch_and_the_schema_are_reconciled.py` holds the
two to each other in both directions: a member here that the sketch does not
describe is a payload the frontend fixtures do not know about, and a member the
sketch describes and this does not is a fixture built against something that will
never arrive.

**Five members diverge from E4's sketch deliberately**, and each is recorded in
its own ticket's pull request rather than only here:

  - `rates.valid_responses` — E4-09's components render the count beside the
    ratio, and the sketch omitted it. Its source is `response.is_valid` as
    `app/services/validity.py` maintains it, per
    [ADR 0147](../../../docs/adr/0147-the-report-views-return-counts-and-the-payload-layer-divides.md),
    and never a `classification` row.
  - `released_from_earlier_weeks` — the from-earlier-weeks list
    [ADR 0152](../../../docs/adr/0152-the-crossing-is-cut-by-a-task-of-its-own-not-at-read-time-and-not-by-the-summary-job.md)
    says E4-07 places. Present in every report as a list, populated only in the
    latest published week's report, and carrying no week anywhere
    ([ADR 0153](../../../docs/adr/0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)).
  - `institution_timezone` — E5-02's, and the first that no E4 record settles.
    The week's close instant is rendered as a weekday and a wall-clock time,
    which is a statement in one named zone, and that zone is configuration the
    server holds and the browser does not.
  - `streams.<stream>.benchmark` and `workload_benchmark` — E5-05's, and they
    could not have been in E4's sketch at all: E4 built no comparison set, so
    there were no figures for the sketch to describe. They are SPEC §5.1's
    second and third lines per panel and its workload statistics "against
    comparison-set and university figures". Their own models are in
    `app.schemas.report_benchmark`, which says why they are not here, and E5's
    breakdown carries the sketch that does describe them.

**A comment carries three fields and no fourth.** `ReportComment` — what
`app.services.report_comments` answers with — is `(text, status, stream)`, and
SPEC §4 is why the absences matter: comment display order is randomized and
timestamps are never shown beside a comment, so an index, a position, a
submission instant or a per-week count added here for a frontend's convenience
would undo at the assembly layer what the module below was reviewed line by line
to guarantee.

**`comparison` is typed with a class this module cannot construct, and it is
re-checked here anyway.** SPEC §4.1 item 7 suppresses any figure computed from a
comparison set below the configured minimums, and E4's breakdown decision 4 puts
the member on the wire from day one so that chokepoint has somewhere to stand
before E5 fills it. `app.services.reporting.ComparisonFigure`'s constructor
demands a token private to that module — but a constructor is not the only way to
produce a pydantic instance, and E4-07's security round demonstrated two that skip
it: `model_construct`, which runs neither validation nor `__init__`, and
`model_copy(update=...)`, which rewrites the fields of a value the helper had
already suppressed.

So item 7's boundary is **the wire**, and it took two parts to put it there. The
inner part is `InstructorReport`'s validation of the member below, which asks
`app.services.reporting.refuse_an_unsealed_comparison` whether the helper produced
the value. The outer part is `revalidate_instances="always"` on that model, and
the review's re-pass is why it exists: the same two methods build a *report*
without validating it, so a field validator alone could be skipped one level out
exactly as the constructor's token was. With the revalidation, the response
re-reads whatever object the route hands it, whatever assembled it.

Item 7 is a rule about what is *shown*, so the check belongs at the last boundary
before showing rather than at the first before building — and "the last boundary"
had to be found three times.

**The section list's own two models are here too** (E4-18: `TaughtSection` and
`TaughtSections`, at the foot of this file). They are not part of the report
payload and the sketch does not describe them — they are what the page reads
before it can ask for a report at all, since every route the report is served from
takes a section key and nothing the client holds supplies one. They sit beside the
report rather than in a module of their own because they name a section in exactly
the governed form `SectionView` below does, and two files naming one thing is two
places for that form to drift.

**Rates that have no value are `None` and never zero.** A validity rate over
zero responses is not "all invalid", and a response rate over an empty enrolment
is not "nobody answered" — both are the absence of a ratio, and E4-09 renders the
absence. The rule is written once, in `app.services.reporting`, and this schema is
what makes the absent state expressible.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import report_benchmark
from app.services.reporting import ComparisonFigure, refuse_an_unsealed_comparison

__all__ = [
    "CommentView",
    "InstructorReport",
    "PublishedWeeks",
    "RatesView",
    "SectionView",
    "SmallNView",
    "StreamReport",
    "StreamsView",
    "SummaryView",
    "TaughtSection",
    "TaughtSections",
    "TrendPoint",
    "WeekView",
    "WorkloadView",
]


class SectionView(BaseModel):
    """Which section this report is about, in the words its instructor knows it by."""

    model_config = ConfigDict(frozen=True)

    # SPEC §2.2's section code — the start letter, the ordinal and the modality.
    code: str = Field(description="The LMS section code, e.g. 'F1WW' (SPEC §2.2).")
    # The same governed label the student's own page carries (E2-09, FIX-01 item
    # 2): the prefix code, the LMS number, the section code, an em dash, the LMS
    # title, a comma and the term's name.
    course_label: str = Field(description="'MATH 140 E1FF — College Algebra, Fall 2026'.")
    # The section's own length, not its term's. E4-08's trend axis draws this many
    # weeks, and a section running six weeks inside an eighteen-week term is the
    # ordinary case rather than the exception (SPEC §2.2).
    length_weeks: int = Field(description="How many weeks this section runs (SPEC §2.2).")


class WeekView(BaseModel):
    """Where on §2.2's two axes this report sits, and where week navigation may go.

    Both axes are on the wire because §2.2 puts both on the page: a course-level
    page plots the course week with the term week as a quiet sub-label, and a
    consumer that had one of the two would have to re-derive the other from the
    section's start-letter calendar.
    """

    model_config = ConfigDict(frozen=True)

    course_week: int
    term_week: int
    # Exactly the course weeks whose survey window has closed, per the clock
    # service (E4's breakdown decision 6). Nothing is stored to make a week
    # published, so this is a comparison rather than a flag.
    published_weeks: list[int]
    # The reported week's own `survey_window.closes_at` — the row the report read
    # already holds, so this member costs no query. It travels as an instant
    # rather than as a string the server has already formatted, because the
    # weekday and wall clock the eyebrow prints are a statement in one particular
    # zone and `institution_timezone` below is what names that zone. A read that
    # formatted here would be deciding the reader's locale on the server.
    #
    # The reported week's, never the current one: week navigation pages back
    # across published weeks (SPEC §5.1), and a close taken from the latest
    # window is right on the week an instructor opens by default and wrong on
    # every week she pages back to.
    closes_at: datetime


class RatesView(BaseModel):
    """SPEC §5.1's two rates and the counts they are ratios of.

    ADR 0147 keeps every division out of SQL and here instead, so that the rule
    for a zero denominator is written in one reviewable place. `response_rate` and
    `validity_rate` are `None` where that rule leaves them undefined.
    """

    model_config = ConfigDict(frozen=True)

    response_rate: float | None
    validity_rate: float | None
    responses: int
    enrolled: int
    # The sketch's declared divergence: E4-09 renders the count as well as the
    # ratio, and `report_response_counts.valid_responses` is where it comes from.
    valid_responses: int


class TrendPoint(BaseModel):
    """One week of one stream's trend line.

    `mean` is `None` for a week nobody rated. Zero is a rating nobody can give —
    SPEC §3.2's scale runs 1 to 5 — so a zero here would draw a line to the floor
    of the chart for a week that has no line at all (ADR 0147's zero-filling: a
    stored zero and a missing week never arrive looking the same).

    `term_week` is the term week of the window row this point was built from —
    §2.2's second axis, stated here rather than left for the client to derive
    (breakdown decision 12, ADR 0157). Today the gap between the two axes is a
    per-section constant (`_section_weeks`' `first_term_week`), so a client
    could compute this member from the report week's own `course_week` /
    `term_week` pair. It is on the wire anyway because `week_of_the_term` is
    this codebase's one reading of the axis mapping (§2.2), and a client that
    derived the pair would freeze today's arithmetic into a second copy of
    that reading — one that would disagree silently the day the mapping
    stops being affine, which is exactly the section-pausing-over-a-break
    case E4-08's copy file anticipates. Stating the number here widens
    nothing: it is what every reader of this payload could already compute
    from `week` alone.
    """

    model_config = ConfigDict(frozen=True)

    course_week: int
    term_week: int
    mean: float | None


class SummaryView(BaseModel):
    """§5.1's generated summary for one stream of one week, as E4-06 stored it.

    The member is absent — `None` on the stream, not an empty string — for a week
    the summary job has not run over, which is the ordinary state of a report read
    before Monday morning.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    response_count: int
    # The sketch carries this and nothing stores it yet: E6 writes the first
    # moderation state this system will hold, and §5.1's "excludes flagged-held
    # content" note is what would fill it. Null in every E4 payload.
    held_note: str | None = None


class CommentView(BaseModel):
    """One comment, with exactly the three fields the comment service answers with.

    No week, no timestamp, no author, no index, at any depth. SPEC §4 and ADR 0153
    are the argument, and
    `tests/integration/test_the_report_payload_repeats_nothing_beyond_the_comment_service.py`
    is what holds this shape to it.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    status: str
    stream: str


class StreamReport(BaseModel):
    """One of SPEC §5.1's two comment groups: its numbers, its summary and its words."""

    # `revalidate_instances="always"` for the reason `InstructorReport` below gives,
    # one level down: this model holds the benchmark members, and pydantic accepts
    # an instance of a nested model without re-validating it unless that model asks
    # to be. Without this line the seal on a series point is a validator that
    # `model_construct` on a *stream* walks past, which is E4-07's defeat one level
    # out (`docs/MISTAKES.md` entry 22) at a new depth.
    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    trend: list[TrendPoint]
    # A count per Likert value, keyed by the value as a string, with a zero for
    # every value nobody chose — E4-09's histogram draws five bars whatever the
    # week held.
    distribution: dict[str, int]
    summary: SummaryView | None
    comments: list[CommentView]
    # The wording of this stream's rating question, as the student answering it
    # read it. SPEC §3.2 stores question text in a versioned table, so this is
    # served rather than copied into the frontend: a second copy in the client is
    # correct exactly until the first re-versioning and wrong afterwards in a way
    # nobody looks for. Which version's wording a given week gets is
    # [ADR 0168](../../../docs/adr/0168-a-weeks-served-question-wording-comes-from-the-rows-its-responses-answered.md).
    #
    # Required rather than optional: the read has an answer for every week — the
    # wording the week's own responses answered, or the newest set's where nobody
    # answered — so there is no week with nothing to serve, and an optional member
    # is one a read can leave empty while the histogram quietly keeps its stream
    # label.
    question_text: str
    # SPEC §5.1's second and third lines for this panel — the comparison set's
    # series and the university-wide one, beside the section's own `trend` above.
    # Every figure in them is sealed by the item-7 chokepoint and re-checked by
    # the models in `app.schemas.report_benchmark`, which is also where the reason
    # those models are not declared in this file is written down.
    benchmark: report_benchmark.StreamBenchmark


class StreamsView(BaseModel):
    """The two groups §5.1 heads separately, never pooled into one."""

    # `revalidate_instances="always"`, for the reason `StreamReport` above gives:
    # this object sits between the report and the benchmark figures, and a level
    # on that path that does not ask to be re-validated is a level a caller can
    # build with `model_construct` to stop every validator below it running.
    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    instructor: StreamReport
    course: StreamReport


class WorkloadView(BaseModel):
    """SPEC §3.2's workload figure for this week, as `report_workload` aggregates it."""

    model_config = ConfigDict(frozen=True)

    mean: float | None
    median: float | None


class SmallNView(BaseModel):
    """Whether this week is under SPEC §4's n-threshold, and what that threshold is.

    Both, because E4-10 renders the reason as well as the state: a week showing no
    raw comments has to say why, and the number is the institution's configured
    one rather than a constant the frontend carries.
    """

    model_config = ConfigDict(frozen=True)

    suppressed: bool
    threshold: int


class InstructorReport(BaseModel):
    """One instructor's Monday report, for one of her own sections and one course week."""

    # **`revalidate_instances="always"` is SPEC §4.1 item 7's outermost layer, and
    # it is not a preference.** Without it a report *instance* handed to the
    # response is taken as already valid, so the field validator below never runs
    # over it — and `model_construct` and `model_copy(update=...)` build such an
    # instance without validating anything. E4-07's review re-pass demonstrated
    # both serving an unsuppressed figure with a 200. With it, whatever assembled
    # the object, the response re-reads it before anything is written to the wire.
    #
    # The cost is a second validation pass per report, paid on every request. That
    # is the price of the guarantee being about what is *shown* rather than about
    # how somebody built the thing shown.
    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    section: SectionView
    week: WeekView
    rates: RatesView
    streams: StreamsView
    workload: WorkloadView
    # §5.1's workload mean and median "against comparison-set and university
    # figures", beside the section's own pair above. Four sealed figures, each
    # suppressed on its own by the chokepoint.
    workload_benchmark: report_benchmark.WorkloadBenchmarkView
    # SPEC §4.1 item 7's chokepoint. The type is
    # `app.services.reporting.ComparisonFigure`, whose constructor demands a token
    # private to that module — which closes the direct door and, on its own, only
    # that one: a caller can produce an instance of any pydantic model without
    # calling its constructor. What makes this member trustworthy is the pair of
    # checks below it and above it — the validator on this field, and the
    # revalidation that guarantees the validator runs.
    comparison: ComparisonFigure
    small_n: SmallNView
    # ADR 0152's release, placed here and nowhere else: a list in every report,
    # populated only in the latest published week's, and carrying no week.
    released_from_earlier_weeks: list[CommentView]
    # The IANA name of the institution's zone, from `settings.institution_timezone`
    # — the same member the student payload carries, for the same reason. The
    # week's close instant above is rendered as a weekday and a wall-clock time,
    # which is only meaningful in a named zone; the zone is configuration the
    # server holds and the browser does not, so a payload carrying the instant
    # without the name cannot be rendered correctly by any client and would leave
    # the eyebrow formatting in whatever zone the reader's machine is set to.
    #
    # A declared divergence from E4's payload sketch, recorded in
    # `tests/unit/test_the_payload_sketch_and_the_schema_are_reconciled.py`.
    institution_timezone: str

    @field_validator("comparison")
    @classmethod
    def _the_comparison_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 at the wire — the inner half of a two-part boundary.

        A `mode="after"` field validator, which is what makes it the right place
        for its half: it runs on the value the field ends up holding, including a
        value that was already an instance of `ComparisonFigure` and therefore
        passed straight through the field's own type check. So a smuggled *figure*
        put into a report that is validated is caught here.

        **What it does not do on its own, stated because the first version of this
        docstring claimed otherwise.** It said "every route in this module serves a
        report by validating one of these models, so there is no way to a
        serialized payload that does not come through here", and that was false as
        written: a validator runs when a model is *validated*, and
        `InstructorReport.model_construct(...)` and
        `report.model_copy(update=...)` produce a report that no validator has
        seen. The review re-pass served an unsuppressed figure through both. What
        closes that is `revalidate_instances="always"` above, which makes the
        response re-validate whatever object it was handed — and that is what makes
        the sentence true rather than this validator's own placement.

        See `app.services.reporting.refuse_an_unsealed_comparison` for what is
        compared and why it is the field values rather than the token. The check
        stays here rather than moving into `ComparisonFigure` as a model validator
        for one reason: a model validator does not run for `model_construct`
        either, so it would be a second guard past the same doors.
        """
        refuse_an_unsealed_comparison(figure)
        return figure


class PublishedWeeks(BaseModel):
    """What the week-navigation route answers with: the course weeks a reader may page to.

    An object with one member rather than a bare array, so that a later addition —
    which week is current, say — is a member beside this one rather than a change
    of the response's own type. It carries the same list `InstructorReport.week`
    does and is derived by the same function, because two derivations of "which
    weeks may I read" is a reader paging to a week the report will not serve.
    """

    model_config = ConfigDict(frozen=True)

    published_weeks: list[int]


class TaughtSection(BaseModel):
    """One of the sections this session's person teaches, as her page lists it (E4-18).

    Three members and no fourth. The key is what every report route is asked with,
    the code is what a reader knows the class by, and the label is the same
    governed form `SectionView` above carries — composed by the one function in
    `app.services.reporting` that composes it, so a section cannot be named one way
    in the list and another way in the report the list opens.

    Nothing here says anything about the section beyond its name: no roster size,
    no rates, no week. This is a menu, and a figure on it would be a figure with no
    §4 suppression rule applied to it.
    """

    model_config = ConfigDict(frozen=True)

    section_id: UUID
    code: str
    course_label: str


class TaughtSections(BaseModel):
    """What the section-list route answers: the sections this reader may ask about.

    An object with one member rather than a bare array, for the reason
    `PublishedWeeks` above gives — a later addition is a member beside this one
    rather than a change of the response's own type.

    The list is empty for a person who teaches nothing and for a session that names
    nobody, and both are ordinary states rather than refusals: this route takes no
    parameter, so there is nothing in the request to refuse.
    """

    model_config = ConfigDict(frozen=True)

    sections: list[TaughtSection]
