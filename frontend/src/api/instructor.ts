/**
 * The three calls the instructor's Monday report is built on — SPEC §13's
 * `frontend/src/api/`, ticket E4-11.
 *
 * `GET /instructor/sections` (E4-18) answers the sections this session's person
 * teaches, `GET /instructor/sections/{id}/published-weeks` answers the course
 * weeks a report may be read for, and
 * `GET /instructor/sections/{id}/report/{week}` answers SPEC §5.1's whole
 * report. `app.api.instructor` is the module all three come from, and its
 * docstring is the authority on what each refuses and why.
 *
 * **The first call is what makes the other two askable.** Both keyed routes take
 * a section in the path and nothing this client holds supplies one: a launch
 * redirect carries the role and the session, and the session claims carry keys
 * and never sections. So the page reads the menu, and the pages behind it are
 * what a reader opens from it.
 *
 * **Hand-written, not generated, and not wrapped in a query cache** — ADR 0117,
 * unchanged. This is a second screen with three calls, and a generator plus a
 * cache would still be two dependencies and a build step bought for it.
 *
 * **The session rides as a Bearer header** (ADR 0089, `../lib/session.ts`), for
 * the reason `student.ts` gives: the tool's cookie is `SameSite=None` and a
 * browser may refuse it inside the LMS's cross-site iframe, so the header is the
 * carrier that always works. Every call here is a GET, so there is no
 * double-submit token to echo and no cookie to read — the whole of the write
 * path's CSRF machinery in `student.ts` is deliberately absent rather than
 * copied.
 *
 * **Every field below is the wire's spelling**, snake case included, because
 * these types describe `backend/app/schemas/report.py` rather than a shape of
 * this screen's choosing. Two departures from "mirror it field for field", both
 * deliberate:
 *
 *   - **`comparison` is not here.** SPEC §4.1 item 7's member exists on the wire
 *     from day one so E5's benchmarks have a chokepoint to pass through, and
 *     nothing in E4 may render a comparison figure. A type with no member for it
 *     is the structural version of that rule — the same move `CommentCard` makes
 *     by having no prop for a timestamp — so no future edit can start reading it
 *     without saying so in this file.
 *   - **`term_week` is on `TrendPointView` before the wire carries it.** SPEC
 *     §2.2 puts both week axes on every course-level chart and `PulseTrendChart`
 *     renders both; E4-19 is adding the field to `report.TrendPoint` in
 *     parallel. It is typed here now because the alternative is deriving it in
 *     the browser, which §2.2 and E4-08 both refuse. Until that ticket merges,
 *     the field arrives absent and the chart's term sub-label reads as such —
 *     loudly, which is the wanted failure.
 *
 * **The answers are cast rather than validated field by field**, and each cast
 * is bounded by one check: the member every render walks has to be there.
 * `student.ts` records the reasoning — the contract is generated from the same
 * pydantic models the server answers with, so re-deriving it here would be a
 * second statement of the same shape, and what a mismatch needs is to be loud
 * rather than re-parsed.
 */

import { authorizationHeader } from '../lib/session';

/** `app.api.instructor.SECTIONS_PATH` — the menu, which takes no parameter. */
export const SECTIONS_PATH = '/instructor/sections';

/** `app.api.instructor.PUBLISHED_WEEKS_PATH`, with the section filled in. */
export function publishedWeeksPath(sectionId: string): string {
  return `${SECTIONS_PATH}/${encodeURIComponent(sectionId)}/published-weeks`;
}

/** `app.api.instructor.REPORT_PATH`, with the section and the course week filled in. */
export function reportPath(sectionId: string, courseWeek: number): string {
  return `${SECTIONS_PATH}/${encodeURIComponent(sectionId)}/report/${String(courseWeek)}`;
}

/** One of the sections this reader teaches, as `TaughtSection` carries it. */
export interface TaughtSectionView {
  readonly section_id: string;
  readonly code: string;
  /** The governed label the student's own page carries, composed on the server. */
  readonly course_label: string;
}

/** What the section list answers. An empty list is a person who teaches nothing. */
export interface TaughtSectionsView {
  readonly sections: readonly TaughtSectionView[];
}

/** What the week-navigation route answers: the course weeks a reader may page to. */
export interface PublishedWeeksView {
  /** Ascending, and exactly the weeks whose survey window has closed. */
  readonly published_weeks: readonly number[];
}

/** Which section this report is about, in the words its instructor knows it by. */
export interface SectionView {
  readonly code: string;
  readonly course_label: string;
  readonly length_weeks: number;
}

/** Where on SPEC §2.2's two axes this report sits, and where navigation may go. */
export interface WeekView {
  readonly course_week: number;
  readonly term_week: number;
  readonly published_weeks: readonly number[];
}

/**
 * SPEC §5.1's two rates and the counts they are ratios of.
 *
 * **A rate with nothing behind it is `null` and never zero** — the schema's own
 * rule. A validity rate over no responses is not "all invalid" and a response
 * rate over an empty enrolment is not "nobody answered"; both are the absence of
 * a ratio, and the page renders the absence.
 */
export interface RatesView {
  readonly response_rate: number | null;
  readonly validity_rate: number | null;
  readonly responses: number;
  readonly enrolled: number;
  readonly valid_responses: number;
}

/**
 * One week of one stream's trend line.
 *
 * `mean` is `null` for a week nobody rated — zero is a rating nobody can give,
 * so a zero here would draw a line to the floor of a chart for a week that has
 * no line at all. `term_week` is E4-19's field; see this module's header.
 */
export interface TrendPointView {
  readonly course_week: number;
  readonly term_week: number;
  readonly mean: number | null;
}

/** §5.1's generated summary for one stream of one week, or absent on the stream. */
export interface SummaryView {
  readonly text: string;
  readonly response_count: number;
  /** ADR 0148's held-note type. Null in every E4 payload; E6 populates it. */
  readonly held_note: string | null;
}

/**
 * One comment, with exactly the three fields the comment service answers with.
 *
 * No week, no timestamp, no author, no index, at any depth (SPEC §4, ADR 0153).
 * `status` and `stream` are strings on the wire rather than closed sets, which
 * is what the schema says; the page narrows them where a component's prop needs
 * one, and says there what it does with a value it does not know.
 */
export interface CommentView {
  readonly text: string;
  readonly status: string;
  readonly stream: string;
}

/** One of §5.1's two comment groups: its numbers, its summary and its words. */
export interface StreamReportView {
  readonly trend: readonly TrendPointView[];
  /**
   * A count per Likert value, keyed by the value as a string.
   *
   * `dict[str, int]` on the wire, zero-filled by the server for every value
   * nobody chose. Typed as the wire types it rather than as the histogram's
   * five declared members, so the narrowing happens once, in the page, where a
   * missing bucket can be said out loud.
   */
  readonly distribution: Readonly<Record<string, number>>;
  readonly summary: SummaryView | null;
  readonly comments: readonly CommentView[];
}

/** The two groups §5.1 heads separately, never pooled into one. */
export interface StreamsView {
  readonly instructor: StreamReportView;
  readonly course: StreamReportView;
}

/** SPEC §3.2's workload figure for this week. Both members absent together. */
export interface WorkloadView {
  readonly mean: number | null;
  readonly median: number | null;
}

/** Whether this week is under SPEC §4's threshold, and what that threshold is. */
export interface SmallNView {
  readonly suppressed: boolean;
  readonly threshold: number;
}

/** One instructor's Monday report, for one of her own sections and one course week. */
export interface InstructorReportView {
  readonly section: SectionView;
  readonly week: WeekView;
  readonly rates: RatesView;
  readonly streams: StreamsView;
  readonly workload: WorkloadView;
  readonly small_n: SmallNView;
  /**
   * ADR 0152's release: comments from earlier weeks that crossed the cumulative
   * threshold, carrying no week anywhere (ADR 0153).
   *
   * A list in every report, populated only in the latest published week's.
   */
  readonly released_from_earlier_weeks: readonly CommentView[];
}

/**
 * What a read of the report answered.
 *
 * **Four outcomes, and the reason each is its own.** `report` is the answer.
 * `session-ended` is a 401: the request carried no session this path would
 * accept, so the page cannot say anything about a week and says which page can
 * — `student.ts` records why collapsing that into an empty state is the quiet
 * mistake, and the same argument holds here. `not-found` is the server refusing
 * to answer for this section or this week, and it carries the server's own
 * sentence: `app.api.instructor` writes two of them, and a second wording here
 * would be a second statement of the same refusal for the two to drift apart in.
 * Both are entries in `app.copy.instructor_report` since E4-12, so both are
 * collected and swept where they are written. `unavailable` is
 * every other failure, including a network one, where there may be no sentence
 * at all and the page falls back to its own.
 *
 * A 404 and a 422 are the same outcome on purpose. The route's 404 is the
 * refusal pair — a section this reader does not teach and a section that does
 * not exist, answered identically so a reader cannot enumerate the institution's
 * sections — and its 422 is FastAPI refusing a path parameter that is not a uuid
 * or not an integer. Both mean the address names no report, and telling them
 * apart on screen would be this page explaining the shape of a URL to somebody
 * who did not type one.
 */
export type ReportRead =
  | { readonly kind: 'report'; readonly report: InstructorReportView }
  | { readonly kind: 'not-found'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of the published weeks answered. The same four, for the same reasons. */
export type PublishedWeeksRead =
  | { readonly kind: 'weeks'; readonly weeks: readonly number[] }
  | { readonly kind: 'not-found'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/**
 * What a read of the section list answered.
 *
 * **Three outcomes rather than four, and the missing one is the API's own
 * shape.** `app.api.instructor`'s section list "has no refusal of either kind,
 * and that is not an omission": it takes no parameter, so there is nothing in
 * the request to refuse, and a person who teaches nothing is answered 200 with
 * an empty list. A `not-found` variant here would be a state nothing can reach
 * and a branch no test could drive.
 */
export type SectionsRead =
  | { readonly kind: 'sections'; readonly sections: readonly TaughtSectionView[] }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** No instructor session on the request (`require_instructor`). */
const UNAUTHORIZED_STATUS = 401;

/** The refusal pair, and the week there is no published report for. */
const NOT_FOUND_STATUS = 404;

/** A path parameter FastAPI would not parse — not a uuid, or not an integer. */
const UNPROCESSABLE_STATUS = 422;

/** The headers one call here carries. Every one of them is a read. */
function requestHeaders(): Record<string, string> {
  return { Accept: 'application/json', ...authorizationHeader() };
}

/**
 * A response's JSON body, or `null` when it did not carry one.
 *
 * Written here rather than imported from `student.ts`: that module's copy is
 * private to the screen it serves, and exporting a five-line helper out of one
 * screen's client so another can share it would put two screens in one blast
 * radius for no measured gain. What must not be duplicated is a *decision*, and
 * every decision this file makes about a refusal is written in the outcome types
 * above.
 */
async function jsonBody(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

/**
 * `detail` out of an error body, when it is a sentence.
 *
 * FastAPI answers a refusal with `{"detail": …}`, and every refusal these three
 * routes serve carries a **string** there — one of `app.api.instructor`'s two
 * governed sentences. FastAPI's own 422 carries a list of validation objects
 * instead, which is not a sentence anybody wrote for a reader, so it is answered
 * `null` here and the page uses its own words.
 */
function refusalSentence(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null;
  const detail = (body as Record<string, unknown>).detail;
  return typeof detail === 'string' ? detail : null;
}

/** The sections this session's person teaches — the menu the other two need. */
export async function readTaughtSections(): Promise<SectionsRead> {
  let response: Response;
  try {
    response = await fetch(SECTIONS_PATH, { headers: requestHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  // The bound on the cast: `sections` is the member every render walks, and a
  // body without it would fail somewhere deeper with nothing to say.
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).sections)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'sections', sections: (body as TaughtSectionsView).sections };
}

/** The course weeks one of this reader's own sections may be asked about. */
export async function readPublishedWeeks(sectionId: string): Promise<PublishedWeeksRead> {
  let response: Response;
  try {
    response = await fetch(publishedWeeksPath(sectionId), { headers: requestHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  const body = await jsonBody(response);
  if (response.status === NOT_FOUND_STATUS || response.status === UNPROCESSABLE_STATUS) {
    return { kind: 'not-found', detail: refusalSentence(body) };
  }
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).published_weeks)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'weeks', weeks: (body as PublishedWeeksView).published_weeks };
}

/** SPEC §5.1's whole report, for one of this reader's sections and one course week. */
export async function readInstructorReport(
  sectionId: string,
  courseWeek: number,
): Promise<ReportRead> {
  let response: Response;
  try {
    response = await fetch(reportPath(sectionId, courseWeek), { headers: requestHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  const body = await jsonBody(response);
  if (response.status === NOT_FOUND_STATUS || response.status === UNPROCESSABLE_STATUS) {
    return { kind: 'not-found', detail: refusalSentence(body) };
  }
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  // The bound on this cast is `streams`, which every part of the assembly below
  // the heading walks — the trend pair, both histograms and both comment groups.
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  const streams = (body as Record<string, unknown>).streams;
  if (typeof streams !== 'object' || streams === null) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'report', report: body as InstructorReportView };
}
