import type { RatingDistribution } from './RatingHistogram';
import type { RateFigure } from './ResponseRateBar';
import type { BenchmarkFigure, WorkloadBenchmark, WorkloadBenchmarkFigures } from './StatPair';

/**
 * The report weeks the stat component tests render — ticket E4-09.
 *
 * Shaped like the payload sketch in `docs/tickets/e4/README.md`, down to its
 * snake_case member names, so that each test does the small mapping E4-11 will
 * do for real and a divergence between the sketch and E4-07's schema shows up as
 * a compile error here rather than as a component that renders the wrong member.
 * These are fixtures for three components, not a claim about the API.
 *
 * **One departure from the sketch, named rather than smuggled:** `rates` carries
 * `validity_rate` but no count of valid responses, and SPEC §5.1's validity bar
 * needs one to say "12 of 13" without multiplying a rounded rate back out. The
 * fixtures add `valid_responses`; E4-07's schema is the authority the moment it
 * merges, and E4-11 is where a divergence is resolved (the breakdown's decision
 * 5).
 *
 * **The numbers are chosen so that a wrong rule renders a different string.**
 * A mean of 9.46 is "9.5" rounded and "9.4" truncated; a median of 8.04 is "8.0"
 * rounded and "8" if trailing zeroes are dropped; a rate of 0.29 is
 * `28.999999999999996` when multiplied out in IEEE 754 and 0.83 is
 * `83.00000000000001`. A fixture like 9.5 or 0.5 formats identically under every
 * wrong rule and would prove nothing (`docs/MISTAKES.md` entry 30's neighbourhood
 * — a fixture that cannot fail).
 */
export interface ReportWeekFixture {
  readonly rates: {
    readonly response_rate: number;
    readonly validity_rate: number;
    readonly responses: number;
    readonly enrolled: number;
    readonly valid_responses: number;
  };
  readonly streams: {
    readonly instructor: { readonly distribution: RatingDistribution };
    readonly course: { readonly distribution: RatingDistribution };
  };
  readonly workload: {
    readonly mean: number | null;
    readonly median: number | null;
  };
}

/** An ordinary week: thirteen of twenty-one responded, twelve of them valid. */
export const AN_ORDINARY_WEEK: ReportWeekFixture = {
  rates: {
    response_rate: 0.62,
    validity_rate: 0.92,
    responses: 13,
    enrolled: 21,
    valid_responses: 12,
  },
  streams: {
    instructor: { distribution: { '1': 0, '2': 1, '3': 4, '4': 5, '5': 3 } },
    course: { distribution: { '1': 1, '2': 2, '3': 3, '4': 4, '5': 3 } },
  },
  workload: { mean: 9.46, median: 8.04 },
};

/** A quiet week: six of twenty-one, five of those valid. */
export const A_THIN_WEEK: ReportWeekFixture = {
  rates: {
    response_rate: 0.29,
    validity_rate: 0.83,
    responses: 6,
    enrolled: 21,
    valid_responses: 5,
  },
  streams: {
    instructor: { distribution: { '1': 1, '2': 1, '3': 2, '4': 1, '5': 1 } },
    course: { distribution: { '1': 0, '2': 2, '3': 2, '4': 1, '5': 1 } },
  },
  workload: { mean: 6.25, median: 6.0 },
};

/**
 * The week nobody answered.
 *
 * Every figure the report draws has nothing behind it here: no bucket has a
 * count, there is no mean and no median, and the validity rate has no responses
 * to be a rate of. It drives every component's absent state, which is what the
 * ticket's fourth criterion asks for — one fixture, every figure.
 */
export const A_WEEK_NOBODY_ANSWERED: ReportWeekFixture = {
  rates: {
    response_rate: 0,
    validity_rate: 0,
    responses: 0,
    enrolled: 21,
    valid_responses: 0,
  },
  streams: {
    instructor: { distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 } },
    course: { distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 } },
  },
  workload: { mean: null, median: null },
};

/**
 * The workload comparison figures — ticket E5-08, reconciled by E5-10 to the
 * shipped `workload_benchmark` member of `app/schemas/report_benchmark.py`.
 *
 * **A column is two independently sealed figures**, not a flag and two numbers:
 * the schema seals the mean and the median separately and "neither rides on the
 * other's decision". The builders below are the only place a figure is written
 * out, so a fixture cannot drift back into the sketch's flat shape one literal
 * at a time.
 *
 * **No two figures in a fixture render the same string**, and none renders the
 * same string as the section's own pair (8.0 h and 9.5 h): a component that drew
 * the university's median where the comparison set's belongs would otherwise
 * agree with the wrong reading. **Each number is rounding-revealing** in the
 * E4-09 way — 8.96 is "9.0" rounded and "8.9" truncated, 7.04 is "7.0" rounded
 * and "7" with trailing zeroes dropped, 10.46 is "10.5" against "10.4", 8.06 is
 * "8.1" against "8.0" — so a wrong number rule prints a different string rather
 * than passing.
 *
 * **A suppressed figure carries `suppressed` and a reason and no number.** That
 * is the server's own rule, and it is the shape rather than a convenience: a
 * value sent beside a suppression is the figure the suppression is withholding.
 */
function reported(figure: number): BenchmarkFigure {
  return { suppressed: false, reason: null, figure };
}

/** A figure SPEC §4.1 item 7 withheld: sealed shut, with the wire's own token. */
const WITHHELD: BenchmarkFigure = { suppressed: true, reason: 'below-minimum', figure: null };

/** A figure the population has nothing for this week — unsuppressed and empty. */
const NO_FIGURE: BenchmarkFigure = { suppressed: false, reason: null, figure: null };

/** One whole column, both of whose figures report. */
function reporting(mean: number, median: number): WorkloadBenchmarkFigures {
  return { mean: reported(mean), median: reported(median) };
}

/** The comparison set's column, and the university's, in the numbers above. */
const COMPARISON_COLUMN = reporting(8.96, 7.04);
const UNIVERSITY_COLUMN = reporting(10.46, 8.06);

/** A column the server withheld outright: both figures sealed, neither carrying one. */
const WITHHELD_COLUMN: WorkloadBenchmarkFigures = { mean: WITHHELD, median: WITHHELD };

export const A_BENCHMARK_BOTH_REPORTING: WorkloadBenchmark = {
  comparison: COMPARISON_COLUMN,
  university: UNIVERSITY_COLUMN,
};

/** The comparison set is below the minimum; the university, computed over every
 * matching section institution-wide, is not. */
export const A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED: WorkloadBenchmark = {
  comparison: WITHHELD_COLUMN,
  university: UNIVERSITY_COLUMN,
};

/** The other way round. Rare in production and not impossible — a section whose
 * length and level are unusual institution-wide can have a named comparison set
 * that clears the minimum while the university's does not. */
export const A_BENCHMARK_WITH_THE_UNIVERSITY_SUPPRESSED: WorkloadBenchmark = {
  comparison: COMPARISON_COLUMN,
  university: WITHHELD_COLUMN,
};

/**
 * A week the comparison set reports nothing in, unsuppressed.
 *
 * Not the same fact as a suppression: the set is large enough to report on, and
 * this week has no figure from it — the trend chart's empty overlay week, in the
 * workload pair's shape. It is here because the two cases say different things
 * to a reader and the component has to tell them apart.
 */
export const A_BENCHMARK_WITH_NO_FIGURE_THIS_WEEK: WorkloadBenchmark = {
  comparison: { mean: NO_FIGURE, median: NO_FIGURE },
  university: UNIVERSITY_COLUMN,
};

/**
 * A column the server could answer for in one figure and not the other — E5-10.
 *
 * **The shape the sketch could not express**, and the reason the reconciliation
 * was worth doing: `workload_benchmark.comparison.mean` and `.median` are sealed
 * independently, so a payload may withhold one and report the other. A component
 * carrying one flag per column would have had to withhold both or show both.
 */
export const A_BENCHMARK_WITH_ONLY_THE_MEDIAN_WITHHELD: WorkloadBenchmark = {
  comparison: { mean: reported(8.96), median: WITHHELD },
  university: UNIVERSITY_COLUMN,
};

/**
 * A member the payload sent as `null`.
 *
 * The shape a server written in Python produces when a comparison figure comes
 * out as `None`: `json.dumps` writes `null`, and a JSON `null` is a member that
 * **was** sent and cannot be read, not a member that was left out. One character
 * from the absent case and a different fact — so it takes the withheld treatment
 * the other unreadable members take, and the component has to reach that branch
 * without reading a property off `null` on the way.
 *
 * Typed rather than cast, because `null` is a value the wire genuinely carries:
 * the security review's finding of 2026-09-13 was that the shape said otherwise
 * and the component crashed on it.
 */
export const A_BENCHMARK_WITH_A_NULL_MEMBER: WorkloadBenchmark = {
  comparison: null,
  university: UNIVERSITY_COLUMN,
};

/**
 * A payload whose flags cannot be read.
 *
 * The comparison column's figures lost their `suppressed` on the way and carry
 * numbers; the university column's flags are not booleans at all. Neither is a
 * shape the server should ever send, and both are shapes a client casting JSON
 * can be handed — which is the whole reason the component's check is `=== false`
 * rather than a truthiness test. The cast is deliberate and named: this fixture
 * exists precisely to be a value the type forbids.
 */
export const A_BENCHMARK_WITH_AN_UNREADABLE_FLAG = {
  comparison: {
    mean: { reason: 'below-minimum', figure: 8.96 },
    median: { reason: 'below-minimum', figure: 7.04 },
  },
  university: {
    mean: { suppressed: null, figure: 10.46 },
    median: { suppressed: null, figure: 8.06 },
  },
} as unknown as WorkloadBenchmark;

/** Everyone answered: the end of the range where a fraction is mistaken for a percent. */
export const A_FULL_RESPONSE_RATE: RateFigure = { rate: 1, numerator: 21, denominator: 21 };

/** A large section with one response: the other end, where a whole percent has to round up. */
export const A_SPARSE_RESPONSE_RATE: RateFigure = { rate: 0.005, numerator: 1, denominator: 200 };

/** The response rate of one week's fixture, in the shape the component takes. */
export function responseRateOf(week: ReportWeekFixture): RateFigure {
  return {
    rate: week.rates.response_rate,
    numerator: week.rates.responses,
    denominator: week.rates.enrolled,
  };
}

/** The validity rate of one week's fixture: valid responses out of responses (SPEC §3.3). */
export function validityRateOf(week: ReportWeekFixture): RateFigure {
  return {
    rate: week.rates.validity_rate,
    numerator: week.rates.valid_responses,
    denominator: week.rates.responses,
  };
}
