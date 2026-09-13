import type { RatingDistribution } from './RatingHistogram';
import type { RateFigure } from './ResponseRateBar';

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
