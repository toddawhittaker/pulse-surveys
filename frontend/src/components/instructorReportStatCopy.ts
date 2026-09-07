/**
 * Every word and every number-format rule the Monday report's stat components
 * ship — ticket E4-09.
 *
 * The three components below it (`RatingHistogram`, `StatPair`,
 * `ResponseRateBar`) carry no string a person reads. Each one looks its words up
 * by key here, in the shape `frontend/src/copy/studentSurvey.ts` settles for a
 * surface's strings: **stable dotted keys, one entry per string, one mapping**,
 * with a `copy()` lookup and a `fillCopy()` that substitutes `{placeholder}`
 * holes.
 *
 * **Why this file sits beside the components rather than in
 * `frontend/src/copy/`.** `tests/fixtures/copy_inventory.py` collects every
 * TypeScript file under `frontend/src/copy/`, recursively, and the
 * invariant-marked inventory test reds on any key prefix its governance map does
 * not list. Growing that map over the report surface — and taking these strings
 * into the inventory with it — is **E4-12**'s heavy-lane work, scheduled after
 * this wave. Until E4-12 lands, this module keeps the strings collectable (one
 * literal, one prefix, no sentence assembled at runtime) without reddening a
 * §4.1 invariant that has not yet been taught about them. Moving the file is
 * then a move, not a rewrite.
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
 * **Every comparison string.** The prototype's histogram carries a "comparable"
 * benchmark beside the mean and its `StatPair` carries a "vs 5.0 h comparable ·
 * 4.8 h university" line. Comparison figures are E5's, reached through E4-07's
 * guarded member, and §4.1 item 7 suppresses them below the configured minimums;
 * nothing in this ticket renders one, so nothing here names one.
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
  'instructor_report_stats.distribution_mean': 'mean {mean}',
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

/**
 * A workload statistic as the report writes it: one decimal place, always.
 *
 * One rule in one place, for both figures and for the distribution's mean, so
 * that "8" and "8.04" and "8.0" are one number on the page. `toFixed` rounds
 * rather than truncating — 9.46 is "9.5" and not "9.4" — and a value that is
 * not a finite number gets the absent treatment rather than reaching the DOM as
 * `NaN`, which is the shape SPEC §5.1's zero-response week would otherwise
 * produce through a division by no responses.
 */
export function formatStatistic(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return copy('instructor_report_stats.absent_figure');
  return value.toFixed(1);
}

/**
 * A rate as the report writes it: a whole percent, from the payload's 0–1
 * fraction.
 *
 * The report's rates arrive as fractions (`{"response_rate": 0.62}`), and a
 * fraction rendered straight is how "62.000000001%" reaches a page —
 * `0.83 * 100` is `83.00000000000001` in IEEE 754 and `0.29 * 100` is
 * `28.999999999999996`. Rounding to a whole percent is the one rule, applied
 * here and nowhere else; the counts beside it carry the precision anyone
 * actually needs.
 */
export function formatRate(rate: number | null): string {
  if (rate === null || !Number.isFinite(rate)) return copy('instructor_report_stats.absent_figure');
  return fillCopy('instructor_report_stats.percent', { percent: String(Math.round(rate * 100)) });
}
