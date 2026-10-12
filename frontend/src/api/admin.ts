/**
 * The calls the admin's People & reporting and Lead Faculty mapping screens
 * make — SPEC §13's `frontend/src/api/`, over `api/admin.py` (SPEC §6.3).
 *
 * **The calls are written by hand and not wrapped in a query cache** (ADR
 * 0117), and **the wire types are generated** from the backend's OpenAPI
 * document (ADR 0185); every type below is one of them.
 *
 * **The session rides as a Bearer header and every write echoes the CSRF
 * cookie**, through `../lib/http.ts` as every client here does.
 *
 * **Four answers are the page's own words, and every other refusal is the
 * server's.** A 401 is `session-ended`. The admin gate's 403 for a real session
 * in another role carries RFC 6750's `insufficient_scope` challenge (ADR 0196)
 * and is `not-your-role`. Any other refusal (a revoke that leaves assignments
 * reporting to it, a web login linked to somebody else, a bad line in an
 * import, a dry run out of date) is `refused` and carries the sentence the
 * server sent, which the screen shows and does not re-derive. A request that
 * never reached the server, or an answer with no sentence, is `unavailable`.
 */

import type { components } from './wire.gen';
import { authorizationHeader } from '../lib/session';
import { jsonBody, readHeaders, refusalSentence, writeHeaders } from '../lib/http';
import type { MappingSort, Order, PeopleSort, Table } from '../lib/adminTable';

type Schemas = components['schemas'];

export type AssignmentRole = Schemas['AssignmentRole'];
export type PersonLineView = Schemas['PersonLine'];
export type AssignmentLineView = Schemas['AssignmentLine'];
export type PeoplePageView = Schemas['PeoplePage'];
export type ReportsToOptionView = Schemas['ReportsToOption'];
export type MappingLineView = Schemas['MappingLine'];
export type MappingPageView = Schemas['MappingPage'];
export type PeopleDiffView = Schemas['PeopleDiff'];
export type MappingDiffView = Schemas['MappingDiff'];

/**
 * Every role the grant control offers: each Pulse-owned role, Care and Admin
 * included, for any person (the E9 breakdown's ruling 1). The one role left
 * out is the teaching assignment, which the roster owns (decision 11).
 *
 * **A record over the generated role type rather than a list**, so a role the
 * server adds fails to compile here until somebody decides whether it is
 * offered, instead of being silently absent from the control.
 */
const OFFERED: Readonly<Record<AssignmentRole, boolean>> = {
  INSTRUCTOR: false,
  LEAD_FACULTY: true,
  CHAIR: true,
  ASSISTANT_DEAN: true,
  DEAN: true,
  VP_ACADEMICS: true,
  CARE: true,
  ADMIN: true,
};

/** The roles the grant control offers, in the order the generated type lists them. */
export const GRANTABLE_ROLES: readonly AssignmentRole[] = (
  Object.keys(OFFERED) as AssignmentRole[]
).filter((role) => OFFERED[role]);

export const PEOPLE_PATH = '/admin/people';
export const MAPPINGS_PATH = '/admin/lead-mappings';
export const REPORTS_TO_OPTIONS_PATH = '/admin/reports-to-options';

export function personPath(personId: string): string {
  return `${PEOPLE_PATH}/${encodeURIComponent(personId)}`;
}

export function grantPath(personId: string): string {
  return `${personPath(personId)}/assignments`;
}

export function webLoginPath(personId: string): string {
  return `${personPath(personId)}/web-login`;
}

export function assignmentPath(assignmentId: string): string {
  return `/admin/assignments/${encodeURIComponent(assignmentId)}`;
}

export function reportsToPath(assignmentId: string): string {
  return `${assignmentPath(assignmentId)}/reports-to`;
}

const TABLE_PATH: Readonly<Record<Table, string>> = {
  people: PEOPLE_PATH,
  mappings: MAPPINGS_PATH,
};

export function exportPath(table: Table): string {
  return `${TABLE_PATH[table]}/export`;
}

export function dryRunPath(table: Table): string {
  return `${TABLE_PATH[table]}/import/dry-run`;
}

export function applyPath(table: Table): string {
  return `${TABLE_PATH[table]}/import`;
}

/** What any admin call answered. */
export type AdminOutcome<T> =
  | { readonly kind: 'ok'; readonly value: T }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'refused'; readonly status: number; readonly detail: string }
  | { readonly kind: 'unavailable' };

const UNAUTHORIZED_STATUS = 401;
const FORBIDDEN_STATUS = 403;
const NOT_YOUR_ROLE_CHALLENGE = 'error="insufficient_scope"';

/** The admin gate's 403 for a verified session in another role (ADR 0196). */
function isNotYourRole(response: Response): boolean {
  return (
    response.status === FORBIDDEN_STATUS &&
    (response.headers.get('WWW-Authenticate') ?? '').includes(NOT_YOUR_ROLE_CHALLENGE)
  );
}

/** The answer common to every call before its own success is read. */
async function refusalOf(response: Response): Promise<AdminOutcome<never>> {
  if (response.status === UNAUTHORIZED_STATUS) return { kind: 'session-ended' };
  if (isNotYourRole(response)) return { kind: 'not-your-role' };
  const detail = refusalSentence(await jsonBody(response));
  // A refusal that carries no sentence of the server's has nothing to show.
  if (detail === null) return { kind: 'unavailable' };
  return { kind: 'refused', status: response.status, detail };
}

async function send(path: string, init: RequestInit): Promise<Response | null> {
  try {
    return await fetch(path, init);
  } catch {
    return null;
  }
}

/** A read answering JSON. */
async function read<T>(path: string): Promise<AdminOutcome<T>> {
  const response = await send(path, { headers: readHeaders() });
  if (response === null) return { kind: 'unavailable' };
  if (!response.ok) return refusalOf(response);
  const body = await jsonBody(response);
  if (typeof body !== 'object' || body === null) return { kind: 'unavailable' };
  return { kind: 'ok', value: body as T };
}

/** A write whose success answers JSON. */
async function write<T>(method: string, path: string, body: unknown): Promise<AdminOutcome<T>> {
  const response = await send(path, { method, headers: writeHeaders(), body: JSON.stringify(body) });
  if (response === null) return { kind: 'unavailable' };
  if (!response.ok) return refusalOf(response);
  const parsed = await jsonBody(response);
  if (typeof parsed !== 'object' || parsed === null) return { kind: 'unavailable' };
  return { kind: 'ok', value: parsed as T };
}

/** A write whose success answers 204, with no body. */
async function writeNothing(
  method: string,
  path: string,
  body?: unknown,
): Promise<AdminOutcome<null>> {
  const response = await send(path, {
    method,
    headers: writeHeaders(),
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response === null) return { kind: 'unavailable' };
  if (!response.ok) return refusalOf(response);
  return { kind: 'ok', value: null };
}

function query(params: Readonly<Record<string, string | number>>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) search.set(name, String(value));
  return `?${search.toString()}`;
}

export function readPeople(
  sort: PeopleSort,
  order: Order,
  page: number,
): Promise<AdminOutcome<PeoplePageView>> {
  return read(`${PEOPLE_PATH}${query({ sort, order, page })}`);
}

export function readMappings(
  sort: MappingSort,
  order: Order,
  page: number,
): Promise<AdminOutcome<MappingPageView>> {
  return read(`${MAPPINGS_PATH}${query({ sort, order, page })}`);
}

/** The assignments a new or existing assignment of `role` may report to. */
export async function readReportsToOptions(
  role: AssignmentRole,
): Promise<AdminOutcome<readonly ReportsToOptionView[]>> {
  const answer = await read<Schemas['ReportsToOptions']>(
    `${REPORTS_TO_OPTIONS_PATH}${query({ role })}`,
  );
  if (answer.kind !== 'ok') return answer;
  if (!Array.isArray(answer.value.options)) return { kind: 'unavailable' };
  return { kind: 'ok', value: answer.value.options };
}

export function addPerson(name: string, category: string): Promise<AdminOutcome<Schemas['PersonCreated']>> {
  return write('POST', PEOPLE_PATH, { name, category });
}

export function editPerson(personId: string, name: string, category: string): Promise<AdminOutcome<null>> {
  return writeNothing('PUT', personPath(personId), { name, category });
}

export function grantRole(
  personId: string,
  role: AssignmentRole,
  scopeNodeId: string,
): Promise<AdminOutcome<Schemas['Granted']>> {
  return write('POST', grantPath(personId), { role, scope_node_id: scopeNodeId });
}

export function revokeRole(assignmentId: string): Promise<AdminOutcome<null>> {
  return writeNothing('DELETE', assignmentPath(assignmentId));
}

export function setReportsTo(assignmentId: string, parent: string | null): Promise<AdminOutcome<null>> {
  return writeNothing('PUT', reportsToPath(assignmentId), { reports_to: parent });
}

export function linkWebLogin(
  personId: string,
  issuer: string,
  subject: string,
): Promise<AdminOutcome<null>> {
  return writeNothing('PUT', webLoginPath(personId), { idp_issuer: issuer, idp_subject: subject });
}

export function unlinkWebLogin(personId: string): Promise<AdminOutcome<null>> {
  return writeNothing('DELETE', webLoginPath(personId));
}

/** An import's diff, whichever table it was for. */
export type DiffView = Schemas['PeopleDiff'] | Schemas['MappingDiff'];

export function dryRun(table: 'people', csv: string): Promise<AdminOutcome<PeopleDiffView>>;
export function dryRun(table: 'mappings', csv: string): Promise<AdminOutcome<MappingDiffView>>;
export function dryRun(table: Table, csv: string): Promise<AdminOutcome<DiffView>> {
  return write('POST', dryRunPath(table), { csv });
}

/** Applies the file the dry run answered, with that dry run's digest and nothing else. */
export function applyImport(
  table: 'people',
  csv: string,
  digest: string,
): Promise<AdminOutcome<PeopleDiffView>>;
export function applyImport(
  table: 'mappings',
  csv: string,
  digest: string,
): Promise<AdminOutcome<MappingDiffView>>;
export function applyImport(table: Table, csv: string, digest: string): Promise<AdminOutcome<DiffView>> {
  return write('POST', applyPath(table), { csv, digest });
}

/** The table's CSV, as text. */
export async function exportCsv(table: Table): Promise<AdminOutcome<string>> {
  const response = await send(exportPath(table), {
    headers: { Accept: 'text/csv', ...authorizationHeader() },
  });
  if (response === null) return { kind: 'unavailable' };
  if (!response.ok) return refusalOf(response);
  try {
    return { kind: 'ok', value: await response.text() };
  } catch {
    return { kind: 'unavailable' };
  }
}
