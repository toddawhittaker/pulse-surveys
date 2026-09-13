/**
 * Every word the instructor report's trend chart family writes — ticket E4-08.
 *
 * The shape is `frontend/src/copy/studentSurvey.ts`'s, which is in turn the
 * shape `backend/app/copy/` settles for the strings the server writes: **stable
 * dotted keys, one entry per string, one mapping**, read through `copy()` and
 * `fillCopy()`. SPEC §4.1 items 4 and 5 are rules about words, and a rule about
 * words can only be checked against words something can find — a sentence
 * written into JSX is a sentence no inventory can read. So no component in this
 * ticket carries a literal a person reads; each one looks its words up by key.
 *
 * E4-08 shipped this file beside its components; **E4-12 moved it into
 * `frontend/src/copy/`**, the directory the inventory walks, so the strings
 * below are collected and swept rather than held to items 4 and 5 by review.
 *
 * ## What is deliberately not here
 *
 * **Every comparison word.** "Comparable courses", "university", and the
 * benchmark legend the prototype draws are E5's, and E4 has no comparison data
 * at all: SPEC §4.1 item 1 makes comparison language a visibility question
 * rather than a copy question, so a string that named a comparison this epic
 * cannot show would be a claim the report is not entitled to make. The legend
 * below names the section's own line and nothing else.
 *
 * **The week eyebrow's wording.** `student_survey.course_week_eyebrow`'s
 * `COURSE WK NN / NN, TERM WK NN` is the owner's FIX-01 ruling of 2026-09-03,
 * with the course length added by the ruling of 2026-09-07 (E4-17), and it
 * governs the eyebrow only. The chart axis follows SPEC §2.2's chart wording —
 * "WK 01" with the quiet "TERM 07" sub-label — and the two are deliberately
 * different strings for two different places.
 *
 * **Ranking and composite-score words.** SPEC §4.1 item 4 forbids them
 * outright, and a chart is where they arrive most easily ("top week", "rating
 * score"). Nothing below carries one.
 */

/**
 * Every user-facing string the trend family ships, keyed by a stable dotted
 * name.
 *
 * A flat key-to-text mapping rather than a `CopyEntry(key, text)` pair: the key
 * here is the mapping's own key, so there is no second spelling of it for the
 * two to disagree in, and a reader — E4-12's collector included — walks one
 * object literal.
 */
export const INSTRUCTOR_REPORT_TREND_COPY = {
  // The two panels of the stacked pair, in the order SPEC §5.1 fixes:
  // instructor stream above, course stream below. `design/Usage Rules.md` §1
  // makes that order the same everywhere — it is also the survey's question
  // order and the comment-group order — so the words are the panel's identity
  // rather than a caption a caller chooses.
  'instructor_report_trend.panel_instructor': 'Instructor',
  'instructor_report_trend.panel_course': 'Course',

  // The x axis. SPEC §2.2's two week axes in the chart's own wording: the
  // course week leads, the term week follows quietly underneath, both filled
  // with numbers the API supplies. Two digits, so the mono figures line up down
  // a column and week 7 and week 12 are the same width. Neither number is
  // computed here; a chart that derived the term week from an offset would
  // disagree with the report the first time a section paused for a break week.
  'instructor_report_trend.course_week_tick': 'WK {week}',
  'instructor_report_trend.term_week_tick': 'TERM {week}',

  // The legend, which names one line because E4 draws one line. The comparison
  // and university entries the prototype's legend carries are E5's to add, with
  // the data behind them.
  'instructor_report_trend.legend_section': 'This section',

  // The accessible alternative. `docs/DESIGN_BRIEF.md` requires one for every
  // chart, and the shape here is a visually hidden table carrying the same
  // weeks and values the line is drawn from, so the chart's data is reachable
  // as text (SPEC §14.2 item 4). The caption is filled with the panel's own
  // label, which is how the two tables in a pair are told apart when they are
  // read rather than seen.
  'instructor_report_trend.table_caption': 'Weekly ratings: {stream}',
  'instructor_report_trend.table_course_week_header': 'Course week',
  'instructor_report_trend.table_term_week_header': 'Term week',
  'instructor_report_trend.table_mean_header': 'Average rating',
  // A week nobody answered in. It says so in words rather than showing a
  // figure: zero is a rating a student can give, and a week with no responses
  // is not a week that was rated badly.
  'instructor_report_trend.no_responses': 'No responses that week',

  // Week navigation. The report pages across published weeks (SPEC §5.1), and
  // which weeks those are is the API's answer — these two controls carry no
  // week numbers of their own, so their names stay the same whichever week is
  // open.
  'instructor_report_trend.week_nav_label': 'Week navigation',
  'instructor_report_trend.week_nav_previous': 'Previous week',
  'instructor_report_trend.week_nav_next': 'Next week',
  // The arrows a person sees. They are here rather than in the components for
  // the reason everything else here is: a character a reader reads is a string,
  // and a string that lives in JSX is one no inventory can find. The two
  // buttons are named by the entries above, so a screen reader hears "Previous
  // week" rather than an arrow.
  'instructor_report_trend.week_nav_previous_glyph': '←',
  'instructor_report_trend.week_nav_next_glyph': '→',
} as const satisfies Record<string, string>;

/** Every key this surface publishes. */
export type InstructorReportTrendCopyKey = keyof typeof INSTRUCTOR_REPORT_TREND_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing so that every component reads the
 * mapping the same way and a key that is not one of this surface's fails to
 * compile.
 */
export function copy(key: InstructorReportTrendCopyKey): string {
  return INSTRUCTOR_REPORT_TREND_COPY[key];
}

/**
 * One entry with its `{placeholders}` filled in.
 *
 * Three entries take them: the two axis labels, whose week numbers are the
 * API's, and the table caption, whose stream name is the panel's own label. The
 * substitution lives here rather than in the components so that a sentence and
 * the shape of its holes stay in one file.
 */
export function fillCopy(
  key: InstructorReportTrendCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
