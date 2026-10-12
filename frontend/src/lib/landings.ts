/**
 * The empty landing views: the testid each one carries and the copy keys each
 * one renders.
 *
 * **No sentence lives here.** The headings and empty-state lines are governed
 * copy under SPEC §4.1 items 4 and 5, so since E9-04 they are in
 * `../copy/landings.ts` under the `landing.` prefix, where the copy inventory
 * collects them; this table names their keys. A rule in
 * `tests/unit/test_the_component_and_route_trees_ship_no_ungoverned_string.py`
 * refuses a sentence written back into this file.
 *
 * **Three rather than five, and each departure is a route that grew a
 * surface.** E2-10 took the student entry: it renders the weekly survey (SPEC
 * §7.6's `StudentWeeklySurvey`), and its strings live in
 * `../copy/studentSurvey.ts`. E4-11 took the instructor entry the same way: it
 * renders SPEC §5.1's Monday report, and its strings are in
 * `../copy/instructorReportPageCopy.ts`. Neither testid moved —
 * `pulse-landing-student` sits on the survey's landmark and
 * `pulse-landing-instructor` on both of the instructor area's — because a long
 * row of end-to-end specs address them to say who landed.
 *
 * The testids are E0-18's, and they are the same strings the door specs,
 * `tests/fixtures/doors.py` and `mock-idp/app/pages.py` address.
 */

import type { LandingCopyKey } from '../copy/landings';

export interface Landing {
  /** The `data-testid` on the view's landmark. E0-18 settled these five names. */
  readonly testid: string;
  /** The key of the view's one first-level heading. */
  readonly heading: LandingCopyKey;
  /** The key of the one line saying nothing is here yet. */
  readonly emptyState: LandingCopyKey;
}

export const LANDINGS = {
  leadership: {
    testid: 'pulse-landing-leadership',
    heading: 'landing.leadership.heading',
    emptyState: 'landing.leadership.empty_state',
  },
  care: {
    testid: 'pulse-landing-care',
    heading: 'landing.care.heading',
    emptyState: 'landing.care.empty_state',
  },
  admin: {
    testid: 'pulse-landing-admin',
    heading: 'landing.admin.heading',
    emptyState: 'landing.admin.empty_state',
  },
} as const satisfies Record<string, Landing>;
