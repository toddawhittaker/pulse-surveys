import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import {
  PulseTrendChart,
  TREND_LEGEND_COMPARISON_TESTID,
  TREND_LEGEND_UNIVERSITY_TESTID,
  TREND_LINE_COMPARISON_TESTID,
  TREND_LINE_UNIVERSITY_TESTID,
  TREND_SUPPRESSION_COMPARISON_TESTID,
  TREND_SUPPRESSION_UNIVERSITY_TESTID,
  type OverlayPoint,
  type OverlaySeries,
  type TrendPoint,
} from './PulseTrendChart';

/**
 * The two comparison series — ticket E5-07.
 *
 * `PulseTrendChart.test.tsx` holds the single-line chart E4 shipped and is not
 * touched by this ticket; this file is the overlays, and it is a second file
 * beside the component for the reason `WeekEyebrow.courseLength.test.tsx` is
 * (ADR 0151's placement convention, one file per body of work).
 *
 * **The fixtures are the wire's own shape** — `app/schemas/report_benchmark.py`
 * as E5-05 shipped it, which E5-10 reconciled this component's props to. A
 * series is its weeks and nothing else; every published week is a point; and
 * each point's `mean` is a sealed figure carrying its own `suppressed`, its own
 * one-word `reason` and its own number. There is no series-level flag to write
 * here, because there is none on the wire. The three builders below are the only
 * place a point is written out, so a fixture cannot drift into the sketch's
 * shape one literal at a time.
 *
 * An overlay point carries a course week and no term week, which is the schema's
 * shape — SPEC §5.1 makes a benchmark past-referencing, so the figure behind one
 * point spans several terms and has no single term week to name.
 *
 * **No two series share a value in any week, and none of the twelve numbers
 * repeats.** A chart that drew one series' points onto another's path would
 * otherwise be invisible here: the assertions below read each line's own
 * coordinates, and coordinates that happen to coincide would agree with the
 * wrong drawing. For the same reason the three series sit at three heights —
 * the section highest, the comparison set under it, the university lowest — so
 * that a swap between the two overlays is a visible inversion rather than a
 * rounding difference.
 */
const SECTION_WEEKS = 12;

const SECTION: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 4, mean: 4.1 },
  { courseWeek: 2, termWeek: 5, mean: 3.6 },
  { courseWeek: 3, termWeek: 6, mean: 4.4 },
];

/** A week the population reported, sealed open, as the server sends one. */
function reported(courseWeek: number, figure: number): OverlayPoint {
  return { course_week: courseWeek, mean: { suppressed: false, reason: null, figure } };
}

/**
 * A week SPEC §4.1 item 7 withheld: the seal says so, there is no number, and the
 * one-word reason is the wire's token.
 *
 * The server's own rule is that a suppressed figure carries no figure — "a value
 * carrying both would be a suppressed figure on the wire" — so a fixture that
 * wrote one here would not be a payload this client can be sent. The one test
 * that does write one says in its own body that it is the contradiction.
 */
function withheld(courseWeek: number): OverlayPoint {
  return {
    course_week: courseWeek,
    mean: { suppressed: true, reason: 'below-minimum', figure: null },
  };
}

/**
 * A week the population reported nothing in — unsuppressed and empty.
 *
 * Not the same fact as a suppression: the set is large enough to report on and
 * this week has no figure from it. The two are told apart in the assertions
 * below, because a reader is owed the right one.
 */
function unreported(courseWeek: number): OverlayPoint {
  return { course_week: courseWeek, mean: { suppressed: false, reason: null, figure: null } };
}

const COMPARISON_POINTS: readonly OverlayPoint[] = [reported(1, 3.9), reported(2, 3.2), reported(3, 3.7)];

const UNIVERSITY_POINTS: readonly OverlayPoint[] = [reported(1, 2.8), reported(2, 3.0), reported(3, 2.6)];

const COMPARISON: OverlaySeries = { points: COMPARISON_POINTS };
const UNIVERSITY: OverlaySeries = { points: UNIVERSITY_POINTS };

/**
 * A series the server withheld altogether: every published week present as a
 * point, and every one of them sealed shut.
 *
 * **That is what a fully suppressed series looks like on the wire**, and it is
 * not an empty array: the points are the report's own published weeks, so the
 * series never says which weeks the comparison population answered in. The
 * reason token rides along and no component writes it on a screen; one of the
 * tests below is that it reaches none.
 */
const SUPPRESSED: OverlaySeries = { points: [withheld(1), withheld(2), withheld(3)] };

const INSTRUCTOR = 'Instructor';
const COMPARISON_LEGEND = 'Comparable 12-week courses';
const UNIVERSITY_LEGEND = 'University';

// `@testing-library/react` registers no cleanup of its own while ADR 0151 keeps
// vitest's globals off, so every render in this file would otherwise stack up in
// one `document`.
afterEach(cleanup);

/** The value, or a failure naming what was missing. */
function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`${what} is not in the rendered chart, so this test asserted nothing.`);
  }
  return value;
}

interface Coordinate {
  readonly command: string;
  readonly x: number;
  readonly y: number;
}

const PATH_COMMAND = /(?<command>[ML])(?<x>-?[\d.]+) (?<y>-?[\d.]+)/g;

/** Every point one path draws, in order, addressed by the selector that finds it. */
function coordinatesOf(container: HTMLElement, selector: string): Coordinate[] {
  const path = required(container.querySelector(selector), `the line at ${selector}`);
  const drawing = required(path.getAttribute('d'), `the path data at ${selector}`);
  const found: Coordinate[] = [];
  for (const match of drawing.matchAll(PATH_COMMAND)) {
    const groups = match.groups;
    if (groups === undefined) continue;
    const { command, x, y } = groups;
    if (command === undefined || x === undefined || y === undefined) continue;
    found.push({ command, x: Number(x), y: Number(y) });
  }
  expect(
    found.length,
    `no coordinates were read out of ${selector}, so the assertions on it asserted nothing.`,
  ).toBeGreaterThan(0);
  return found;
}

const HERO = '.pulse-trend-line';
const COMPARISON_LINE = `[data-testid="${TREND_LINE_COMPARISON_TESTID}"]`;
const UNIVERSITY_LINE = `[data-testid="${TREND_LINE_UNIVERSITY_TESTID}"]`;

/** A chart carrying both series, which is the state most of this file is about. */
function renderThreeLines(): HTMLElement {
  return render(
    <PulseTrendChart
      points={SECTION}
      label={INSTRUCTOR}
      lengthWeeks={SECTION_WEEKS}
      comparison={COMPARISON}
      university={UNIVERSITY}
      showLegend
    />,
  ).container;
}

describe('the three lines', () => {
  it('draws one path per series, each on the section’s own week axis', () => {
    const container = renderThreeLines();

    const hero = coordinatesOf(container, HERO);
    const comparison = coordinatesOf(container, COMPARISON_LINE);
    const university = coordinatesOf(container, UNIVERSITY_LINE);

    expect(hero).toHaveLength(3);
    expect(comparison).toHaveLength(3);
    expect(university).toHaveLength(3);

    // All three plot week N at the same place across the panel. Two series on
    // different horizontal domains would be two charts drawn over each other,
    // and nothing about the shape of either line would say so.
    expect(comparison.map((point) => point.x)).toEqual(hero.map((point) => point.x));
    expect(university.map((point) => point.x)).toEqual(hero.map((point) => point.x));
  });

  it('puts each series at its own heights, so no line is drawn from another’s numbers', () => {
    const container = renderThreeLines();

    const hero = coordinatesOf(container, HERO);
    const comparison = coordinatesOf(container, COMPARISON_LINE);
    const university = coordinatesOf(container, UNIVERSITY_LINE);

    // Higher ratings sit higher on the screen, so a larger mean is a smaller y.
    // Week by week, the fixtures put the section above the comparison set and
    // the comparison set above the university — the mutation this kills is the
    // two overlay props being read in each other's place, which swaps the lower
    // two lines and changes nothing else about the picture.
    for (const week of [0, 1, 2]) {
      const section = required(hero[week], `the section's week ${String(week + 1)}`);
      const comparable = required(comparison[week], `the comparison set's week ${String(week + 1)}`);
      const wide = required(university[week], `the university's week ${String(week + 1)}`);
      expect(section.y).toBeLessThan(comparable.y);
      expect(comparable.y).toBeLessThan(wide.y);
    }
  });

  it('leaves the terminal dot to the section’s line alone', () => {
    // The dot marks the section's most recent answered week; a benchmark has no
    // "most recent week of mine" to mark, and three dots would read as three
    // heroes.
    const container = renderThreeLines();
    expect(container.querySelectorAll('.pulse-trend-dot')).toHaveLength(1);
  });
});

describe('a series the payload did not send', () => {
  it('draws nothing at all: no line, no legend entry, no table, no notice', () => {
    // SPEC §4.1 item 1's edge in this ticket. The student surfaces render this
    // same component, and a prop with a drawing default would put a comparison
    // line in front of a reader whose payload carries none.
    const { container } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        showLegend
      />,
    );

    for (const testid of [
      TREND_LINE_COMPARISON_TESTID,
      TREND_LINE_UNIVERSITY_TESTID,
      TREND_LEGEND_COMPARISON_TESTID,
      TREND_LEGEND_UNIVERSITY_TESTID,
      TREND_SUPPRESSION_COMPARISON_TESTID,
      TREND_SUPPRESSION_UNIVERSITY_TESTID,
    ]) {
      expect(screen.queryByTestId(testid), `${testid} is in a chart given no benchmark`).toBeNull();
    }

    // One line, one table, one legend entry, and no comparison word anywhere —
    // which is the chart E4 shipped.
    expect(container.querySelectorAll('path')).toHaveLength(1);
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(container.querySelectorAll('.pulse-trend-legend-item')).toHaveLength(1);
    expect(screen.getByText('This section')).toBeTruthy();
    expect(screen.queryByText(/comparable|university|benchmark/i)).toBeNull();
  });

  it('is not the same state as a suppressed one', () => {
    // Without this the test above passes just as well over a component that
    // renders nothing for a suppressed series either, and the honest-absence
    // half of the ticket would be asserted by a chart that says nothing in
    // either case.
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={SUPPRESSED}
        university={SUPPRESSED}
        showLegend
      />,
    );

    expect(screen.getByTestId(TREND_SUPPRESSION_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.getByTestId(TREND_SUPPRESSION_UNIVERSITY_TESTID)).toBeTruthy();
  });
});

describe('a suppressed series', () => {
  it('states the suppression and leaves the other series alone', () => {
    // The two suppress independently — one fixture each way. §4.1 item 7 is a
    // rule about each figure, so a chart that hid both because one was hidden
    // would withhold a figure the payload was entitled to show.
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={SUPPRESSED}
        university={UNIVERSITY}
        showLegend
      />,
    );

    expect(screen.getByTestId(TREND_SUPPRESSION_COMPARISON_TESTID).textContent).toBe(
      'Comparable 12-week courses: no line this week. The set behind it is too small to report on.',
    );
    expect(screen.queryByTestId(TREND_LINE_COMPARISON_TESTID)).toBeNull();
    expect(screen.queryByTestId(TREND_LEGEND_COMPARISON_TESTID)).toBeNull();

    // The university line is untouched: drawn, named in the legend, and read
    // out in its own table.
    expect(screen.getByTestId(TREND_LINE_UNIVERSITY_TESTID)).toBeTruthy();
    expect(screen.getByTestId(TREND_LEGEND_UNIVERSITY_TESTID)).toBeTruthy();
    expect(screen.queryByTestId(TREND_SUPPRESSION_UNIVERSITY_TESTID)).toBeNull();
    expect(
      screen.getByRole('table', { name: 'Weekly ratings: Instructor, University' }),
    ).toBeTruthy();
  });

  it('states it the other way round too', () => {
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={COMPARISON}
        university={SUPPRESSED}
        showLegend
      />,
    );

    expect(screen.getByTestId(TREND_SUPPRESSION_UNIVERSITY_TESTID).textContent).toBe(
      'University: no line this week. The set behind it is too small to report on.',
    );
    expect(screen.queryByTestId(TREND_LINE_UNIVERSITY_TESTID)).toBeNull();
    expect(screen.queryByTestId(TREND_LEGEND_UNIVERSITY_TESTID)).toBeNull();

    expect(screen.getByTestId(TREND_LINE_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.getByTestId(TREND_LEGEND_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.queryByTestId(TREND_SUPPRESSION_COMPARISON_TESTID)).toBeNull();
  });

  it('publishes no table and no figure of any kind', () => {
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={SUPPRESSED}
        university={SUPPRESSED}
        showLegend
      />,
    );

    // The section's own table is the only one left. A suppressed series with a
    // table of "no figure" rows would be publishing the set's week list, which
    // is a shape of the set the suppression is withholding.
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(screen.getByRole('table', { name: 'Weekly ratings: Instructor' })).toBeTruthy();
  });

  it('writes the payload’s reason token on no screen', () => {
    // `reason` is a wire value, not a governed string (ADR 0159): the words a
    // reader sees come from the copy module. The token is carried through the
    // props so E5-10 can hand this component the payload whole.
    const { container } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={SUPPRESSED}
        university={SUPPRESSED}
        showLegend
      />,
    );

    expect(
      SUPPRESSED.points.map((point) => point.mean.reason),
      'the fixture carries no reason token, so this asserted nothing',
    ).toEqual(['below-minimum', 'below-minimum', 'below-minimum']);
    expect(container.textContent).not.toContain('below-minimum');
  });

  it('draws no week whose seal says suppressed, even when a figure arrives beside it', () => {
    // The server's rule is that `figure` is `null` wherever `suppressed` is
    // true, so a week carrying both is a payload contradicting itself. This
    // component does not take the number on trust: the seal wins, so a payload
    // that ever sent both would still show the notice rather than the line it
    // says is not there. Every week of this series is that contradiction, so
    // nothing at all is drawable.
    const contradicting: OverlaySeries = {
      points: COMPARISON_POINTS.map((point) => ({
        course_week: point.course_week,
        mean: { suppressed: true, reason: 'below-minimum', figure: point.mean.figure },
      })),
    };

    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={contradicting}
        showLegend
      />,
    );

    expect(screen.queryByTestId(TREND_LINE_COMPARISON_TESTID)).toBeNull();
    expect(screen.getByTestId(TREND_SUPPRESSION_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.getAllByRole('table')).toHaveLength(1);
  });
});

describe('a week whose seal does not say exactly false', () => {
  /**
   * The four shapes a per-point seal that is not "false beside a number" arrives
   * in.
   *
   * **The casts are the point rather than a shortcut.** The client casts the
   * report JSON into its TypeScript shapes without parsing it at runtime, so
   * `OverlayFigure` describes what the server is expected to send and does not
   * check that it did. These are what the props actually hold the day the field
   * is renamed on the wire, dropped, or serialised loosely — and each of the
   * first three is falsy or truthy in a way a plain `if (mean.suppressed)` reads
   * as "not suppressed", which draws a figure SPEC §4.1 item 7 had suppressed.
   * That reading is the security round's LOW on this file, carried down to the
   * per-point seal E5-10 reconciled the props to.
   *
   * The fourth is the other half of the seal: a flag that says exactly `false`
   * beside a number that is not one. A component that asked only about the flag
   * would plot the string and print `NaN` across the panel.
   */
  const MALFORMED: readonly { readonly what: string; readonly mean: unknown }[] = [
    { what: 'the flag was dropped from the payload', mean: { reason: 'below-minimum', figure: 3.9 } },
    { what: 'the flag arrived null', mean: { suppressed: null, reason: null, figure: 3.9 } },
    { what: 'the flag arrived as a string', mean: { suppressed: 'false', reason: null, figure: 3.9 } },
    {
      what: 'the figure arrived as a string',
      mean: { suppressed: false, reason: null, figure: '3.9' },
    },
  ];

  for (const { what, mean } of MALFORMED) {
    it(`is treated as withheld when ${what}`, () => {
      // Every week of the series carries the same malformed seal, so the series
      // has nothing drawable and the panel's notice is what a reader meets.
      const series = {
        points: COMPARISON_POINTS.map((point) => ({ course_week: point.course_week, mean })),
      } as unknown as OverlaySeries;

      render(
        <PulseTrendChart
          points={SECTION}
          label={INSTRUCTOR}
          lengthWeeks={SECTION_WEEKS}
          comparison={series}
          showLegend
        />,
      );

      // No line, no legend entry, no table — and the notice, so a reader is
      // told a series is missing rather than left with a chart that quietly
      // has one line fewer than it should.
      expect(screen.queryByTestId(TREND_LINE_COMPARISON_TESTID)).toBeNull();
      expect(screen.queryByTestId(TREND_LEGEND_COMPARISON_TESTID)).toBeNull();
      expect(screen.getAllByRole('table')).toHaveLength(1);
      expect(screen.getByTestId(TREND_SUPPRESSION_COMPARISON_TESTID).textContent).toBe(
        'Comparable 12-week courses: no line this week. The set behind it is too small to report on.',
      );
    });
  }

  it('is drawn when the seal says exactly false beside a real number', () => {
    // The near miss, and the half that makes the four above mean anything: a
    // component that withheld everything would satisfy them all. The same three
    // weeks, and only the seal is well formed.
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={COMPARISON}
        showLegend
      />,
    );

    expect(screen.getByTestId(TREND_LINE_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.getByTestId(TREND_LEGEND_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.queryByTestId(TREND_SUPPRESSION_COMPARISON_TESTID)).toBeNull();
    expect(
      screen.getByRole('table', { name: `Weekly ratings: Instructor, ${COMPARISON_LEGEND}` }),
    ).toBeTruthy();
  });

  it('is a different question from a prop that was never sent', () => {
    // The boundary the fail-closed reading must not cross. A malformed member
    // is still a member: the payload said something about this series and the
    // chart could not read it, so it says so. An absent prop said nothing at
    // all — §4.1 item 1's case — and a notice there would be the chart
    // announcing a comparison to a reader whose payload carries none.
    const malformed = { reason: 'below-minimum', points: [] } as unknown as OverlaySeries;

    const { container: present } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={malformed}
        showLegend
      />,
    );
    expect(present.querySelectorAll('.pulse-trend-suppression')).toHaveLength(1);

    const { container: absent } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        showLegend
      />,
    );
    expect(absent.querySelectorAll('.pulse-trend-suppression')).toHaveLength(0);
    expect(absent.querySelectorAll('path')).toHaveLength(1);
  });
});

/** One week reported, one week the population reported nothing in, one reported. */
const GAPPED: OverlaySeries = { points: [reported(1, 3.9), unreported(2), reported(3, 3.7)] };

/** The same three weeks, with the middle one withheld by §4.1 item 7 instead. */
const PARTLY_WITHHELD: OverlaySeries = {
  points: [reported(1, 3.9), withheld(2), reported(3, 3.7)],
};

describe('a week the series has no figure for', () => {
  it('breaks the line rather than drawing across it', () => {
    const gapped = GAPPED;

    const { container } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={gapped}
        showLegend
      />,
    );

    // Two runs: the line stops at week 1 and starts again at week 3. The near
    // miss is the same three weeks with the middle one reported, which is one
    // run and one `M`.
    const broken = coordinatesOf(container, COMPARISON_LINE);
    expect(broken.filter((point) => point.command === 'M')).toHaveLength(2);
    expect(new Set(broken.map((point) => point.x)).size).toBe(2);

    const { container: unbroken } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={COMPARISON}
        showLegend
      />,
    );
    expect(
      coordinatesOf(unbroken, COMPARISON_LINE).filter((point) => point.command === 'M'),
    ).toHaveLength(1);
  });

  it('says so in words, and does not call it a rating of zero', () => {
    const gapped = GAPPED;

    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={gapped}
        showLegend
      />,
    );

    const table = screen.getByRole('table', {
      name: `Weekly ratings: Instructor, ${COMPARISON_LEGEND}`,
    });
    const values = within(table)
      .getAllByRole('cell')
      .map((cell) => cell.textContent);
    expect(values).toEqual(['3.9', 'No figure that week', '3.7']);
    expect(values).not.toContain('0.0');
  });
});

describe('a series some of whose weeks are withheld', () => {
  it('draws the weeks it has, leaves a gap at the withheld one, and posts no notice', () => {
    // The per-point decision, which is what E5-10 reconciled these props to
    // (ADR 0171). Week 2 is withheld by §4.1 item 7 and weeks 1 and 3 are not,
    // so the line is drawn in two runs with a hole between them — and no notice,
    // because the series is on the panel and a reader can see where it stops.
    // The alternative the ADR rejects is a notice whenever any week is withheld,
    // which would put "no line this week" under a line.
    const { container } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={PARTLY_WITHHELD}
        showLegend
      />,
    );

    const drawn = coordinatesOf(container, COMPARISON_LINE);
    expect(drawn.filter((point) => point.command === 'M')).toHaveLength(2);
    expect(new Set(drawn.map((point) => point.x)).size).toBe(2);
    expect(screen.queryByTestId(TREND_SUPPRESSION_COMPARISON_TESTID)).toBeNull();
    expect(screen.getByTestId(TREND_LEGEND_COMPARISON_TESTID)).toBeTruthy();

    // And the withheld week's own number is nowhere: neither on the path nor in
    // the table beside it, which reads it as an absence like any other.
    const table = screen.getByRole('table', {
      name: `Weekly ratings: Instructor, ${COMPARISON_LEGEND}`,
    });
    expect(
      within(table)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['3.9', 'No figure that week', '3.7']);
  });

  it('posts the notice once every week of it is withheld, and not before', () => {
    // The boundary, both sides of it, one week apart: a series with a single
    // drawable week draws, and the same series with that week withheld too says
    // so in words. Without the first half, a component that posted the notice
    // whenever *any* week was withheld would pass the second.
    const oneWeekLeft: OverlaySeries = {
      points: [withheld(1), withheld(2), reported(3, 3.7)],
    };

    const { container: drawing } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={oneWeekLeft}
        showLegend
      />,
    );
    expect(drawing.querySelectorAll(`[data-testid="${TREND_LINE_COMPARISON_TESTID}"]`)).toHaveLength(1);
    expect(drawing.querySelectorAll('.pulse-trend-suppression')).toHaveLength(0);

    const { container: silent } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={SUPPRESSED}
        showLegend
      />,
    );
    expect(silent.querySelectorAll(`[data-testid="${TREND_LINE_COMPARISON_TESTID}"]`)).toHaveLength(0);
    expect(silent.querySelectorAll('.pulse-trend-suppression')).toHaveLength(1);
  });
});

describe('a member the payload sent without its weeks', () => {
  /**
   * The shapes a `points` that is not an array of weeks arrives in.
   *
   * `points` is required by the schema, so each of these is a malformed
   * first-party payload — the same class as an unreadable seal, and it takes the
   * same treatment. **Before E5-10 the first of them crashed the panel**: the
   * reader returned `undefined` for a member whose flag said `false` and whose
   * `points` key was missing, and the spread that builds the week axis threw, so
   * the whole report's render failed. `docs/tickets/e5/deferred.md` carried it
   * as E5-10's, and this is the pin its done-when asks for.
   */
  const WITHOUT_WEEKS: readonly { readonly what: string; readonly series: unknown }[] = [
    { what: 'there is no points key at all', series: { reason: 'below-minimum' } },
    { what: 'points arrived null', series: { points: null } },
    { what: 'points arrived as an object', series: { points: { 1: 3.9 } } },
    { what: 'the member itself arrived null', series: null },
  ];

  for (const { what, series } of WITHOUT_WEEKS) {
    it(`renders the suppressed treatment when ${what}`, () => {
      const { container } = render(
        <PulseTrendChart
          points={SECTION}
          label={INSTRUCTOR}
          lengthWeeks={SECTION_WEEKS}
          comparison={series as OverlaySeries}
          showLegend
        />,
      );

      // The panel rendered at all, which is the half the crash took away: the
      // section's own line and its table are on the page.
      expect(container.querySelectorAll('.pulse-trend-line')).toHaveLength(1);
      expect(screen.getAllByRole('table')).toHaveLength(1);

      // And the member said something, because it was there.
      expect(screen.queryByTestId(TREND_LINE_COMPARISON_TESTID)).toBeNull();
      expect(screen.getByTestId(TREND_SUPPRESSION_COMPARISON_TESTID).textContent).toBe(
        'Comparable 12-week courses: no line this week. The set behind it is too small to report on.',
      );
    });
  }

  it('still draws the axis over the section’s own term', () => {
    // The crash was in the week-axis calculation, so the near miss is a panel
    // that renders and draws a shorter axis. Twelve ticks is `lengthWeeks`,
    // which is what the axis is (E4-21).
    const { container } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={{ reason: 'below-minimum' } as unknown as OverlaySeries}
      />,
    );

    expect(container.querySelectorAll('.pulse-trend-tick-label')).toHaveLength(SECTION_WEEKS);
  });
});

describe('the accessible alternative', () => {
  it('gives each drawn series a table of its own weeks and values', () => {
    renderThreeLines();

    // Three tables, each named by the panel it belongs to and the series it
    // carries, so a reader hearing them can tell which is which.
    expect(
      screen.getAllByRole('table').map((table) => within(table).getByRole('caption').textContent),
    ).toEqual([
      'Weekly ratings: Instructor',
      `Weekly ratings: Instructor, ${COMPARISON_LEGEND}`,
      `Weekly ratings: Instructor, ${UNIVERSITY_LEGEND}`,
    ]);

    const comparison = screen.getByRole('table', {
      name: `Weekly ratings: Instructor, ${COMPARISON_LEGEND}`,
    });
    expect(
      within(comparison)
        .getAllByRole('rowheader')
        .map((cell) => cell.textContent),
    ).toEqual(['WK 01', 'WK 02', 'WK 03']);
    expect(
      within(comparison)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['3.9', '3.2', '3.7']);

    const university = screen.getByRole('table', {
      name: `Weekly ratings: Instructor, ${UNIVERSITY_LEGEND}`,
    });
    expect(
      within(university)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['2.8', '3.0', '2.6']);

    // And no term-week column on either: an overlay point carries no term week,
    // and a column filled by counting from the section's would be the client
    // derivation SPEC §2.2 forbids.
    expect(
      within(comparison)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual(['Course week', 'Average rating']);
  });
});

describe('the legend', () => {
  it('names the three lines in the brief’s words', () => {
    renderThreeLines();

    const legend = required(document.querySelector('.pulse-trend-legend'), 'the legend');
    expect([...legend.querySelectorAll('.pulse-trend-legend-item')].map((item) => item.textContent)).toEqual(
      ['This section', COMPARISON_LEGEND, UNIVERSITY_LEGEND],
    );
  });

  it('takes the comparison label’s week count from the section’s length', () => {
    // `design/Usage Rules.md` §1: the legend names the comparison honestly, and
    // comparables are same-length (SPEC §5.1). The number is the API's
    // `length_weeks`, which this component is already given for its axis —
    // nothing here derives a length from a section code, which
    // `tests/unit/test_no_frontend_source_derives_how_long_a_section_runs.py`
    // holds the whole tree to.
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={8}
        comparison={COMPARISON}
        showLegend
      />,
    );

    expect(screen.getByText('Comparable 8-week courses')).toBeTruthy();
    expect(screen.queryByText(COMPARISON_LEGEND)).toBeNull();
  });

  it('carries no ranking or composite language', () => {
    // SPEC §4.1 item 4, self-checked before review as the ticket's fourth
    // criterion asks. The shipped strings are swept globally by
    // `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`;
    // this is the same rule read off what the panel actually renders, notices
    // and legend together.
    const forbidden =
      /\b(rank(?:ed|ing)?|percentile|composite|overall score|top performer|underperform|better than|worse than|above average|below average|beats?|leader)\b/i;

    // Both directions before the verdict (`docs/MISTAKES.md` entry 3): a
    // pattern that has gone blind reports a clean panel.
    expect(forbidden.test('This section is ranked above average against its peers.')).toBe(true);
    expect(forbidden.test(COMPARISON_LEGEND)).toBe(false);

    const { container } = render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={SUPPRESSED}
        university={UNIVERSITY}
        showLegend
      />,
    );
    const rendered = container.textContent ?? '';
    expect(rendered.length, 'the panel rendered no text at all').toBeGreaterThan(0);
    expect(rendered).not.toMatch(forbidden);
  });
});

/**
 * The one stroke pin that needs a rendered chart to mean anything.
 *
 * jsdom applies no CSS, so what a rendered chart can be asked is which class
 * each line carries; what that class draws is a property of the file. The test
 * below asks both halves in one breath, which is why it is here and not with
 * the rest of the report's measured corrections: a class that styled nothing
 * would satisfy the class half on its own, and the render it needs is this
 * file's.
 *
 * **E5-07's other four stroke pins moved to `reportContrastTokens.test.ts`**
 * (E5-13, closing `docs/tickets/e5/deferred.md`'s entry on the split). Every
 * pin that reads only `instructorReportTrend.css` is there now, with the rest
 * of the report's stylesheet rulings, so "every contrast correction on the
 * report" is one file to open. The rule the split follows: a pin that reads
 * only the stylesheet goes to the pin module; a pin that reads a rendering
 * stays beside the tests that build one.
 */
const HERE = dirname(fileURLToPath(import.meta.url));
const STYLESHEET = readFileSync(join(HERE, 'instructorReportTrend.css'), 'utf8');

/** The first declaration block following this exact selector. */
function ruleFor(selector: string): string {
  const at = STYLESHEET.indexOf(`${selector} {`);
  if (at < 0) {
    throw new Error(
      `No rule for "${selector}" — if the selector was renamed, this pin must move with it, ` +
        'because the treatment it pins lives on the rule, not on the name.',
    );
  }
  return STYLESHEET.slice(at, STYLESHEET.indexOf('}', at));
}

/** The dash pattern one rule draws with. */
function dashOf(selector: string): string {
  const rule = ruleFor(selector);
  const found = /stroke-dasharray:\s*(?<pattern>[^;]+);/.exec(rule);
  return required(found?.groups?.pattern, `a stroke-dasharray on ${selector}`).trim();
}

describe('the lines are told apart without colour', () => {
  it('carries a different class, and so a different dash pattern, per series', () => {
    const container = renderThreeLines();

    // The class is what a rendering carries; the pattern is what the class
    // draws. Both halves, because a class that styled nothing would satisfy the
    // first on its own.
    expect(
      required(container.querySelector(COMPARISON_LINE), 'the comparison line').getAttribute(
        'class',
      ),
    ).toBe('pulse-trend-line-comparison');
    expect(
      required(container.querySelector(UNIVERSITY_LINE), 'the university line').getAttribute(
        'class',
      ),
    ).toBe('pulse-trend-line-university');

    const comparison = dashOf('.pulse-trend-line-comparison');
    const university = dashOf('.pulse-trend-line-university');
    expect(comparison).not.toBe(university);

    // And neither is the hero's, which is not a pattern at all: the section's
    // line carries `stroke-dasharray: 1` against `pathLength="1"` so that the
    // draw-on animation runs in units of the whole stroke. A solid hero between
    // a dashed line and a dotted one is three treatments, not two.
    expect(ruleFor('.pulse-trend-line')).toContain('stroke-dasharray: 1;');
    expect(comparison).not.toBe('1');
    expect(university).not.toBe('1');
  });
});
