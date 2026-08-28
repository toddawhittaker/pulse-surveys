/**
 * The five empty landing views: the testid each one carries and the governed
 * copy each one renders.
 *
 * **This file is the single source of these strings.** It began as a
 * deliberate duplication of `backend/app/services/landing.py`, and E1-13
 * deleted that module when role resolution moved to the assignment model —
 * this is the copy that survived, and there is no second place to keep in
 * step.
 *
 * The strings are governed copy under SPEC §4.1 items 4 and 5 — calm, plain,
 * counting nothing and blaming nobody — enforced by review until E2's copy
 * inventory. `tests/e2e/landing-views.spec.ts` holds its own copy of them
 * deliberately, so that a spec cannot pass by asking the page what its own
 * heading is.
 *
 * The testids are E0-18's, and they are the same strings the door specs,
 * `tests/fixtures/doors.py` and `mock-idp/app/pages.py` address.
 */

export interface Landing {
  /** The `data-testid` on the view's landmark. E0-18 settled these five names. */
  readonly testid: string;
  /** The view's one first-level heading. */
  readonly heading: string;
  /** The one line saying nothing is here yet. */
  readonly emptyState: string;
}

export const LANDINGS = {
  student: {
    testid: 'pulse-landing-student',
    heading: 'Your weekly check-in',
    emptyState: 'There is no survey open for you yet. When one opens, it appears here.',
  },
  instructor: {
    testid: 'pulse-landing-instructor',
    heading: 'Your section report',
    emptyState:
      'There are no responses to report yet. Reports appear here once a week has closed.',
  },
  leadership: {
    testid: 'pulse-landing-leadership',
    heading: 'Your roll-up',
    emptyState:
      'There is nothing to roll up yet. Sections you oversee appear here once they report.',
  },
  // SPEC §6.2 keeps the Care surface to the threat queue and nothing else, and
  // there is no queue to show yet.
  care: {
    testid: 'pulse-landing-care',
    heading: 'Community standards queue',
    emptyState: 'Nothing needs attention.',
  },
  admin: {
    testid: 'pulse-landing-admin',
    heading: 'Pulse console',
    emptyState: 'There is nothing to administer yet.',
  },
} as const satisfies Record<string, Landing>;
