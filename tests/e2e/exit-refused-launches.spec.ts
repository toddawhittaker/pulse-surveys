// E1-15, exit clause 4 — SPEC §14.3, E1: "a replayed or state/nonce-tampered
// launch is refused".
//
// **Driven in a real browser, through E1-07's mints.** The mock platform's
// authorization route takes `?defect=<name>` and answers with a launch that is
// wrong in exactly one way (`mock-lms/app/wrong_launches.py` — one defect per
// mint, always, so a refusal names one guard). The launch is otherwise driven
// exactly as an ordinary one and the defect is applied to the authorization
// request the tool itself built, so every mint below rests on a `state` and a
// `nonce` the tool genuinely issued. That is the difference between refusing a
// real launch and refusing a fabrication: the same shape
// `tests/integration/test_lti_launch_door.py::mint_defect` uses.
//
// **The interception is on `/lti/login`, not on the authorization endpoint, and
// the first version of this file had it wrong.** A route armed on
// `http://localhost:8080/oidc/authorize*` fired zero times — the browser reaches
// that endpoint by following the tool's 302, and Playwright does not invoke
// route handlers for a hop inside a server redirect chain. Both refusal tests
// failed their own premise guard rather than passing over an un-defected launch,
// which is the only reason the mistake cost a re-run instead of a false green
// (`docs/MISTAKES.md` entry 3 — the guard that says the instrument is blind).
// `support/doors.ts::mintDefectiveLaunches` now intercepts the launch form's own
// POST, which the browser originates and Playwright therefore routes, and edits
// the `Location` it answers with.
//
// **The two selectors are literals, and that is a recorded cost.** E1-07's
// deferral 1 (`docs/tickets/e1/deferred.md`) says the defect vocabulary has no
// served source: nothing outside `mock-lms/` can import `ALL_SELECTORS`, so the
// integration suite holds one copy and this file is the next. A stale literal
// fails loudly rather than quietly — the dispatcher answers 400 to a name it
// does not recognise, no refusal page is rendered, and the assertions below fail
// on the page they were waiting for.
//
// **How the absence of a session is asserted, and how it is not.** The trap in
// asserting an absence in a browser is that almost everything is absent when
// nothing happened (`docs/MISTAKES.md` entry 2 asks for the forbidden state;
// entry 3 asks that the instrument be shown finding it). So two instruments are
// used and each is shown finding a session on a delivery that succeeds:
//
//   - every response's `Location` is collected, and a `#session=` fragment must
//     never appear in one after a refusal — "the session was never delivered",
//     read off the wire;
//   - the SPA's `sessionStorage` key must be empty — "the session was never
//     captured", read where E1-08 puts it.
//
// The first test is the control for both, and the replay case below is a second
// control in itself: its first delivery succeeds, both instruments find the
// session, and only then is the replay made.
//
// **The cookie jar is deliberately not consulted.** On the dev stack the tool's
// session and CSRF cookies are emitted `SameSite=None` without `Secure`, and a
// browser refuses to store such a cookie at all — so the jar is empty after a
// *successful* launch too, and its emptiness proves nothing. That is
// `cookieless-launch.spec.ts:27-41`'s finding and `web-login-cancel.spec.ts:24-30`'s
// ruling; asserting on it here would be the one way this file passes while a
// session is being handed out.
//
// **A note for whoever runs the weakened-guard battery (acceptance criterion 2).**
// Neither refusal below is guaranteed to isolate the single guard the battery's
// table names, and pretending otherwise would be `docs/MISTAKES.md` entry 9
// wearing a green tick:
//
//   - the *replay* case delivers the identical signed artifact a second time.
//     The tool's launch handshake is single-use server side — that is what
//     `test_a_delivered_state_is_refused_on_replay_after_an_unrelated_refusal`
//     proves — so the second delivery may be refused for a consumed handshake
//     before any nonce-replay check is reached. Disabling the nonce-replay
//     refusal *alone* may therefore leave this green. The mutation that makes it
//     red is the replay refusal as a whole: a door that will accept a handshake
//     it has already consumed.
//   - the *tamper* case returns a `state` that is the real one with a suffix
//     appended. If the door looks a handshake up **by** that value, a tampered
//     state is refused as "no such handshake" and disabling a separate
//     comparison changes nothing. The mutation that makes it red is a door that
//     accepts a `state` it did not issue.
//
// Both are findings about the mutations, not about the clause: what this file
// asserts is the criterion — the launch is refused, and no session exists
// afterwards.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from '@playwright/test';

import {
  SESSION_STORAGE_KEY,
  launchAs,
  launchResponseStatuses,
  mintDefectiveLaunches,
  sessionToken,
  sessionsDelivered,
} from './support/doors';

const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';
const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// E1-07's two selectors, copied whole from `mock-lms/app/wrong_launches.py`.
// `reused_nonce` hands back the identical signed bytes for a `nonce` it has
// already minted for; `tampered_state` signs a correct token and echoes a
// `state` that is the tool's own with a suffix appended.
const REUSED_NONCE = 'reused_nonce';
const TAMPERED_STATE = 'tampered_state';

// What the tool shows somebody whose launch was refused, and the status it
// answers the delivery with.
const REFUSAL_VIEW = 'pulse-entry-refused';
const REFUSAL_HEADING = 'This did not open';
const REFUSAL_STATUS = 400;

test('an undefected launch lands on the instructor view and hands over a session', async ({
  page,
}) => {
  // The control, and the two refusal cases are worth nothing without it. If a
  // spec whose launch never happened can report "no session delivered, nothing
  // stored", so can one whose page failed to navigate — this is what tells the
  // two apart (`docs/MISTAKES.md` entry 35: require the instrument to find the
  // thing on a subject that certainly has it). It is also the control on the
  // shared helpers in `support/doors.ts`, over the same flow `lti-launch.spec.ts`
  // proves green on every CI run.
  const delivered = sessionsDelivered(page);
  const statuses = launchResponseStatuses(page);

  // Armed with **no defect**, so this launch runs through the identical
  // interception the two refusal cases run through and has nothing edited. That
  // is what separates "the defect caused the refusal" from "the harness broke
  // the launch" — two states that look the same from a browser, and the second
  // of which is what actually happened the first time this file was run.
  const rewritten = await mintDefectiveLaunches(page, null);

  await launchAs(page, INSTRUCTOR_SUBJECT);

  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();
  expect(
    rewritten,
    'the POST to /lti/login was not intercepted, so the two refusal cases below are driving ' +
      'un-defected launches and their premise guards are the only thing standing between that ' +
      'and a false green',
  ).not.toHaveLength(0);
  expect(
    delivered.length,
    'a completed launch must deliver its session in a Location fragment; if this is zero the ' +
      'collector sees nothing and both refusal cases prove nothing',
  ).toBeGreaterThan(0);
  expect(
    await sessionToken(page),
    'a completed launch leaves the session in sessionStorage; if this is null the read is blind ' +
      'and both refusal cases prove nothing',
  ).not.toBeNull();
  expect(
    statuses.filter((status) => status === REFUSAL_STATUS),
    'an undefected launch must not be refused; if it is, the refusal assertions below are about ' +
      'a door that refuses everything',
  ).toHaveLength(0);
});

test('a replayed launch is refused and delivers no second session', async ({ page }) => {
  const delivered = sessionsDelivered(page);
  const statuses = launchResponseStatuses(page);

  // Every launch this page begins now selects `reused_nonce`. The first request
  // for a given `nonce` mints a correct token and remembers it; every later
  // request carrying that same `nonce` is handed the identical bytes back. So
  // the replay is made by asking for the *same* authorization URL twice — same
  // `state`, same `nonce`, byte-identical `id_token` — which is a launch
  // artifact delivered twice rather than a second launch that happens to look
  // similar.
  const rewritten = await mintDefectiveLaunches(page, REUSED_NONCE);

  await launchAs(page, INSTRUCTOR_SUBJECT);

  // Positive first, three times over, and each one closes a way this test could
  // pass while proving nothing.
  expect(
    rewritten,
    `no authorization address was rewritten to select \`${REUSED_NONCE}\`, so nothing below is a ` +
      'replay: the route handler never fired, and the "refusal" would be an ordinary launch ' +
      'failing for an unrelated reason. This is the guard that caught the first version of the ' +
      'helper, which armed a route on the authorization endpoint — a hop the browser reaches by ' +
      'following a redirect, and one Playwright does not route.',
  ).not.toHaveLength(0);
  await expect(
    page.getByTestId(INSTRUCTOR_VIEW),
    'the first delivery of a `reused_nonce` mint is a correct launch and must land normally — ' +
      'that is what makes the second delivery a replay rather than a second wrong launch',
  ).toBeVisible();
  expect(
    delivered.length,
    'the first delivery handed over no session, so the "no second session" assertion below would ' +
      'be comparing an absence with an absence',
  ).toBeGreaterThan(0);

  // Everything the legitimate first entry left behind is set aside, so that
  // anything found after the replay was delivered by the replay. The wire
  // instrument is read as a count rather than cleared, which is the stronger of
  // the two: it cannot be emptied by anything this spec does to the page.
  const deliveredBeforeReplay = delivered.length;
  await page.evaluate((key) => window.sessionStorage.removeItem(key), SESSION_STORAGE_KEY);

  // The replay: the identical authorization request, answered with the identical
  // signed bytes, delivered to the tool a second time. `waitUntil: 'commit'`
  // because the platform's response is a self-submitting form — the navigation
  // this starts is immediately replaced by the form's own POST.
  await page.goto(rewritten[0], { waitUntil: 'commit' });

  // Positive first: this waits for the refusal page to render, so the absences
  // below are about a finished navigation (`docs/MISTAKES.md` entry 3).
  await expect(
    page.getByTestId(REFUSAL_VIEW),
    'a replayed launch reached no refusal page. SPEC §14.3 (E1) requires a replayed launch to be ' +
      'refused; a door that accepted this one accepted a launch artifact it had already spent.',
  ).toBeVisible();
  await expect(page.getByText(REFUSAL_HEADING)).toBeVisible();
  expect(
    statuses,
    'the replayed delivery was not answered with a client error; the statuses the tool answered ' +
      'its launch deliveries with are listed here in order',
  ).toContain(REFUSAL_STATUS);

  expect(
    delivered.length,
    'a response carried a session token in its Location after the replay. The token is how this ' +
      'tool hands a session to a browser, and a replayed launch must hand over nothing.',
  ).toBe(deliveredBeforeReplay);
  expect(
    await sessionToken(page),
    'the SPA holds a session after a replayed launch. The control test above shows this same ' +
      'read finding one when a launch succeeds, so an empty answer here is a refusal rather than ' +
      'a blind instrument.',
  ).toBeNull();
});

test('a state-tampered launch is refused and no session is ever delivered', async ({ page }) => {
  const delivered = sessionsDelivered(page);
  const statuses = launchResponseStatuses(page);

  // `tampered_state` signs a perfectly correct `id_token` and returns a `state`
  // that is the tool's own with a suffix appended — so the only thing wrong with
  // this launch is the value that ties it to the request the tool started. That
  // is the near miss worth having: everything a signature check looks at is
  // right.
  const rewritten = await mintDefectiveLaunches(page, TAMPERED_STATE);

  await launchAs(page, INSTRUCTOR_SUBJECT);

  expect(
    rewritten,
    `no authorization address was rewritten to select \`${TAMPERED_STATE}\`, so this launch was ` +
      'an ordinary one and its refusal — or its success — says nothing about a tampered `state`',
  ).not.toHaveLength(0);

  // Positive first: wait for the refusal page.
  await expect(
    page.getByTestId(REFUSAL_VIEW),
    'a launch whose `state` came back altered reached no refusal page. The `state` is what ties a ' +
      'delivered launch to the request this tool began; a door that accepts one it did not issue ' +
      'has no cross-site request forgery defence on its launch endpoint at all.',
  ).toBeVisible();
  await expect(page.getByText(REFUSAL_HEADING)).toBeVisible();
  expect(
    statuses,
    'the tampered delivery was not answered with a client error; the statuses the tool answered ' +
      'its launch deliveries with are listed here in order',
  ).toContain(REFUSAL_STATUS);

  expect(
    delivered,
    'no response in a refused launch may carry a session token in its Location — the token is how ' +
      'this tool hands a session to a browser, and nothing was signed in',
  ).toEqual([]);
  expect(
    await sessionToken(page),
    'the SPA holds a session after a refused launch. The control test at the top of this file ' +
      'shows this same read finding one when a launch succeeds.',
  ).toBeNull();
});
