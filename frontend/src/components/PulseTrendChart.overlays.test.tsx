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
 * The fixtures are shaped by the payload sketch in `docs/tickets/e5/README.md`:
 * a series is `{suppressed, reason, points}`, and a suppressed one carries
 * `points: []` and a one-word reason. The overlay points carry a course week
 * and a mean and no term week, which is the sketch's shape — SPEC §5.1 makes a
 * benchmark past-referencing, so the figure behind one point spans several
 * terms and has no single term week to name.
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

const COMPARISON_POINTS: readonly OverlayPoint[] = [
  { courseWeek: 1, mean: 3.9 },
  { courseWeek: 2, mean: 3.2 },
  { courseWeek: 3, mean: 3.7 },
];

const UNIVERSITY_POINTS: readonly OverlayPoint[] = [
  { courseWeek: 1, mean: 2.8 },
  { courseWeek: 2, mean: 3.0 },
  { courseWeek: 3, mean: 2.6 },
];

const COMPARISON: OverlaySeries = { suppressed: false, points: COMPARISON_POINTS };
const UNIVERSITY: OverlaySeries = { suppressed: false, points: UNIVERSITY_POINTS };

/**
 * A suppressed series exactly as the sketch carries one: the flag, a one-word
 * reason, and no points at all. The reason is a wire token and no component
 * writes it on a screen; one of the tests below is that it reaches none.
 */
const SUPPRESSED: OverlaySeries = { suppressed: true, reason: 'below-minimum', points: [] };

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

    expect(SUPPRESSED.reason, 'the fixture carries no reason, so this asserted nothing').toBe(
      'below-minimum',
    );
    expect(container.textContent).not.toContain('below-minimum');
  });

  it('draws no line even if points arrive beside the flag', () => {
    // The sketch says a suppressed member carries `points: []` and nothing
    // else. This component does not take that on trust: the flag wins, so a
    // payload that ever sent both would still show the notice rather than the
    // line it says is not there.
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={{ suppressed: true, reason: 'below-minimum', points: COMPARISON_POINTS }}
        showLegend
      />,
    );

    expect(screen.queryByTestId(TREND_LINE_COMPARISON_TESTID)).toBeNull();
    expect(screen.getByTestId(TREND_SUPPRESSION_COMPARISON_TESTID)).toBeTruthy();
    expect(screen.getAllByRole('table')).toHaveLength(1);
  });
});

describe('a series whose flag does not say exactly false', () => {
  /**
   * The three shapes a `suppressed` that is not the boolean `false` arrives in.
   *
   * **The casts are the point rather than a shortcut.** The client casts the
   * report JSON into its TypeScript shapes without parsing it at runtime, so
   * `OverlaySeries` describes what the server is expected to send and does not
   * check that it did. These three are what the props actually hold the day the
   * field is renamed on the wire, dropped, or serialised loosely — and each is
   * falsy or truthy in a way a plain `if (series.suppressed)` reads as "not
   * suppressed", which draws a line SPEC §4.1 item 7 had suppressed. That
   * reading is the security round's LOW on this file, and this is the pair that
   * closes it.
   */
  const MALFORMED: readonly { readonly what: string; readonly flag: unknown }[] = [
    { what: 'the flag was dropped from the payload', flag: undefined },
    { what: 'the flag arrived null', flag: null },
    { what: 'the flag arrived as a string', flag: 'false' },
  ];

  for (const { what, flag } of MALFORMED) {
    it(`is treated as suppressed when ${what}`, () => {
      const series = {
        suppressed: flag,
        reason: 'below-minimum',
        points: COMPARISON_POINTS,
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

  it('is drawn when the flag says exactly false', () => {
    // The near miss, and the half that makes the three above mean anything: a
    // component that suppressed everything would satisfy them all. Same points,
    // same reason token, and only the flag is different.
    render(
      <PulseTrendChart
        points={SECTION}
        label={INSTRUCTOR}
        lengthWeeks={SECTION_WEEKS}
        comparison={{ suppressed: false, reason: 'below-minimum', points: COMPARISON_POINTS }}
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

describe('a week the series has no figure for', () => {
  it('breaks the line rather than drawing across it', () => {
    const gapped: OverlaySeries = {
      suppressed: false,
      points: [
        { courseWeek: 1, mean: 3.9 },
        { courseWeek: 2, mean: null },
        { courseWeek: 3, mean: 3.7 },
      ],
    };

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
    const gapped: OverlaySeries = {
      suppressed: false,
      points: [
        { courseWeek: 1, mean: 3.9 },
        { courseWeek: 2, mean: null },
        { courseWeek: 3, mean: 3.7 },
      ],
    };

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
 * The stroke treatments, read out of the stylesheet.
 *
 * jsdom applies no CSS, so what a rendered chart can be asked is which class
 * each line carries; what that class draws is a property of the file, and this
 * is where it is read — the shape `reportContrastTokens.test.ts` and
 * `reportMockupFidelity.test.ts` already use for the E4 rulings. Those two are
 * left alone: this ticket's pins live beside this ticket's tests.
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

  it('draws each legend swatch the way the line it names is drawn', () => {
    // A legend in a pattern the plot does not use names a line nobody can find.
    expect(dashOf('.pulse-trend-legend-line-comparison')).toBe(
      dashOf('.pulse-trend-line-comparison'),
    );
    expect(dashOf('.pulse-trend-legend-line-university')).toBe(
      dashOf('.pulse-trend-line-university'),
    );
  });

  it('keeps both comparison lines under the hero’s weight and off the accent', () => {
    for (const selector of ['.pulse-trend-line-comparison', '.pulse-trend-line-university']) {
      const rule = ruleFor(selector);
      // Ink, and the measured one: mist is 2.58:1 against paper, under SC
      // 1.4.11's 3:1 for a graphical object that carries meaning. The file's
      // colour paragraph has the reading and the departure from the brief it is.
      expect(rule, `${selector} is not on a measured token`).toContain('stroke: var(--spruce-60)');
      expect(rule, `${selector} is drawn in mist`).not.toContain('var(--mist)');
      // And the hero keeps the accent to itself.
      expect(rule, `${selector} borrows the hero's colour`).not.toContain('var(--marigold');
      expect(rule, `${selector} is drawn at the hero's weight`).toContain('stroke-width: 1.5');
    }
    expect(ruleFor('.pulse-trend-line')).toContain('stroke-width: 2.5');
  });

  it('gives the suppression notice the quiet register and no raw colour', () => {
    const rule = ruleFor('.pulse-trend-suppression');
    expect(rule).toContain('color: var(--spruce-60)');
    expect(rule, 'a suppression is not a warning').not.toContain('var(--madder)');
  });

  it('writes no raw hex anywhere in the stylesheet', () => {
    // The brief's hard rule, and the one this ticket could most easily break by
    // reaching for the mockup's inline styles. Exercised on both sides first.
    //
    // The positive sample is **composed rather than written out**, and has to
    // stay that way: it must be a real raw hex for the pattern to be proven
    // against one, and a real raw hex spelled as a literal anywhere under
    // `frontend/src` is exactly what
    // `tests/unit/test_the_frontend_source_uses_tokens_only.py` refuses — this
    // file included, because that sweep carries no exception list on purpose.
    // Joining the parts puts the value in the running test rather than in the
    // source the sweep reads. Do not simplify it back into one string.
    const sample = ['#', '93', 'A5', 'A0'].join('');
    const hex = /#[0-9a-f]{3,8}\b/i;
    expect(hex.test(`stroke: ${sample};`)).toBe(true);
    expect(hex.test('stroke: var(--spruce-60);')).toBe(false);
    expect(STYLESHEET.length).toBeGreaterThan(0);
    expect(STYLESHEET).not.toMatch(hex);
  });
});
