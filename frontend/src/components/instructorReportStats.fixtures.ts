import type { RatingDistribution } from './RatingHistogram';
import type { RateFigure } from './ResponseRateBar';
import type { WorkloadBenchmark } from './StatPair';

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
 * The workload comparison figures — ticket E5-08, shaped by the
 * `workload_benchmark` member of the payload sketch in `docs/tickets/e5/README.md`.
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
 * **A suppressed member carries `suppressed` and a reason and nothing else.**
 * That is the sketch's own rule, and it is the shape rather than a convenience:
 * a mean sent beside a suppression is a figure the suppression is withholding,
 * so the payload does not carry one and neither do these.
 */
export const A_BENCHMARK_BOTH_REPORTING: WorkloadBenchmark = {
  comparison: { suppressed: false, mean: 8.96, median: 7.04 },
  university: { suppressed: false, mean: 10.46, median: 8.06 },
};

/** The comparison set is below the minimum; the university, computed over every
 * matching section institution-wide, is not. */
export const A_BENCHMARK_WITH_THE_COMPARISON_SUPPRESSED: WorkloadBenchmark = {
  comparison: { suppressed: true, reason: 'below-minimum' },
  university: { suppressed: false, mean: 10.46, median: 8.06 },
};

/** The other way round. Rare in production and not impossible — a section whose
 * length and level are unusual institution-wide can have a named comparison set
 * that clears the minimum while the university's does not. */
export const A_BENCHMARK_WITH_THE_UNIVERSITY_SUPPRESSED: WorkloadBenchmark = {
  comparison: { suppressed: false, mean: 8.96, median: 7.04 },
  university: { suppressed: true, reason: 'below-minimum' },
};

/**
 * A week the comparison set reports nothing in, unsuppressed.
 *
 * Not the same fact as a suppression: the set is large enough to report on, and
 * this week has no figure from it — the trend chart's `mean: null` week, in the
 * workload pair's shape. It is here because the two cases say different things
 * to a reader and the component has to tell them apart.
 */
export const A_BENCHMARK_WITH_NO_FIGURE_THIS_WEEK: WorkloadBenchmark = {
  comparison: { suppressed: false, mean: null, median: null },
  university: { suppressed: false, mean: 10.46, median: 8.06 },
};

/**
 * A payload whose flag cannot be read.
 *
 * The comparison member lost its `suppressed` on the way and carries figures;
 * the university member has a flag that is not a boolean at all. Neither is a
 * shape the server should ever send, and both are shapes a client casting JSON
 * can be handed — which is the whole reason the component's check is `=== false`
 * rather than a truthiness test. The cast is deliberate and named: this fixture
 * exists precisely to be a value the type forbids.
 */
export const A_BENCHMARK_WITH_AN_UNREADABLE_FLAG = {
  comparison: { reason: 'below-minimum', mean: 8.96, median: 7.04 },
  university: { suppressed: null, mean: 10.46, median: 8.06 },
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
