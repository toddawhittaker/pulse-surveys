/**
 * Every sentence the instructor's Monday report page writes itself — ticket E4-11.
 *
 * The shape is `frontend/src/copy/studentSurvey.ts`'s, and the three files
 * beside this one (`instructorReportTrendCopy.ts`, `instructorReportStatCopy.ts`,
 * `instructorReportCommentCopy.ts`) already follow it: **stable dotted keys, one
 * entry per string, one mapping**, with `copy()` and `fillCopy()` as the only
 * ways a component reaches a word. Nothing in the page carries a literal a
 * person reads, so SPEC §4.1 items 4 and 5 — rules about words — have one file
 * to be read over rather than a search through JSX.
 *
 * E4-11 shipped this file beside its components; **E4-12 moved it into
 * `frontend/src/copy/`**, the directory the inventory walks, so the strings
 * below are collected and swept rather than held to items 4 and 5 by review.
 *
 * ## What is deliberately not here
 *
 * **The two refusal sentences the API writes.** `app.api.instructor` serves
 * "There is no report here for you to read." and "There is no report for that
 * week of this section." — governed copy that lives on the server, chosen by the
 * server for reasons about what a reader may learn from a refusal. The page
 * shows whichever one it was sent. `instructor_report_page.unavailable` below is
 * the fallback for the case where there is no sentence to show: a network
 * failure, or a gateway answering with no body at all.
 *
 * **Anything a summary says.** The model's prose is data, not copy.
 *
 * **Every comparison word.** E4 has no comparison data; §4.1 item 7 governs the
 * figures and E5 brings both. Nothing here names a benchmark, a comparable
 * course or a university line.
 *
 * **A count of anything withheld.** §5.2 forbids a count or a flag hint below
 * the threshold, and the released block below states no week and no number for
 * the same family of reasons (ADR 0153).
 */

export const INSTRUCTOR_REPORT_PAGE_COPY = {
  // The page's own title, for every state that has no report to name a section
  // with. E1-04's governed wording for the instructor landing, kept rather than
  // rewritten: a report page still loading is the same page it was empty.
  'instructor_report_page.heading': 'Your section report',

  // While the answer is on its way, and when it did not arrive. The second is
  // not "this section has no report": a read that failed is a different fact
  // from a section with nothing to show, and saying the calm thing about a
  // broken one is how an instructor concludes their students said nothing.
  'instructor_report_page.loading': 'Opening this week’s report…',
  'instructor_report_page.unavailable':
    'This report could not be loaded just now. Reload the page to try again.',

  // What a 401 says. The session a launch issues lives an hour and an instructor
  // reading a Monday report is very often coming back to a tab from earlier in
  // the day, so this is an ordinary state rather than an error — and the one
  // thing the page must not do is say anything about the week, having just been
  // refused the answer. So it says which page can. The student surface's pair is
  // the precedent and the wording follows it.
  'instructor_report_page.session_ended_title': 'Open this from your course',
  'instructor_report_page.session_ended_body':
    'This page is not signed in, so it cannot show a report. Open Pulse Surveys from inside your course in the LMS, and this section’s week will be here.',

  // A section before its first Monday. `docs/DESIGN_BRIEF.md`'s tone rules apply
  // to it as much as to data: this is most instructors' first sight of the
  // product, so it states the rhythm and asks for nothing.
  'instructor_report_page.no_published_weeks_title': 'No weeks have closed yet',
  'instructor_report_page.no_published_weeks_body':
    'Reports arrive here on Monday, once a survey window has closed. Nothing is needed from you before then.',

  // A person the teaching grants name no sections for — a new instructor on the
  // day she is hired, or one between terms. Ordinary, and said as such.
  'instructor_report_page.no_sections_title': 'No sections to report on yet',
  'instructor_report_page.no_sections_body':
    'Sections you teach appear here once they reach Pulse. If you have just been added to one, open Pulse Surveys from inside that course in the LMS.',

  // The menu, when a reader teaches more than one section. A heading and a line;
  // the sections name themselves, in the label the server composed.
  'instructor_report_page.picker_heading': 'Your sections',
  'instructor_report_page.picker_body': 'Choose a section to read its week.',
  'instructor_report_page.picker_list_label': 'Sections you teach',

  // The report's own regions, in the order `design/InstructorMondayReport.dc.html`
  // lays them out. Each is a second-level heading on the page, so the report is
  // navigable by heading rather than by scrolling.
  'instructor_report_page.trend_heading': 'Rating trend',
  'instructor_report_page.ratings_heading': 'This week’s ratings',
  'instructor_report_page.workload_heading': 'Workload',
  'instructor_report_page.participation_heading': 'Participation',
  'instructor_report_page.comments_heading': 'Comments',
  // The prototype's line under that heading. SPEC §4 requires randomized order
  // and no timestamps, and this says so where a reader can see it rather than
  // leaving the absence to be noticed.
  'instructor_report_page.comments_note': 'Shown in random order. No names, no timestamps.',

  // A section nobody is enrolled in has no response rate — not a nought-percent
  // one. The schema makes the rate `null` rather than `0` for exactly this, and
  // the page states the absence in words rather than drawing an empty bar.
  'instructor_report_page.participation_absent':
    'There is no response rate for this week: nobody is enrolled in this section yet.',

  // The credit rule, explained where the rates are read — E4-12, closing the
  // instructor half of an E3 carried entry. SPEC §3.3 makes a comment judged too
  // brief or nonsense cost its response's validity, §3.4 makes a participation
  // score completed items over total items with the per-week arithmetic visible
  // only in the gradebook comment, and §3.3 lets a later re-classification lower
  // a score that has already posted. None of that was said to an instructor
  // anywhere, and the rate above is the number she reads it against.
  //
  // **It shows in every week, including one with no rate at all.** It explains a
  // rule rather than a figure, and a rule that appeared only in the weeks
  // somebody answered would be missing from the weeks it most needs explaining.
  //
  // Three things it deliberately does not do. It shows no score: v1 renders a
  // participation score nowhere, and a number invented here would be a second
  // arithmetic beside the gradebook's. It names no student and no count. And it
  // carries no confidentiality promise — §4.1 item 5 allows this surface exactly
  // one, `comments_note` above is it, and a reassurance added here would be the
  // second (ADR 0158). The student half of this explanation is E8's.
  'instructor_report_page.participation_credit_note':
    'The validity rate is the share of responses that count as valid: a comment judged too brief or nonsense makes its response invalid, and costs that student one item of their participation credit. Credit is completed items out of total items across the weeks a student has been enrolled, and the week-by-week arithmetic behind each posted score sits in that score’s gradebook comment. A comment judged again later can lower a score that has already posted.',

  // ADR 0152's release. §4 requires under-threshold comments to surface "batched
  // so that timing cannot identify an author", and ADR 0153 strips the week from
  // every one of them — so this block names no week, no count and no timing, and
  // says only what these comments are.
  'instructor_report_page.released_heading': 'Comments from earlier weeks',
  'instructor_report_page.released_body':
    'These were written in earlier weeks of this section and are shown now that enough responses have arrived. They are not part of this week’s figures.',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type InstructorReportPageCopyKey = keyof typeof INSTRUCTOR_REPORT_PAGE_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing, so a key that is not one of this
 * surface's fails to compile rather than rendering `undefined`.
 */
export function copy(key: InstructorReportPageCopyKey): string {
  return INSTRUCTOR_REPORT_PAGE_COPY[key];
}
