import { useEffect, useRef, useState, type JSX } from 'react';

import { useNavigate, useParams, useSearch } from '@tanstack/react-router';

import {
  readInstructorReport,
  readPublishedWeeks,
  readTaughtSections,
  type CommentView,
  type InstructorReportView,
  type StreamReportView,
  type SummaryView,
  type TrendPointView,
} from '../../api/instructor';
import { CommentCard, type ReportComment } from '../../components/CommentCard';
import { CommentGroup } from '../../components/CommentGroup';
import { RatingHistogram, type RatingDistribution } from '../../components/RatingHistogram';
import { ResponseRateBar } from '../../components/ResponseRateBar';
import { StatPair } from '../../components/StatPair';
import { StateNotice } from '../../components/StateNotice';
import { TrendPair } from '../../components/TrendPair';
import type { TrendPoint } from '../../components/PulseTrendChart';
import { WeekEyebrow } from '../../components/WeekEyebrow';
import { WeekNav } from '../../components/WeekNav';
import { copy } from '../../copy/instructorReportPageCopy';
import '../../components/instructorReportPage.css';

/**
 * SPEC §7.6's `InstructorMondayReport` — ticket E4-11.
 *
 * The screen §5.1 describes, assembled out of the components E4-08, E4-09 and
 * E4-10 built and the payload E4-07 serves: the week's eyebrow, the section's
 * name, navigation across the published weeks, the stacked trend pair, both
 * rating distributions, the workload pair, the two participation rates, and the
 * two comment groups each led by its own summary.
 *
 * **Nothing here decides what may be shown.** SPEC §4's suppression, §4.1 item
 * 7's comparison chokepoint and §5.2's concealment all happen before this
 * request answers: a small-N week arrives with no comments in it, a comparison
 * figure arrives suppressed, and this page renders what it was given. The one
 * confidentiality decision that is genuinely this file's is which of the two
 * comment groups carries the small-N notice, and it is made once, out loud,
 * below. It is not §4.1 item 5's line: this surface's line is
 * `instructor_report_page.comments_note` (ADR 0158).
 *
 * **No week arithmetic anywhere, and that is criterion 3.** Which weeks a reader
 * may page to is `published_weeks` from the API, handed straight to `WeekNav`;
 * which week to open when the address names none is the last entry of that list;
 * and whether a week the address *does* name may be read is the API's answer to
 * asking for it. A section whose week 3 never published has a hole in that list,
 * and a page that stepped by one — or that checked membership itself before
 * asking — would be a second, worse copy of a rule the server already holds.
 *
 * **Two reads, in order, and a third only in one state.** The published weeks
 * first, because the report route takes a week and nothing this client holds
 * supplies one; then the report for the week that follows. The section list is
 * read only when the first answer is empty, so that a section before its first
 * Monday can still be named — which costs one request in the one state that has
 * nothing else to say, rather than a third round trip on every report.
 *
 * **The error state renders no report content, ever** (criterion 2). Every state
 * below the heading is exclusive: there is no branch in which a refusal's
 * sentence stands beside a chart, a rate or a comment, because the state the
 * page holds is one value and not a report plus a flag.
 */

/**
 * The landmark's testid, and it is E0-18's rather than a new one.
 *
 * Eight end-to-end specs assert `pulse-landing-instructor` is visible to say
 * that an instructor launch landed — `lti-launch`, `cookieless-launch`,
 * `two-hat`, `student-survey`, `exit-weekly-survey`, `exit-roster-auth`,
 * `exit-identity-merge`, `exit-refused-launches` and `exit-synced-section-dates`
 * among them, several through `tests/e2e/support/doors.ts`'s `ALL_LANDINGS`. The
 * instructor area is now two routes rather than one, so **both** carry it: an
 * instructor who teaches one section is replace-navigated straight to her
 * report, and a testid that stayed behind on the dispatcher would make "the
 * instructor landed" false for exactly the people the product is for. This is
 * the move E2-10 made when the survey replaced the student landing.
 */
export const INSTRUCTOR_LANDING_TESTID = 'pulse-landing-instructor';

/** Where a spec finds the report's own content, as opposed to one of its states. */
export const INSTRUCTOR_REPORT_TESTID = 'pulse-instructor-report';

/** Where a spec finds the one honest error state, whatever refused the read. */
export const INSTRUCTOR_REPORT_ERROR_TESTID = 'pulse-instructor-report-error';

const HEADING_ID = 'pulse-instructor-report-heading';

/** The route this page is served at, and the one `WeekNav` navigates within. */
export const REPORT_ROUTE = '/instructor/sections/$sectionId';

/**
 * Which address a set of reads was made for.
 *
 * An answer is shown only while the address it was read for is still the one on
 * screen; anything else is a report from the week before under this week's
 * heading.
 */
function requestKey(sectionId: string, week: number | null): string {
  return `${sectionId}#${week === null ? 'latest' : String(week)}`;
}

/** What the reads answered, as this screen holds it. */
type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  /** The API's refusal or a network failure — one state, carrying whichever sentence there is. */
  | { readonly kind: 'error'; readonly detail: string | null }
  /** A section before its first Monday, named if the section list could name it. */
  | { readonly kind: 'no-weeks'; readonly courseLabel: string | null }
  | { readonly kind: 'report'; readonly report: InstructorReportView };

/**
 * The report page, given the section and the week its address names.
 *
 * Props rather than router hooks, so that every state below can be driven
 * without a router and the URL behaviour is proven separately against a real
 * one. `week` is the validated search parameter — a positive integer, or `null`
 * where the address carried none or carried junk — and `onSelectWeek` is what
 * puts a chosen week in the address, which is what makes any week linkable
 * (criterion 6).
 */
export function InstructorMondayReport({
  sectionId,
  week,
  onSelectWeek,
}: {
  readonly sectionId: string;
  readonly week: number | null;
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  // **What was asked for, and what came back for it.** Loading is derived from
  // the two disagreeing rather than stored: a state written at the top of the
  // effect would be a second render for every address change, and — worse — the
  // window in which it has not run yet is a render showing the previous week's
  // report under the new week's address.
  const asking = requestKey(sectionId, week);
  const [answered, setAnswered] = useState<{ readonly to: string; readonly load: Load } | null>(
    null,
  );
  const load: Load =
    answered !== null && answered.to === asking ? answered.load : { kind: 'loading' };

  // Whether the week now being loaded is one the reader asked for, so that focus
  // moves to the heading when it arrives and not on the first paint of the page
  // (which would take focus off whatever the browser had just given it).
  const askedForAWeek = useRef(false);

  useEffect(() => {
    let live = true;
    const to = requestKey(sectionId, week);
    const setLoad = (next: Load): void => {
      setAnswered({ to, load: next });
    };

    void (async () => {
      const weeks = await readPublishedWeeks(sectionId);
      if (!live) return;
      if (weeks.kind === 'session-ended') {
        setLoad({ kind: 'session-ended' });
        return;
      }
      if (weeks.kind !== 'weeks') {
        setLoad({ kind: 'error', detail: weeks.detail });
        return;
      }

      // The list arrives ascending, so the latest published week is its last
      // entry. The address wins where it names one — including when it names a
      // week that is not on this list, which is answered by asking for it.
      const target = week ?? weeks.weeks.at(-1) ?? null;
      if (target === null) {
        const named = await readTaughtSections();
        if (!live) return;
        const courseLabel =
          named.kind === 'sections'
            ? (named.sections.find((section) => section.section_id === sectionId)?.course_label ??
              null)
            : null;
        setLoad({ kind: 'no-weeks', courseLabel });
        return;
      }

      const answer = await readInstructorReport(sectionId, target);
      if (!live) return;
      if (answer.kind === 'session-ended') {
        setLoad({ kind: 'session-ended' });
        return;
      }
      if (answer.kind !== 'report') {
        setLoad({ kind: 'error', detail: answer.detail });
        return;
      }
      setLoad({ kind: 'report', report: answer.report });
    })();

    return () => {
      live = false;
    };
  }, [sectionId, week]);

  useEffect(() => {
    if (answered === null || answered.load.kind !== 'report') return;
    if (!askedForAWeek.current) return;
    askedForAWeek.current = false;
    // SPEC §14.2 item 4's keyboard basics: paging to another week replaces
    // everything under the heading, and a reader whose focus stayed on a
    // navigation button would have no way of knowing what had arrived. The
    // heading takes focus because it is what names the thing that changed.
    document.getElementById(HEADING_ID)?.focus();
  }, [answered]);

  function selectWeek(next: number): void {
    askedForAWeek.current = true;
    onSelectWeek(next);
  }

  const report = load.kind === 'report' ? load.report : null;
  const heading =
    report?.section.course_label ??
    (load.kind === 'no-weeks' ? load.courseLabel : null) ??
    copy('instructor_report_page.heading');

  return (
    <main
      className="pulse-report"
      data-testid={INSTRUCTOR_LANDING_TESTID}
      aria-labelledby={HEADING_ID}
    >
      {report === null ? null : (
        <WeekEyebrow
          courseWeek={report.week.course_week}
          termWeek={report.week.term_week}
          lengthWeeks={report.section.length_weeks}
        />
      )}
      {/* Focusable but not in the tab order, so the week change below can put a
          reader on it without adding a stop nobody asked for. */}
      <h1 className="pulse-report-title" id={HEADING_ID} tabIndex={-1}>
        {heading}
      </h1>
      <PulseDivider />
      <ReportBody load={load} onSelectWeek={selectWeek} />
    </main>
  );
}

/** Whichever one of the page's states is true, and never two of them. */
function ReportBody({
  load,
  onSelectWeek,
}: {
  readonly load: Load;
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  if (load.kind === 'loading') {
    return (
      <p className="pulse-report-status" role="status">
        {copy('instructor_report_page.loading')}
      </p>
    );
  }
  if (load.kind === 'session-ended') {
    return (
      <StateNotice
        variant="flat"
        title={copy('instructor_report_page.session_ended_title')}
        body={copy('instructor_report_page.session_ended_body')}
      />
    );
  }
  if (load.kind === 'error') {
    return (
      <div data-testid={INSTRUCTOR_REPORT_ERROR_TESTID}>
        {/* The server's own sentence where there is one — `app.api.instructor`
            writes two, each chosen for what a reader may learn from a refusal,
            so this page shows what it was sent rather than deciding. Both are
            entries in `app.copy.instructor_report` and are swept there. This
            page's own line stands only where there was no answer to carry a
            sentence: a network failure, or a gateway in front of the tool. */}
        <StateNotice
          variant="flat"
          body={load.detail ?? copy('instructor_report_page.unavailable')}
        />
      </div>
    );
  }
  if (load.kind === 'no-weeks') {
    return (
      <StateNotice
        variant="flat"
        title={copy('instructor_report_page.no_published_weeks_title')}
        body={copy('instructor_report_page.no_published_weeks_body')}
      />
    );
  }

  return (
    // **Keyed by the week, so the whole region remounts when one is chosen.**
    // E4-10's residue: a comment carries no id — an id is a handle on one
    // student's words — so a card's key is its position in an array the server
    // randomized, and a flagged card left expanded would stay expanded over
    // whatever landed in that position next week. Remounting is what makes the
    // disclosure state belong to the week it was opened in.
    <div
      className="pulse-report-week"
      data-testid={INSTRUCTOR_REPORT_TESTID}
      key={load.report.week.course_week}
    >
      <WeekNav
        publishedWeeks={load.report.week.published_weeks}
        currentWeek={load.report.week.course_week}
        onSelectWeek={onSelectWeek}
      />
      <ReportWeek report={load.report} />
    </div>
  );
}

/** One published week of one section, in the order §5.1 and the prototype give it. */
function ReportWeek({ report }: { readonly report: InstructorReportView }): JSX.Element {
  const { rates, streams, small_n: smallN } = report;
  const suppressed = smallN.suppressed;

  return (
    <>
      <h2 className="pulse-report-heading">{copy('instructor_report_page.trend_heading')}</h2>
      <TrendPair
        instructor={trendOf(streams.instructor.trend)}
        course={trendOf(streams.course.trend)}
      />

      <h2 className="pulse-report-heading">{copy('instructor_report_page.ratings_heading')}</h2>
      <div className="pulse-report-histograms">
        <RatingHistogram stream="instructor" distribution={bucketsOf(streams.instructor)} />
        <RatingHistogram stream="course" distribution={bucketsOf(streams.course)} />
      </div>

      <h2 className="pulse-report-heading">{copy('instructor_report_page.workload_heading')}</h2>
      <StatPair median={report.workload.median} mean={report.workload.mean} />

      <h2 className="pulse-report-heading">
        {copy('instructor_report_page.participation_heading')}
      </h2>
      {rates.response_rate === null ? (
        // The schema's rule, rendered: a rate with nothing to be a rate of is
        // `null` and never zero, and a "0%" here would read as a verdict on a
        // week rather than as an empty enrolment.
        <p className="pulse-report-note">{copy('instructor_report_page.participation_absent')}</p>
      ) : (
        <ResponseRateBar
          response={{
            rate: rates.response_rate,
            numerator: rates.responses,
            denominator: rates.enrolled,
          }}
          validity={
            rates.validity_rate === null
              ? undefined
              : {
                  rate: rates.validity_rate,
                  numerator: rates.valid_responses,
                  denominator: rates.responses,
                }
          }
        />
      )}
      {/* The credit rule, in every week and not only the weeks with a rate to
          read it against: it explains SPEC §3.3's validity and §3.4's items
          rather than this week's figures, and a week nobody answered is a week
          an instructor most wants the rule for. It renders no score — v1 has no
          participation-score view anywhere — and E8 owes the student half. */}
      <p className="pulse-report-note">
        {copy('instructor_report_page.participation_credit_note')}
      </p>

      <h2 className="pulse-report-heading">{copy('instructor_report_page.comments_heading')}</h2>
      <p className="pulse-report-note">{copy('instructor_report_page.comments_note')}</p>
      {/* **One small-N notice for the week, and it is the page's decision.**
          SPEC §4's threshold suppresses a week and not a group, so both groups
          go quiet together and there is one fact to state: the first of them
          carries the notice and the second does not, because a page saying it
          twice would be reporting two suppressions where §5.2 has one. The
          instructor group is first everywhere in this product
          (`design/Usage Rules.md` §1), so it is the one that carries it.
          `CommentGroup` requires the field rather than defaulting it, which is
          what makes this a choice made out loud.

          **This is not SPEC §4.1 item 5's line.** Item 5 counts confidentiality
          copy once per surface, and this surface's one line is
          `instructor_report_page.comments_note` under the heading above: a
          standing promise about what an instructor is shown, where the small-N
          notice is a statement about how many people answered this week. The
          inventory recognises the first and deliberately not the second, so
          item 5 cannot pass or fail by the response count (ADR 0158). */}
      <CommentGroup
        stream="instructor"
        summary={summaryOf(streams.instructor.summary)}
        comments={cardsOf(streams.instructor.comments)}
        smallN={suppressed ? { threshold: smallN.threshold, withNotice: true } : undefined}
      />
      <CommentGroup
        stream="course"
        summary={summaryOf(streams.course.summary)}
        comments={cardsOf(streams.course.comments)}
        smallN={suppressed ? { threshold: smallN.threshold, withNotice: false } : undefined}
      />

      <ReleasedFromEarlierWeeks comments={report.released_from_earlier_weeks} />
    </>
  );
}

/**
 * ADR 0152's release, on the page SPEC §4 requires it to surface on.
 *
 * §4: comments from under-threshold weeks "are not discarded … and they surface
 * as raw text once the section's cumulative comment volume for the term crosses
 * the threshold, batched so that timing cannot identify an author". The payload
 * carries them in every report and populates them only in the latest published
 * week's, so this block is present exactly when there is something in it.
 *
 * **It names no week, no count and no timing** (ADR 0153): the release drops its
 * week precisely because the gradebook ledger would otherwise name the author,
 * and a heading that said "from weeks 1–3" or a line that said "four comments"
 * would put back at the assembly layer what the payload took out. What it does
 * say is that these are earlier weeks' words and not this week's figures, which
 * is the one thing a reader has to know to read them correctly.
 *
 * **The cards carry the stream chip**, which is what §7.6's "optional stream
 * chip, default off" exists for: this is the one list in the product that mixes
 * both streams, so a chip here names which question a comment answered rather
 * than repeating a heading above it.
 */
function ReleasedFromEarlierWeeks({
  comments,
}: {
  readonly comments: readonly CommentView[];
}): JSX.Element | null {
  if (comments.length === 0) return null;
  return (
    <section className="pulse-report-released">
      <h2 className="pulse-report-heading">{copy('instructor_report_page.released_heading')}</h2>
      <p className="pulse-report-note">{copy('instructor_report_page.released_body')}</p>
      <ul className="pulse-report-released-cards">
        {comments.map((comment, position) => (
          // The payload gives a comment no id, by design, so the key is its
          // position in the array the server randomized. It is not rendered.
          <li key={position}>
            <CommentCard
              text={comment.text}
              status={cardStatus(comment.status)}
              stream={cardStream(comment.stream)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The short marigold pulse line the brief puts under a report title. */
function PulseDivider(): JSX.Element {
  return (
    <svg
      className="pulse-line pulse-line-divider"
      width="120"
      height="14"
      viewBox="0 0 120 14"
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M1 10 H52 L60 3 L68 10 H106"
        stroke="var(--marigold)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="112" cy="10" r="3.5" fill="var(--marigold)" />
    </svg>
  );
}

/**
 * One stream's trend, in the shape the chart takes.
 *
 * **The term week is mapped and never derived.** SPEC §2.2 puts the term week on
 * every course-level axis and says why it cannot be computed from the course
 * week: a section that began in the term's fourth week, or paused over a break,
 * breaks any offset. E4-19 is the ticket putting the field on the wire; until it
 * merges the value arrives absent, and the sub-label says so rather than being
 * quietly filled from the number beside it.
 */
function trendOf(points: readonly TrendPointView[]): TrendPoint[] {
  return points.map((point) => ({
    courseWeek: point.course_week,
    termWeek: point.term_week,
    mean: point.mean,
  }));
}

/**
 * One stream's distribution, as the histogram's five declared members.
 *
 * The payload zero-fills every value nobody chose (`StreamReport.distribution`),
 * so a bucket that is missing here is a payload that did not, and the zero this
 * writes is the count the server would have sent. It is not a guess about a
 * count: a bucket cannot be absent *and* non-zero.
 */
function bucketsOf(stream: StreamReportView): RatingDistribution {
  const counts = stream.distribution;
  return {
    '1': counts['1'] ?? 0,
    '2': counts['2'] ?? 0,
    '3': counts['3'] ?? 0,
    '4': counts['4'] ?? 0,
    '5': counts['5'] ?? 0,
  };
}

/** One stream's summary in the group's shape, or `null` where none was written. */
function summaryOf(
  summary: SummaryView | null,
): { text: string; responseCount: number; heldNote: string | null } | null {
  if (summary === null) return null;
  return {
    text: summary.text,
    responseCount: summary.response_count,
    heldNote: summary.held_note,
  };
}

/** One stream's comments in the card's shape. */
function cardsOf(comments: readonly CommentView[]): ReportComment[] {
  return comments.map((comment) => ({ text: comment.text, status: cardStatus(comment.status) }));
}

/**
 * A comment's moderation status, narrowed to the three states the card draws.
 *
 * The wire types this as a string because `app.schemas.report` does; the
 * vocabulary is SPEC §5.2's lifecycle and `app.services.report_comments`
 * produces no fourth value. **A value this build does not know renders as the
 * plain card** — the comment's own words, with no moderation treatment on them.
 * The alternatives are worse in both directions: drawing it flagged or excluded
 * puts a verdict on a student's words that nothing recorded, and dropping it
 * takes a comment off an instructor's report without saying so. Suppression is
 * unaffected either way — a below-threshold week reaches `CommentGroup` with the
 * suppression already declared, and no card renders whatever this answers.
 */
function cardStatus(status: string): ReportComment['status'] {
  if (status === 'flagged' || status === 'excluded') return status;
  return 'published';
}

/** Which of §5.1's two questions a comment answered, where the chip is drawn. */
function cardStream(stream: string): 'instructor' | 'course' | undefined {
  if (stream === 'instructor' || stream === 'course') return stream;
  return undefined;
}

/**
 * The route glue: the address in, a navigation out, and nothing else.
 *
 * `sectionId` is the path parameter and `week` is the validated search one —
 * `router.tsx` holds the validation, because that is where the route is
 * declared. Choosing a week navigates rather than setting state, which is the
 * whole of criterion 6: the address is what says which week is open, so any week
 * a reader reaches is a week they can send to somebody.
 */
export function InstructorReportRoute(): JSX.Element {
  const { sectionId } = useParams({ from: REPORT_ROUTE });
  const { week } = useSearch({ from: REPORT_ROUTE });
  const navigate = useNavigate();

  return (
    <InstructorMondayReport
      sectionId={sectionId}
      week={week ?? null}
      onSelectWeek={(chosen) => {
        void navigate({ to: REPORT_ROUTE, params: { sectionId }, search: { week: chosen } });
      }}
    />
  );
}
