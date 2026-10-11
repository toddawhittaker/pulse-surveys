/**
 * Every sentence the leadership response pages write (SPEC §5.3 and §5.6): the
 * response policy, the responses owed, and responding on behalf.
 *
 * The shape is `leadershipModerationCopy.ts`'s: stable dotted keys, one entry per
 * string, `copy()` and `fillCopy()` as the only ways a component reaches a word.
 * The prefix is `leadership_response.`, the one the server's two refusals for the
 * same pages already use (`app/copy/response_loop.py`).
 *
 * ## What is deliberately not here
 *
 * **The server's refusals.** A policy with nothing to set and an on-behalf door
 * that is closed are answered with their own sentences, and the pages show the
 * ones they were sent.
 *
 * **Any ranking, count of instructors or name.** The owed list is a list of
 * section-weeks in the reader's own courses (SPEC §4.1 item 4); it names no
 * instructor and says "response owed", never anything that blames.
 */

export const LEADERSHIP_RESPONSE_COPY = {
  // The two states every page shares.
  'leadership_response.session_ended_title': 'This page is not signed in',
  'leadership_response.session_ended_body':
    'The session this page was opened with has ended. Open Pulse Surveys again to come back to it.',
  'leadership_response.not_your_role_title': 'This page is not part of your role',
  'leadership_response.not_your_role_body':
    'You are signed in, in a role this page is not for. Open Pulse Surveys again the way you usually do, and it opens the pages your role has.',

  // The policy page.
  'leadership_response.policy.heading': 'Response policy',
  'leadership_response.policy.intro':
    'Choose whether a response is required for the courses you set. Where it is required, students see each week’s results once the instructor publishes a response.',
  'leadership_response.policy.timing':
    'A change applies from the next week’s report. A week that is already open keeps the setting it opened with.',
  'leadership_response.policy.loading': 'Opening the response policy…',
  'leadership_response.policy.unavailable':
    'The response policy could not be loaded just now. Reload the page to try again.',
  'leadership_response.policy.empty_title': 'No courses to show',
  'leadership_response.policy.empty_body':
    'The courses you set or read a response policy for appear here.',
  'leadership_response.policy.list_label': 'Courses in {prefix}',
  'leadership_response.policy.mode_required': 'Response required',
  'leadership_response.policy.mode_encouraged': 'Response encouraged',
  'leadership_response.policy.toggle_label': 'Response required',
  'leadership_response.policy.toggle_aria': 'Response required for {prefix} courses you set',
  'leadership_response.policy.toggle_detail':
    'Covers the {prefix} courses you set. Other courses in the prefix keep their own setting.',
  'leadership_response.policy.toggle_help':
    'When on, student results for each week are held until the instructor publishes a response, and responding on behalf opens after 96 hours.',
  'leadership_response.policy.set_by_lead_faculty': 'Set by the course’s Lead Faculty. Read-only at your role.',
  'leadership_response.policy.set_by_chair': 'Set by the department’s chair. Read-only at your role.',
  'leadership_response.policy.saving': 'Saving the setting…',
  'leadership_response.policy.saved': 'Setting saved for {prefix}. It applies from the next week’s report.',
  'leadership_response.policy.save_unavailable':
    'The setting could not be saved just now. Reload the page to see what is recorded.',

  // The owed list.
  'leadership_response.owed.heading': 'Responses owed',
  'leadership_response.owed.intro':
    'Section-weeks in your courses whose required response has not been published 48 hours after the report opened. After 96 hours you can respond on behalf of the section.',
  'leadership_response.owed.loading': 'Opening the list of responses owed…',
  'leadership_response.owed.unavailable':
    'The list could not be loaded just now. Reload the page to try again.',
  'leadership_response.owed.empty_title': 'No responses are owed',
  'leadership_response.owed.empty_body':
    'Section-weeks in your courses that need a response appear here.',
  'leadership_response.owed.list_label': 'Section-weeks with a response owed',
  'leadership_response.owed.week': 'Week {week}',
  'leadership_response.owed.respond': 'Respond on behalf',
  'leadership_response.owed.respond_aria': 'Respond on behalf for {section}, week {week}',

  // The on-behalf page.
  'leadership_response.on_behalf.heading': 'Respond on behalf',
  'leadership_response.on_behalf.intro':
    'This section’s instructor has not published a response for this week. What you publish here is shown to the section’s students under your own name and role.',
  'leadership_response.on_behalf.week': '{section}, week {week}',
  'leadership_response.on_behalf.loading': 'Opening the week…',
  'leadership_response.on_behalf.unavailable':
    'This week could not be loaded just now. Reload the page to try again.',
  'leadership_response.on_behalf.not_found_title': 'Nothing to respond to here',
  'leadership_response.on_behalf.not_found_body':
    'This address does not open a week you can respond to.',
  'leadership_response.on_behalf.responses': '{count} responses',
  'leadership_response.on_behalf.responses_one': '1 response',
  'leadership_response.on_behalf.no_summary':
    'No summary is shown for this stream this week.',
  'leadership_response.on_behalf.back': 'Back to responses owed',

  // The composer in its on-behalf mode.
  'leadership_response.composer.heading': 'Your response on behalf of the section',
  'leadership_response.composer.intro':
    'Tell the students what the section said and what will change. They read it with this week’s results, under your name and role.',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type LeadershipResponseCopyKey = keyof typeof LEADERSHIP_RESPONSE_COPY;

/** The words behind one key; a key that is not this surface's fails to compile. */
export function copy(key: LeadershipResponseCopyKey): string {
  return LEADERSHIP_RESPONSE_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(
  key: LeadershipResponseCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
