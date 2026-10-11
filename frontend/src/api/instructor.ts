/**
 * The calls the instructor's Monday report is built on — SPEC §13's
 * `frontend/src/api/`, ticket E4-11.
 *
 * `GET /instructor/sections` (E4-18) answers the sections this session's person
 * teaches, `GET /instructor/sections/{id}/published-weeks` answers the course
 * weeks a report may be read for,
 * `GET /instructor/sections/{id}/report/{week}` answers SPEC §5.1's whole
 * report, and `POST /instructor/comments/{answer_id}/decisions` (E6-03)
 * records one moderation decision. `app.api.instructor` is the module all four
 * come from, and its
 * docstring is the authority on what each refuses and why.
 *
 * **The first call is what makes the other two askable.** Both keyed routes take
 * a section in the path and nothing this client holds supplies one: a launch
 * redirect carries the role and the session, and the session claims carry keys
 * and never sections. So the page reads the menu, and the pages behind it are
 * what a reader opens from it.
 *
 * **The calls are written by hand and not wrapped in a query cache** (ADR
 * 0117); **the wire types are generated** from the backend's OpenAPI document
 * (ADR 0185).
 *
 * **The session rides as a Bearer header** (ADR 0089, `../lib/session.ts`), for
 * the reason `student.ts` gives: the tool's cookie is `SameSite=None` and a
 * browser may refuse it inside the LMS's cross-site iframe, so the header is the
 * carrier that always works. The reads carry `readHeaders()`; the one write,
 * a moderation decision (SPEC §5.2), carries `writeHeaders()`, which echoes
 * the double-submit token the way the leadership pages' writes do.
 *
 * **Every type below is the wire's own**, aliased from `wire.gen.ts`, which
 * describes `backend/app/schemas/report.py`. Two departures from the generated
 * shape, both deliberate:
 *
 *   - **The top-level `comparison` is not here, and the benchmark members are**
 *     — ticket E5-10. SPEC §4.1 item 7's `comparison` member exists on the wire
 *     from day one so E5's benchmarks have a chokepoint to pass through, and the
 *     report page renders the benchmarks through `workload_benchmark` and the
 *     per-stream `benchmark` members below. The top-level member carries the
 *     same sealed figure `workload_benchmark.comparison.mean` carries
 *     (`app.schemas.report.InstructorReport`'s own docstring says so), so
 *     nothing reads it: a second reader of one figure is two places for one
 *     number to be rendered differently. A type with no member for it is the
 *     structural version of that rule — the same move `CommentCard` makes by
 *     having no prop for a timestamp — so no future edit can start reading it
 *     without saying so in this file.
 *   - **The members a later epic added to the payload may be absent** —
 *     `AddedLater` below. The server requires them; an answer cached before it
 *     wrote them, or a fixture built before then, has none, and the page
 *     renders without them rather than crashing.
 *
 * **The answers are cast rather than validated field by field**, and each cast
 * is bounded by one check: the member every render walks has to be there.
 * `student.ts` records the reasoning — the contract is generated from the same
 * pydantic models the server answers with, so re-deriving it here would be a
 * second statement of the same shape, and what a mismatch needs is to be loud
 * rather than re-parsed.
 */

import type { components } from './wire.gen';
import { jsonBody, readHeaders, refusalSentence, writeHeaders } from '../lib/http';

/** The generated wire schemas (ADR 0185); every wire type below is one of these. */
type Schemas = components['schemas'];

/**
 * `T` with the members `K` allowed to be absent.
 *
 * A member added to a live payload is required on the server and optional here:
 * an answer cached before the server wrote it, or a fixture built before then,
 * has none, and the page renders without it rather than crashing.
 */
type AddedLater<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

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
export type TaughtSectionView = Schemas['TaughtSection'];

/** What the section list answers. An empty list is a person who teaches nothing. */
export type TaughtSectionsView = Schemas['TaughtSections'];

/** What the week-navigation route answers: the course weeks a reader may page to. */
export type PublishedWeeksView = Schemas['PublishedWeeks'];

/** Which section this report is about, in the words its instructor knows it by. */
export type SectionView = Schemas['SectionView'];

/**
 * Where on SPEC §2.2's two axes this report sits, and where navigation may go.
 *
 * `closes_at` (E5-02) is the week's own close, read in `institution_timezone`
 * and never in the browser's zone; a report without it renders the eyebrow
 * without the note.
 */
export type WeekView = AddedLater<Schemas['WeekView'], 'closes_at'>;

/**
 * SPEC §5.1's two rates and the counts they are ratios of.
 *
 * **A rate with nothing behind it is `null` and never zero** — the schema's own
 * rule. A validity rate over no responses is not "all invalid" and a response
 * rate over an empty enrolment is not "nobody answered"; both are the absence of
 * a ratio, and the page renders the absence.
 */
export type RatesView = Schemas['RatesView'];

/**
 * One week of one stream's trend line.
 *
 * `mean` is `null` for a week nobody rated — zero is a rating nobody can give,
 * so a zero here would draw a line to the floor of a chart for a week that has
 * no line at all.
 */
export type TrendPointView = Schemas['TrendPoint'];

/**
 * One benchmark number, sealed — `app.services.reporting.ComparisonFigure`.
 *
 * **Every single benchmark figure on the wire is one of these**, and that is the
 * shape rather than a wrapper: SPEC §4.1 item 7 suppresses each figure computed
 * from a comparison set below the benchmark minimums, and the server decides it
 * per figure. `figure` is `None` on the server — `null` here — whenever
 * `suppressed` is true, because a value carrying both would be a suppressed
 * figure on the wire.
 *
 * `reason` is the server's one-word token (`"below-minimum"`) and nothing
 * renders it: a wire token is not a governed string, and the words a reader sees
 * come from the copy modules.
 *
 * The client casts this rather than parsing it, so every reader asks
 * `isShownFigure` (`../lib/shownFigure`), which wants `suppressed` to be exactly
 * `false` and `figure` a finite number before anything is shown.
 */
export type ComparisonFigureView = Schemas['ComparisonFigure'];

/**
 * One course week of one comparison series — `report_benchmark.BenchmarkSeriesPoint`.
 *
 * **A suppressed week is a point, not an absence.** Every course week the report
 * publishes is present here, and whether that week has a figure is what its own
 * `mean` says. There is no term week: a benchmark is past-referencing (SPEC
 * §5.1), so the figure behind one point spans several terms and has no single
 * term week to carry.
 */
export type BenchmarkSeriesPointView = Schemas['BenchmarkSeriesPoint'];

/**
 * One comparison population's trend — `report_benchmark.BenchmarkSeries`.
 *
 * **There is no series-level `suppressed` flag, and that is deliberate on the
 * server's side** (`app.schemas.report_benchmark`'s docstring carries the
 * argument): a flag over a series would be a statistic about a comparison set,
 * computed in the assembly layer, which is the one place no minimum was applied.
 * A series every one of whose weeks is suppressed is exactly that and nothing
 * more.
 */
export type BenchmarkSeriesView = Schemas['BenchmarkSeries'];

/** One stream's two comparison series — `report_benchmark.StreamBenchmark`. */
export type StreamBenchmarkView = Schemas['StreamBenchmark'];

/**
 * One comparison population's workload pair — `report_benchmark.WorkloadBenchmarkFigures`.
 *
 * **The mean and the median are sealed independently and neither rides on the
 * other's decision**, which is the server's rule and the reason there is no flag
 * over the pair.
 */
export type WorkloadBenchmarkFiguresView = Schemas['WorkloadBenchmarkFigures'];

/** The workload pair's two comparison columns — `report_benchmark.WorkloadBenchmarkView`. */
export type WorkloadBenchmarkView = Schemas['WorkloadBenchmarkView'];

/** §5.1's generated summary for one stream of one week, or absent on the stream. */
export type SummaryView = Schemas['SummaryView'];

/**
 * One comment: the comment service's three fields, and since E6-03 its handle
 * (`answer_id`), its flag class (`harmful`, `privacy` or null) and whether the
 * latest decision on it was the reader's (`decided_by_you`).
 *
 * No week, no timestamp, no author, no decider, no index, at any depth (SPEC §4,
 * ADRs 0153 and 0189).
 * `status` and `stream` are strings on the wire rather than closed sets, which
 * is what the schema says; the page narrows them where a component's prop needs
 * one, and says there what it does with a value it does not know.
 */
export type CommentView = Schemas['CommentView'];

/**
 * One of §5.1's two comment groups: its numbers, its summary and its words.
 *
 * `question_text` (E5-02) and `benchmark` (E5-05) may be absent. Without the
 * first the histogram keeps its stream-label title; without the second SPEC
 * §4.1 item 1 is why the stream renders no comparison at all rather than an
 * empty one.
 */
export type StreamReportView = AddedLater<Schemas['StreamReport'], 'question_text' | 'benchmark'>;

/** The two groups §5.1 heads separately, never pooled into one. */
export type StreamsView = {
  readonly [Stream in keyof Schemas['StreamsView']]: StreamReportView;
};

/** SPEC §3.2's workload figure for this week. Both members absent together. */
export type WorkloadView = Schemas['WorkloadView'];

/**
 * Whether one stream is under SPEC §4's threshold this week, and what that
 * threshold is. No count of anybody: the threshold is configuration (§5.2).
 */
export type SmallNView = Schemas['SmallNView'];

/** One instructor's Monday report, for one of her own sections and one course week. */
export type InstructorReportView = AddedLater<
  Omit<Schemas['InstructorReport'], 'comparison' | 'week' | 'streams'>,
  'workload_benchmark' | 'institution_timezone'
> & {
  readonly week: WeekView;
  readonly streams: StreamsView;
};

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

/** The sections this session's person teaches — the menu the other two need. */
export async function readTaughtSections(): Promise<SectionsRead> {
  let response: Response;
  try {
    response = await fetch(SECTIONS_PATH, { headers: readHeaders() });
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
    response = await fetch(publishedWeeksPath(sectionId), { headers: readHeaders() });
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
    response = await fetch(reportPath(sectionId, courseWeek), { headers: readHeaders() });
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

/** `app.api.instructor.DECISIONS_PATH`, with the comment's handle filled in. */
export function decisionsPath(answerId: string): string {
  return `/instructor/comments/${encodeURIComponent(answerId)}/decisions`;
}

/** What the instructor sends to exclude, keep or undo one comment (SPEC §5.2). */
export type CommentDecisionView = Schemas['CommentDecision'];

/**
 * What one decision answered.
 *
 * `decided` carries the comment's new card, which the page shows in place of the
 * old one: the server's card is the record of what was decided, so the page
 * does not guess at it before the answer arrives. `refused` carries the
 * server's sentence for a 404, a 409 or a 422 — each refusal is written once,
 * in `app.copy`, and shown as sent. `session-ended` and `unavailable` are the
 * reads' two, for the same reasons.
 */
export type DecisionOutcome =
  | { readonly kind: 'decided'; readonly card: CommentView }
  | { readonly kind: 'refused'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** One decision on one comment of the reader's report. A write, so it echoes the CSRF token. */
export async function decideOnComment(
  answerId: string,
  decision: CommentDecisionView,
): Promise<DecisionOutcome> {
  let response: Response;
  try {
    response = await fetch(decisionsPath(answerId), {
      method: 'POST',
      headers: writeHeaders(),
      body: JSON.stringify(decision),
    });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  const body = await jsonBody(response);
  if (response.status >= 400 && response.status < 500) {
    return { kind: 'refused', detail: refusalSentence(body) };
  }
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  // The bound on the cast: the card is rendered from its text and its status.
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  const card = body as Record<string, unknown>;
  if (typeof card.text !== 'string' || typeof card.status !== 'string') {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'decided', card: body as CommentView };
}
