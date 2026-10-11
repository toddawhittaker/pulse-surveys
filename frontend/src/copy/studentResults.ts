/**
 * Every sentence the student's results page, its response card and the link to
 * them write themselves.
 *
 * Same shape as `studentSurvey.ts`, and under the same `student_survey.` key
 * prefix: the copy inventory (SPEC §4.1 items 4 and 5) collects by prefix, so
 * these keys are on the survey's governed surface without a registration of
 * their own. The page is a student screen that will carry comments, so it
 * belongs under the survey's one confidentiality line.
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
  'student_survey.results_with_instructors': 'with {names}',
  'student_survey.results_see_reply_link': 'See your instructor’s reply',

  // The page.
  'student_survey.results_heading': 'Your instructor’s reply',
  'student_survey.results_loading': 'Loading your instructor’s reply.',
  'student_survey.results_week_label': 'Week {week}',

  // The four states. `awaiting` says one thing and no more: no date, no count,
  // no name and nothing about the response itself.
  'student_survey.results_awaiting': 'There is no reply to show for this week yet.',
  'student_survey.results_unanswered': 'There is no reply for this week.',

  // A refusal of any kind, one calm sentence that says nothing about why.
  'student_survey.results_nothing_to_show': 'There is nothing to show for this section yet.',
  'student_survey.results_session_ended_title': 'Your session has ended',
  'student_survey.results_session_ended_body':
    'Open this page again from your course to see your instructor’s reply.',
  'student_survey.results_unavailable': 'This page could not be loaded right now. Try again in a moment.',

  // The card. The role words are the same weight whoever wrote the reply.
  'student_survey.results_author_instructor': '{name}',
  'student_survey.results_author_lead_faculty': '{name}, Lead Faculty',
  'student_survey.results_author_chair': '{name}, Department Chair',
  'student_survey.results_published_on': 'Published {day}',

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
