// E2-06, criterion 3 — "Open/closed flips with the dev clock against the running
// stack — the interactive check this epic was asked to support, scripted so it
// stays true."
//
// The pytest layer already asserts what the derivation writes and what
// `open_window_for_section` answers in process
// (`tests/integration/test_survey_windows_derive_from_the_term_calendar.py` and
// `tests/integration/test_at_most_one_survey_window_is_open_at_a_time.py`). What
// only a browser on the composed stack can add is that the three parts meet: the
// seed derived windows for the sections it created, the `/dev` clock control moves
// the clock the *tool process* reads, and the console's sections table renders the
// answer. Each of those is a different process or a different container, and each
// is a place the chain has silently broken before.
//
// **The window this spec drives is the daylight-saving one, and that is the point
// of choosing it.** Term week 11 of the seeded Fall 2026 calendar opens at 18:00
// on Friday 30 October — daylight time — and closes at 23:59:59 on Sunday 1
// November, by which time the clocks have gone back. A stack that resolved one
// offset per window shows a close an hour early here and is correct on every
// other week of the term.
//
// **The expectations are the seeded calendar's, not the service's.** `MATH 210
// U1WW` is `scripts/seed.py`'s own section on start letter `U`, which
// `START_LETTER_MAP` gives twelve weeks from Monday 17 August 2026 — the term's
// first week — so its eleventh course week is the term's eleventh. The instants
// below are transcribed from `tests/fixtures/survey_windows.py`'s hand-written
// calendar, whose own control is
// `tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py`. Nothing
// here is computed from the code under test (`docs/MISTAKES.md` entry 19).
//
// **This spec moves the stack's clock to another date, and that is shared state.**
// `dev-clock.spec.ts` says why it deliberately does *not*: "an override that moved
// the stack to another date would move every date-derived value a neighbouring
// spec depends on while it ran". This spec has no such option — the window it is
// about is in October 2026 — so two things narrow the blast radius and neither
// removes it. The pretended instants all sit inside the seeded Fall 2026 term, so
// a launch running beside this one resolves the same term it always does; and the
// clock is cleared in a `finally`, so a failing assertion does not leave the stack
// overridden. **What cannot be solved inside this file is that Playwright runs
// spec files in parallel and this one and `dev-clock.spec.ts` both write the
// single `clock_override` row** — that spec clears the row at the start of its
// test and again in its own `finally`, so the two cannot run concurrently and
// stay meaningful. It is a runner-configuration decision rather than a spec one,
// and it is settled by pinning `workers` to 1 in `playwright.config.ts` rather
// than by anything written here.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import { DEV_CONSOLE_PATH } from './support/doors';

// The five clock testids E2-04's work order settles, spelled the same way
// `dev-clock.spec.ts` spells them.
const EFFECTIVE_NOW = 'clock-effective-now';
const PRETEND_NOW_INPUT = 'clock-pretend-now';
const SET_BUTTON = 'clock-set';
const CLEAR_BUTTON = 'clock-clear';

// The console's row for the seeded section, keyed the way E1-15 keys one:
// `dev-section-{COURSE_PREFIX}-{COURSE_NUMBER}-{lms_section_code}`. The cell is
// E2-06's own addition to that table.
const SECTION = 'MATH-210-U1WW';
const SECTION_ROW = `dev-section-${SECTION}`;
const OPEN_WINDOW_CELL = 'section-open-window';

// What that cell reads. E2-06's work order settles both spellings: exactly
// `closed` when no window is open, and `open until {ISO}` when one is, with the
// instant written the way the clock section already writes instants — the
// institution's timezone, offset included (ADR 0109's readout).
const CLOSED_TEXT = 'closed';
const OPEN_PREFIX = 'open until';

// The window this spec drives, transcribed from the hand-written Fall 2026
// calendar: term week 11 opens Friday 30 October 2026 at 18:00 and closes Sunday
// 1 November at 23:59:59, both in `America/New_York`. Daylight time ends at 02:00
// on that Sunday, so the close carries `-05:00` and the open does not.
const WINDOW_CLOSES_ISO = '2026-11-01T23:59:59-05:00';

// Three moments, as an `<input type="datetime-local">` takes them — a wall time in
// the institution's zone, to the minute. The form's field is minute-precision
// (E2-04), so the exact-second boundary belongs to the pytest layer and these
// three are the coarsest questions that still tell the rule apart: inside the
// window near its opening, inside it in its last minute, and one minute past its
// close.
const JUST_AFTER_IT_OPENS = '2026-10-30T18:05';
const ITS_LAST_MINUTE = '2026-11-01T23:59';
const THE_MONDAY_AFTER = '2026-11-02T00:00';

/** The whitespace-trimmed text of one testid on the page as it stands. */
async function readout(page: Page, testid: string): Promise<string> {
  return ((await page.getByTestId(testid).textContent()) ?? '').trim();
}

/** Clear any override the stack is carrying and come back to the console. */
async function clearTheClock(page: Page): Promise<void> {
  await page.goto(DEV_CONSOLE_PATH);
  await page.getByTestId(CLEAR_BUTTON).click();
  await expect(page.getByTestId(EFFECTIVE_NOW)).toBeVisible();
}

/** Move the stack's clock to one wall-clock minute and come back to the console. */
async function setTheClockTo(page: Page, pretendNow: string): Promise<void> {
  await page.goto(DEV_CONSOLE_PATH);
  await page.getByTestId(PRETEND_NOW_INPUT).fill(pretendNow);
  await page.getByTestId(SET_BUTTON).click();
  // The control answers 303 back to `/dev`, so a browser that got here is looking
  // at the console again. Asserting the address is what tells "the control worked"
  // from "the control answered something the browser rendered in place".
  await expect(page).toHaveURL(new RegExp(`${DEV_CONSOLE_PATH}/?$`));
}

/** The section's open-window cell as it reads right now. */
async function openWindowCell(page: Page): Promise<string> {
  const row = page.getByTestId(SECTION_ROW);
  await expect(
    row,
    `The development console shows no row for ${SECTION}. Three causes look the same from here: ` +
      'the stack was never seeded, so the demo institution has no sections; the seed ran but did ' +
      'not derive windows for the sections it created, which E2-06 adds after `seed_sections()`; ' +
      'or the console renders no sections table, which E1-15 added and this spec reads.',
  ).toBeVisible();
  return ((await row.getByTestId(OPEN_WINDOW_CELL).textContent()) ?? '').trim();
}

test('the seeded section opens and closes as the development clock crosses its window', async ({
  page,
}) => {
  // The stack is shared and the clock is global, so this starts by putting it back
  // to real time rather than assuming whatever ran last did. Without it, a
  // previous run that failed between setting and clearing would make every
  // reading below one taken under somebody else's override.
  await clearTheClock(page);

  try {
    await setTheClockTo(page, JUST_AFTER_IT_OPENS);
    const open = await openWindowCell(page);
    expect(
      open,
      `With the stack's clock at ${JUST_AFTER_IT_OPENS} the console says ${JSON.stringify(open)} ` +
        `for ${SECTION}. SPEC §3.1 opens the week's survey Friday at 18:00 in the institution's ` +
        'timezone, and this is five minutes past that Friday — the eleventh course week of a ' +
        '12-week `U` cohort that started on the term\'s first Monday. A cell reading "closed" ' +
        'here is either a derivation that wrote no window for that week or an open/closed answer ' +
        'that never read the development clock, which is the failure this whole epic is about.',
    ).toContain(OPEN_PREFIX);
    expect(
      open,
      `The console says the window is open until something other than ${WINDOW_CLOSES_ISO}: it ` +
        `reads ${JSON.stringify(open)}. That instant is 23:59:59 on Sunday 1 November 2026 in ` +
        'the institution\'s timezone, and the `-05:00` is load-bearing — daylight time ends at ' +
        '02:00 that morning, so the window opens on UTC-4 and closes on UTC-5. A close an hour ' +
        'earlier is one zone conversion done per window instead of per instant.',
    ).toContain(WINDOW_CLOSES_ISO);

    await setTheClockTo(page, ITS_LAST_MINUTE);
    const stillOpen = await openWindowCell(page);
    expect(
      stillOpen,
      `With the clock at ${ITS_LAST_MINUTE} — the window's last minute — the console says ` +
        `${JSON.stringify(stillOpen)}. SPEC §3.1 closes the survey at 23:59:59 on the Sunday, so ` +
        'it is still open through that minute. A cell reading "closed" here is a window closed ' +
        'at the end of Saturday, at 23:00, or on the wrong offset.',
    ).toContain(OPEN_PREFIX);

    await setTheClockTo(page, THE_MONDAY_AFTER);
    const closed = await openWindowCell(page);
    expect(
      closed,
      `With the clock at ${THE_MONDAY_AFTER} — Monday morning, after the window closed — the ` +
        `console says ${JSON.stringify(closed)}. §3.1 puts the report after the close, so a ` +
        'section still showing an open window on Monday is a week that can still change under a ' +
        'report that has already been generated. This is also the half that makes the two ' +
        'readings above mean something: a cell that said "open until …" whatever the clock was ' +
        'would pass both of them.',
    ).toBe(CLOSED_TEXT);
  } finally {
    // Whatever happened above, the stack goes back to real time. A failing
    // assertion that left the clock in October 2026 would fail the specs running
    // beside this one, and those failures would point at everything except this
    // file.
    await clearTheClock(page);
  }
});
