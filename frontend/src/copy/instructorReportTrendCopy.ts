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
 * ## The comparison words arrived in E5-07
 *
 * E4 shipped this file with every comparison word deliberately absent, because
 * E4 had no comparison data at all and SPEC §4.1 item 1 makes comparison
 * language a visibility question rather than a copy question. E5-07 draws the
 * two overlay series, so the words the legend and the suppression notices need
 * are below — and only those. **They belong to the instructor surface.** The
 * student surfaces read `studentSurvey.ts`, where the same words are still
 * forbidden and swept for (`tests/unit/test_the_submit_paths_copy_is_externalised.py`'s
 * `FORBIDDEN_COMPARISONS`); item 1 is what keeps the two files apart, and a
 * comparison string reaching a student surface would have to be written into
 * that file to get there.
 *
 * ## What is deliberately not here
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

  // The legend. One entry per line the panel actually draws: the section's own,
  // and — from E5-07, and only when the payload carries them unsuppressed — the
  // comparison set and the university.
  'instructor_report_trend.legend_section': 'This section',
  // `design/Usage Rules.md` §1: "Legend names the comparison honestly
  // ('Comparable 12-week courses' — comparables are same-length,
  // past-referencing)". The number is the section's own `length_weeks`, which
  // the API supplies and the chart already draws its axis from; SPEC §5.1 makes
  // length half of what a section must match on to be comparable, so naming it
  // is the honest half of the label rather than decoration. Nothing here counts
  // the sections in the set: a set size under a legend is the inference §4.1
  // item 7 exists to prevent, exactly as it is under a suppression.
  'instructor_report_trend.legend_comparison': 'Comparable {weeks}-week courses',
  'instructor_report_trend.legend_university': 'University',

  // A series the payload suppressed. Two sentences: the line is not there, and
  // the set behind it is too small to report on.
  //
  // **No number, and no cause spelled finer than this.** SPEC §4.1 item 7
  // suppresses every figure computed from a comparison set, and E5's breakdown
  // decision 2 puts two minimums behind that — a count of sections and a count
  // of distinct students — so a notice naming one of them would be wrong
  // whenever the other fired. "Too small" covers both and states no figure the
  // suppression is withholding.
  //
  // **This is state copy, not the surface's confidentiality line** (§4.1 item
  // 5, in the item's own words since the ruling of 2026-09-08): it explains why
  // something is hidden, renders only in that state, and promises nothing about
  // identity. `instructor_report_page.comments_note` is still the report's one
  // standing identity promise.
  //
  // **"On this chart", not "this week".** The notice renders only when every
  // week of the series is withheld (ADR 0171's per-point decision draws a gap,
  // not a notice, for one withheld week), so what it states is a fact about the
  // whole chart; a sentence naming one week told the reader something narrower
  // than the truth.
  'instructor_report_trend.comparison_suppressed':
    'Comparable {weeks}-week courses: no line on this chart. The set behind it is too small to report on.',
  'instructor_report_trend.university_suppressed':
    'University: no line on this chart. The set behind it is too small to report on.',

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

  // Each overlay series gets its own table beside the drawing, for the same
  // reason the section's line has one: a line is a picture, and the brief asks
  // every chart for an alternative that carries the same facts. The caption
  // names both the panel and the series, so a reader hearing four tables in a
  // stacked pair can tell which is which.
  'instructor_report_trend.overlay_table_caption': 'Weekly ratings: {stream}, {series}',
  // A week the series carries no figure for. Not the same sentence as the
  // section's silent week: nobody's responses are being described here, only a
  // week the cohort has no reportable figure in — which is why the line breaks
  // there rather than being drawn straight across it.
  'instructor_report_trend.overlay_no_figure': 'No figure that week',

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
 * The entries that take them are the two axis labels, whose week numbers are the
 * API's; the two table captions, whose stream name is the panel's own label; and
 * the comparison legend and the two suppression notices, whose `{weeks}` is the
 * section's own length as the API gave it. The substitution lives here rather
 * than in the components so that a sentence and the shape of its holes stay in
 * one file.
 */
export function fillCopy(
  key: InstructorReportTrendCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
