// The two doors, as the E1-15 exit specs drive them — SPEC §14.3 (E1's exit
// line) and §9.2.
//
// **Why this module exists.** Five new specs prove five clauses, and four of
// them open a door before they assert anything. Until now each spec carried its
// own copy of the launch form's three testids and its own `launchAs`; a fifth
// and sixth copy is `docs/MISTAKES.md` entry 13 written out in full — a quirk
// worked around in one of the places facing it. So the shared question is
// answered once, here, and the five new specs import it.
//
// **The six existing specs are deliberately left alone.** Refactoring them onto
// this module is out of E1-15's scope: it would put a diff on the specs that are
// this suite's proven-green baseline, in the same pull request that is trying to
// use that baseline as a control.
//
// **New machinery ships with a control that must be green.** Nothing here is
// believed on the strength of reading it. Each helper is named below with the
// test that exercises it on a path this suite already proves green, so a helper
// that has quietly stopped working reports that fact rather than turning a
// clause's proof into a vacuous pass (`docs/MISTAKES.md` entry 3):
//
//   - `launchAs`, `sessionToken`, `sessionsDelivered` — controlled by
//     `exit-refused-launches.spec.ts`'s first test, "an undefected launch lands
//     on the instructor view and hands over a session". That is the same flow
//     `lti-launch.spec.ts` proves on every CI run, so a red there is the helper,
//     not the door.
//   - `placementsOfferedTo`, `placementInto` — controlled by the instructor-view
//     assertion inside `exit-synced-section-dates.spec.ts`'s `syncedSectionRow`,
//     which runs before anything about the development console: a placement
//     these helpers chose wrongly is a launch that is refused or lands on the
//     calm page, and that fails there rather than in a dates assertion.
//   - `signInAs`, `sessionPayload` — controlled by
//     `exit-identity-merge.spec.ts`, whose first half is the web login
//     `two-hat.spec.ts` already proves lands on the Care view, and which asserts
//     a decoded `person_id` is present *before* it asserts the two doors agree.
//   - `launchTokensDelivered`, `onMockLmsHostOrigin` — controlled by
//     `exit-roster-auth.spec.ts`'s canary, which requires the captured launch to
//     carry an absolute roster address and requires the rewritten origin to
//     serve the mock's own launch page.
//   - `mintDefectiveLaunches` — controlled in the same file by the undefected
//     launch above, which arms it with **no defect** and so runs the identical
//     interception with nothing edited. That is the control the first version of
//     this helper did not have and needed: a handler that never fires, and a
//     handler that fires and breaks the launch, both end in a launch that did
//     not land, and only this tells them apart.

import { expect, type Page } from '@playwright/test';

// The horizons `docker-compose.override.yml` publishes, and the same two
// literals the existing specs carry (`lti-launch.spec.ts:65`,
// `cookieless-launch.spec.ts:71-72`). Only the tool is `baseURL`; the mocks are
// cross-origin and named.
export const MOCK_LMS_ORIGIN = 'http://localhost:8080/';
export const TOOL_ORIGIN = 'http://localhost:8000';

// The tool's own paths these specs drive or watch. `/lti/login` is where the
// mock's launch form posts its third-party login initiation and `/lti/launch`
// is where the platform's self-submitting form posts the signed `id_token`
// (`docker-compose.override.yml` sets `MOCK_LMS_TOOL_LOGIN_URL` and
// `MOCK_LMS_TOOL_LAUNCH_URL` to exactly these addresses on the host);
// `/auth/oidc/login` begins the web door's code flow, and `/dev` is the
// development console.
export const LOGIN_PATH = '/lti/login';
export const LAUNCH_PATH = '/lti/launch';
export const WEB_LOGIN_PATH = '/auth/oidc/login';
export const DEV_CONSOLE_PATH = '/dev';

// What `page.route` matches to reach the launch handshake, and the query
// parameter E1-07's mints are selected by.
//
// **It is the login initiation and not the authorization request, and that is a
// measured finding rather than a preference.** A route on
// `http://localhost:8080/oidc/authorize*` intercepts nothing: the browser
// reaches the authorization endpoint by *following the tool's 302*, and
// Playwright does not invoke route handlers for a hop inside a server redirect
// chain. The first version of `mintDefectiveLaunches` armed that glob, fired
// zero times, and every refusal case failed its own premise guard — which is
// the guard doing its job, and the reason it is there.
//
// The form's own POST to `/lti/login` is a request the browser originates, so
// it *is* routable, and the defect is applied to the `Location` that request
// answers with. See `mintDefectiveLaunches`.
export const LOGIN_URL_GLOB = 'http://localhost:8000/lti/login*';
export const DEFECT_QUERY_PARAM = 'defect';

// Where the mock serves the vocabulary of selectors it answers to, and the
// member the list lives under (E1 cleanup Batch B, item 3). Outside the OIDC
// namespace the way `/mock/posted-scores` sits outside the AGS one.
//
// **This is the one place a selector name is checked rather than assumed.**
// E1-07's deferred item 1: `app.wrong_launches.ALL_SELECTORS` cannot be imported
// by anything outside `mock-lms/` (both mocks' packages are called `app` — ADR
// 0039's collision), so this file and the integration suite each held a copy,
// and ADR 0088's consequences record that nothing enforced they move together.
// A stale name used to surface only when something dispatched it: the mock
// answers 400, no refusal page renders, and the spec fails on the page it was
// waiting for — a real failure, arriving as a timeout in the wrong place.
export const MOCK_DEFECTS_PATH = 'mock/defects';
export const SERVED_SELECTORS_MEMBER = 'selectors';

// Testids the mock LMS launch form publishes (`mock-lms/app/pages.py`).
export const LAUNCH_USER = 'mock-lms-login-hint';
export const LAUNCH_PLACEMENT = 'mock-lms-message-hint';
export const LAUNCH_SUBMIT = 'mock-lms-launch';

// Testids the mock IdP login form publishes (`mock-idp/app/pages.py`).
export const IDP_IDENTITY = 'mock-idp-identity';
export const IDP_SUBMIT = 'mock-idp-submit';

// Where the SPA keeps the session it lifted out of the fragment (E1-08,
// `frontend/src/lib/session.ts`; the key `web-login.spec.ts` and
// `cookieless-launch.spec.ts` both read).
export const SESSION_STORAGE_KEY = 'pulse.session';

// Every landing view the tool can render. Each entry is one of the five testids
// E0-18 established and `landing-views.spec.ts` pins; a spec that asserts a
// person reached one of them asserts the other four absent.
export const ALL_LANDINGS = [
  'pulse-landing-student',
  'pulse-landing-instructor',
  'pulse-landing-leadership',
  'pulse-landing-care',
  'pulse-landing-admin',
];

/**
 * The option values one of the mock forms currently offers.
 *
 * Read off the form rather than assumed, so a premise about who a door will let
 * in is an assertion with a message rather than a `selectOption` that times out
 * pointing at nothing.
 */
async function optionValues(page: Page, testid: string): Promise<string[]> {
  return page
    .getByTestId(testid)
    .evaluate((element) =>
      Array.from((element as HTMLSelectElement).options)
        .map((option) => option.value)
        .filter((value) => value.length > 0),
    );
}

/** The subjects the mock LMS launch page will sign a launch for right now. */
export async function launchSubjectsOffered(page: Page): Promise<string[]> {
  await page.goto(MOCK_LMS_ORIGIN);
  return optionValues(page, LAUNCH_USER);
}

/**
 * The placements the launch page offers **for one subject**, value and text.
 *
 * **The subject is selected first, and that ordering is the contract.** Since
 * E1-15 the page pairs each user with their own sections rather than offering
 * every user against every placement: the leadership subject is enrolled in one
 * section, and enrolling him in all three would put a sixth member in
 * `NURS-8100-Q2FF`, whose five are exactly one page and are what
 * `test_a_single_page_roster_advertises_first_last_and_current_and_no_next`
 * rests on. So the placement list is a function of the chosen user, and a read
 * taken before the user is chosen is a read of somebody else's list.
 *
 * This works whichever way the page expresses the pairing — a list rendered per
 * user, or one narrowed in the browser after the selection — because Playwright
 * drives a real one. The served-HTML form of the same property is asserted in
 * `tests/integration/test_mock_lms_launch.py`.
 */
export async function placementsOfferedTo(
  page: Page,
  subject: string,
): Promise<{ value: string; text: string }[]> {
  await page.goto(MOCK_LMS_ORIGIN);
  // The same guard `launchAs` makes, and it is here rather than only there
  // because both select a subject and either can meet a page that does not
  // offer one (`docs/MISTAKES.md` entry 13: one helper for the question, not a
  // workaround at one of the two sites facing it). Without it a missing person
  // is thirty seconds of `selectOption` timing out against a locator, which
  // reads as a broken harness — which is exactly how it read once.
  const offered = await optionValues(page, LAUNCH_USER);
  expect(
    offered,
    `The mock LMS launch page does not offer ${subject}, so it offers them no placements ` +
      `either. It offers ${JSON.stringify(offered)}.`,
  ).toContain(subject);
  await page.getByTestId(LAUNCH_USER).selectOption(subject);
  return page.getByTestId(LAUNCH_PLACEMENT).evaluate((element) =>
    Array.from((element as HTMLSelectElement).options)
      .map((option) => ({ value: option.value, text: option.textContent ?? '' }))
      .filter((option) => option.value.length > 0),
  );
}

/**
 * The placement value that launches `subject` into the section written `section`.
 *
 * **Discovered, not derived.** The platform prints the section on the option
 * itself — `mock-lms/app/pages.py` labels each placement
 * `"{context.label} — {placement.title}"` — so the section code a spec cares
 * about is matched against what the page says, and never assembled out of the
 * mock's identifier-naming scheme. A spec that built
 * `mock-lms-link-biol-215-r3ww-weekly-pulse` from a section code would be
 * holding a copy of the seed's spelling (`docs/MISTAKES.md` entry 19) and would
 * pass or fail on a renaming that has nothing to do with what it proves.
 *
 * Exactly one match is required. Two would mean the spec was launching into
 * whichever the page happened to list first, and none means this subject is not
 * offered that section — both are failures worth a sentence rather than a
 * silent first-of-list.
 */
export async function placementInto(
  page: Page,
  subject: string,
  section: string,
): Promise<string> {
  const offered = await placementsOfferedTo(page, subject);
  const matching = offered.filter((option) => option.text.includes(section));
  expect(
    matching,
    `The mock LMS launch page offers ${subject} ${matching.length} placements into ${section}; ` +
      'this spec needs exactly one, because a section is what a derived calendar and a roster ' +
      `both belong to. The page offers them ${JSON.stringify(offered)}.`,
  ).toHaveLength(1);
  return matching[0].value;
}

/**
 * Drive the mock LMS's launch form: pick a subject, pick a placement, submit.
 *
 * The `lti-launch.spec.ts:87-95` shape, with one addition: the offered subjects
 * are read and the chosen one required to be among them. Without that, a
 * subject the seed does not hold fails as a `selectOption` timeout naming a
 * locator, which reads as a broken harness and sends the next person to the
 * wrong place; with it, the failure names the person who is missing.
 *
 * `placement` is optional. Given, the launch uses that exact resource link;
 * omitted, it takes the first offered option — which is what a case that does
 * not care which section it launches from should do.
 */
export async function launchAs(page: Page, subject: string, placement?: string): Promise<void> {
  await page.goto(MOCK_LMS_ORIGIN);
  const offered = await optionValues(page, LAUNCH_USER);
  expect(
    offered,
    `The mock LMS launch page does not offer ${subject}. It offers ${JSON.stringify(offered)}. ` +
      'Since E1-15 the page offers `app.seed.launch_users()`, which returns the members of the ' +
      'written cast `LAUNCH_PAGE_CAST` that the seed actually enrolled — not everybody enrolled ' +
      'somewhere. The narrower rule is deliberate: "anybody enrolled in at least one context" ' +
      'would put E0-28’s windowless member on the page, which ' +
      '`test_the_windowless_member_is_an_active_student_away_from_the_add_and_drop_section` ' +
      'forbids. So a subject missing here is one the cast does not name, or one it names that ' +
      'the seed never enrolled.',
  ).toContain(subject);
  await page.getByTestId(LAUNCH_USER).selectOption(subject);
  await page
    .getByTestId(LAUNCH_PLACEMENT)
    .selectOption(placement === undefined ? { index: 0 } : placement);
  await page.getByTestId(LAUNCH_SUBMIT).click();
}

/**
 * Sign in at the mock IdP as one named subject (the `two-hat.spec.ts:37-39` shape).
 *
 * **By subject and not by role, deliberately.** `web-login.spec.ts:84-118`
 * finds a person by the role they hold, and that finder cannot reach either of
 * the two people E1-15 needs: it excludes anybody carrying a launch-only
 * assignment, which is exactly what makes the two-hat person the two-hat
 * person. Both subjects here are already pinned by name on the Pulse side —
 * `tests/integration/test_demo_seed_script.py::MOCK_WORLD_SUBJECTS` and
 * `tests/integration/test_dev_console.py`'s `DEAN_SUBJECT`/`TWO_HAT_SUBJECT` —
 * so a rename is a named failure in three places rather than a spec quietly
 * signing in as somebody else.
 */
export async function signInAs(page: Page, subject: string): Promise<void> {
  await page.goto(WEB_LOGIN_PATH);
  const offered = await optionValues(page, IDP_IDENTITY);
  expect(
    offered,
    `The mock IdP's login form does not offer ${subject}. It offers ${JSON.stringify(offered)}. ` +
      'The form lists the seeded web-login identities (ADR 0058), so a subject missing here is a ' +
      'person the demo world no longer publishes.',
  ).toContain(subject);
  await page.getByTestId(IDP_IDENTITY).selectOption(subject);
  await page.getByTestId(IDP_SUBMIT).click();
}

/**
 * The session token the SPA is holding, read at a point where the answer is settled.
 *
 * **The wait is the instrument, not a courtesy** — `web-login-cancel.spec.ts:76-97`
 * and `web-login.spec.ts:136-152` both say why, and this is the third place
 * facing the same hazard (`docs/MISTAKES.md` entry 13, which is why it is here
 * and not copied a third time). The SPA captures the token out of the fragment
 * and then strips it from the address bar, in that order, so a URL with no
 * `session=` in it is the observable proof that the capture effect has run.
 * Read before that edge — under six workers, where the bundle executes late —
 * and `sessionStorage` is legitimately still empty on an entry that succeeded.
 *
 * A refusal satisfies the edge trivially, having delivered no fragment at all,
 * and uses the same read anyway so that both answers are taken at one defined
 * point rather than at whichever moment each test happened to reach.
 */
export async function sessionToken(page: Page): Promise<string | null> {
  await expect(page).not.toHaveURL(/session=/);
  return page.evaluate((key) => window.sessionStorage.getItem(key), SESSION_STORAGE_KEY);
}

/**
 * The claims inside a compact JWS, decoded and **not verified**.
 *
 * A spec reads claims to say what a door decided; it does not trust them for
 * anything, and verifying here would mean this file holding a key. Used on the
 * app's own session token and, in `exit-roster-auth.spec.ts`, on the launch
 * `id_token` the platform posted — one question, one helper.
 */
export function sessionPayload(token: string): Record<string, unknown> {
  const segments = token.split('.');
  expect(
    segments.length,
    `A compact JWS has three dot-separated segments and this token has ${segments.length}: ` +
      `${JSON.stringify(token.slice(0, 40))}…`,
  ).toBe(3);
  const decoded: unknown = JSON.parse(Buffer.from(segments[1], 'base64url').toString('utf8'));
  expect(
    typeof decoded === 'object' && decoded !== null && !Array.isArray(decoded),
    'A JWS payload is a JSON object.',
  ).toBeTruthy();
  return decoded as Record<string, unknown>;
}

/**
 * Collect the `Location` of every response that hands this browser a session token.
 *
 * The `web-login-cancel.spec.ts:66-73` instrument, attached before the first
 * navigation so it sees the entry redirect itself. It is what makes "no session
 * was delivered" a reading off the wire rather than an inference from a page
 * that never navigated — and the specs using it show it finding a session on the
 * entry that succeeds, in the same file.
 *
 * **The cookie jar is deliberately not part of this.** On the dev stack the
 * tool's session and CSRF cookies are emitted `SameSite=None` without `Secure`,
 * and a browser refuses to store such a cookie at all, so the jar is empty after
 * a *successful* entry too and its emptiness proves nothing. That is
 * `cookieless-launch.spec.ts:27-41`'s finding and `web-login-cancel.spec.ts:24-30`'s
 * ruling, and reaching for the jar is the one way a refusal spec passes while a
 * session is being handed out.
 */
export function sessionsDelivered(page: Page): string[] {
  const delivered: string[] = [];
  page.on('response', (response) => {
    const location = response.headers()['location'];
    if (location !== undefined && location.includes('session=')) delivered.push(location);
  });
  return delivered;
}

/**
 * Collect the status of every response to a launch delivery, in order.
 *
 * The launch arrives as a form post to the tool, so the status a refusal answers
 * with is not the status of anything a spec navigated to itself.
 */
export function launchResponseStatuses(page: Page): number[] {
  const statuses: number[] = [];
  page.on('response', (response) => {
    if (response.url().startsWith(`${TOOL_ORIGIN}${LAUNCH_PATH}`)) statuses.push(response.status());
  });
  return statuses;
}

/**
 * Collect every `id_token` the platform's self-submitting form posts to the tool.
 *
 * This is the one seam by which a browser can learn what a launch actually
 * carried — LTI 1.3's `form_post` response keeps the token out of every URL, so
 * the request body is where it is. The integration suite discovers a section's
 * roster address exactly this way, off the launch's own NRPS claim
 * (`tests/fixtures/lti_services.py::SeededContext.memberships_url`), and
 * `exit-roster-auth.spec.ts` is the browser-side reader of the same fact.
 */
export function launchTokensDelivered(page: Page): string[] {
  const tokens: string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    if (!request.url().startsWith(`${TOOL_ORIGIN}${LAUNCH_PATH}`)) return;
    const body = request.postData();
    if (body === null) return;
    const token = new URLSearchParams(body).get('id_token');
    if (token !== null && token.length > 0) tokens.push(token);
  });
  return tokens;
}

/**
 * The defect selectors the mock platform says it answers to, fetched over HTTP.
 *
 * The served source E1-07's deferred item 1 asks for, read the way a consumer
 * outside `mock-lms/` has to read it. A spec asserts that the selector it is
 * about to drive is a member of this list, so a rename in
 * `app.wrong_launches.ALL_SELECTORS` fails at the name — naming both spellings —
 * rather than thirty seconds later at a page that never rendered.
 *
 * **Controlled by its own non-emptiness**, which is not ceremony: a route that
 * answered `{"selectors": []}`, or an object with the list under some other
 * member, would make every membership assertion below a comparison against
 * nothing, and every one of them would fail rather than pass — but they would
 * fail saying "this selector is not served", which points at the wrong file.
 * The assertion here is what points at this one.
 */
export async function servedDefectSelectors(page: Page): Promise<string[]> {
  const response = await page.request.get(`${MOCK_LMS_ORIGIN}${MOCK_DEFECTS_PATH}`);
  expect(
    response.status(),
    `GET ${MOCK_LMS_ORIGIN}${MOCK_DEFECTS_PATH} answered ${response.status()}. The mock serves ` +
      'its selector vocabulary there so that no consumer outside `mock-lms/` has to hold a copy ' +
      '(E1-07 deferred item 1).',
  ).toBe(200);
  const document: unknown = await response.json();
  const served =
    typeof document === 'object' && document !== null
      ? (document as Record<string, unknown>)[SERVED_SELECTORS_MEMBER]
      : undefined;
  expect(
    Array.isArray(served) && served.length > 0,
    `${MOCK_DEFECTS_PATH} served ${JSON.stringify(document)}. The shape is ` +
      `{"${SERVED_SELECTORS_MEMBER}": [...]}, non-empty — an empty list agrees with a stale ` +
      'name about nothing.',
  ).toBeTruthy();
  return served as string[];
}

/**
 * Make every launch this page begins select one of E1-07's mints.
 *
 * The mock's authorization route takes `?defect=<name>` on GET and POST
 * (`mock-lms/app/main.py`), and the launch is otherwise driven exactly as an
 * ordinary one — so the mint is built against a `state` and `nonce` the tool
 * genuinely issued, which is what makes the refusal a refusal of a real launch
 * rather than of a fabricated one. Same shape as
 * `tests/integration/test_lti_launch_door.py::mint_defect`.
 *
 * **How the selector gets onto the authorization request, and why not the
 * obvious way.** The obvious way does not work, and it failed silently in
 * exactly the manner a premise guard exists to catch: a route armed on the
 * authorization URL fires zero times, because the browser reaches that endpoint
 * by following the tool's own 302 and Playwright does not invoke route handlers
 * for a hop inside a server redirect chain. So the request that *is* routable
 * is intercepted instead — the launch form's own POST to `/lti/login`, which
 * the browser originates. Its answer is fetched with redirects switched off,
 * the defect is appended to the `Location` the tool built, and the 302 is
 * fulfilled with the rewritten address. The browser then navigates straight to
 * an authorization URL that already carries the selector, and no interception
 * of that hop is needed.
 *
 * Nothing about the launch changes but that one query parameter: the `state`
 * and `nonce` in the `Location` are the tool's own, untouched.
 *
 * **`defect` may be `null`, and that is the control.** With no defect armed the
 * handler takes the identical path — fetch, read the `Location`, fulfil — and
 * edits nothing, so a spec can prove the interception itself is harmless before
 * asking a spec to believe that a refusal came from the defect. Without that,
 * "the launch was refused" and "the harness broke the launch" look alike.
 *
 * Returns the list of authorization URLs it saw, which fills as the launch
 * proceeds; a rewritten one when a defect is armed, the tool's own when not.
 * A replay case needs that value: re-requesting the identical authorization URL
 * is what asks the platform for the identical signed bytes a second time.
 */
export async function mintDefectiveLaunches(
  page: Page,
  defect: string | null,
): Promise<string[]> {
  const rewritten: string[] = [];
  await page.route(LOGIN_URL_GLOB, async (route) => {
    const answered = await route.fetch({ maxRedirects: 0 });
    const location = answered.headers()['location'];
    if (location === undefined) {
      // Not a redirect, so there is no authorization request to steer. Pass the
      // answer through untouched rather than inventing one: a login initiation
      // the tool refused is a failure the spec should meet at its own assertion.
      await route.fulfill({ response: answered });
      return;
    }
    const url = new URL(location);
    if (defect !== null) url.searchParams.set(DEFECT_QUERY_PARAM, defect);
    rewritten.push(url.toString());
    await route.fulfill({
      response: answered,
      headers: { ...answered.headers(), location: url.toString() },
    });
  });
  return rewritten;
}

/**
 * The same URL, on the mock LMS's host-facing origin.
 *
 * The addresses a launch advertises are the ones the *tool* resolves, and on
 * Compose that is `http://mock-lms:8000` — a name only a container on that
 * network can resolve. Playwright runs on the host, where the same service is
 * published at `MOCK_LMS_ORIGIN` (`docker-compose.override.yml`). Only the
 * origin is swapped: the path, and so the context identifier inside it, stays
 * exactly what the platform advertised.
 */
export function onMockLmsHostOrigin(url: string): string {
  const advertised = new URL(url);
  const host = new URL(MOCK_LMS_ORIGIN);
  advertised.protocol = host.protocol;
  advertised.host = host.host;
  return advertised.toString();
}
