/**
 * Every word the Monday report's stat components ship — ticket E4-09.
 *
 * The three components that use it (`RatingHistogram`, `StatPair`,
 * `ResponseRateBar`) carry no string a person reads. Each one looks its words up
 * by key here, in the shape `frontend/src/copy/studentSurvey.ts` settles for a
 * surface's strings: **stable dotted keys, one entry per string, one mapping**,
 * with a `copy()` lookup and a `fillCopy()` that substitutes `{placeholder}`
 * holes.
 *
 * E4-09 shipped this file beside its components; **E4-12 moved it into
 * `frontend/src/copy/`**, the directory the inventory walks, so the strings
 * below are collected and swept rather than held to items 4 and 5 by review.
 *
 * **The number-format rules left with the move**, into
 * `../components/instructorReportFigures.ts`. The copy parser refuses a
 * quotation mark anywhere outside the object literal below, which is what stops
 * a sentence shipping from among a copy file's helpers — and it refuses a
 * helper naming its own key by the same rule. Rounding a percent and fixing a
 * decimal place are presentation rather than words, so they are beside the
 * components now and read these entries through `copy()` like everything else.
 *
 * **SPEC §4.1 item 4 governs every label here.** Aggregate language counts
 * sections and never instructors; "needs attention" and never
 * "underperforming"; no ranking, no composite score, no score-sorting. None of
 * these strings ranks anything, and the two stream titles are §5.1's own comment
 * grouping — "About the instructor" / "About the course" — singular, about one
 * section's own week.
 *
 * ## What is deliberately not here
 *
 * **The five questions' wording.** SPEC §3.2 keeps the questions in a versioned
 * table and serves them; `studentSurvey.ts` refuses to copy them for that
 * reason, and the same refusal holds here. The prototype titles each histogram
 * with the quoted question, and this implementation titles it with the stream
 * the distribution belongs to instead — a title copied from §3.2 would be a
 * second instrument agreeing with the real one only until a set is versioned.
 *
 * **The histogram's comparison strings.** The prototype's histogram carries a
 * "comparable" benchmark beside the mean. That figure is E5's, reached through
 * E4-07's guarded member, and no ticket has drawn it yet; nothing here names it.
 *
 * ## The workload comparison words arrived in E5-08
 *
 * E4 shipped this file with every comparison word absent, because E4 had no
 * comparison data at all and SPEC §4.1 item 1 makes comparison language a
 * visibility question rather than a copy question. **E5-08 draws the two
 * comparison columns of the workload pair**, so the labels those columns need,
 * and the words a withheld one says instead of a number, are below — and only
 * those. They belong to the instructor surface: the student surfaces read
 * `studentSurvey.ts`, where the same words are forbidden and swept for
 * (`tests/unit/test_the_submit_paths_copy_is_externalised.py`'s
 * `FORBIDDEN_COMPARISONS`), and item 1 is what keeps the two files apart.
 */

/**
 * Every user-facing string the three stat components ship, keyed by a stable
 * dotted name.
 */
export const INSTRUCTOR_REPORT_STATS_COPY = {
  // The two comment streams SPEC §5.1 groups the report by, used here to title
  // each week's rating distribution. Singular "instructor": this is one
  // section's own stream, and §4.1 item 4's rule is about counting instructors.
  'instructor_report_stats.instructor_stream': 'About the instructor',
  'instructor_report_stats.course_stream': 'About the course',

  // The quiet mono line above the bars, and the histogram's accessible
  // alternative. `docs/DESIGN_BRIEF.md` requires charts to have one: the bars
  // themselves are `aria-hidden`, and this sentence is what a screen reader
  // gets in their place — the total the week rests on and every bucket's count,
  // in rating order.
  // The label alone, with the figure beside it rather than inside it: the mockup
  // sets the digits in full spruce against the label's spruce-60
  // (`design/RatingHistogram.dc.html:13`), and a colour cannot be applied to part
  // of one text node. So the word is copy and the number is a figure, which is
  // what they are — nothing a reader sees is assembled here beyond the space
  // between them.
  'instructor_report_stats.distribution_mean_label': 'mean',
  'instructor_report_stats.distribution_reading':
    '{stream}, ratings this week: {total} responses, mean {mean}. Responses by rating 1 to 5: {counts}.',
  'instructor_report_stats.distribution_reading_absent':
    '{stream}, ratings this week: no responses yet.',

  // The absent statistic, in the treatment the prototypes use for a figure that
  // has nothing behind it (`CarePanel`'s oldest-case age, `JobRow`'s duration):
  // an em dash where the number would be, never a zero and never `NaN`. A
  // zero-response week has no mean, no workload figure and no rate — and a page
  // of "0%" would read as a verdict on the week rather than as an empty one.
  'instructor_report_stats.absent_figure': '—',
  // Said in words as well as drawn as a dash, because a dash alone tells a
  // reader nothing about why. The brief's empty state is this sentence.
  'instructor_report_stats.no_responses': 'No responses yet this week',

  // SPEC §5.1's workload pair, in the prototype's order — median first, then
  // mean, as `design/InstructorMondayReport.dc.html` lays them out.
  'instructor_report_stats.workload_median': 'Median hours this week',
  'instructor_report_stats.workload_mean': 'Mean hours this week',
  'instructor_report_stats.workload_unit': 'h',

  // The two comparison columns beside the section's own pair — ticket E5-08,
  // SPEC §5.1's "workload mean/median for the section against comparison-set
  // and university figures".
  //
  // **One complete label per figure**, rather than a column heading a value
  // sits under: the pair is a description list, each label bound to its own
  // value, so a reader hearing "Mean hours, comparable courses: 9.0 h" gets the
  // whole fact in one place. Four entries and no assembled sentence — a label
  // built from two holes at render time is a string no inventory can read.
  //
  // **"Comparable courses" is `instructor_report_trend.legend_comparison`'s
  // term** ("Comparable {weeks}-week courses"), minus the length. The trend
  // legend names the length because the chart is given the section's
  // `length_weeks` and `design/Usage Rules.md` §1 asks the legend to name the
  // comparison honestly; this component is given no length, and a label naming
  // one it was not handed would be a claim rather than a fact. What the two
  // surfaces must not do is call the same set two different things, and they
  // do not.
  //
  // **No ranking, no composite, nothing "vs" anything** (§4.1 item 4). The
  // prototype's third line reads "vs 5.0 h comparable · 4.8 h university"
  // (`design/StatPair.dc.html`); three labelled figures state the same numbers
  // without the comparative framing, and no word here sorts, scores or
  // positions a section against another.
  'instructor_report_stats.workload_median_comparison': 'Median hours, comparable courses',
  'instructor_report_stats.workload_mean_comparison': 'Mean hours, comparable courses',
  'instructor_report_stats.workload_median_university': 'Median hours, university',
  'instructor_report_stats.workload_mean_university': 'Mean hours, university',

  // A comparison figure the report is not showing.
  //
  // **In words, never in the absent figure's em dash.** The dash is this
  // surface's treatment for a *section* figure with nothing behind it, and it
  // sits in a column of hours: a dash there reads as "no hours", and a "0.0"
  // reads as "this course took nobody any time". Neither is what a suppression
  // says, so a withheld comparison figure says it in words and shows no
  // number-shaped thing at all (E5-08's named trap).
  //
  // **Two reasons, each true of its own case, and the note is on the screen
  // rather than only in the accessible text** — a sighted reader is owed the
  // reason as much as a reader hearing it.
  //
  // The suppression sentence is `instructor_report_trend.comparison_suppressed`'s
  // second sentence, for the same reason it is worded that way there: SPEC §4.1
  // item 7 suppresses on a count of sections and a count of distinct students
  // both, so a notice naming either minimum would be wrong whenever the other
  // fired, and a notice carrying a figure would publish a shape of the set the
  // suppression exists to withhold. Nothing here says or implies zero.
  'instructor_report_stats.benchmark_withheld': 'Not shown',
  'instructor_report_stats.benchmark_withheld_suppressed':
    'The set behind this figure is too small to report on.',
  'instructor_report_stats.benchmark_withheld_no_figure': 'There is no figure for this week.',

  // SPEC §5.1's two participation figures. The validity rate is instructor and
  // leadership only (§3.3), which is why `ResponseRateBar` renders it from an
  // optional prop: a surface that must not show it — E8's student results —
  // passes no validity figure and gets no validity word in its DOM.
  'instructor_report_stats.response_rate': 'Response rate',
  'instructor_report_stats.validity_rate': 'Validity rate',

  // The bar's own readout, and its accessible alternative. The counts and the
  // percent are separate holes because they come from separate members of the
  // payload: "13 of 21" is the pair of integers the report was given, never a
  // number multiplied back out of the rate.
  'instructor_report_stats.rate_readout': '{numerator} / {denominator} · {percent}',
  'instructor_report_stats.rate_reading': '{label}: {numerator} of {denominator}, {percent}.',
  // A rate with no responses behind it states its counts and withholds the
  // percent: "0 of 21" is exact and complete, and "0%" beside it would invite
  // the reading a zero-response week must not get. The same sentence serves a
  // week where the classifier found nothing valid — "0 of 13" says that too,
  // and says it without a percent that reads as a score.
  'instructor_report_stats.rate_reading_counts_only': '{label}: {numerator} of {denominator}.',
  // And a rate with nothing to be a rate of — the validity rate of a week with
  // no responses — states neither, because "0 / 0" is not a fact about anything.
  'instructor_report_stats.rate_reading_absent': '{label}: no responses yet this week.',

  // Whole percents, written where the rest of the report's words are, so the
  // one place a percent sign is spelled is this file.
  'instructor_report_stats.percent': '{percent}%',
} as const satisfies Record<string, string>;

/** Every key these components publish. */
export type InstructorReportStatsCopyKey = keyof typeof INSTRUCTOR_REPORT_STATS_COPY;

/**
 * The words behind one key.
 *
 * A function rather than direct indexing so that every component reads the
 * mapping the same way and a key that is not one of these fails to compile.
 */
export function copy(key: InstructorReportStatsCopyKey): string {
  return INSTRUCTOR_REPORT_STATS_COPY[key];
}

/** One entry with its `{placeholders}` filled in. */
export function fillCopy(
  key: InstructorReportStatsCopyKey,
  values: Readonly<Record<string, string>>,
): string {
  return copy(key).replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
