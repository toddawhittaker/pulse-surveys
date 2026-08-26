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
 * This is entry plumbing, not application logic: there is nothing to fetch in E1,
 * and what a real request looks like is E2's to decide against a real screen.
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
