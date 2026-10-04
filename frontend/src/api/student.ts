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
 * **The calls are written by hand and not wrapped in a query cache** (ADR
 * 0117); **the wire types are generated** from the backend's OpenAPI document
 * (ADR 0185), so a renamed or added member fails a check rather than going
 * stale here silently.
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
 * `writeHeaders` in `../lib/http`, which spreads `csrfHeader()` from
 * `../lib/session`.
 *
 * **Every type below is the wire's own**, snake case included, aliased from
 * `wire.gen.ts`, which describes `backend/app/schemas/student.py` and
 * `backend/app/schemas/survey.py`. The three numeric columns arrive as
 * **strings**: they are `Decimal` on the
 * server and pydantic writes a decimal to JSON as a string, which is the whole
 * point of the column type — half an hour is exactly half an hour and not
 * whatever a float rounds to.
 */

import type { components } from './wire.gen';
import { jsonBody, readHeaders, refusalSentence, writeHeaders } from '../lib/http';

/** The generated wire schemas (ADR 0185); every wire type below is one of these. */
type Schemas = components['schemas'];

/** Where the form reads from, and where it posts. `app.api.student`'s two paths. */
export const SURVEY_PATH = '/student/survey';
export const SUBMIT_PATH = '/student/submissions';

/** Which of SPEC §3.2's three answer shapes a question takes. */
export type QuestionKind = Schemas['QuestionKind'];

/** One question of the set in force, as the form has to render it (SPEC §3.2). */
export type SurveyQuestion = Schemas['SurveyQuestion'];

/** One answer this reader already gave, in whichever of the three it holds. */
export type SubmittedAnswer = Schemas['SubmittedAnswer-Output'];

/** What this reader has already submitted for this week, if anything. */
export type OwnSubmission = Schemas['OwnSubmission'];

/** The one survey open for a section right now (SPEC §3.1's one-open rule). */
export type OpenSurvey = Schemas['OpenSurvey'];

/** One section this reader is enrolled in today, and its survey state. */
export type EnrolledSection = Schemas['EnrolledSection'];

/** Everything the form needs, in one answer. An empty list is between terms. */
export type StudentSurveyView = Schemas['StudentSurveyView'];

/**
 * One question of one submission, answered.
 *
 * Exactly one of the three value members is filled, and a question left blank is
 * an **absent entry** rather than one holding null — `app.schemas.survey` says
 * why: "the comment is blank" and "the required comment is missing" look the
 * same on the wire, and the difference between them is the rating beside it.
 */
export type SubmittedValue = Schemas['SubmittedAnswer-Input'];

/** One student's answers to one section's open weekly survey. */
export type SubmissionRequest = Schemas['SubmissionRequest'];

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

/** The bounce's verdict and coaching sentence, when the body is one. */
function bounceDetail(body: unknown): { verdict: string; message: string } | null {
  if (typeof body !== 'object' || body === null) return null;
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail !== 'object' || detail === null) return null;
  const { verdict, message } = detail as Record<string, unknown>;
  if (typeof verdict !== 'string' || typeof message !== 'string') return null;
  return { verdict, message };
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
    response = await fetch(SURVEY_PATH, { headers: readHeaders() });
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
      headers: writeHeaders(),
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
