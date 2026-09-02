// The development clock, driven from a browser — ADR 0109, ticket E2-04.
//
// **Why this module exists.** `student-survey.spec.ts` has to stand a section
// inside its own survey window, and the only way to do that against a running
// stack is the `/dev` console's clock control. `dev-clock.spec.ts` and
// `window-scheduling.spec.ts` each already carry the five testids and a
// `clearTheClock`/`setTheClockTo` pair; a third hand-copy is `docs/MISTAKES.md`
// entry 13 written out in full, so the shared question is answered once, here.
//
// **Those two specs are deliberately left holding their own copies**, for the
// reason `doors.ts` records for the six specs it did not refactor: they are this
// suite's proven-green baseline for the clock, and the spec importing this
// module depends on that baseline being what it was. Putting a diff on the
// control in the same pull request that leans on it is the thing that record
// declined to do. The next ticket that edits either of them moves it over; until
// then this file is the destination and not yet the only spelling.
//
// **The clock is global state on a shared stack**, which is why
// `playwright.config.ts` pins `workers` to 1 and why every user of this module
// clears the override in a `finally`. A failing assertion that left the stack in
// October 2026 fails the specs running after it, and those failures point at
// everything except the file that caused them.

import { expect, type Page } from '@playwright/test';

import { DEV_CONSOLE_PATH } from './doors';

// The five testids E2-04's work order settles, spelled here, in
// `dev-clock.spec.ts`, in `window-scheduling.spec.ts` and in
// `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`.
export const EFFECTIVE_NOW = 'clock-effective-now';
export const OVERRIDE_STATE = 'clock-override-state';
export const PRETEND_NOW_INPUT = 'clock-pretend-now';
export const SET_BUTTON = 'clock-set';
export const CLEAR_BUTTON = 'clock-clear';

/** The whitespace-trimmed text of one testid on the page as it stands. */
export async function readout(page: Page, testid: string): Promise<string> {
  return ((await page.getByTestId(testid).textContent()) ?? '').trim();
}

/** Clear any override the stack is carrying and come back to the console. */
export async function clearTheClock(page: Page): Promise<void> {
  await page.goto(DEV_CONSOLE_PATH);
  await page.getByTestId(CLEAR_BUTTON).click();
  await expect(page.getByTestId(EFFECTIVE_NOW)).toBeVisible();
}

/**
 * Move the stack's clock to one wall-clock minute and come back to the console.
 *
 * `pretendNow` is an `<input type="datetime-local">` value — a wall time in the
 * institution's zone, to the minute (E2-04's work order).
 *
 * The control answers 303 back to `/dev`, so the address is asserted rather than
 * the page's content: that is what tells "the control worked" from "the control
 * answered something the browser rendered in place".
 */
export async function setTheClockTo(page: Page, pretendNow: string): Promise<void> {
  await page.goto(DEV_CONSOLE_PATH);
  await page.getByTestId(PRETEND_NOW_INPUT).fill(pretendNow);
  await page.getByTestId(SET_BUTTON).click();
  await expect(page).toHaveURL(new RegExp(`${DEV_CONSOLE_PATH}/?$`));
  // Nothing is asserted about the effective-now *readout* here, deliberately:
  // E2-04 settles the testids and not the rendering, which is why
  // `dev-clock.spec.ts` carries a list of spellings it will accept rather than a
  // format. A caller that needs to know the clock moved asserts it against
  // whatever it is really about — a window that opened, a section cell that
  // changed — which is a stronger reading than the console agreeing with itself.
}
