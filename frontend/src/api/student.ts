/**
 * The two calls the weekly survey screen makes — SPEC §13's `frontend/src/api/`.
 *
 * `GET /student/survey` (E2-09) answers the form's whole question — which
 * sections this reader is enrolled in today, which of them has a window open,
 * the questions to answer and what they have already submitted — and
 * `POST /student/submissions` (E2-08) is the weekly submission. Neither takes a
 * parameter naming a section, a person or a week that the reader could choose:
 * the read takes none at all, and the write names only a section the server then
 * checks the reader's own enrollment in.
 *
 * **Hand-written, not generated, and not wrapped in a query cache.** ADR 0117
 * records the decision and the alternatives; the short version is that this is
 * one screen with two calls and a generator plus a cache would be two
 * dependencies and a build step bought for it.
 *
 * **The session rides as a Bearer header** (ADR 0089, `../lib/session.ts`): the
 * launch door hands the token over in the URL fragment, the SPA lifts it into
 * `sessionStorage`, and every request here carries it. The tool's session cookie
 * is `SameSite=None` and a browser may refuse it inside the LMS's cross-site
 * iframe, so the header is the carrier that always works — and a request that
 * carries one is exempt from the write path's double-submit check by
 * construction, because no cross-site page can make a browser attach it.
 *
 * **A session that rides the cookie instead is not exempt, and until E2-17 this
 * file had no answer for it**: `csrf_verified_student` requires `X-Pulse-CSRF`
 * from a cookie carrier, nothing under `frontend/src` read `pulse_csrf`, and a
 * cookie-borne student could therefore read the survey and never submit it. Every
 * POST below carries the cookie's value when the cookie is readable — see
 * `requestHeaders`.
 *
 * **Every field below is the wire's spelling**, snake case included, because
 * these types describe `backend/app/schemas/student.py` and
 * `backend/app/schemas/survey.py` rather than a shape of this screen's choosing.
 * The three numeric columns arrive as **strings**: they are `Decimal` on the
 * server and pydantic writes a decimal to JSON as a string, which is the whole
 * point of the column type — half an hour is exactly half an hour and not
 * whatever a float rounds to.
 */

import { authorizationHeader } from '../lib/session';

/** Where the form reads from, and where it posts. `app.api.student`'s two paths. */
export const SURVEY_PATH = '/student/survey';
export const SUBMIT_PATH = '/student/submissions';

/** Which of SPEC §3.2's three answer shapes a question takes. */
export type QuestionKind = 'likert' | 'comment' | 'workload';

/** One question of the set in force, as the form has to render it (SPEC §3.2). */
export interface SurveyQuestion {
  readonly id: string;
  readonly position: number;
  readonly kind: QuestionKind;
  readonly name: string;
  /** The wording a person reads. Null for the questions §3.2 quotes none for. */
  readonly prompt: string | null;
  /** Position of the question whose answer can make this one required. */
  readonly required_if_position: number | null;
  /** This question is required when that answer is at most this value. */
  readonly required_if_at_most: number | null;
  readonly minimum_value: string | null;
  readonly maximum_value: string | null;
  readonly step: string | null;
}

/** One answer this reader already gave, in whichever of the three it holds. */
export interface SubmittedAnswer {
  readonly question_id: string;
  readonly rating: number | null;
  readonly comment_text: string | null;
  readonly workload_hours: string | null;
}

/** What this reader has already submitted for this week, if anything. */
export interface OwnSubmission {
  readonly first_submitted_at: string;
  readonly last_submitted_at: string;
  readonly answers: readonly SubmittedAnswer[];
}

/** The one survey open for a section right now (SPEC §3.1's one-open rule). */
export interface OpenSurvey {
  readonly window_id: string;
  readonly course_week: number;
  readonly term_week: number;
  readonly opens_at: string;
  readonly closes_at: string;
  readonly question_set_version: number;
  readonly questions: readonly SurveyQuestion[];
  readonly submission: OwnSubmission | null;
}

/** One section this reader is enrolled in today, and its survey state. */
export interface EnrolledSection {
  readonly section_id: string;
  readonly section_code: string;
  /**
   * The reader's own course, as a person names it:
   * "MATH 140 E1FF — College Algebra, Fall 2026".
   *
   * Composed on the server out of the prefix, number, section code, title and
   * term name of the course above *this* section (`app.services.survey_read`),
   * because §4.1 item 1 makes which course may be named a scoping question
   * rather than a formatting one. The heading renders the whole string, and the
   * order is the owner's ruling of 2026-09-03.
   */
  readonly course_label: string;
  readonly survey_is_open: boolean;
  /**
   * When this section's next survey opens, or null.
   *
   * Null both while a survey is open and when this section has no materialized
   * window ahead of it — the closed-state placeholder is dated on an instant and
   * plain on a null.
   */
  readonly next_window_opens_at: string | null;
  readonly open_survey: OpenSurvey | null;
}

/** Everything the form needs, in one answer. An empty list is between terms. */
export interface StudentSurveyView {
  readonly sections: readonly EnrolledSection[];
  /**
   * The IANA zone this deployment's survey windows are written in (SPEC §8).
   *
   * Deployment configuration rather than anything about the reader, and the zone
   * `next_window_opens_at` is rendered in: a browser handed an instant and no
   * zone renders it in its own, which would tell a student an hour their
   * institution does not keep.
   */
  readonly institution_timezone: string;
}

/**
 * One question of one submission, answered.
 *
 * Exactly one of the three value members is filled, and a question left blank is
 * an **absent entry** rather than one holding null — `app.schemas.survey` says
 * why: "the comment is blank" and "the required comment is missing" look the
 * same on the wire, and the difference between them is the rating beside it.
 */
export interface SubmittedValue {
  readonly position: number;
  readonly rating?: number;
  readonly comment_text?: string;
  readonly workload_hours?: string;
}

/** One student's answers to one section's open weekly survey. */
export interface SubmissionRequest {
  readonly section_id: string;
  readonly answers: readonly SubmittedValue[];
}

/**
 * What the read answered.
 *
 * **Three outcomes and not two, because "nothing is due" is a claim.** A 401 is
 * `session-ended`: the request carried no session this path would accept, so the
 * honest answer is that this page cannot say what is due and where to get a page
 * that can. It is emphatically *not* an empty week — the session a launch issues
 * lives an hour and a window stands open for days, so the ordinary way to meet
 * this is a student reloading yesterday's tab, and telling them "there is no
 * survey open for you yet" is an authoritative sentence about a question this
 * page was refused an answer to. The submit path never made that mistake; it
 * maps its own 401 to a refusal, and this is the read path catching up.
 *
 * `unavailable` is every other failed read, for the same reason narrowed: a read
 * that failed is not an empty week either, and saying so would be how a student
 * misses a survey they could have answered.
 */
export type SurveyRead =
  | { readonly kind: 'view'; readonly view: StudentSurveyView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable' };

/**
 * What the write answered.
 *
 * The four outcomes are `app.api.student`'s own status table, read from the
 * caller's side. A `bounced` carries SPEC §3.3's verdict and the coaching
 * sentence `app.copy.submit` serves with it; `closed` and `refused` carry the
 * server's sentence for the same reason — every one of them is governed copy
 * that lives on the server, and a second wording here would be a second
 * statement of a §4.1 string.
 *
 * **`closed` and `refused` differ in what the screen does with the form, and the
 * server's own sentences are what decide which is which.** The 409s all say the
 * submission cannot be stored as it stands — the window shut, the week is already
 * recorded, a judged comment cannot be withdrawn — so the form is taken away and
 * the sentence stands in its place. Everything else says the answers are still
 * worth keeping: `submit.classifier_down` says so in as many words ("Your answers
 * are still in the form, so nothing is lost"), and a form cleared underneath that
 * sentence would make it false.
 */
export type SubmitOutcome =
  | { readonly kind: 'stored' }
  | { readonly kind: 'bounced'; readonly verdict: string; readonly message: string }
  | { readonly kind: 'closed'; readonly message: string }
  | { readonly kind: 'refused'; readonly message: string };

/** SPEC §3.3's synchronous gate, as `app.api.student` answers it. */
const BOUNCED_STATUS = 422;
/** A closed window and a duplicate submission (SPEC §3.1, §8). */
const CONFLICT_STATUS = 409;
/** No student session on the request (`require_student`). */
const UNAUTHORIZED_STATUS = 401;

/**
 * The cookie the double-submit token rides in, and the header it is echoed in.
 *
 * `csrf_verified_student` (`app.api.deps`) requires the header from any request
 * whose session rides the cookie, and exempts the Bearer carrier — a Bearer
 * header is not something a cross-site form can be tricked into sending, so
 * there is nothing there for a double submit to protect. The cookie is
 * deliberately not `HttpOnly` (ADR 0089) for exactly this reason: this page has
 * to read it.
 */
const CSRF_COOKIE = 'pulse_csrf';
const CSRF_HEADER = 'X-Pulse-CSRF';

/** The headers one call here carries. */
function requestHeaders(method: 'GET' | 'POST'): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json', ...authorizationHeader() };
  if (method === 'GET') return headers;
  headers['Content-Type'] = 'application/json';
  // **Every POST, whenever the cookie is readable, and no POST when it is not.**
  // A cookie-borne session could read this survey and never submit it before
  // E2-17: the SPA never read `pulse_csrf` at all, so the one action the screen
  // exists for arrived as a 403. Sending a value the cookie did not supply would
  // be worse than sending nothing — a double submit the server cannot compare is
  // a check that verifies nothing — and withholding the request itself would
  // lock every student in the LMS iframe out, where the session rides Bearer and
  // the browser refuses the tool's cookies anyway.
  const token = readCookie(CSRF_COOKIE);
  if (token !== null) headers[CSRF_HEADER] = token;
  return headers;
}

/**
 * One cookie's value as this document can read it, or `null`.
 *
 * Written out rather than pattern-matched: a name is compared whole, so
 * `pulse_csrf` is not answered by a cookie called `not_pulse_csrf`, and a value
 * carrying `=` keeps everything after the first one.
 */
function readCookie(name: string): string | null {
  for (const pair of document.cookie.split(';')) {
    const at = pair.indexOf('=');
    if (at < 0) continue;
    if (pair.slice(0, at).trim() !== name) continue;
    return decodeURIComponent(pair.slice(at + 1).trim());
  }
  return null;
}

/**
 * `detail` out of an error body, when it is a sentence.
 *
 * FastAPI answers a refusal with `{"detail": …}`, and this route serves two
 * shapes under that name: a **string** for every refusal, which is one of
 * `app.copy`'s sentences, and an **object** `{verdict, message}` for §3.3's
 * bounce. They are told apart by type rather than by status, because 422 is also
 * the status three value refusals carry and those carry a string.
 */
function refusalSentence(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null;
  const detail = (body as Record<string, unknown>).detail;
  return typeof detail === 'string' ? detail : null;
}

/** The bounce's verdict and coaching sentence, when the body is one. */
function bounceDetail(body: unknown): { verdict: string; message: string } | null {
  if (typeof body !== 'object' || body === null) return null;
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail !== 'object' || detail === null) return null;
  const { verdict, message } = detail as Record<string, unknown>;
  if (typeof verdict !== 'string' || typeof message !== 'string') return null;
  return { verdict, message };
}

/** A response's JSON body, or `null` when it did not carry one. */
async function jsonBody(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

/**
 * This reader's enrollments and the survey open for each.
 *
 * **The answer is cast rather than validated field by field**, and the cast is
 * bounded by the one check below: `sections` has to be an array, because that is
 * the member every render walks and a body without it would fail somewhere
 * deeper with nothing to say. The contract is generated from the same pydantic
 * models the server answers with (SPEC §7.6's OpenAPI document), so re-deriving
 * it here would be a second statement of the same shape — what a mismatch needs
 * is to be loud, not to be re-parsed.
 */
export async function readStudentSurvey(): Promise<SurveyRead> {
  let response: Response;
  try {
    response = await fetch(SURVEY_PATH, { headers: requestHeaders('GET') });
  } catch {
    return { kind: 'unavailable' };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (!response.ok) return { kind: 'unavailable' };

  const body = await jsonBody(response);
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable' };
  if (!Array.isArray((body as Record<string, unknown>).sections)) return { kind: 'unavailable' };
  return { kind: 'view', view: body as StudentSurveyView };
}

/**
 * Submit one section's open weekly survey.
 *
 * Every non-2xx answer is turned into an outcome carrying the server's own
 * sentence. Nothing here decides what a refusal *means* beyond which of the four
 * shapes it is: the status table is `app.api.student`'s, the words are
 * `app.copy`'s, and this screen's job is to show them where the student is
 * standing.
 */
export async function submitWeeklySurvey(
  submission: SubmissionRequest,
  fallbackMessage: string,
): Promise<SubmitOutcome> {
  let response: Response;
  try {
    response = await fetch(SUBMIT_PATH, {
      method: 'POST',
      headers: requestHeaders('POST'),
      body: JSON.stringify(submission),
    });
  } catch {
    return { kind: 'refused', message: fallbackMessage };
  }

  if (response.ok) return { kind: 'stored' };

  const body = await jsonBody(response);

  if (response.status === BOUNCED_STATUS) {
    const bounce = bounceDetail(body);
    if (bounce !== null) return { kind: 'bounced', ...bounce };
  }

  const sentence = refusalSentence(body) ?? fallbackMessage;
  if (response.status === CONFLICT_STATUS) return { kind: 'closed', message: sentence };
  return { kind: 'refused', message: sentence };
}
