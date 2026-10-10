/**
 * Every sentence the leadership review queue and exclusion log write (SPEC §5.2).
 *
 * The shape is `leadershipComparisonSetCopy.ts`'s: **stable dotted keys, one
 * entry per string, one mapping**, with `copy()` and `fillCopy()` as the only
 * ways a component reaches a word, so SPEC §4.1 items 4 and 5 have one file to
 * read over. The prefix is `leadership_moderation.`, the one the server's
 * refusals for the same two pages already use (`app/copy/leadership_moderation.py`),
 * because a reader meets both sets of words on the same screens.
 *
 * ## What is deliberately not here
 *
 * **The server's refusals.** A reader whose grant puts nothing under review, a
 * comment no longer in the queue and a reason out of bounds are each answered
 * by `api/leadership.py` with its own sentence, and the pages show the one they
 * were sent.
 *
 * **Any week, time of day or count of comments.** The queue shows a comment
 * from below SPEC §4's threshold, and a week or an hour beside it would place
 * it (ADR 0190). The log carries a date and nothing finer.
 *
 * **A confidentiality promise.** These pages show comments to the people who
 * review them; item 5's sentence is a promise to the person answering a survey
 * and has no subject here.
 */

export const LEADERSHIP_MODERATION_COPY = {
  // The two headings double as the leadership landing's link words, so a link
  // and the page it opens name the same thing identically.
  'leadership_moderation.queue.heading': 'Comments awaiting your review',
  'leadership_moderation.queue.intro':
    'The AI flagged each comment here as harmful, in a course you review. Excluding a comment keeps it from students; keeping it publishes it. Both decisions go into the exclusion log, and neither can be undone from this page.',
  'leadership_moderation.queue.loading': 'Opening your review queue…',
  'leadership_moderation.queue.unavailable':
    'This queue could not be loaded just now. Reload the page to try again.',
  'leadership_moderation.queue.empty_title': 'Nothing awaits your review',
  'leadership_moderation.queue.empty_body':
    'Comments the AI flags as harmful in the courses you review appear here.',
  'leadership_moderation.queue.list_label': 'Comments awaiting review',
  // Said once in the status line when a decision lands, because the comment it
  // was about has just left the page.
  'leadership_moderation.queue.excluded': 'Comment excluded. The exclusion log records it.',
  'leadership_moderation.queue.kept': 'Comment kept. The exclusion log records it.',
  // A decision that never reached the server, or a session that ended between
  // reading the queue and deciding. Neither says nothing changed, because a
  // request that was lost on the way back may have landed.
  'leadership_moderation.queue.decision_unavailable':
    'This decision could not be sent just now. Reload the page to see whether it was recorded.',

  'leadership_moderation.log.heading': 'Exclusion log',
  'leadership_moderation.log.intro':
    'Every exclusion and every keep made in the courses you review, newest first. It records both directions, so a fair comment that was quietly dropped leaves a trail.',
  'leadership_moderation.log.loading': 'Opening the exclusion log…',
  'leadership_moderation.log.unavailable':
    'The exclusion log could not be loaded just now. Reload the page to try again.',
  'leadership_moderation.log.empty_title': 'No decisions yet',
  'leadership_moderation.log.empty_body':
    'Exclusions and keeps made in the courses you review appear here.',
  'leadership_moderation.log.list_label': 'Moderation decisions',

  // One row. The decider is a role and never a person (SPEC §5.2).
  'leadership_moderation.log.excluded': 'Excluded',
  'leadership_moderation.log.kept': 'Kept',
  'leadership_moderation.log.role_instructor': 'Instructor',
  'leadership_moderation.log.role_lead_faculty': 'Lead Faculty',
  'leadership_moderation.log.role_chair': 'Chair',
  'leadership_moderation.log.ai_flagged': 'AI-flagged',
  'leadership_moderation.log.unflagged': 'Unflagged, reason given',
  'leadership_moderation.log.status': '{decision} · {flag}',
  'leadership_moderation.log.no_excerpt':
    'No excerpt. This comment is not shown in its section’s report, so the log does not quote it.',

  // What a 401 says, in the register the comparison-set screen set.
  'leadership_moderation.session_ended_title': 'This page is not signed in',
  'leadership_moderation.session_ended_body':
    'The session this page was opened with has ended. Open Pulse Surveys again to come back to it.',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type LeadershipModerationCopyKey = keyof typeof LEADERSHIP_MODERATION_COPY;

/** The words behind one key; a key that is not this surface's fails to compile. */
export function copy(key: LeadershipModerationCopyKey): string {
  return LEADERSHIP_MODERATION_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(
  key: LeadershipModerationCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
