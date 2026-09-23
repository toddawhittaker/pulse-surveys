/**
 * The seven calls the comparison-set management screen makes — SPEC §13's
 * `frontend/src/api/`, ticket E5-09.
 *
 * `api/leadership.py` (E5-06) serves SPEC §5.1's named sets: a list, a create, a
 * read, an edit, a delete, the closed choice lists the form is built from, and
 * the preview that says what a set reaches. This module is the client half, and
 * it is the third in this directory rather than a growth of either of the other
 * two: `instructor.ts` reads one instructor's own report and `student.ts` is one
 * student's survey, and neither has anything to say about a leadership surface.
 *
 * **Hand-written, not generated, and not wrapped in a query cache** — ADR 0117,
 * unchanged, and this screen is the case it was argued for: seven calls with no
 * shared cache key between them.
 *
 * **The session rides as a Bearer header** (ADR 0089, `../lib/session.ts`), and
 * **every write echoes the double-submit cookie** through `csrfHeader()`. This
 * is the first client in this directory with writes other than the student's
 * submission, which is why that reader moved out of `student.ts` and up into
 * `lib/session.ts` rather than being copied here (`docs/MISTAKES.md` entry 13).
 *
 * **What checks that echo is `csrf_verified_leadership`** (`api/deps.py`,
 * E5-06), which the three writing routes below declare and the four reading
 * routes do not.
 *
 * **Every field below is the wire's spelling**, snake case included, because
 * these types describe E5-06's Pydantic schemas rather than a shape of this
 * screen's choosing.
 *
 * **A refusal is shown, never re-derived.** SPEC §5.1 puts the rules about which
 * length and level may be combined, who may edit a set and what a duplicate name
 * means on the server; `api/leadership.py` answers each with one sentence under
 * `detail`, and the screen renders the sentence it was sent. The form makes the
 * invalid combinations unreachable for a person using it — that is §5.1's "makes
 * invalid combinations impossible rather than erroring on them" — and the
 * refusals stay reachable by the races a form cannot prevent: a course that left
 * the catalogue while the form was open, a name somebody else took first.
 */

import { authorizationHeader, csrfHeader } from '../lib/session';

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
export interface ComparisonSetCourseView {
  readonly id: string;
  /** The governed label the server composes; nothing here assembles one. */
  readonly label: string;
  /** One of SPEC §8's five bands, as the server spells it. */
  readonly level: string;
}

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
export interface ComparisonSetOptionsView {
  readonly lengths: readonly number[];
  readonly levels: readonly string[];
  readonly courses: readonly ComparisonSetCourseView[];
}

/** One set as the list carries it. */
export interface ComparisonSetSummaryView {
  readonly id: string;
  readonly name: string;
  readonly length_weeks: number;
  readonly level: string;
  readonly member_count: number;
  /**
   * Whether this reader may edit and delete this set.
   *
   * The server's answer to a question about who defined the set and what this
   * session's person may do with it, and it is not re-derived here: a screen
   * deciding for itself which controls to draw would be a second authority on a
   * question SPEC §2.1 gives to one. The controls follow the flag; the route
   * still refuses a write the flag should have withheld.
   */
  readonly editable: boolean;
}

/** One set with its membership, as the read and both writes answer. */
export interface ComparisonSetDetailView extends ComparisonSetSummaryView {
  readonly member_course_ids: readonly string[];
  readonly created_at: string;
  readonly updated_at: string;
}

/** What a create or an edit sends. */
export interface ComparisonSetWrite {
  readonly name: string;
  readonly length_weeks: number;
  readonly level: string;
  readonly member_course_ids: readonly string[];
}

/**
 * What a set reaches.
 *
 * `section_count` is optional because E5-06's scope note allows the preview to
 * answer the member count without it. An absent count is rendered as an absence;
 * a zero printed in its place would state something the server did not say.
 */
export interface ComparisonSetPreviewView {
  readonly member_count: number;
  readonly section_count?: number | null;
}

/** What a read of the set list answered. */
export type ComparisonSetsRead =
  | { readonly kind: 'sets'; readonly sets: readonly ComparisonSetSummaryView[] }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of the choice lists answered. */
export type ComparisonSetOptionsRead =
  | { readonly kind: 'options'; readonly options: ComparisonSetOptionsView }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of one set answered. */
export type ComparisonSetRead =
  | { readonly kind: 'set'; readonly set: ComparisonSetDetailView }
  | { readonly kind: 'not-found'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a read of one set's preview answered. */
export type ComparisonSetPreviewRead =
  | { readonly kind: 'preview'; readonly preview: ComparisonSetPreviewView }
  | { readonly kind: 'not-found'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
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
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** What a delete answered. The same shape, with nothing to carry back. */
export type ComparisonSetDeleteOutcome =
  | { readonly kind: 'deleted' }
  | { readonly kind: 'refused'; readonly detail: string | null }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/** No leadership session on the request (`require_leadership`). */
const UNAUTHORIZED_STATUS = 401;

/** The set is not there, or is not one this reader may read. */
const NOT_FOUND_STATUS = 404;

/** The headers a read carries. */
function readHeaders(): Record<string, string> {
  return { Accept: 'application/json', ...authorizationHeader() };
}

/**
 * The headers a write carries: the session, the body's type and the
 * double-submit echo when the cookie is readable.
 */
function writeHeaders(): Record<string, string> {
  return {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    ...authorizationHeader(),
    ...csrfHeader(),
  };
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
 * `detail` out of an error body, when it is a sentence.
 *
 * FastAPI answers a refusal with `{"detail": …}`, and every refusal these routes
 * serve carries a **string** there. FastAPI's own 422 for a body it could not
 * parse carries a list of validation objects instead, which is not a sentence
 * anybody wrote for a reader, so it is answered `null` here and the screen uses
 * its own words.
 */
function refusalSentence(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null;
  const detail = (body as Record<string, unknown>).detail;
  return typeof detail === 'string' ? detail : null;
}

/** The sets this session's person may read, by name. */
export async function readComparisonSets(): Promise<ComparisonSetsRead> {
  let response: Response;
  try {
    response = await fetch(COMPARISON_SETS_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'unavailable', detail: null };
  }

  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
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
  if (response.ok) return { kind: 'deleted' };
  return { kind: 'refused', detail: refusalSentence(await jsonBody(response)) };
}
