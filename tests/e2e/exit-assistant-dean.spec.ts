// SPEC §14.3's E9 exit: "the assistant-dean worked example (§2.1) resolves
// correctly from either door". The demo institution's assistant dean supervises
// the Mathematics and Biology chairs and leads PSYC 110, in a department whose
// chair reports to the dean. So the roll-up's roots are Biology, Mathematics and
// the PSYC prefix, and PSYC holds PSYC 110 alone.
//
// **Two doors, one person.** The launch is made as `mock-lms-user-assistant-dean`
// and the web login as `mock-idp-user-assistant-dean`; `scripts/seed.py` links
// both to that person. Each door's tree is read from the roll-up route's own
// answer, then from the page, and the two answers must be equal.
//
// **The launch runs inside a frame, as the LMS embeds the tool**, and the switch
// and the logout run there too. In that frame the tool's cookies are never stored
// (`cookieless-launch.spec.ts` says why), so the session rides the Bearer header
// alone, and the switch and the logout are proved on that carrier.
//
// **The other role is the student view.** Both of the assistant dean's
// assignments open the leadership view; their launch subject is enrolled in
// `MATH-140-E1FF` as a learner (`mock-lms/app/seed.py`), so once the roster sync
// has enrolled them the launch door offers the student view as well.
//
// **The clock stands on the last day of the term the demo sections belong to**,
// read from the database. Inside the term, so the roll-up's current term is that
// term whatever the real date; and on or after any day the roster sync can have
// stamped the enrollment on, so the student view is live. It is cleared in
// `afterAll`. The drive adds no rows a rerun trips over: the enrollment is the
// mock roster's own, and the sessions it ends stay ended.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Frame, type Page, type Response } from '@playwright/test';

import { expectNoAxeViolations } from './support/axe';
import { clearTheClock, setTheClockTo } from './support/clock';
import {
  MOCK_LMS_ORIGIN,
  TOOL_ORIGIN,
  sessionPayload,
  sessionToken,
  signInAs,
} from './support/doors';
import { databaseStatement } from './support/stack';

// The wrapper's frame reaches the mock LMS on loopback, which Chromium's Local
// Network Access check blocks for a page fulfilled by `page.route`; the same
// switch `cookieless-launch.spec.ts` uses, for the same reason.
test.use({
  launchOptions: {
    args: ['--test-third-party-cookie-phaseout', '--disable-features=LocalNetworkAccessChecks'],
  },
});

const WEB_SUBJECT = 'mock-idp-user-assistant-dean';
const LAUNCH_SUBJECT = 'mock-lms-user-assistant-dean';
const LAUNCH_SECTION = 'MATH-140-E1FF';

const LEADERSHIP_VIEW = 'pulse-landing-leadership';
const STUDENT_VIEW = 'pulse-landing-student';
const SIGNED_OUT = 'pulse-signed-out';
const SESSION_STORAGE_KEY = 'pulse.session';
const PERSON_CLAIM = 'person_id';

const ROOTS = ['Biology', 'Mathematics', 'PSYC'];
const PSYCHOLOGY_ROOT = 'PSYC';
const PSYCHOLOGY_COURSES = ['PSYC 110 — Introduction to Psychology'];

// Governed copy, transcribed from `frontend/src/copy/landings.ts`.
const SWITCH_LABEL = 'Switch view';
const SWITCH_SUBMIT = 'Switch';
const SIGN_OUT = 'Sign out';

const WRAPPER_URL = `${TOOL_ORIGIN}/e2e-assistant-dean-wrapper`;
const ROLLUP_ROUTE = '/leadership/rollup?';
const LANDINGS_ROUTE = '/session/landings';

const CASE_TIMEOUT_MS = 240_000;
const SYNC_WAIT_MS = 150_000;

interface RollupNode {
  readonly kind: string;
  readonly name: string;
  readonly children: readonly RollupNode[];
}

interface RollupTree {
  readonly hierarchy: readonly RollupNode[];
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const lastDay = databaseStatement(
    "select to_char(t.end_date, 'YYYY-MM-DD') from term t " +
      "join section s on s.term_id = t.id where s.lms_section_code = 'S1FF';",
  );
  expect(lastDay, 'The demo term behind PSYC 110 S1FF could not be read.').toMatch(
    /^\d{4}-\d\d-\d\d$/,
  );
  const context = await browser.newContext();
  try {
    await setTheClockTo(await context.newPage(), `${lastDay}T12:00`);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await clearTheClock(await context.newPage());
  } finally {
    await context.close();
  }
});

/** The roll-up route's answer, caught as the page asks for it. */
function theRollupAnswer(page: Page): Promise<Response> {
  return page.waitForResponse(
    (response) => response.url().includes(ROLLUP_ROUTE) && response.request().method() === 'GET',
  );
}

/** Root names and the Psychology root's children, as the payload states them. */
function shapeOf(tree: RollupTree): { roots: string[]; psychology: string[] } {
  const psychology = tree.hierarchy.find((node) => node.name === PSYCHOLOGY_ROOT);
  return {
    roots: tree.hierarchy.map((node) => node.name),
    psychology: (psychology?.children ?? []).map((node) => node.name),
  };
}

/** The tree as the page draws it: root names, then the Psychology root opened. */
async function expectTheDrawnTree(where: Page | Frame): Promise<void> {
  const roots = where.locator('nav.pulse-hierarchy > ul.pulse-hierarchy-list > li');
  await expect(roots.locator(':scope > div .pulse-hierarchy-select .pulse-hierarchy-name')).toHaveText(
    ROOTS,
  );
  const psychology = roots.filter({
    has: where.locator(':scope > div .pulse-hierarchy-name', { hasText: PSYCHOLOGY_ROOT }),
  });
  await psychology.locator(':scope > div button.pulse-hierarchy-toggle').click();
  await expect(
    psychology.locator(':scope > ul > li > div .pulse-hierarchy-select .pulse-hierarchy-name'),
  ).toHaveText(PSYCHOLOGY_COURSES);
}

/** Open the mock LMS in a frame, as an LMS embeds the tool, and launch the assistant dean. */
async function launchInAFrame(page: Page): Promise<Frame> {
  await page.route(WRAPPER_URL, (route) =>
    route.fulfill({
      contentType: 'text/html',
      body:
        '<!doctype html><html lang="en"><head><title>LMS</title></head><body><main>' +
        `<iframe title="lms" src="${MOCK_LMS_ORIGIN}" width="1000" height="800"></iframe>` +
        '</main></body></html>',
    }),
  );
  await page.goto(WRAPPER_URL);
  const lms = page.frameLocator('iframe[title="lms"]');
  await lms.getByTestId('mock-lms-login-hint').selectOption(LAUNCH_SUBJECT);
  const placement = lms.getByTestId('mock-lms-message-hint');
  await expect(placement.locator('option')).toHaveText([new RegExp(LAUNCH_SECTION)]);
  await placement.selectOption({ index: 0 });
  await lms.getByTestId('mock-lms-launch').click();
  const frame = page.frames().find((candidate) => candidate !== page.mainFrame());
  if (frame === undefined) throw new Error('The launch frame was lost after the launch.');
  return frame;
}

/** The frame's own session token. */
async function frameToken(frame: Frame): Promise<string> {
  await expect.poll(() => frame.url()).not.toContain('session=');
  const token = await frame.evaluate(
    (key) => window.sessionStorage.getItem(key),
    SESSION_STORAGE_KEY,
  );
  expect(token, 'The launch handed the frame no session.').not.toBeNull();
  return token ?? '';
}

/** `GET /session/landings` with one token, from outside every page. */
async function landingsWith(page: Page, token: string): Promise<{ status: number; body: unknown }> {
  const answer = await page.request.get(LANDINGS_ROUTE, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
  return { status: answer.status(), body: answer.ok() ? await answer.json() : null };
}

/** Let the frame's finite animations end before a scan measures its colours. */
async function settled(frame: Frame): Promise<void> {
  await frame.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) =>
          Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity),
        )
        .map((animation) => animation.finished.catch(() => undefined)),
    );
  });
}

/** Choose a view in the frame's switcher and wait for its landing. */
async function switchTo(frame: Frame, view: string, landing: string): Promise<void> {
  await frame.getByLabel(SWITCH_LABEL).selectOption(view);
  await frame.getByRole('button', { name: SWITCH_SUBMIT, exact: true }).click();
  await expect(frame.getByTestId(landing)).toBeVisible();
}

test('the assistant dean sees the same tree from the launch and from web login', async ({
  page,
  browser,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  // The launch first: it may provision MATH-140-E1FF, and a section provisioned
  // between the two reads would make two correct trees differ.
  const launchedAnswer = theRollupAnswer(page);
  const frame = await launchInAFrame(page);
  await expect(frame.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  const launchedTree = (await (await launchedAnswer).json()) as RollupTree;
  expect(shapeOf(launchedTree)).toEqual({ roots: ROOTS, psychology: PSYCHOLOGY_COURSES });
  await expectTheDrawnTree(frame);
  await settled(frame);
  await expectNoAxeViolations(page, 'The roll-up in the launch frame');

  const context = await browser.newContext();
  try {
    const web = await context.newPage();
    const webAnswer = theRollupAnswer(web);
    await signInAs(web, WEB_SUBJECT);
    await expect(web.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
    const webTree = (await (await webAnswer).json()) as RollupTree;
    expect(shapeOf(webTree)).toEqual({ roots: ROOTS, psychology: PSYCHOLOGY_COURSES });
    expect(webTree, 'The two doors answered different trees.').toEqual(launchedTree);
    await expectTheDrawnTree(web);
    await expectNoAxeViolations(web, 'The roll-up after web login');

    // Both sessions name one person.
    const webToken = await sessionToken(web);
    expect(webToken, 'The web login handed the page no session.').not.toBeNull();
    const webPerson = sessionPayload(webToken ?? '')[PERSON_CLAIM];
    expect(webPerson, 'The web session names no person.').toBeTruthy();
    expect(sessionPayload(await frameToken(frame))[PERSON_CLAIM]).toBe(webPerson);
  } finally {
    await context.close();
  }
});

test('from the launch, the assistant dean switches to the student view and back, then signs out', async ({
  page,
}) => {
  test.setTimeout(CASE_TIMEOUT_MS);

  const frame = await launchInAFrame(page);
  await expect(frame.getByTestId(LEADERSHIP_VIEW)).toBeVisible();
  const launched = await frameToken(frame);

  // The roster sync the launch asked for enrols them in MATH-140-E1FF; until it
  // has, the launch door offers the leadership view alone.
  await expect
    .poll(
      async () => {
        const answer = await landingsWith(page, launched);
        return answer.status === 200
          ? ((answer.body as { landings: string[] }).landings ?? [])
          : [`status ${String(answer.status)}`];
      },
      {
        message: `The roster sync never enrolled ${LAUNCH_SUBJECT} in ${LAUNCH_SECTION}.`,
        timeout: SYNC_WAIT_MS,
        intervals: [2_000, 5_000],
      },
    )
    .toEqual(['leadership', 'student']);

  // A fresh load, so the shell reads the views the server now offers.
  await frame.goto(frame.url());
  await expect(frame.getByTestId(LEADERSHIP_VIEW)).toBeVisible();

  await switchTo(frame, 'student', STUDENT_VIEW);
  await settled(frame);
  await expectNoAxeViolations(page, 'The student view after the switch');
  const asStudent = await frameToken(frame);
  expect(asStudent).not.toBe(launched);

  await switchTo(frame, 'leadership', LEADERSHIP_VIEW);
  const backAgain = await frameToken(frame);
  expect(backAgain).not.toBe(asStudent);
  expect((await landingsWith(page, backAgain)).status).toBe(200);

  await frame.getByRole('button', { name: SIGN_OUT, exact: true }).click();
  await expect(frame.getByTestId(SIGNED_OUT)).toBeVisible();
  await settled(frame);
  await expectNoAxeViolations(page, 'The signed-out state');

  // Every session the drive held is refused now: the signed-out one, and the two
  // each switch replaced.
  for (const token of [backAgain, asStudent, launched]) {
    expect((await landingsWith(page, token)).status).toBe(401);
  }
});
