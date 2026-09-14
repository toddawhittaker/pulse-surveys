/**
 * The session the entry doors hand the first-party SPA — ticket E1-08.
 *
 * A launch runs this application inside the LMS's cross-site iframe, where a
 * cookie is a third-party cookie the browser may block. So the launch door does
 * not rely on the cookie alone: on a valid launch it redirects to
 * `/app/<role>#session=<jwt>`, carrying the session in the URL *fragment*. A
 * fragment reaches neither the server access log nor a `Referer` header, so the
 * token is not written down on the way here.
 *
 * `captureSessionFromFragment` runs once at startup (`main.tsx`): it lifts the
 * token out of the fragment into `sessionStorage` and strips the fragment from
 * the address bar, so the token does not sit in the browser history or a
 * screenshot. Thereafter `authorizationHeader` supplies it as a Bearer header on
 * every fetch — the backend's `session_from_request` reads the Bearer header
 * before any cookie, so this path carries the session with no cookie required.
 *
 * This is entry plumbing, not application logic. E1 had nothing to fetch and
 * left what a real request looks like to E2's first real screen; `api/student.ts`
 * is that answer, and `authorizationHeader` is what it spreads into both calls.
 */

/** Where the captured session lives for the tab's lifetime. */
const SESSION_STORAGE_KEY = 'pulse.session';

/** The fragment a door redirects with: `#session=<jwt>`. */
const SESSION_FRAGMENT_PREFIX = '#session=';

/**
 * Lift a `#session=<jwt>` fragment into `sessionStorage`, then strip it from the
 * address bar. A no-op when the fragment is absent, so it is safe to call on
 * every load. Every storage access is guarded: a private window, cleared site
 * data, or a browser that blocks storage throws rather than returning empty, and
 * a launch must still render.
 */
export function captureSessionFromFragment(): void {
  const hash = window.location.hash;
  if (!hash.startsWith(SESSION_FRAGMENT_PREFIX)) {
    return;
  }

  const token = hash.slice(SESSION_FRAGMENT_PREFIX.length);
  if (token.length === 0) {
    return;
  }

  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, token);
  } catch {
    // Storage is unavailable (private mode, blocked site data). The Bearer path
    // then cannot carry the session, but the page still renders rather than
    // failing on the way up.
  }

  // Strip the fragment so the token leaves the address bar, the history entry
  // and any screenshot. `replaceState` rather than `pushState`: this is the same
  // navigation, with the credential removed, not a new one.
  const { pathname, search } = window.location;
  window.history.replaceState(null, '', `${pathname}${search}`);
}

/** The captured session token, or `null` when there is none to read. */
export function sessionToken(): string | null {
  try {
    return window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * The `Authorization` header a request carries the session in, or an empty object
 * when there is no session — so a caller can spread it into a header set
 * unconditionally.
 */
export function authorizationHeader(): Record<string, string> {
  const token = sessionToken();
  return token === null ? {} : { Authorization: `Bearer ${token}` };
}

/**
 * The cookie the double-submit token rides in, and the header it is echoed in.
 *
 * `csrf_verified_student` (`app.api.deps`) requires the header from any request
 * whose session rides the cookie, and exempts the Bearer carrier — a Bearer header is not something a cross-site form can be tricked
 * into sending, so there is nothing there for a double submit to protect. The
 * cookie is deliberately not `HttpOnly` (ADR 0089) for exactly this reason: the
 * SPA has to read it.
 *
 * **That dependency is the only one on this branch today.** `api/deps.py`
 * carries one such check, the student's; E5-06 adds `csrf_verified_leadership`
 * for the comparison-set routes `api/leadership.ts` writes to, and this branch
 * merges after it. The cookie and the header are the same on both, which is why
 * one helper serves both clients — but until E5-06 lands, the leadership writes
 * echo a token no dependency on this branch is checking.
 */
const CSRF_COOKIE = 'pulse_csrf';
const CSRF_HEADER = 'X-Pulse-CSRF';

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
 * The double-submit header a write carries when the cookie is readable, and an
 * empty object when it is not — so a caller can spread it unconditionally.
 *
 * **Every write, whenever the cookie is readable, and no write when it is
 * not.** Sending a value the cookie did not supply would be worse than sending
 * nothing, because a double submit the server cannot compare is a check that
 * verifies nothing; and withholding the request itself would lock out every
 * reader whose session rides the Bearer header, where the browser refuses the
 * tool's cookies anyway.
 *
 * **It lives here rather than in one client.** E2-17 wrote this reader inside
 * `api/student.ts`, where it was the only write path in the application;
 * E5-09's leadership client is the second, and two readers answering one
 * question about one cookie is `docs/MISTAKES.md` entry 13. So the reader moved
 * up beside `authorizationHeader`, which is the header the same requests carry
 * for the same session, and both clients call it.
 */
export function csrfHeader(): Record<string, string> {
  const token = readCookie(CSRF_COOKIE);
  return token === null ? {} : { [CSRF_HEADER]: token };
}
