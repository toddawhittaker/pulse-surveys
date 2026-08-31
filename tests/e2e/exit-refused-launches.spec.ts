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
// **Which guard refuses, and a correction to what this comment used to claim.**
// It said the second delivery of a replay was probably refused for a *consumed
// handshake*, on the strength of
// `test_a_delivered_state_is_refused_on_replay_after_an_unrelated_refusal`. That
// test is about a state delivered once and **refused**; a launch that succeeded
// does not consume its state (`backend/app/lti/launch.py:325-327`), so the
// second delivery here reaches the nonce ledger and it is the replay guard that
// answers. The old note had the mechanism backwards and would have sent the
// battery at the wrong mutation.
//
// What the security review found in its place is sharper, and it was a gap in
// these tests rather than in the door: they asserted that a refusal page
// appeared and not whose guard produced it. A re-sent launch carrying the same
// nonce is caught by the ledger whether or not the mint handed back identical
// bytes — so deleting `wrong_launches.py`'s `reused_nonce` branch entirely left
// the replay case green, still refused, proving nothing about the mint it is
// named for.
//
// **Closed by asserting each guard's own reason**, which is the seam that tells
// them apart. Each case requires its own guard present *and* no other guard's —
// the second half is what would catch a page that printed every reason it knows,
// which would leave the first half true and meaningless.
//
// **Since E1's cleanup Batch B that reading is the marker, not the prose.** The
// refusal page carries `data-reason="<guard>"` — the firing
// `LaunchRefusedError` subclass's own class name, which was always the machine
// vocabulary and used to be discarded at the page's door. The old version of
// this file matched the guards' error sentences instead, which worked and cost
// what the note here used to admit it cost: a reword of an error message broke
// two exit specs, and the file said so in a paragraph explaining why that was
// acceptable. It is not acceptable now that there is a marker.
//
// So each case reads `[data-reason]` and requires **exactly one** of them,
// carrying its own guard's name. The count is the cross-guard negative
// assertion the sentence-absent check used to be, and it is stronger: it fails
// on a page that renders every guard it knows *and* on one that renders an
// empty marker.
//
// **One prose assertion is kept, deliberately, and it is the canary.** The
// replay case still matches `REPLAY_REASON`. Without it, error copy on this
// page would have nothing asserting it at all: the marker is a machine name and
// a page could carry the right one above a blank space, or above the wrong
// sentence, and every assertion here would pass. One case guards the copy; the
// rest read the marker.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect } from '@playwright/test';

import {
  SESSION_STORAGE_KEY,
  launchAs,
  launchResponseStatuses,
  mintDefectiveLaunches,
  servedDefectSelectors,
  sessionToken,
  sessionsDelivered,
} from './support/doors';

const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';
const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// E1-07's two selectors. They are still literals here — nothing outside
// `mock-lms/` can import `ALL_SELECTORS` (ADR 0039's collision) — but since E1's
// cleanup Batch B they are **checked**: each refusal case below asserts its
// selector is a member of the list the mock serves at `/mock/defects` before it
// arms anything. That is E1-07's deferred item 1, and it turns a rename into a
// failure that names both spellings instead of a page that never renders.
//
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

// The marker each guard puts on the page, and it is the guard's own class name.
// The ten `LaunchRefusedError` subclasses are the door's machine vocabulary —
// one per validate step, each already classified by which step raised — and
// `tests/integration/test_lti_launch_door.py`'s `DEFECT_GUARDS` is where the
// mapping from an E1-07 selector to the guard it fires is pinned on the Python
// side. `reused_nonce` is not in that mapping (a replay needs two deliveries, so
// it has its own test there), and the guard it fires is `NonceReplayedError` —
// the whole point of that test being that a replay is not the ordinary
// `NonceRefused` a missing or mismatched nonce gets.
//
// A rename of one of those classes breaks this file, which is the intended
// coupling and is a narrower one than the prose these assertions used to match:
// the class name is a published vocabulary a reader is meant to depend on, and
// an error sentence is copy somebody may reword on a Tuesday.
const REPLAY_GUARD = 'NonceReplayedError';
const TAMPERED_STATE_GUARD = 'StateRefused';

// What reads a marker off the page. An attribute selector rather than a testid,
// so nothing here pins which element carries it.
const REASON_MARKER = '[data-reason]';

// The one prose assertion kept as the copy canary — see the note at the top of
// this file for why exactly one is kept and why zero would be wrong.
//
// **Copied as whole source lines, which is the rule and not a formality**
// (`docs/MISTAKES.md` entry 3: build the sample by copying whole lines, the line
// the sentence starts on included — a sentence retyped from where you think it
// begins is the thing the sample exists to disprove). It is one sentence pair
// built from two adjacent literals in `backend/app/lti/replay_guard.py:76-79`,
// and the split below is written to mirror that source split — the first part
// ends with `and ` exactly as the source line does, so the join this assertion
// depends on is visible in this file rather than assumed.
const REPLAY_REASON =
  'This launch has already been delivered once. A launch nonce is single-use, and ' +
  'presenting the same signed launch a second time is refused.';

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

  // The control for the reason marker, and the other half of the pair the two
  // refusal cases below make: a launch nobody refused carries no guard name.
  // Without it, "this page carries exactly one marker naming my guard" could be
  // satisfied by a page that renders a marker unconditionally, and the count
  // assertions below would be measuring the template rather than the refusal.
  await expect(
    page.locator(REASON_MARKER),
    'a launch that landed carries a `data-reason` marker. Nothing refused it, so nothing should ' +
      'have named a guard — a marker rendered unconditionally makes both refusal cases below ' +
      'assertions about a constant.',
  ).toHaveCount(0);
});

test('a replayed launch is refused and delivers no second session', async ({ page }) => {
  const delivered = sessionsDelivered(page);
  const statuses = launchResponseStatuses(page);

  // Before anything is armed: the mock still answers to this name. A rename in
  // `ALL_SELECTORS` used to surface as a 400 nobody sees and a refusal page that
  // never renders, thirty seconds later, in an assertion about something else.
  expect(
    await servedDefectSelectors(page),
    `the mock platform does not serve the selector \`${REUSED_NONCE}\`, so the mint this case is ` +
      'named for cannot be selected and everything below would be about an ordinary launch',
  ).toContain(REUSED_NONCE);

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
    `no authorization address was rewritten to select \`${REUSED_NONCE}\`, so the route handler ` +
      'never fired and the second delivery below is not the mint this case is named for. It ' +
      'would still be a re-sent launch carrying the same nonce, and the door would still refuse ' +
      'it as a replay — so this guard alone cannot tell the two apart, and the reason assertion ' +
      'below is what does. This is also the guard that caught the first version of the helper, ' +
      'which armed a route on the authorization endpoint — a hop the browser reaches by ' +
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

  // **Whose guard refused, which is the assertion this case was missing.** A
  // re-sent launch carrying the same nonce is caught by the nonce ledger whether
  // or not the mint handed back identical bytes, so "a refusal page appeared"
  // stays true with `wrong_launches.py`'s `reused_nonce` branch deleted
  // altogether — refused, green, and proving nothing about the mint this case is
  // named for. The marker the page carries is what tells the guards apart.
  //
  // Exactly one marker, and it is the replay guard's. The count is what would
  // catch a page rendering every guard it knows, which would leave the name
  // assertion true and meaningless.
  await expect(
    page.locator(REASON_MARKER),
    'the refusal page carries no single `data-reason` marker, so nothing on it says which guard ' +
      'refused. More than one means the page names every guard it knows, and neither this case ' +
      'nor the tamper case could then tell one from another.',
  ).toHaveCount(1);
  await expect(
    page.locator(REASON_MARKER),
    `the refusal page does not name \`${REPLAY_GUARD}\`. Something refused this launch and it ` +
      'was not the nonce ledger — read the page before changing anything, because a refusal from ' +
      'a different guard here means the replay never reached the one this case is about.',
  ).toHaveAttribute('data-reason', REPLAY_GUARD);

  // The copy canary, and this file's only prose assertion. The marker above is
  // a machine name: a page could carry the right one over a blank space or over
  // the wrong sentence and every other assertion here would pass. This is what
  // keeps the words a refused person actually reads under guard.
  await expect(
    page.getByText(REPLAY_REASON),
    "the refusal page does not carry the replay guard's own sentence. The marker says the right " +
      'guard fired, so this is about the copy rather than the door: either the message was ' +
      'reworded — update the literal in this file and say so — or the page is naming a guard ' +
      'whose words it does not print.',
  ).toBeVisible();

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

  // Before anything is armed: the mock still answers to this name.
  expect(
    await servedDefectSelectors(page),
    `the mock platform does not serve the selector \`${TAMPERED_STATE}\`, so the mint this case ` +
      'is named for cannot be selected and everything below would be about an ordinary launch',
  ).toContain(TAMPERED_STATE);

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

  // Whose guard refused, the other half of the pair. The `state` this mint
  // returns is the tool's own with a suffix, so a door that looked its handshake
  // up by that value would refuse with "no such handshake" — a refusal, and the
  // wrong one. This is what distinguishes the guard that compared a `state` from
  // one that merely failed to find it.
  //
  // The count first: one marker, so a page naming every guard fails here rather
  // than satisfying the name assertion beneath it. This case carries no prose
  // assertion — the replay case above holds the file's one copy canary.
  await expect(
    page.locator(REASON_MARKER),
    'the refusal page carries no single `data-reason` marker, so nothing on it says which guard ' +
      'refused a launch whose `state` came back altered.',
  ).toHaveCount(1);
  await expect(
    page.locator(REASON_MARKER),
    `the refusal page does not name \`${TAMPERED_STATE_GUARD}\`. The launch was refused by ` +
      'something else — read the page: a refusal for a missing handshake, or for a signature, is ' +
      'not the same fact as a tool refusing a `state` it did not issue, and only the second is ' +
      'what SPEC §14.3 (E1) asks this case to prove.',
  ).toHaveAttribute('data-reason', TAMPERED_STATE_GUARD);

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
