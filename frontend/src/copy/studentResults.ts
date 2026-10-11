/**
 * Every sentence the student's results page, its response card and the link to
 * them write themselves.
 *
 * Same shape as `studentSurvey.ts`, under a key prefix of its own,
 * `student_results.`: the copy inventory (SPEC §4.1 items 4 and 5) collects by
 * prefix, and the results page is its own surface. It shows what classmates
 * wrote and how they rated the week, so it carries item 5's line exactly once:
 * `student_results.confidentiality` (ADR 0197). The keys the survey page uses
 * for its heading and its link to this page are filed here with the rest.
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

  // The figures. The two streams are told apart by their words and not by a
  // legend, because the trend draws one line in each panel and nothing else.
  'student_results.class_heading': 'Your class this week',
  'student_results.trend_instructor': 'Instructor',
  'student_results.trend_course': 'Course',
  'student_results.trend_mean_header': 'Mean rating',
  'student_results.workload_median': 'Class median: {hours} h on this course',

  // The comments. A stream held back says why in one voice to the student and
  // states no number: how many commented is what the hold exists to keep.
  'student_results.comments_none': 'No comments this week.',
  'student_results.small_n_title': 'Comments in this group stay private this week',
  'student_results.small_n_body':
    'Comments appear here once enough classmates have commented. Until then they stay private, so that none can be traced back to the person who left it. They may appear later among comments from earlier weeks.',
  'student_results.released_heading': 'Comments from earlier weeks',

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

  // SPEC §4.1 item 5: the page's one confidentiality line. There is exactly one
  // entry for it here, which is the form the inventory reads it in.
  'student_results.confidentiality':
    'Comments are shown without the names of the students who wrote them.',

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
