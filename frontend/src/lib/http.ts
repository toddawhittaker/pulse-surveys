/**
 * The request and response plumbing every client in `api/` shares.
 *
 * The headers a call carries, a response's JSON body, and the refusal sentence
 * out of FastAPI's `{"detail": …}`. Each was once written in every client
 * module, and a copy per module is a copy that drifts (`docs/MISTAKES.md`
 * entry 13). What each client *decides* about a status stays in that client's
 * own outcome types.
 *
 * **The session rides as a Bearer header** (ADR 0089, `./session.ts`) on every
 * call, and **every write echoes the double-submit cookie** through
 * `csrfHeader()` whenever the cookie is readable. A cookie-borne session is
 * not exempt from the write path's double-submit check the way a Bearer one is,
 * and `csrfHeader` carries the reasoning, including why a value the cookie did
 * not supply would be worse than sending nothing.
 */

import { authorizationHeader, csrfHeader } from './session';

/** The headers a read carries. */
export function readHeaders(): Record<string, string> {
  return { Accept: 'application/json', ...authorizationHeader() };
}

/** The headers a write carries: a JSON body, the session, and the CSRF echo. */
export function writeHeaders(): Record<string, string> {
  return {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    ...authorizationHeader(),
    ...csrfHeader(),
  };
}

/** A response's JSON body, or `null` when it did not carry one. */
export async function jsonBody(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

/**
 * `detail` out of an error body, when it is a sentence.
 *
 * FastAPI answers a refusal with `{"detail": …}`. The routes' own refusals put
 * one of `app.copy`'s sentences there as a **string**; FastAPI's own 422 puts a
 * list of validation objects, and the student submission's bounce puts an
 * object. Neither of those is a sentence anybody wrote for a reader, so both
 * answer `null` here and the caller uses its own words or its own reading.
 */
export function refusalSentence(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null;
  const detail = (body as Record<string, unknown>).detail;
  return typeof detail === 'string' ? detail : null;
}
