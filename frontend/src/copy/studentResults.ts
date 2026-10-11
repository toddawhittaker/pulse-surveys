/**
 * Every sentence the student's results page, its response card and the link to
 * them write themselves.
 *
 * Same shape as `studentSurvey.ts`, under a key prefix of its own,
 * `student_results.`: the copy inventory (SPEC §4.1 items 4 and 5) collects by
 * prefix, and the results page is its own surface (E7-10). It shows only text
 * staff wrote, so it owes item 5 no confidentiality line today;
 * `docs/tickets/e8/carried-from-e7.md` reopens that when E8 adds anything
 * derived from students to the page. The keys the survey page uses for its
 * heading and its link to this page are filed here with the rest.
 *
 * **The words state facts and blame nobody** (`design/Usage Rules.md` §4). A
 * response written by someone other than the instructor is attributed by name
 * and role at the same weight as one the instructor wrote, and no sentence here
 * says why it was written by someone else.
 *
 * **Not here:** the response text and the author's name. Both arrive on the
 * wire and are shown as they arrive.
 */
export const STUDENT_RESULTS_COPY = {
  // The survey page's section heading: who teaches the section, and the way to
  // the reply. `{names}` is the instructors' own names, comma-joined.
  'student_results.with_instructors': 'with {names}',
  'student_results.see_reply_link': 'See your instructor’s reply',
  // The link's accessible name: the visible text first, then the course, so
  // several links on one page are told apart.
  'student_results.see_reply_link_named': 'See your instructor’s reply for {course}',

  // The page.
  'student_results.heading': 'Your instructor’s reply',
  'student_results.loading': 'Loading your instructor’s reply.',
  'student_results.week_label': 'Week {week}',

  // The four states. `awaiting` says one thing and no more: no date, no count,
  // no name and nothing about the response itself.
  'student_results.awaiting': 'There is no reply to show for this week yet.',
  'student_results.unanswered': 'There is no reply for this week.',

  // A refusal of any kind, one calm sentence that says nothing about why.
  'student_results.nothing_to_show': 'There is nothing to show for this section yet.',
  'student_results.session_ended_title': 'Your session has ended',
  'student_results.session_ended_body':
    'Open this page again from your course to see your instructor’s reply.',
  'student_results.unavailable': 'This page could not be loaded right now. Try again in a moment.',

  // The card. The role words are the same weight whoever wrote the reply.
  'student_results.author_instructor': '{name}',
  'student_results.author_lead_faculty': '{name}, Lead Faculty',
  'student_results.author_chair': '{name}, Department Chair',
  'student_results.published_on': 'Published {day}',

  // The student's own posted participation score, shown in every state. The one
  // sentence says only that a count can change; it names no cause and no fault.
  'student_results.participation_heading': 'Your participation score',
  'student_results.participation_score': 'Score posted to your gradebook: {score}',
  'student_results.participation_note':
    'A comment counted when you submitted it can be re-checked later, so a week’s count can go down.',

  // The landing's lead for a section with no survey open: the newest results.
  'student_results.results_lead': 'Week {week} results are in',
  'student_results.results_lead_link': 'See Week {week} results',
  'student_results.results_lead_link_named': 'See Week {week} results for {course}',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type StudentResultsCopyKey = keyof typeof STUDENT_RESULTS_COPY;

/** The words behind one key; a key that is not this surface's fails to compile. */
export function copy(key: StudentResultsCopyKey): string {
  return STUDENT_RESULTS_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(
  key: StudentResultsCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
