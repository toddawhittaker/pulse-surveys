/**
 * The calls the leadership pages make — SPEC §13's `frontend/src/api/`: seven
 * for the comparison-set management screen (SPEC §5.1), and three for the
 * moderation review queue and exclusion log (SPEC §5.2), at the foot of the file.
 *
 * `api/leadership.py` (E5-06) serves SPEC §5.1's named sets: a list, a create, a
 * read, an edit, a delete, the closed choice lists the form is built from, and
 * the preview that says what a set reaches. This module is the client half, and
 * it is the third in this directory rather than a growth of either of the other
 * two: `instructor.ts` reads one instructor's own report and `student.ts` is one
 * student's survey, and neither has anything to say about a leadership surface.
 *
 * **The calls are written by hand and not wrapped in a query cache** (ADR
 * 0117): ten calls with no shared cache key between them. **The wire types
 * are generated** from the backend's OpenAPI document (ADR 0185).
 *
 * **The session rides as a Bearer header** (ADR 0089, `../lib/session.ts`), and
 * **every write echoes the double-submit cookie** through `csrfHeader()`. This
 * is the first client in this directory with writes other than the student's
 * submission, which is why that reader moved out of `student.ts` and up into
 * `lib/session.ts` rather than being copied here (`docs/MISTAKES.md` entry 13).
 *
 * **What checks that echo is `csrf_verified_leadership`** (`api/deps.py`,
 * E5-06), which every writing route below declares and no reading route
 * does.
 *
 * **Every type below is the wire's own**, snake case included, aliased from
 * `wire.gen.ts`, which describes E5-06's Pydantic schemas.
 *
 * **Two refusals are the page's own words, not the server's** (E7-08, ADR
 * 0196): a 401 is `session-ended`, and the leadership gate's 403 for a real
 * session in another role is `not-your-role`, on every call. The pages say "not
 * part of your role" for the second, where they once said the session had ended.
 *
 * **Every other refusal is shown, never re-derived.** SPEC §5.1 puts the rules about which
 * length and level may be combined, who may edit a set and what a duplicate name
 * means on the server; `api/leadership.py` answers each with one sentence under
 * `detail`, and the screen renders the sentence it was sent. The form makes the
 * invalid combinations unreachable for a person using it — that is §5.1's "makes
 * invalid combinations impossible rather than erroring on them" — and the
 * refusals stay reachable by the races a form cannot prevent: a course that left
 * the catalogue while the form was open, a name somebody else took first.
 */

import type { components } from './wire.gen';
import { jsonBody, readHeaders, refusalSentence, writeHeaders } from '../lib/http';
import type {
  CheckThemeView,
  DraftCheckOutcome,
  InstructorReportView,
  PublishedWeeksRead,
  ReportRead,
  ResponseDraftOutcome,
  ResponseWriteOutcome,
  ResponseWriteView,
} from './instructor';
import { responseCall, weekResponseOf } from './instructor';

/** The generated wire schemas (ADR 0185); every wire type below is one of these. */
type Schemas = components['schemas'];

/** `app.api.leadership.COMPARISON_SETS_PATH` — the list, and the create. */
export const COMPARISON_SETS_PATH = '/leadership/comparison-sets';

/** The closed choice lists the form is built from. */
export const COMPARISON_SET_OPTIONS_PATH = `${COMPARISON_SETS_PATH}/options`;

/** One set: the read, the edit and the delete all address it. */
export function comparisonSetPath(setId: string): string {
  return `${COMPARISON_SETS_PATH}/${encodeURIComponent(setId)}`;
}

/** What one set reaches: its member count and its resolved section count. */
export function comparisonSetPreviewPath(setId: string): string {
  return `${comparisonSetPath(setId)}/preview`;
}

/** One course the form may offer, in the level band that decides where it appears. */
export type ComparisonSetCourseView = Schemas['CourseOption'];

/**
 * The closed sets the form offers, and nothing else.
 *
 * **This is the only source of the lengths and the levels.** The lengths are
 * the distinct lengths the institution's sections run, read from its data, and
 * §8 owns the five level bands; both live on the server's side of the wire. A
 * list written into a component would be a second copy that is right until the
 * first section that runs a new length —
 * the two-currencies defect this ticket's trap section names — so the form
 * renders what this answer carries and has no opinion about what it should have
 * carried.
 */
export type ComparisonSetOptionsView = Schemas['SetOptions'];

/** One set as the list carries it. */
export type ComparisonSetSummaryView = Schemas['SetSummary'];

/** One set with its membership, as the read and both writes answer. */
export type ComparisonSetDetailView = Schemas['SetDetail'];

/** What a create or an edit sends. */
export type ComparisonSetWrite = Schemas['SetWrite'];

/**
 * What a set reaches: its member count and its resolved section count.
 *
 * The list's line still says the section count is not known when an answer
 * arrives without one, because the answer is cast rather than parsed.
 */
export type ComparisonSetPreviewView = Schemas['SetPreview'];

/** What a read of the set list answered. */
export type ComparisonSetsRead =
  | { readonly kind: 'sets'; readonly sets: readonly ComparisonSetSummaryView[] }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of the choice lists answered. */
export type ComparisonSetOptionsRead =
  | { readonly kind: 'options'; readonly options: ComparisonSetOptionsView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of one set answered. */
export type ComparisonSetRead =
  | { readonly kind: 'set'; readonly set: ComparisonSetDetailView }
  | { readonly kind: 'not-found'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of one set's preview answered. */
export type ComparisonSetPreviewRead =
  | { readonly kind: 'preview'; readonly preview: ComparisonSetPreviewView }
  | { readonly kind: 'not-found'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/**
 * What a create or an edit answered.
 *
 * **The four refusals are one outcome on purpose.** A duplicate name, a set this
 * person may not edit, a set that is not there and a member the server will not
 * accept are 409, 403, 404 and 422, and each carries its own sentence. The
 * screen shows the sentence; it does not tell the four apart, because telling
 * them apart would mean holding a second copy of the rules that decide them.
 */
export type ComparisonSetWriteOutcome =
  | { readonly kind: 'saved'; readonly set: ComparisonSetDetailView }
  | { readonly kind: 'refused'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a delete answered. The same shape, with nothing to carry back. */
export type ComparisonSetDeleteOutcome =
  | { readonly kind: 'deleted' }
  | { readonly kind: 'refused'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** No session the server could verify (`require_leadership`): the session ended. */
const UNAUTHORIZED_STATUS = 401;

/**
 * A real session in another role (`require_leadership`, E7-08, ADR 0196).
 *
 * **The status alone does not say it.** These routes answer 403 for other
 * reasons too — a leader with no review grant, another leader's set on a
 * write, a write without its double-submit token — and each of those carries
 * its own sentence for the page to show. Only the gate's 403 carries RFC 6750's
 * `insufficient_scope` challenge, so that is what this reads. A page that read
 * every 403 as "not your role" would tell a dean with no review queue that the
 * page is not part of their role, which ADR 0190 answers differently.
 */
const FORBIDDEN_STATUS = 403;
const NOT_YOUR_ROLE_CHALLENGE = 'error="insufficient_scope"';

/** Whether `response` is the leadership gate's 403 for a session in another role. */
function isNotYourRole(response: Response): boolean {
  return (
    response.status === FORBIDDEN_STATUS &&
    (response.headers.get('WWW-Authenticate') ?? '').includes(NOT_YOUR_ROLE_CHALLENGE)
  );
}

/** The set is not there, or is not one this reader may read. */
const NOT_FOUND_STATUS = 404;

/** The sets this session's person may read, by name. */
export async function readComparisonSets(): Promise<ComparisonSetsRead> {
  let response: Response;
  try {
    response = await fetch(COMPARISON_SETS_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  // The bound on the cast: `sets` is the member every render walks, and a body
  // without it would fail somewhere deeper with nothing to say.
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).sets)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'sets', sets: (body as { sets: readonly ComparisonSetSummaryView[] }).sets };
}

/** The closed choice lists the form offers. */
export async function readComparisonSetOptions(): Promise<ComparisonSetOptionsRead> {
  let response: Response;
  try {
    response = await fetch(COMPARISON_SET_OPTIONS_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  // All three members are walked by the form, and a form built from a partial
  // answer would offer a choice list the server never sent.
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  const options = body as Record<string, unknown>;
  if (
    !Array.isArray(options.lengths) ||
    !Array.isArray(options.levels) ||
    !Array.isArray(options.courses)
  ) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'options', options: body as ComparisonSetOptionsView };
}

/** One set, with the courses in it. */
export async function readComparisonSet(setId: string): Promise<ComparisonSetRead> {
  let response: Response;
  try {
    response = await fetch(comparisonSetPath(setId), { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (response.status === NOT_FOUND_STATUS) {
    return { kind: 'not-found', detail: refusalSentence(body) };
  }
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).member_course_ids)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'set', set: body as ComparisonSetDetailView };
}

/** What one set reaches, for the list's preview line. */
export async function readComparisonSetPreview(setId: string): Promise<ComparisonSetPreviewRead> {
  let response: Response;
  try {
    response = await fetch(comparisonSetPreviewPath(setId), { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (response.status === NOT_FOUND_STATUS) {
    return { kind: 'not-found', detail: refusalSentence(body) };
  }
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  // `member_count` is the one member the preview always carries; the section
  // count is allowed to be absent and the line says so in words when it is.
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (typeof (body as Record<string, unknown>).member_count !== 'number') {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'preview', preview: body as ComparisonSetPreviewView };
}

/** Define a set. */
export async function createComparisonSet(
  write: ComparisonSetWrite,
): Promise<ComparisonSetWriteOutcome> {
  return await sendComparisonSet(COMPARISON_SETS_PATH, 'POST', write);
}

/** Edit a set that already exists. */
export async function updateComparisonSet(
  setId: string,
  write: ComparisonSetWrite,
): Promise<ComparisonSetWriteOutcome> {
  return await sendComparisonSet(comparisonSetPath(setId), 'PUT', write);
}

/**
 * The body of both writes, which differ only in address and method.
 *
 * One function rather than two near-identical ones: what a create and an edit
 * each do with a refusal, with a 401 and with the answer is the same decision,
 * and two copies of it are two places for that decision to drift.
 */
async function sendComparisonSet(
  path: string,
  method: 'POST' | 'PUT',
  write: ComparisonSetWrite,
): Promise<ComparisonSetWriteOutcome> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: writeHeaders(),
      body: JSON.stringify(write),
    });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'refused', detail: refusalSentence(body) };

  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).member_course_ids)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'saved', set: body as ComparisonSetDetailView };
}

/** Delete a set. */
export async function deleteComparisonSet(setId: string): Promise<ComparisonSetDeleteOutcome> {
  let response: Response;
  try {
    response = await fetch(comparisonSetPath(setId), {
      method: 'DELETE',
      headers: writeHeaders(),
    });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  if (response.ok) return { kind: 'deleted' };
  return { kind: 'refused', detail: refusalSentence(await jsonBody(response)) };
}

// ---------------------------------------------------------------------------
// Moderation review: the queue, a leader's decision, and the exclusion log
// (SPEC §5.2, ADR 0190).
//
// The same shape as the sets above: a read answers its payload, a 401 is a
// session that ended, the gate's 403 is a session in another role, and any
// other refusal carries the server's own sentence. `api/leadership.py` answers a reader whose grant puts no course under
// review with a 403 and one sentence; the pages show that sentence rather than an
// empty queue, because "nothing to review" is a claim about the reader that a
// refusal does not entitle a page to make.
// ---------------------------------------------------------------------------

/** `app.api.leadership.QUEUE_PATH` — the comments awaiting this reader's review. */
export const REVIEW_QUEUE_PATH = '/leadership/moderation/queue';

/** `app.api.leadership.LOG_PATH` — every exclusion and keep inside this reader's grant. */
export const EXCLUSION_LOG_PATH = '/leadership/moderation/log';

/** `app.api.leadership.DECISIONS_PATH` — one decision on one queued comment. */
export function queuedCommentDecisionPath(answerId: string): string {
  return `/leadership/moderation/comments/${encodeURIComponent(answerId)}/decisions`;
}

/** One queued comment: its key, its words and its section, and nothing else. */
export type QueueItemView = Schemas['QueueItem'];

/** What a lead or chair sends: exclude or keep, with an optional reason. */
export type LeadDecisionWrite = Schemas['LeadDecision'];

/** One decision in the log. */
export type LogRowView = Schemas['LogRow'];

/** What a read of the review queue answered. */
export type ReviewQueueRead =
  | { readonly kind: 'queue'; readonly items: readonly QueueItemView[] }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of the exclusion log answered. */
export type ExclusionLogRead =
  | { readonly kind: 'log'; readonly rows: readonly LogRowView[] }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/**
 * What a decision answered.
 *
 * A 204 is `decided`, with nothing to carry back: the comment has left the
 * queue. Every refusal — the 404 for a comment no longer in this queue, the 422
 * for a reason out of bounds, the 403 — is `refused` with its sentence.
 */
export type LeadDecisionOutcome =
  | { readonly kind: 'decided' }
  | { readonly kind: 'refused'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable' };

/** The comments awaiting this reader's review, in the order the server drew. */
export async function readReviewQueue(): Promise<ReviewQueueRead> {
  let response: Response;
  try {
    response = await fetch(REVIEW_QUEUE_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).items)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'queue', items: (body as { items: readonly QueueItemView[] }).items };
}

/** Exclude or keep one queued comment. */
export async function decideOnQueuedComment(
  answerId: string,
  decision: LeadDecisionWrite,
): Promise<LeadDecisionOutcome> {
  let response: Response;
  try {
    response = await fetch(queuedCommentDecisionPath(answerId), {
      method: 'POST',
      headers: writeHeaders(),
      body: JSON.stringify(decision),
    });
  } catch {
    return { kind: 'unavailable' };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  if (response.ok) return { kind: 'decided' };
  return { kind: 'refused', detail: refusalSentence(await jsonBody(response)) };
}

/** The exclusion log inside this reader's own grant, newest decision first. */
export async function readExclusionLog(): Promise<ExclusionLogRead> {
  let response: Response;
  try {
    response = await fetch(EXCLUSION_LOG_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };

  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).rows)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'log', rows: (body as { rows: readonly LogRowView[] }).rows };
}

// ---------------------------------------------------------------------------
// The response loop's leadership doors (SPEC §5.3, §5.6): the response policy,
// the responses owed, and responding on behalf of a section.
//
// The same outcomes as above for a 401 and for the gate's 403. The on-behalf
// doors refuse with one 404 whatever the cause (`app.api.leadership`), which
// the read renders as the not-found state and the composer's calls hand back
// as the sentence they were sent.
// ---------------------------------------------------------------------------

/** `app.api.leadership.POLICY_PATH` — every course whose policy the reader sets or reads. */
export const RESPONSE_POLICY_PATH = '/leadership/response-policy';

/** `app.api.leadership.OWED_PATH` — the section-weeks owed a response. */
export const RESPONSES_OWED_PATH = '/leadership/responses-owed';

/** `app.api.leadership.POLICY_PREFIX_PATH`, with the prefix filled in. */
export function responsePolicyPrefixPath(prefixId: string): string {
  return `${RESPONSE_POLICY_PATH}/${encodeURIComponent(prefixId)}`;
}

/** `app.api.leadership.ON_BEHALF_PATH`, with the section and the course week filled in. */
export function onBehalfPath(sectionId: string, courseWeek: number): string {
  return `/leadership/sections/${encodeURIComponent(sectionId)}/weeks/${String(courseWeek)}/on-behalf`;
}

/** Every prefix and the courses of it the reader sets or reads. */
export type ResponsePolicyView = Schemas['PolicyOverview'];

/** One prefix with its courses. */
export type PolicyPrefixView = Schemas['PolicyPrefix'];

/** One course's setting as the reader reads it. */
export type PolicyCourseView = Schemas['PolicyCourse'];

/** Encouraged or required. */
export type PolicyModeView = Schemas['PolicyMode'];

/** One section-week owed a response. */
export type OwedWeekView = Schemas['OwedWeek'];

/** One stream of the on-behalf read. */
export type OnBehalfStreamView = Schemas['OnBehalfStream'];

/** What a lead reads before responding on behalf: stored summaries and ratings, never a comment. */
export type OnBehalfWeekView = Schemas['OnBehalfWeek'];

/** What a read of the response policy answered. */
export type ResponsePolicyRead =
  | { readonly kind: 'policy'; readonly policy: ResponsePolicyView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What switching a prefix answered: the overview as it now stands, or why not. */
export type ResponsePolicyWriteOutcome =
  | { readonly kind: 'saved'; readonly policy: ResponsePolicyView }
  | { readonly kind: 'refused'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of the responses owed answered. */
export type ResponsesOwedRead =
  | { readonly kind: 'owed'; readonly weeks: readonly OwedWeekView[] }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of one section-week for responding on behalf answered. */
export type OnBehalfRead =
  | { readonly kind: 'week'; readonly week: OnBehalfWeekView }
  | { readonly kind: 'not-found' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** The courses the reader sets or reads a response policy for, by prefix. */
export async function readResponsePolicy(): Promise<ResponsePolicyRead> {
  let response: Response;
  try {
    response = await fetch(RESPONSE_POLICY_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }
  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).prefixes)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'policy', policy: body as ResponsePolicyView };
}

/** Switch every course of a prefix the reader sets; the server decides which that is. */
export async function setResponsePolicy(
  prefixId: string,
  mode: PolicyModeView,
): Promise<ResponsePolicyWriteOutcome> {
  let response: Response;
  try {
    response = await fetch(responsePolicyPrefixPath(prefixId), {
      method: 'PUT',
      headers: writeHeaders(),
      body: JSON.stringify({ mode }),
    });
  } catch {
    return { kind: 'unavailable', detail: null };
  }
  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'refused', detail: refusalSentence(body) };
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).prefixes)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'saved', policy: body as ResponsePolicyView };
}

/** The section-weeks in the reader's courses that are owed a response. */
export async function readResponsesOwed(): Promise<ResponsesOwedRead> {
  let response: Response;
  try {
    response = await fetch(RESPONSES_OWED_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }
  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };
  if (!Array.isArray(body)) return { kind: 'unavailable', detail: null };
  return { kind: 'owed', weeks: body as readonly OwedWeekView[] };
}

/** The week's stored summaries and ratings, for the reader who may respond on behalf. */
export async function readOnBehalfWeek(
  sectionId: string,
  courseWeek: number,
): Promise<OnBehalfRead> {
  let response: Response;
  try {
    response = await fetch(onBehalfPath(sectionId, courseWeek), { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }
  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  if (response.status === NOT_FOUND_STATUS) return { kind: 'not-found' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable', detail: null };
  if (!Array.isArray((body as Record<string, unknown>).streams)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'week', week: body as OnBehalfWeekView };
}

/** An AI draft over the on-behalf gather. Advisory: nothing is stored or posted. */
export async function requestOnBehalfDraft(
  sectionId: string,
  courseWeek: number,
): Promise<ResponseDraftOutcome> {
  const answer = await responseCall(`${onBehalfPath(sectionId, courseWeek)}/response-draft`, {
    method: 'POST',
    headers: writeHeaders(),
  });
  if (answer.kind !== 'body') return answer;
  const text = (answer.body as Record<string, unknown> | null)?.text;
  return typeof text === 'string' ? { kind: 'draft', text } : { kind: 'unavailable', detail: null };
}

/** The themes of the week an on-behalf draft does not address. Advisory. */
export async function requestOnBehalfCheck(
  sectionId: string,
  courseWeek: number,
  draft: string,
): Promise<DraftCheckOutcome> {
  const answer = await responseCall(`${onBehalfPath(sectionId, courseWeek)}/draft-check`, {
    method: 'POST',
    headers: writeHeaders(),
    body: JSON.stringify({ draft }),
  });
  if (answer.kind !== 'body') return answer;
  const themes = (answer.body as Record<string, unknown> | null)?.unaddressed;
  return Array.isArray(themes)
    ? { kind: 'checked', unaddressed: themes as readonly CheckThemeView[] }
    : { kind: 'unavailable', detail: null };
}

/** Publish (`POST`) or edit (`PUT`) the on-behalf response. Only a person pressing publish calls this. */
export async function writeOnBehalfResponse(
  method: 'POST' | 'PUT',
  sectionId: string,
  courseWeek: number,
  write: ResponseWriteView,
): Promise<ResponseWriteOutcome> {
  const answer = await responseCall(`${onBehalfPath(sectionId, courseWeek)}/response`, {
    method,
    headers: writeHeaders(),
    body: JSON.stringify(write),
  });
  if (answer.kind !== 'body') return answer;
  const view = weekResponseOf(answer.body);
  return view === null ? { kind: 'unavailable', detail: null } : { kind: 'saved', view };
}

// ---------------------------------------------------------------------------
// The roll-ups (SPEC §5.5, ADR 0205): the context the pages read first, the
// tree, one node's figures, a named set's line, and the drill-down.
//
// The same outcomes as above for a 401 and for the gate's 403. A node or a
// section outside the purview is one 404 with one sentence, exactly as one
// that does not exist, and the pages show the sentence they were sent.
// ---------------------------------------------------------------------------

/** `app.api.leadership.CONTEXT_PATH` — the reader's roles, the terms, and the current term. */
export const LEADERSHIP_CONTEXT_PATH = '/leadership/context';

/** `app.api.leadership.ROLLUP_PATH`, for one term. */
export function rollupTreePath(termId: string): string {
  return `/leadership/rollup?term_id=${encodeURIComponent(termId)}`;
}

/** `app.api.leadership.ROLLUP_NODE_PATH`, for one node in one term. */
export function rollupFiguresPath(kind: RollupFiguresKind, nodeId: string, termId: string): string {
  return `/leadership/rollup/${kind}/${encodeURIComponent(nodeId)}?term_id=${encodeURIComponent(termId)}`;
}

/** `app.api.leadership.SET_SERIES_PATH`, for one set in one term. */
export function setSeriesPath(setId: string, termId: string): string {
  return `${comparisonSetPath(setId)}/series?term_id=${encodeURIComponent(termId)}`;
}

/** `app.api.leadership.DRILL_DOWN_WEEKS_PATH`, with the section filled in. */
export function drillDownWeeksPath(sectionId: string): string {
  return `/leadership/sections/${encodeURIComponent(sectionId)}/published-weeks`;
}

/** `app.api.leadership.DRILL_DOWN_PATH`, with the section and the course week filled in. */
export function drillDownPath(sectionId: string, courseWeek: number): string {
  return `/leadership/sections/${encodeURIComponent(sectionId)}/weeks/${String(courseWeek)}/report`;
}

/** The reader's leadership roles, highest first, every term, and the term containing today. */
export type LeadershipContextView = Schemas['LeadershipContext'];

/** One leadership role, as the context names it. */
export type LeaderRoleView = Schemas['LeadershipContext']['roles'][number];

/** One term a roll-up may be read for. */
export type RollupTermView = Schemas['RollupTerm'];

/** The whole tree: the hierarchy's roots, and the by-lead groups where they are offered. */
export type RollupTreeView = Schemas['RollupTree'];

/** One row of the tree, with its children. */
export type RollupNodeView = Schemas['RollupNode'];

/** The kinds of node whose figures may be asked for. A section's are its report. */
export type RollupFiguresKind = Schemas['RollupFigures']['kind'];

/** One node's figures in one term: a line per start cohort, and the attention cards. */
export type RollupFiguresView = Schemas['RollupFigures'];

/** One start cohort of a node's sections, its line on the term axis, and its participation. */
export type RollupCohortView = Schemas['RollupCohort'];

/** One course week of one cohort, on both week axes. The means arrive as decimal strings. */
export type RollupWeekView = Schemas['RollupWeek'];

/** One §5.6 rule met by one section. */
export type AttentionCardView = Schemas['AttentionCard'];

/** A named set's figures for this reader in one term, one series per start cohort. */
export type NamedSetSeriesView = Schemas['NamedSetSeries'];

/** One start cohort of a named set's series. */
export type NamedSetCohortView = Schemas['NamedSetCohort'];

/** What the context read answered. */
export type LeadershipContextRead =
  | { readonly kind: 'context'; readonly context: LeadershipContextView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What the tree read answered. */
export type RollupTreeRead =
  | { readonly kind: 'tree'; readonly tree: RollupTreeView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What one node's figures answered. A node outside the purview is `unavailable` with the server's sentence. */
export type RollupFiguresRead =
  | { readonly kind: 'figures'; readonly figures: RollupFiguresView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a named set's series answered. */
export type SetSeriesRead =
  | { readonly kind: 'series'; readonly series: NamedSetSeriesView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What the drill-down's week list answered: the instructor page's outcomes, and the gate's 403. */
export type DrillDownWeeksRead = PublishedWeeksRead | { readonly kind: 'not-your-role' };

/** What the drill-down's report answered. */
export type DrillDownReportRead = ReportRead | { readonly kind: 'not-your-role' };

/** One read over the roll-up routes, answered in the shape every one of them shares. */
async function rollupRead(
  path: string,
  required: string,
): Promise<
  | { readonly kind: 'body'; readonly body: unknown }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null }
> {
  let response: Response;
  try {
    response = await fetch(path, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }
  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'unavailable', detail: refusalSentence(body) };
  // The bound on the cast: the member every render walks has to be there.
  if (typeof body !== 'object' || body === null || !(required in body)) {
    return { kind: 'unavailable', detail: null };
  }
  return { kind: 'body', body };
}

/** The reader's roles and the terms, read before anything else on the roll-up. */
export async function readLeadershipContext(): Promise<LeadershipContextRead> {
  const answer = await rollupRead(LEADERSHIP_CONTEXT_PATH, 'terms');
  if (answer.kind !== 'body') return answer;
  return { kind: 'context', context: answer.body as LeadershipContextView };
}

/** The tree over the reader's purview in one term. */
export async function readRollupTree(termId: string): Promise<RollupTreeRead> {
  const answer = await rollupRead(rollupTreePath(termId), 'hierarchy');
  if (answer.kind !== 'body') return answer;
  return { kind: 'tree', tree: answer.body as RollupTreeView };
}

/** One node's figures and attention cards in one term. */
export async function readRollupFigures(
  kind: RollupFiguresKind,
  nodeId: string,
  termId: string,
): Promise<RollupFiguresRead> {
  const answer = await rollupRead(rollupFiguresPath(kind, nodeId, termId), 'cohorts');
  if (answer.kind !== 'body') return answer;
  return { kind: 'figures', figures: answer.body as RollupFiguresView };
}

/** A named set's figures over the reader's purview in one term. */
export async function readSetSeries(setId: string, termId: string): Promise<SetSeriesRead> {
  const answer = await rollupRead(setSeriesPath(setId, termId), 'cohorts');
  if (answer.kind !== 'body') return answer;
  return { kind: 'series', series: answer.body as NamedSetSeriesView };
}

/** The published course weeks of one section in the reader's purview. */
export async function readDrillDownWeeks(sectionId: string): Promise<DrillDownWeeksRead> {
  const answer = await rollupRead(drillDownWeeksPath(sectionId), 'published_weeks');
  if (answer.kind !== 'body') return answer;
  return {
    kind: 'weeks',
    weeks: (answer.body as { published_weeks: readonly number[] }).published_weeks,
  };
}

/** One section's Monday report, read-only, for a section in the reader's purview. */
export async function readDrillDownReport(
  sectionId: string,
  courseWeek: number,
): Promise<DrillDownReportRead> {
  const answer = await rollupRead(drillDownPath(sectionId, courseWeek), 'streams');
  if (answer.kind !== 'body') return answer;
  return { kind: 'report', report: answer.body as InstructorReportView };
}
