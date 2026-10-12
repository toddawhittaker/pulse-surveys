/**
 * The `landing` surface's words — ticket E9-04 (the E9 breakdown's decision 15).
 *
 * Two kinds of string live here. The headings and empty-state lines of the
 * three landing views that are still empty (leadership, Care, admin), moved
 * word for word out of `frontend/src/lib/landings.ts`, where neither the copy
 * inventory nor the component-string sweep read them (the carried E4 entry in
 * `docs/tickets/e4/deferred.md`). And the role switcher's and logout's labels
 * and refusal sentences, which E9-11 draws in the app shell.
 *
 * The shape is the one `studentSurvey.ts` settles: **stable dotted keys, one
 * entry per string, one mapping**, and a lookup function after it. The view
 * table in `lib/landings.ts` names these keys; it holds no sentence.
 *
 * **This surface owes SPEC §4.1 item 5 no confidentiality line.** None of it
 * renders anybody's response, comment or rating. The copy inventory records
 * that answer with its reason, in `SURFACES_WITH_NO_CONFIDENTIALITY_LINE`.
 *
 * `tests/e2e/landing-views.spec.ts` keeps its own copy of the view sentences on
 * purpose, so a spec cannot pass by asking the page what its own heading is.
 */

export const LANDING_COPY = {
  // The leadership landing: still the empty roll-up view, with its links below.
  'landing.leadership.heading': 'Your roll-up',
  'landing.leadership.empty_state':
    'There is nothing to roll up yet. Sections you oversee appear here once they report.',
  // SPEC §6.2 keeps the Care surface to the threat queue and nothing else, and
  // there is no queue to show yet.
  'landing.care.heading': 'Community standards queue',
  'landing.care.empty_state': 'Nothing needs attention.',
  'landing.admin.heading': 'Pulse console',
  'landing.admin.empty_state': 'There is nothing to administer yet.',
  // The role switcher: its control's label, and what it says when the server
  // refuses a switch. A refused switch changes nothing, and the sentence says so.
  'landing.switcher.label': 'Switch view',
  'landing.switcher.refused': 'That view could not be opened. Your current view is unchanged.',
  // Logout: its control's label, and what it says when the request did not go
  // through. The session is still live then, so it asks for another try.
  'landing.logout.label': 'Sign out',
  'landing.logout.refused': 'Signing out did not go through. Please try again.',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type LandingCopyKey = keyof typeof LANDING_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing, so a key that is not one of this
 * surface's fails to compile rather than rendering `undefined`.
 */
export function copy(key: LandingCopyKey): string {
  return LANDING_COPY[key];
}
