// E1-15, exit clause 3 — SPEC §14.3, E1: "a synced section shows correct
// derived dates".
//
// **Driven end to end**, which is the whole of what makes this an exit proof and
// not a unit test with a browser attached: a staff launch provisions the section
// and stores its roster address (SPEC §7.3), the scheduled sync reads the roster
// through the platform's service, and the dates the section then shows are the
// ones §2.2's start letter derives. Every link in that chain has to work for the
// assertion at the bottom to be reachable.
//
// **The expectation is the seeded calendar, not the parser.** The four values
// below are transcribed from `scripts/seed.py`'s own term calendar — its
// `START_LETTER_MAP` row `("R", 12, date(2026, 9, 7))` and the convention stated
// at `scripts/seed.py:232-236`, that a term's end date is its last day
// inclusive. They are **not** computed from `app.services.section_codes`, whose
// answer is the thing under test: a test holding its expectation in a copy of
// the code it is checking passes on any consistent wrongness
// (`docs/MISTAKES.md` entry 19). An off-by-one-week derivation is the mutation
// this must kill, and it is exactly the mutation a copy would survive.
//
// **The surface.** E1 ships no product screen that renders a section's dates —
// all five landing views are empty by design — so the proof reads them off the
// development console's sections table, which E1-15 adds for this and gates
// exactly as the rest of `/dev` is gated. The alternative was building a product
// surface inside a ticket whose own scope says it proves and does not build.
//
// **Shared state, and why this polls.** All the specs run against one composed
// stack under several workers, so this section may already have been launched
// and synced by a neighbouring spec before this test starts, and
// `request_section_sync` skips a section that saw a roster call in the last five
// minutes. Polling for the state absorbs both orders and asserts nothing about
// what was there before (`lti-launch.spec.ts:36-39`).
//
// This is also the spec that witnesses the *positive* half of exit clause 5:
// the enrolled count below is non-zero because the roster sync read the mock's
// roster as an authenticated service client (`app.services.roster_sync` obtains
// a token through `pylti1p3`), so a green here is "the roster read succeeded".
// `exit-roster-auth.spec.ts` carries the other half.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Locator, type Page } from '@playwright/test';

import { DEV_CONSOLE_PATH, launchAs, placementInto } from './support/doors';

const INSTRUCTOR_SUBJECT = 'mock-lms-user-instructor';
const INSTRUCTOR_VIEW = 'pulse-landing-instructor';

// The section, written as §2.2 writes it: start letter `R`, ordinal 3, modality
// `WW`. The mock platform seeds it as `BIOL-215-R3WW` and publishes that label
// on the launch page's placement option, which is how the placement is found.
const SECTION = 'BIOL-215-R3WW';

// The development console's row for it, and the cells that carry the derived
// calendar. The testid vocabulary is E1-15's contract for the sections table.
const SECTION_ROW = `dev-section-${SECTION}`;
const START_DATE = 'section-start-date';
const END_DATE = 'section-end-date';
const LENGTH_WEEKS = 'section-length-weeks';
const MODALITY = 'section-modality';
const ENROLLED_COUNT = 'section-enrolled-count';

// The four expected values, from the seed's calendar and §2.2's grammar.
//
//   - `R` is a 12-week cohort starting Monday 7 September 2026
//     (`scripts/seed.py::START_LETTER_MAP`, row `("R", 12, date(2026, 9, 7))`);
//   - twelve weeks inclusive of the first day ends on Sunday 29 November 2026 —
//     7 September plus 83 days — under the convention `scripts/seed.py:232-236`
//     states for the term itself: "the end date is the term's last day,
//     inclusive";
//   - `WW` is online (§2.2 fixes `WW` online and `FF` face-to-face).
//
// Written as text because the console renders text; the dates are ISO, which is
// the one spelling that is unambiguous in a table a person also reads.
const EXPECTED_START = '2026-09-07';
const EXPECTED_END = '2026-11-29';
const EXPECTED_LENGTH_WEEKS = '12';
const EXPECTED_MODALITY = 'ONLINE';

// How long to keep re-reading the console while the sync worker works, and how
// long to leave between reads. Chosen against worker latency, which is seconds
// (`lti-launch.spec.ts:115-130` measures the same thing and says why thirty
// seconds is not a debounce wait: the five-minute debounce governs how often a
// staff launch re-triggers a sync, and only one staff launch happens here).
const SYNC_TIMEOUT_MS = 30_000;
const SYNC_RETRY_MS = 3_000;

// How long one read gives the console to render before it is believed absent.
const RENDER_WAIT_MS = 2_000;

/**
 * Drive the staff launch, wait for the sync, and hand back the console's row.
 *
 * Shared by the two tests below so that each drives the whole live path itself
 * rather than inheriting it from whichever ran first — the same discipline
 * `lti-launch.spec.ts` adopted after a case turned out to be resting on a
 * neighbour's side effect.
 */
async function syncedSectionRow(page: Page): Promise<Locator> {
  const placement = await placementInto(page, INSTRUCTOR_SUBJECT, SECTION);
  await launchAs(page, INSTRUCTOR_SUBJECT, placement);

  // Positive first, and it is the control on the trigger: SPEC §7.3 has an
  // instructor's launch store the roster address, which is the whole of what
  // gives the scheduled sync its discovery. A staff launch that was refused, or
  // that reached the calm no-access page, provisioned nothing and stored
  // nothing, and the poll below would be waiting for a sync nobody asked for.
  await expect(page.getByTestId(INSTRUCTOR_VIEW)).toBeVisible();

  const row = page.getByTestId(SECTION_ROW);

  // Wait for evidence that the roster was actually read, rather than for the
  // row to exist: a launch provisions the section immediately, so a row alone
  // says nothing about a sync. The enrolled count is the observable the sync
  // produces, and requiring it above zero is also what keeps this from being a
  // dates assertion against a section nothing has happened to.
  await expect
    .poll(
      async () => {
        await page.goto(DEV_CONSOLE_PATH);
        try {
          await row.waitFor({ state: 'visible', timeout: RENDER_WAIT_MS });
        } catch {
          return -1;
        }
        const shown = ((await row.getByTestId(ENROLLED_COUNT).textContent()) ?? '').trim();
        const count = Number.parseInt(shown, 10);
        return Number.isNaN(count) ? -1 : count;
      },
      {
        message:
          `The development console never showed section ${SECTION} with anybody enrolled in it. ` +
          'Three causes look identical from here and this is the place to tell them apart: the ' +
          'staff launch above stored no roster address, so nothing discovered the section; the ' +
          'sync worker never ran or the roster read was refused, so no `enrollment` row was ' +
          'written; or the console renders no sections table, which is the surface E1-15 adds ' +
          'for this clause. A `-1` means the row itself was never rendered.',
        timeout: SYNC_TIMEOUT_MS,
        intervals: [SYNC_RETRY_MS],
      },
    )
    .toBeGreaterThan(0);

  return row;
}

test('a synced section shows the dates its seeded term calendar derives', async ({ page }) => {
  // The poll alone may spend its whole budget, and a launch runs before it.
  // Playwright's default per-test timeout is below that sum, so a case that
  // needed the full window would fail on the harness rather than on its
  // assertion — a failure that reads as a flake.
  test.setTimeout(SYNC_TIMEOUT_MS + 60_000);

  const row = await syncedSectionRow(page);

  // The clause. Each value is asserted separately so the runner names which one
  // is wrong without anyone opening this file — and the two dates are separate
  // because a length taken from the wrong start letter moves both, while an
  // off-by-one week moves only the end.
  await expect(
    row.getByTestId(START_DATE),
    `Section ${SECTION} starts on the wrong day. §2.2's start letter \`R\` names the 12-week ` +
      `cohort beginning ${EXPECTED_START} in the seeded Fall 2026 calendar.`,
  ).toHaveText(EXPECTED_START);
  await expect(
    row.getByTestId(END_DATE),
    `Section ${SECTION} ends on the wrong day. Twelve weeks from ${EXPECTED_START}, counting ` +
      `the first day, is ${EXPECTED_END} — the value the seeded calendar's own inclusive-end ` +
      'convention gives, transcribed rather than recomputed from the parser under test.',
  ).toHaveText(EXPECTED_END);
  await expect(
    row.getByTestId(LENGTH_WEEKS),
    `Section ${SECTION} is not ${EXPECTED_LENGTH_WEEKS} weeks long. The start letter carries the ` +
      "length as well as the start date, so a wrong length here is a section code read against " +
      'the wrong row of the map.',
  ).toHaveText(EXPECTED_LENGTH_WEEKS);
  await expect(
    row.getByTestId(MODALITY),
    `Section ${SECTION} is not online. §2.2 fixes \`WW\` as online and \`FF\` as face to face, ` +
      'and this code ends `WW`.',
  ).toHaveText(new RegExp(`^\\s*${EXPECTED_MODALITY}\\s*$`, 'i'));
});

test('the console reports a synced section without naming anybody in it', async ({ page }) => {
  test.setTimeout(SYNC_TIMEOUT_MS + 60_000);

  // The console's sections table is a new read path over roster-derived rows, and
  // E1-15's contract for it is that it carries **no identity columns of any
  // kind** — no user identifiers, no names, no addresses; the enrolled count is
  // an integer. That rule is worth an assertion rather than a review note
  // (`docs/MISTAKES.md` entry 2: prefer asserting the forbidden state).
  //
  // **The canary is the enrolled count, and without it this test is worthless.**
  // "This row names nobody" is trivially true of a row about a section nobody is
  // in, and of a table that does not exist. `syncedSectionRow` will not return
  // until the row is on screen with a non-zero count — so the row asserted about
  // below is demonstrably describing a section with real, seeded people in it,
  // whose identifiers and addresses the tool holds and could have printed.
  //
  // The scope is the row and not the page on purpose: the console lists the
  // web-login people by subject elsewhere, by design (that is what makes it a
  // one-click sign-in menu), so a page-wide scan would be red against every
  // correct implementation. The durable, whole-read-path version of this
  // property belongs in the §4.1 invariant suite, in Python, and this is the
  // browser-level guard on the one surface E1-15 adds.
  const row = await syncedSectionRow(page);
  const shown = ((await row.textContent()) ?? '').trim();

  expect(
    shown,
    `The console's row for ${SECTION} carries an "@", which is how an email address gets onto a ` +
      'page. The mock roster exposes an address per member (ADR 0050) and the sync stores it; ' +
      `the sections table reports the section, never the people. The row reads ${shown}.`,
  ).not.toContain('@');
  expect(
    shown,
    `The console's row for ${SECTION} names a launch subject. A subject is what SPEC §4 keys ` +
      'every response to, and a development console that prints one has put an identity on a ' +
      `read path that is supposed to carry a section's calendar and a count. The row reads ` +
      `${shown}.`,
  ).not.toContain('mock-lms-user-');
});
