// E0-18 PR 2 — the proof, flow 1 and 2: what an LTI launch lands on.
//
// **Rewritten for E1-13, and the header is rewritten with it.** This comment used
// to read "the landing role is derived from the verified token's roles claim
// alone", which was true and is the model E1-13 retires. The landing now comes
// from the launching person's own live assignments, filtered by ADR 0026's
// `permits_launch` column, with enrollment as the student fallback (ADR 0028);
// no roles claim, in either vocabulary, has any say in which view a person
// reaches. That is the same one-level-up correction E1-13 made to the section
// header in tests/integration/test_web_login_door.py — a record left asserting
// the retired model is how the next reader learns the wrong rule.
//
// What the two cases prove now:
//
//   - **An Instructor launch reaches the instructor view**, because the seeded
//     mock-world person behind that subject holds a live INSTRUCTOR assignment.
//     This case is unchanged and is now a stronger witness than it was: it used
//     to show a claim being routed and now shows an assignment being resolved.
//   - **A Learner launch reaches the student view once the roster sync has
//     enrolled them** — the browser witness for the other half of E1-13's rule,
//     ADR 0028's enrollment fallback, over the whole live path that produces it.
//
// **Why the Learner case has to drive a staff launch of its own first.** A
// student's access resolves from `enrollment` (ADR 0028); enrollment rows are
// written by E1-11's roster sync; the sync is discovered from a roster address a
// launch stores; and a **student** launch stores none and triggers nothing (SPEC
// §7.3 — instructors and leadership only). So the ordering is staff launch →
// sync → student launch, and the case drives all three rather than inheriting the
// first from whichever test ran before it.
//
// An earlier version of this case asserted the opposite — that a Learner launch
// on a "fresh stack" reaches the calm no-access page — and it failed for the best
// possible reason: the Instructor case below had already triggered the sync, the
// worker wrote the mock roster's enrollments within seconds, and the Learner
// landed on `/app/student` by enrollment. "Fresh stack" was a premise this very
// file falsifies, and CI's gate has the same dynamics. The system was doing
// exactly what E1-11 and E1-13 built. The lesson is worth keeping: a premise
// about global state that the suite itself can change is not a premise, and the
// fix was a different assertion rather than a repair.
//
// **The deterministic no-access states are asserted in the integration suite**,
// where a test owns the rows and nothing races it —
// tests/integration/test_landing_resolves_from_assignments.py has the launch and
// web-login cases for a person with no assignment and no enrollment, and both
// enrollment edges. Nothing here needs to re-prove them against a worker.
// **E1-15 still owns the five-clause exit proof.**
//
// Falsification (the changes that must turn these red): a resolution that stopped
// consulting enrollment lands the Learner nowhere and fails the first case, and a
// sync that never enrolled anybody fails it the same way — the failure message
// names both, because from a browser they look alike. A door that stopped
// resolving assignments, or filtered them by the wrong permission column, lands
// the instructor on the calm page and fails the second. A door that rendered a
// single fixed answer for every launch fails one or the other.
//
// This spec cannot be run without the implementer's Playwright harness
// (package.json, playwright.config.ts, baseURL) and a seeded, running Compose
// stack.

import { test, expect, Page } from '@playwright/test';

// Settled fact (E0-18 ticket + docker-compose.override.yml): the mock LMS serves
// its launch page at this browser-facing origin. baseURL — the tool, on
// http://localhost:8000 — comes from playwright.config.ts and is not repeated here.
const MOCK_LMS_ORIGIN = 'http://localhost:8080/';

// Testids the mock LMS launch form publishes (mock-lms/app/pages.py) and the
// tool's landing views publish. Named once so a rename is one line, not a search.
const LAUNCH_USER = 'mock-lms-login-hint';
const LAUNCH_PLACEMENT = 'mock-lms-message-hint';
const LAUNCH_SUBMIT = 'mock-lms-launch';

// `placement` is optional: given, the launch uses that exact resource link;
// omitted, it takes the first offered option. The Learner case below needs both
// of its launches pinned to one section and so passes a value; the Instructor
// case does not care which section it launches from and does not.
//
// Reading the offered value rather than writing a `resource_link_id` here keeps
// this from encoding a section identifier the seed may renumber.
//
// "A placement the mock offers" is not "a row in Pulse's `enrollment` table",
// and since E1-13 the difference decides where a launch lands. The mock's
// placements are what a platform lets somebody launch *from*; enrollment is
// Pulse's own record of who is in a section, written by the roster sync, and it
// is what the student fallback reads. The Learner case turns on exactly that
// gap, which is why it drives the sync that closes it.
async function launchAs(page: Page, subject: string, placement?: string): Promise<void> {
  await page.goto(MOCK_LMS_ORIGIN);
  // Subject by its settled value (the option's wire value is the user_id).
  await page.getByTestId(LAUNCH_USER).selectOption(subject);
  await page
    .getByTestId(LAUNCH_PLACEMENT)
    .selectOption(placement === undefined ? { index: 0 } : placement);
  await page.getByTestId(LAUNCH_SUBMIT).click();
}

// The placements the launch page offers for one subject, read off the form.
async function placementsOfferedTo(page: Page, subject: string): Promise<string[]> {
  await page.goto(MOCK_LMS_ORIGIN);
  await page.getByTestId(LAUNCH_USER).selectOption(subject);
  return page
    .getByTestId(LAUNCH_PLACEMENT)
    .evaluate((element) =>
      Array.from((element as HTMLSelectElement).options)
        .map((option) => option.value)
        .filter((value) => value.length > 0),
    );
}

const LEARNER_SUBJECT = 'mock-lms-user-learner';
const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';
const STUDENT_VIEW = 'pulse-landing-student';
const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// How long the Learner case keeps re-launching while it waits for the sync
// worker, and how long it leaves between attempts. Chosen against **worker
// latency**, which is seconds: the observed sequence writes the roster's
// enrollments within a few seconds of the staff launch that triggers it, and
// thirty seconds is far above that with room for a loaded CI box.
//
// **This is not docs/MISTAKES.md entry 7** — a verification window equal to the
// thing's own debounce — and the difference is worth stating rather than
// assuming. The sync's five-minute debounce governs how often a *staff* launch
// re-triggers it. Every retry below is a **student** launch, which triggers
// nothing (SPEC §7.3); the single staff launch above them did the triggering,
// once. So this window is not waiting out a debounce, and it is deliberately far
// below one: were it ever mistaken for a debounce wait it would be too short to
// work, which is the failure direction that reports itself.
const SYNC_TIMEOUT_MS = 30_000;
const SYNC_RETRY_MS = 3_000;

// How long one attempt gives the landed page to paint before reading it. The
// launch answers with a redirect and the SPA renders the view after hydrating,
// so a read taken the instant `launchAs` resolves is a read taken before there
// is anything to see — which is the race that failed this case once already:
// the timeout snapshot showed "Your weekly check-in" on screen while the
// predicate had measured zero, because every attempt counted and immediately
// navigated away.
//
// Two seconds is far above hydration and short against `SYNC_RETRY_MS`, so a
// genuine not-yet-enrolled attempt still costs about the same as it did and the
// window stays a wall-clock thirty seconds. The calm page never grows this
// testid, so an attempt that really did reach no-access waits the full two
// seconds, returns nothing found, and retries — which is the behaviour this
// case needs while the worker is still working.
const RENDER_WAIT_MS = 2_000;

test('a Learner launch lands on the student view once the roster sync has enrolled them', async ({
  page,
}) => {
  // The poll alone may spend `SYNC_TIMEOUT_MS`, and two placement reads and a
  // staff launch run before it. Playwright's default per-test timeout is below
  // that sum, so a case that needed its full budget would fail on the harness
  // rather than on its assertion — a failure that reads as a flake and sends
  // whoever meets it looking in the wrong place.
  test.setTimeout(SYNC_TIMEOUT_MS + 60_000);

  // Both launches are pinned to one placement, chosen explicitly and shared. A
  // sync is discovered per section, so a staff launch into section A enrolls
  // nobody in section B — and taking each subject's *first* offered option would
  // silently do exactly that if the two lists differ. Requiring a shared value
  // makes "the same section" an assertion rather than an assumption.
  const staffPlacements = await placementsOfferedTo(page, INSTRUCTOR_SUBJECT);
  const learnerPlacements = await placementsOfferedTo(page, LEARNER_SUBJECT);
  const shared = staffPlacements.filter((value) => learnerPlacements.includes(value));
  expect(
    shared,
    'the launch page should offer at least one placement to both the instructor and the learner; ' +
      'without one this case cannot sync the section it then launches a student into',
  ).not.toHaveLength(0);
  const placement = shared[0];

  // The trigger, driven here rather than inherited from whichever test ran
  // first. SPEC §7.3: a launch by an instructor stores the roster service
  // address, which is the whole of what gives the scheduled sync its discovery.
  // Landing her is the control on it — a staff launch that was refused, or that
  // reached the calm page, provisioned no section and stored no address, and the
  // poll below would then be waiting for a sync nobody asked for.
  //
  // If an earlier test already triggered this section's sync inside the
  // five-minute debounce, this launch is debounced and the enrollments are
  // already there, so the poll succeeds on its first attempt. The debounce can
  // only make this case faster, never slower.
  await launchAs(page, INSTRUCTOR_SUBJECT, placement);
  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();

  // Re-launching is legal: each attempt runs the whole login handshake and gets
  // a fresh `state` and `nonce`, so a repeat is a new launch rather than a
  // replay. The *launch* is what is polled, and it has to be: the answer is
  // decided server-side at launch time, so a page that already rendered the calm
  // page would never become a student view on its own however long it were
  // watched.
  //
  // The bounded `waitFor` inside the attempt is not a second poll — it lets the
  // answer this attempt already produced finish painting before it is read.
  // Without it the read is instantaneous, lands between the redirect and the
  // SPA's hydration, and reports nothing found for an attempt that had in fact
  // succeeded; the retry then navigates away and repeats the identical race, so
  // the poll can never observe the render it causes. That is what this case
  // failed on once, with the student view on screen in the timeout snapshot.
  await expect
    .poll(
      async () => {
        await launchAs(page, LEARNER_SUBJECT, placement);
        try {
          await page
            .getByTestId(STUDENT_VIEW)
            .waitFor({ state: 'visible', timeout: RENDER_WAIT_MS });
          return 1;
        } catch {
          return 0;
        }
      },
      {
        message:
          'a Learner launch never reached the student view. Two causes look identical from a ' +
          'browser and this is the place to tell them apart: either the roster sync never ran, ' +
          'so no `enrollment` row exists for this subject in the section the staff launch above ' +
          'provisioned — check the worker, and that the staff launch stored a roster address — ' +
          'or the landing resolution stopped consulting enrollment, in which case a person whose ' +
          'only claim on a view is ADR 0028 has lost it, and the enrollment cases in ' +
          'tests/integration/test_landing_resolves_from_assignments.py will say which edge broke.',
        timeout: SYNC_TIMEOUT_MS,
        intervals: [SYNC_RETRY_MS],
      },
    )
    .toBeGreaterThan(0);

  // She landed as a student and not as anything else. The all-five sweep this
  // case used to carry is gone with the premise it rested on — she lands one of
  // them now — but a door rendering two views at once is still worth catching,
  // and this is the same absence check the Instructor case below makes.
  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toHaveCount(0);
});

test('an Instructor launch lands on the instructor view and nothing else', async ({ page }) => {
  await launchAs(page, 'mock-lms-user-instructor');
  // Positive assertion first: getByTestId(...).toBeVisible() waits for the
  // correct landing to render, so the absence check below cannot pass merely
  // because navigation had not finished (docs/MISTAKES.md entry 3).
  await expect(page.getByTestId('pulse-landing-instructor')).toBeVisible();
  await expect(page.getByTestId('pulse-landing-student')).toHaveCount(0);
});
