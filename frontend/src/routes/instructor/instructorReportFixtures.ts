import type { InstructorReportView, TaughtSectionView } from '../../api/instructor';

/**
 * The report payloads the page's tests render — ticket E4-11.
 *
 * **Shaped as the wire shapes them**, snake_case members and all, because these
 * describe `backend/app/schemas/report.py` rather than anything of this page's
 * choosing: a divergence between the schema and what the page maps then shows up
 * as a compile error here rather than as a report rendering the wrong member.
 * ADR 0151 puts a fixture module beside the test files it serves; this one sits
 * beside the two.
 *
 * **`comparison` is on every body below and is typed nowhere.** SPEC §4.1 item 7
 * puts the member on the wire from day one so E5's benchmarks have a chokepoint
 * to pass through, and nothing in E4 may render a comparison figure. The
 * fixtures carry it exactly as the server sends it so that "the page renders no
 * comparison" is a fact about a payload that had one, rather than about a
 * payload that did not (`docs/MISTAKES.md` entry 3 — a test that passes because
 * there was nothing there).
 *
 * **The numbers are chosen so a wrong rule renders a different string**, the way
 * `instructorReportStats.fixtures.ts` chose its: a mean of 9.46 is "9.5" rounded
 * and "9.4" truncated, a median of 8.04 is "8.0" rounded and "8" if trailing
 * zeroes are dropped, and a rate of 0.62 multiplied out in IEEE 754 is not a
 * whole number. Course week 4, term week 7 and a twelve-week section are three
 * different numbers, so serving one in another's place is visible.
 *
 * **Every week pair sits at one constant offset**, three, and that is a property
 * of the payload rather than a tidy-up: the server derives a section's term week
 * from its course week with one per-section constant, so within a single report
 * `term_week - course_week` is the same for every trend point and for the week
 * the report is about. E4-19's security round found E4-08's component fixtures
 * encoding a break week — a payload `app.services.reporting` cannot emit — and
 * these hold the property from the start. Three rather than zero, so a section
 * that began in the term's third week is what makes the two axes
 * distinguishable.
 *
 * **The published weeks have a hole in them on purpose.** `[2, 4, 7]` is a
 * section whose weeks 1, 3, 5 and 6 never published — a window that had not
 * closed, or a week the section does not run. A page that derived a range from
 * the first and last entries, or that stepped by one, offers a reader a week the
 * report cannot answer for; E4-11's third criterion is that it does neither.
 */

/** The section every fixture below is about, named as the server composes it. */
export const SECTION_ID = 'b6c0e2a4-8f1d-4c0a-9d3e-77aa0c5f2b19';
export const COURSE_LABEL = 'BIOL 215 R3WW — Cell Biology, Fall 2026';

/** A second section, so the menu has something to be a menu of. */
export const OTHER_SECTION_ID = 'e1f7d9b2-3a45-4e6c-8b0f-2d9c4a6e18f3';
export const OTHER_COURSE_LABEL = 'MATH 140 E1FF — College Algebra, Fall 2026';

/** Exactly the weeks the API says a report may be read for. Note the gaps. */
export const PUBLISHED_WEEKS = [2, 4, 7];

/** The configured response threshold, deliberately not the default 5 everywhere. */
export const SMALL_N_THRESHOLD = 4;

/** The section every report fixture is about, as the menu lists it. */
export const THIS_TAUGHT_SECTION: TaughtSectionView = {
  section_id: SECTION_ID,
  code: 'R3WW',
  course_label: COURSE_LABEL,
};

/** What the section-list route answers for a reader who teaches two sections. */
export const TWO_TAUGHT_SECTIONS: readonly TaughtSectionView[] = [
  THIS_TAUGHT_SECTION,
  { section_id: OTHER_SECTION_ID, code: 'E1FF', course_label: OTHER_COURSE_LABEL },
];

/** And for a reader who teaches exactly one. */
export const ONE_TAUGHT_SECTION: readonly TaughtSectionView[] = [THIS_TAUGHT_SECTION];

/** The instructor stream's comments, in the order the server randomized them. */
export const INSTRUCTOR_COMMENT =
  'Went to office hours for the first time this week. Should have gone sooner.';
export const COURSE_COMMENT =
  'The field sampling lab finally made the quadrat math click for me.';

/** A comment released from an earlier week, with the stream it answered. */
export const RELEASED_COMMENT =
  'The reading is stacking up faster than I can keep pace with, but the labs are good.';

/**
 * The wire body for one published week with data in it.
 *
 * `comparison` is present and suppressed, as every E4 payload's is.
 */
export const A_PUBLISHED_WEEK = {
  section: { code: 'R3WW', course_label: COURSE_LABEL, length_weeks: 12 },
  week: { course_week: 4, term_week: 7, published_weeks: PUBLISHED_WEEKS },
  rates: {
    response_rate: 0.62,
    validity_rate: 0.92,
    responses: 13,
    enrolled: 21,
    valid_responses: 12,
  },
  streams: {
    instructor: {
      trend: [
        { course_week: 2, term_week: 5, mean: 4.1 },
        // The published weeks have gaps; the two axes do not drift apart across
        // them. Course week 3 never published, so the trend steps from 2 to 4 —
        // and the term week steps with it, because the offset is constant.
        { course_week: 4, term_week: 7, mean: 3.6 },
      ],
      distribution: { '1': 0, '2': 1, '3': 4, '4': 5, '5': 3 },
      summary: {
        text: 'Students describe office hours as genuinely helpful. The most consistent criticism is pacing.',
        response_count: 13,
        held_note: null,
      },
      comments: [{ text: INSTRUCTOR_COMMENT, status: 'published', stream: 'instructor' }],
    },
    course: {
      trend: [
        { course_week: 2, term_week: 5, mean: 3.8 },
        { course_week: 4, term_week: 7, mean: 3.3 },
      ],
      distribution: { '1': 1, '2': 2, '3': 3, '4': 4, '5': 3 },
      summary: {
        text: 'The field sampling lab is called out as the strongest part of the week.',
        response_count: 13,
        held_note: null,
      },
      comments: [{ text: COURSE_COMMENT, status: 'published', stream: 'course' }],
    },
  },
  workload: { mean: 9.46, median: 8.04 },
  comparison: { suppressed: true, reason: 'below-minimum' },
  small_n: { suppressed: false, threshold: SMALL_N_THRESHOLD },
  released_from_earlier_weeks: [],
} satisfies InstructorReportView & { comparison: unknown };

/**
 * The week nobody answered.
 *
 * Every figure the report draws has nothing behind it: no bucket has a count,
 * there is no mean and no median, the validity rate has no responses to be a
 * rate of, and neither stream has a summary or a comment. The response rate is a
 * real zero over a real enrolment — twenty-one students, none of whom answered —
 * which is a different fact from the enrolment being empty, and both are drawn
 * apart below.
 */
export const A_WEEK_NOBODY_ANSWERED = {
  ...A_PUBLISHED_WEEK,
  week: { course_week: 2, term_week: 5, published_weeks: PUBLISHED_WEEKS },
  rates: {
    response_rate: 0,
    validity_rate: null,
    responses: 0,
    enrolled: 21,
    valid_responses: 0,
  },
  streams: {
    instructor: {
      trend: [{ course_week: 2, term_week: 5, mean: null }],
      distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
      summary: null,
      comments: [],
    },
    course: {
      trend: [{ course_week: 2, term_week: 5, mean: null }],
      distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
      summary: null,
      comments: [],
    },
  },
  workload: { mean: null, median: null },
} satisfies InstructorReportView & { comparison: unknown };

/**
 * A section nobody is enrolled in, whose rates are absent rather than zero.
 *
 * The schema's rule — "rates that have no value are `None` and never zero" —
 * only means something if the page renders the absence differently from a nought,
 * so this fixture and the one above are a pair.
 */
export const A_WEEK_WITH_NOBODY_ENROLLED = {
  ...A_WEEK_NOBODY_ANSWERED,
  rates: {
    response_rate: null,
    validity_rate: null,
    responses: 0,
    enrolled: 0,
    valid_responses: 0,
  },
} satisfies InstructorReportView & { comparison: unknown };

/**
 * A week below the response threshold.
 *
 * **The comment arrays are empty because the payload's are** — SPEC §4 hides
 * under-threshold comments in the payload rather than in the browser, and
 * `tests/e2e/instructor-report.spec.ts` is what asserts the wire itself. What
 * this fixture proves on the page is the other half: that the notice appears
 * exactly once across two suppressed groups (§4.1 item 5), and that the summary
 * still leads each of them, which §5.1 requires of a small-N week because there
 * the summary is the only comment signal.
 */
export const A_SMALL_N_WEEK = {
  ...A_PUBLISHED_WEEK,
  week: { course_week: 7, term_week: 10, published_weeks: PUBLISHED_WEEKS },
  rates: {
    response_rate: 0.14,
    validity_rate: 1,
    responses: 3,
    enrolled: 21,
    valid_responses: 3,
  },
  streams: {
    instructor: {
      ...A_PUBLISHED_WEEK.streams.instructor,
      summary: {
        text: 'All three responses mention the field sampling lab positively.',
        response_count: 3,
        held_note: null,
      },
      comments: [],
    },
    course: {
      ...A_PUBLISHED_WEEK.streams.course,
      summary: {
        text: 'Two note that the reading load felt heavier than usual.',
        response_count: 3,
        held_note: null,
      },
      comments: [],
    },
  },
  small_n: { suppressed: true, threshold: SMALL_N_THRESHOLD },
} satisfies InstructorReportView & { comparison: unknown };

/**
 * The latest published week, carrying ADR 0152's release.
 *
 * The released comment names no week and the payload gives it none; what it does
 * carry is its stream, which is what the card's optional chip is for — this is
 * the one list on the surface that holds both streams together.
 */
export const A_WEEK_WITH_A_RELEASE = {
  ...A_PUBLISHED_WEEK,
  released_from_earlier_weeks: [
    { text: RELEASED_COMMENT, status: 'published', stream: 'course' },
  ],
} satisfies InstructorReportView & { comparison: unknown };
