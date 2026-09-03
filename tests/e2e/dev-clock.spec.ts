// E2-04, criterion 2's "against the running stack" half — the `/dev` clock control
// driven in a real browser.
//
// The ticket asks for the set-and-clear round trip to be "proven against the
// running stack, not only in-process". The in-process halves are
// `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py` (the
// routes, the row, the readouts) and
// `tests/integration/test_the_dev_clock_reaches_the_worker.py` (a separate
// process reading the same row). What only a browser can add is that the form on
// the page actually posts to the route, that the redirect lands back on the
// console, and that a developer clicking two buttons sees the clock move and come
// back. That is what this spec is for, and it deliberately asserts nothing the
// Python suites already own.
//
// **The pretend now is on today's own calendar day, and that is a decision about
// the other specs rather than about this one.** The stack is shared: Playwright
// runs spec files in parallel, and a clock override is global state on the tool
// and the worker alike. An override that moved the stack to another *date* would
// move every date-derived value a neighbouring spec depends on while it ran — the
// term a launch resolves into, the day a roster sync stamps a member as first
// seen. Moving the clock to 04:05 on the day it already is moves the instant and
// no date at all, which is enough for this assertion and reaches nothing else.
// The clock is cleared in a `finally` as well, so a failing assertion does not
// leave the stack overridden for whatever runs next.
//
// **The institution timezone is named here** because the form field is an HTML
// `datetime-local` value, read in that zone (E2-04's work order), and the day this
// spec fills in has to be that zone's day rather than the runner's. The value is
// `.env.example`'s documented default and the one the development stack runs on.
//
// **What the readout says is the implementer's, and this spec says so in one
// constant.** E2-04 settles the testids and not the rendering, so the effective-now
// assertion accepts any spelling of the pretended minute — in the institution's
// zone or in UTC, zero-padded or not. Widening `PRETEND_MINUTE_SPELLINGS` is one
// line, and the pull request that widens it says what the page now shows. The
// override-state half needs no such list: it asserts that the two states read
// *differently*, which is the whole job of that readout.
//
// This spec cannot be run without a seeded, running Compose stack; its green is
// the stack-up run and CI.

import { test, expect, type Page } from '@playwright/test';

import { DEV_CONSOLE_PATH } from './support/doors';

// The five testids E2-04's work order settles, spelled here and in
// `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`.
const EFFECTIVE_NOW = 'clock-effective-now';
const OVERRIDE_STATE = 'clock-override-state';
const PRETEND_NOW_INPUT = 'clock-pretend-now';
const SET_BUTTON = 'clock-set';
const CLEAR_BUTTON = 'clock-clear';

// The zone the development stack runs in (`.env.example`: `INSTITUTION_TIMEZONE`),
// and the zone an `<input type="datetime-local">` value is read in.
const INSTITUTION_TIMEZONE = 'America/New_York';

// The minute this spec pretends it is: an hour of the morning nothing else here
// runs at, on today's own date. Same day, different instant — see the header.
const PRETEND_TIME = '04:05';

// How that minute could reasonably be written on the page. `4:05` covers the
// institution-local rendering zero-padded or not; `8:05` and `9:05` cover the same
// instant rendered in UTC, which `America/New_York` is four or five hours behind
// depending on the season. **The rendering is not settled by the ticket**, so this
// is a list to widen rather than a format to obey.
const PRETEND_MINUTE_SPELLINGS = ['4:05', '8:05', '9:05'];

/** The whitespace-trimmed text of one testid on the page as it stands. */
async function readout(page: Page, testid: string): Promise<string> {
  return ((await page.getByTestId(testid).textContent()) ?? '').trim();
}

/** Today's calendar date in the institution's zone, as `YYYY-MM-DD`. */
function institutionDay(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: INSTITUTION_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

/** Clear any override the stack is carrying and come back to the console. */
async function clearTheClock(page: Page): Promise<void> {
  await page.goto(DEV_CONSOLE_PATH);
  await page.getByTestId(CLEAR_BUTTON).click();
  await expect(page.getByTestId(EFFECTIVE_NOW)).toBeVisible();
}

test('the development console sets a pretend now and gives the real clock back', async ({
  page,
}) => {
  // The stack is shared and this spec is the only thing that writes the override,
  // so it starts by putting the clock back to real time rather than assuming
  // somebody else did. Without it, a previous run that failed between setting and
  // clearing would make the "before" reading below an overridden one, and the
  // whole comparison would be between two overridden states.
  await clearTheClock(page);

  const unmoved = await readout(page, OVERRIDE_STATE);
  expect(
    unmoved,
    'The console\'s override-state readout is empty with no override standing. It exists so that ' +
      'an overridden stack is never mistaken for a live one, and a blank space says neither.',
  ).not.toBe('');

  const pretendNow = `${institutionDay()}T${PRETEND_TIME}`;

  try {
    await page.getByTestId(PRETEND_NOW_INPUT).fill(pretendNow);
    await page.getByTestId(SET_BUTTON).click();

    // The form posts to `/dev/clock` and the route answers 303 back to `/dev`, so
    // a browser that got here is looking at the console again. Asserting the URL
    // is what tells "the control worked" from "the control answered something the
    // browser rendered in place".
    await expect(page).toHaveURL(new RegExp(`${DEV_CONSOLE_PATH}/?$`));

    const moved = await readout(page, EFFECTIVE_NOW);
    expect(
      PRETEND_MINUTE_SPELLINGS.some((spelling) => moved.includes(spelling)),
      `The console's effective-now readout says ${JSON.stringify(moved)} after the clock was set ` +
        `to ${pretendNow}. None of ${JSON.stringify(PRETEND_MINUTE_SPELLINGS)} appears in it, so ` +
        'either the control did not move the clock or the readout is rendering the real one ' +
        'beside an override it is ignoring. If the page renders that minute in some spelling ' +
        'none of these reaches, widen the list — deliberately, and say in the pull request what ' +
        'the page now shows.',
    ).toBeTruthy();

    expect(
      await readout(page, OVERRIDE_STATE),
      'The console\'s override-state readout says the same thing with an override standing as it ' +
        `did without one (${JSON.stringify(unmoved)}). Telling those two states apart is the ` +
        'whole job of that readout.',
    ).not.toBe(unmoved);

    await page.getByTestId(CLEAR_BUTTON).click();
    await expect(page).toHaveURL(new RegExp(`${DEV_CONSOLE_PATH}/?$`));

    expect(
      await readout(page, OVERRIDE_STATE),
      'The console still reports an override after the clear button was clicked. On a running ' +
        'stack that is a clock a developer cannot give back: the row survives, the tool and the ' +
        'worker go on answering the pretended instant, and every window and enrollment check in ' +
        'the product is judged against it until somebody finds the row by hand.',
    ).toBe(unmoved);
  } finally {
    // Whatever happened above, the stack goes back to real time. A failing
    // assertion that left the clock moved would fail the specs running beside
    // this one, and those failures would point at everything except this file.
    await clearTheClock(page);
  }
});
