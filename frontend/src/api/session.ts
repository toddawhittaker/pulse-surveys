/**
 * The calls the app shell's role switcher and logout make (SPEC §2, ADR 0202).
 *
 * `GET /session/landings` answers the view this session is in and every view
 * its person holds at the door the session came through; `POST /session/switch`
 * issues a new session in one of them and revokes the old one; `POST
 * /session/logout` revokes the session and clears both cookies. Which views a
 * person holds is the server's answer, read now, and the shell offers exactly
 * the list it was sent.
 *
 * The writes carry `writeHeaders()`, so a cookie-borne session echoes its
 * double-submit token, as every other write here does.
 */

import type { components } from './wire.gen';
import { jsonBody, readHeaders, refusalSentence, writeHeaders } from '../lib/http';

type Schemas = components['schemas'];

/** `app.api.auth.SESSION_LANDINGS_PATH`. */
export const SESSION_LANDINGS_PATH = '/session/landings';
/** `app.api.auth.SESSION_SWITCH_PATH`. */
export const SESSION_SWITCH_PATH = '/session/switch';
/** `app.api.auth.LOGOUT_PATH`. */
export const LOGOUT_PATH = '/session/logout';

/** The session's own view and every view it may switch to, in the server's order. */
export type SessionLandingsView = Schemas['SessionLandings'];

/** One view by name: `student`, `instructor`, `leadership`, `care` or `admin`. */
export type LandingName = Schemas['SessionLandings']['current'];

/** What a switch answers: the new view, and the session in it. */
export type SessionSwitchedView = Schemas['SessionSwitched'];

/** What a read of the landings answered. No session is not an error; it is no shell. */
export type SessionLandingsRead =
  | { readonly kind: 'landings'; readonly landings: SessionLandingsView }
  | { readonly kind: 'no-session' };

/** What a switch answered. A refusal changes nothing, and says so in its own words. */
export type SwitchOutcome =
  | { readonly kind: 'switched'; readonly switched: SessionSwitchedView }
  | { readonly kind: 'refused'; readonly detail: string | null };

/** What a logout answered. */
export type LogoutOutcome = { readonly kind: 'signed-out' } | { readonly kind: 'refused' };

/** The views this session may switch to, or no session at all. */
export async function readSessionLandings(): Promise<SessionLandingsRead> {
  let response: Response;
  try {
    response = await fetch(SESSION_LANDINGS_PATH, { headers: readHeaders() });
  } catch {
    return { kind: 'no-session' };
  }
  if (!response.ok) return { kind: 'no-session' };
  const body = await jsonBody(response);
  if (typeof body !== 'object' || body === null) return { kind: 'no-session' };
  if (!Array.isArray((body as Record<string, unknown>).landings)) return { kind: 'no-session' };
  return { kind: 'landings', landings: body as SessionLandingsView };
}

/** Ask for a new session in `role`. Only a person choosing a view calls this. */
export async function switchSession(role: LandingName): Promise<SwitchOutcome> {
  let response: Response;
  try {
    response = await fetch(SESSION_SWITCH_PATH, {
      method: 'POST',
      headers: writeHeaders(),
      body: JSON.stringify({ role }),
    });
  } catch {
    return { kind: 'refused', detail: null };
  }
  const body = await jsonBody(response);
  if (!response.ok) return { kind: 'refused', detail: refusalSentence(body) };
  if (typeof body !== 'object' || body === null) return { kind: 'refused', detail: null };
  const switched = body as Record<string, unknown>;
  if (typeof switched.session !== 'string' || typeof switched.role !== 'string') {
    return { kind: 'refused', detail: null };
  }
  return { kind: 'switched', switched: body as SessionSwitchedView };
}

/** End this session. */
export async function logOut(): Promise<LogoutOutcome> {
  let response: Response;
  try {
    response = await fetch(LOGOUT_PATH, { method: 'POST', headers: writeHeaders() });
  } catch {
    return { kind: 'refused' };
  }
  return response.ok ? { kind: 'signed-out' } : { kind: 'refused' };
}
