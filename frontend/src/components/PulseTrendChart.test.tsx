import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import { PulseTrendChart, type TrendPoint } from './PulseTrendChart';

/**
 * The fixtures below are shaped by the payload sketch in
 * `docs/tickets/e4/README.md` — one trend row per published course week, a mean
 * that is `null` when nobody answered — with the term week each row's course
 * week falls in, which SPEC §2.2 requires on every course-level axis and E4-07
 * serves alongside it.
 *
 * The means are deliberately away from the scale's midpoint and away from each
 * other: a wrong y-mapping, an inverted axis or a rounding slip all move a 4.4
 * somewhere visibly different, while values clustered around 3.0 would land
 * within a pixel of where they belong however the arithmetic went.
 */
const THREE_WEEKS: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 4.1 },
  { courseWeek: 2, termWeek: 8, mean: 3.6 },
  // Course week 3 falls in term week 10 because term week 9 was the break. The
  // gap is real and it is the server's: nothing here may reconstruct it.
  { courseWeek: 3, termWeek: 10, mean: 4.4 },
];

/** The same three weeks, with the middle one unanswered. */
const A_SILENT_MIDDLE_WEEK: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 4.1 },
  { courseWeek: 2, termWeek: 8, mean: null },
  { courseWeek: 3, termWeek: 10, mean: 4.4 },
];

/** A week at the bottom of the scale, and one well above it. */
const A_WEEK_AT_THE_FLOOR: readonly TrendPoint[] = [
  { courseWeek: 1, termWeek: 7, mean: 1.0 },
  { courseWeek: 2, termWeek: 8, mean: 4.4 },
];

const INSTRUCTOR = 'Instructor';

// `@testing-library/react` registers its own cleanup only when `afterEach` is an
// ambient global, and ADR 0151 turns globals off on purpose. So the teardown is
// named here: without it every render in this file stacks up in one `document`,
// and a query that should find one table finds four.
afterEach(cleanup);

/** The value, or a failure naming what was missing rather than a `null` dereference. */
function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) {
    throw new Error(`${what} is not in the rendered chart, so this test asserted nothing.`);
  }
  return value;
}

/**
 * The plot, addressed by the class its own stylesheet paints it with.
 *
 * The drawing is `aria-hidden` and carries no text a role query can reach — it
 * is the picture, and the table beside it is the part a person can read. So the
 * assertions about geometry below go through the classes
 * `instructorReportTrend.css` styles, which are the component's published
 * surface rather than a selector added for a test.
 */
function plotOf(container: HTMLElement): Element {
  return required(container.querySelector('.pulse-trend-plot'), 'the plot');
}

interface Coordinate {
  readonly command: string;
  readonly x: number;
  readonly y: number;
}

const PATH_COMMAND = /(?<command>[ML])(?<x>-?[\d.]+) (?<y>-?[\d.]+)/g;

/** Every point the hero line's path draws, in order. */
function heroCoordinates(container: HTMLElement): Coordinate[] {
  const path = required(
    plotOf(container).querySelector('.pulse-trend-line'),
    'the hero line',
  );
  const drawing = required(path.getAttribute('d'), "the hero line's path data");
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
    'no coordinates were read out of the hero line, so every assertion below would ' +
      'have passed over an empty list.',
  ).toBeGreaterThan(0);
  return found;
}

/** Where the gridline for one point of the scale sits. */
function gridlineFor(container: HTMLElement, label: string): number {
  const labels = [...plotOf(container).querySelectorAll('.pulse-trend-grid-label')];
  expect(labels.map((element) => element.textContent)).toEqual([
    '1.0',
    '2.0',
    '3.0',
    '4.0',
    '5.0',
  ]);
  const wanted = labels.find((element) => element.textContent === label);
  return Number(
    required(required(wanted, `the gridline labelled ${label}`).getAttribute('y'), 'its y'),
  );
}

/** The text of every element with one of the plot's classes, in document order. */
function textsOf(container: HTMLElement, className: string): (string | null)[] {
  return [...plotOf(container).querySelectorAll(`.${className}`)].map(
    (element) => element.textContent,
  );
}

describe('PulseTrendChart', () => {
  it('carries every week and its value into the table beside the drawing', () => {
    render(<PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} />);

    const table = screen.getByRole('table', { name: 'Weekly ratings: Instructor' });
    expect(within(table).getAllByRole('rowheader').map((cell) => cell.textContent)).toEqual([
      'WK 01',
      'WK 02',
      'WK 03',
    ]);
    expect(within(table).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'TERM 07',
      '4.1',
      'TERM 08',
      '3.6',
      'TERM 10',
      '4.4',
    ]);
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Course week',
      'Term week',
      'Average rating',
    ]);
  });

  it('breaks the line at a week nobody answered and says so in words', () => {
    const { container } = render(
      <PulseTrendChart points={A_SILENT_MIDDLE_WEEK} label={INSTRUCTOR} />,
    );

    // The silent week is a sentence, not a figure: a zero is a rating, and a
    // week with no responses is not a week that was rated badly.
    const table = screen.getByRole('table', { name: 'Weekly ratings: Instructor' });
    const values = within(table).getAllByRole('cell').map((cell) => cell.textContent);
    expect(values).toEqual(['TERM 07', '4.1', 'TERM 08', 'No responses that week', 'TERM 10', '4.4']);
    expect(values).not.toContain('0.0');
    expect(values).not.toContain('0');

    // Two runs, so the line is visibly broken across the gap. The near miss is
    // the same three weeks with the middle one answered: one run, one `M`.
    const broken = heroCoordinates(container);
    expect(broken.filter((point) => point.command === 'M')).toHaveLength(2);

    const { container: unbroken } = render(
      <PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} />,
    );
    expect(heroCoordinates(unbroken).filter((point) => point.command === 'M')).toHaveLength(1);

    // Neither answered week is lost to the break: each is still drawn at its own
    // place on the axis, which is what makes the gap a gap rather than a chart
    // that stops early.
    expect(new Set(broken.map((point) => point.x)).size).toBe(2);
  });

  it('puts a week rated 1.0 on the scale’s bottom gridline', () => {
    const { container } = render(
      <PulseTrendChart points={A_WEEK_AT_THE_FLOOR} label={INSTRUCTOR} />,
    );

    const floor = gridlineFor(container, '1.0');
    const ceiling = gridlineFor(container, '5.0');
    // Higher ratings are higher on the screen, so the floor's y is the larger
    // number. Without this the assertion below would also hold for a chart drawn
    // upside down.
    expect(floor).toBeGreaterThan(ceiling);

    const [first, second] = heroCoordinates(container);
    expect(required(first, 'the first week').y).toBe(floor);
    expect(required(second, 'the second week').y).toBeLessThan(floor);

    // And the same week reads as a rating in the table, which is how a 1.0 week
    // and a silent week are told apart by anyone reading rather than looking.
    const table = screen.getByRole('table', { name: 'Weekly ratings: Instructor' });
    expect(within(table).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'TERM 07',
      '1.0',
      'TERM 08',
      '4.4',
    ]);
  });

  it('keeps the 1 to 5 scale whatever the weeks happen to span', () => {
    // Nothing here reaches below 3.6 or above 4.4. A chart that scaled to its
    // own data would draw its gridlines somewhere else entirely.
    const { container } = render(<PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} />);

    expect(textsOf(container, 'pulse-trend-grid-label')).toEqual([
      '1.0',
      '2.0',
      '3.0',
      '4.0',
      '5.0',
    ]);
    expect(
      heroCoordinates(container).every(
        (point) =>
          point.y <= gridlineFor(container, '1.0') && point.y >= gridlineFor(container, '5.0'),
      ),
    ).toBe(true);
  });

  it('takes the term week from the payload rather than counting from an offset', () => {
    // Course week 3 is term week 10 here: term week 9 was the break. A chart
    // that added an offset to the course week would print 09.
    const { container } = render(<PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} />);

    expect(textsOf(container, 'pulse-trend-tick-label')).toEqual(['WK 01', '02', '03']);
    expect(textsOf(container, 'pulse-trend-tick-sub')).toEqual(['TERM 07', '08', '10']);

    // The same course weeks in a section that started earlier in the term. Only
    // the sub-labels move, because only the term weeks did.
    const { container: earlier } = render(
      <PulseTrendChart
        points={THREE_WEEKS.map((point, index) => ({ ...point, termWeek: index + 3 }))}
        label={INSTRUCTOR}
      />,
    );
    expect(textsOf(earlier, 'pulse-trend-tick-label')).toEqual(['WK 01', '02', '03']);
    expect(textsOf(earlier, 'pulse-trend-tick-sub')).toEqual(['TERM 03', '04', '05']);
  });

  it('writes the term week under the course week, at the same place on the axis', () => {
    const { container } = render(<PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} />);

    const week = required(
      plotOf(container).querySelector('.pulse-trend-tick-label'),
      'the first week label',
    );
    const term = required(
      plotOf(container).querySelector('.pulse-trend-tick-sub'),
      'the first term-week label',
    );
    expect(week.textContent).toBe('WK 01');
    expect(term.textContent).toBe('TERM 07');
    expect(term.getAttribute('x')).toBe(week.getAttribute('x'));
    expect(Number(term.getAttribute('y'))).toBeGreaterThan(Number(week.getAttribute('y')));
  });

  it('marks the most recent answered week with the terminal dot', () => {
    // The last week here is silent, so the dot belongs to the week before it —
    // there is nothing to mark on a week nobody rated.
    const { container } = render(
      <PulseTrendChart
        points={[
          { courseWeek: 1, termWeek: 7, mean: 4.1 },
          { courseWeek: 2, termWeek: 8, mean: 3.6 },
          { courseWeek: 3, termWeek: 10, mean: null },
        ]}
        label={INSTRUCTOR}
      />,
    );

    const dots = [...plotOf(container).querySelectorAll('.pulse-trend-dot')];
    expect(dots).toHaveLength(1);
    const dot = required(dots[0], 'the terminal dot');
    const answered = heroCoordinates(container);
    const last = required(answered[answered.length - 1], 'the last drawn week');
    expect(Number(dot.getAttribute('cx'))).toBe(last.x);
    expect(Number(dot.getAttribute('cy'))).toBe(last.y);
  });

  it('shows the legend only when it is asked to, and names one line', () => {
    const { container } = render(<PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} />);
    expect(container.querySelector('.pulse-trend-legend')).toBeNull();

    render(<PulseTrendChart points={THREE_WEEKS} label={INSTRUCTOR} showLegend />);
    expect(screen.getByText('This section')).toBeTruthy();
    // E4 draws the section's own line and nothing else. The comparison and
    // university entries the prototype's legend carries arrive with E5, and
    // SPEC §4.1 item 1 is why they may not arrive early.
    expect(screen.queryByText(/comparable|university|benchmark/i)).toBeNull();
  });
});

/**
 * The stylesheet and the sources, read as text.
 *
 * jsdom applies no CSS and evaluates no media query, so a test that asked the
 * rendered chart what it computed to would be asking the wrong thing. The
 * motion budget and the reduced-motion switch are properties of the files, and
 * that is where these read them.
 */
// `fileURLToPath` rather than `new URL(path, import.meta.url)`: Vite rewrites
// that second form into an asset reference, which is a URL the build serves
// rather than a file on disk.
const HERE = dirname(fileURLToPath(import.meta.url));
const STYLESHEET = readFileSync(join(HERE, 'instructorReportTrend.css'), 'utf8');
const TOKENS = readFileSync(join(HERE, '..', '..', '..', 'design', 'tokens.css'), 'utf8');

/** One CSS rule: everything before a `{`, and everything inside it. */
const CSS_RULE = /(?<selector>[^{}]+)\{(?<body>[^{}]*)\}/g;

/** An `animation:` shorthand's value, up to the end of the declaration. */
const ANIMATION = /animation:\s*(?<value>[^;}]+)/;

/** The first time in a shorthand is its duration; a second one is a delay. */
const DURATION = /(?<milliseconds>\d+)ms/;

interface AnimatedRule {
  readonly selector: string;
  readonly duration: number;
}

/** Every rule in one stylesheet that animates something, with its duration. */
function animatedRules(stylesheet: string): AnimatedRule[] {
  const found: AnimatedRule[] = [];
  for (const rule of stylesheet.matchAll(CSS_RULE)) {
    const groups = rule.groups;
    if (groups === undefined) continue;
    const { selector, body } = groups;
    if (selector === undefined || body === undefined) continue;
    const animation = ANIMATION.exec(body);
    if (animation?.groups?.value === undefined) continue;
    const duration = DURATION.exec(animation.groups.value);
    if (duration?.groups?.milliseconds === undefined) continue;
    found.push({
      selector: selector.trim().split('\n').slice(-1).join('').trim(),
      duration: Number(duration.groups.milliseconds),
    });
  }
  return found;
}

describe('the trend family’s stylesheet', () => {
  it('gives the hero line one 600ms draw, and nothing else that long', () => {
    // The reader is exercised on both sides before the stylesheet is read: a
    // pattern that matched nothing would report a clean budget over any file at
    // all (`docs/MISTAKES.md` entry 3).
    expect(animatedRules('.a { animation: draw 600ms ease-out; }')).toEqual([
      { selector: '.a', duration: 600 },
    ]);
    expect(animatedRules('.a { color: var(--spruce); }')).toEqual([]);

    const animated = animatedRules(STYLESHEET);
    expect(animated.length).toBeGreaterThan(0);

    const signature = animated.filter((rule) => rule.duration === 600);
    expect(signature).toEqual([{ selector: '.pulse-trend-line', duration: 600 }]);
  });

  it('keeps every other piece of motion inside the 150 to 220ms budget', () => {
    // SPEC §7.6: the hero line draws once at 600ms and everything else lives in
    // 150–220ms. The week navigation's hover transition is the only other piece
    // of motion this ticket ships.
    const others = animatedRules(STYLESHEET).filter((rule) => rule.duration !== 600);
    expect(others.length).toBeGreaterThan(0);
    for (const rule of others) {
      expect(rule.duration, `${rule.selector} is outside the motion budget`).toBeGreaterThanOrEqual(
        150,
      );
      expect(rule.duration, `${rule.selector} is outside the motion budget`).toBeLessThanOrEqual(
        220,
      );
    }

    const transitions = [...STYLESHEET.matchAll(/transition:\s*(?<value>[^;}]+)/g)];
    expect(transitions.length).toBeGreaterThan(0);
    for (const transition of transitions) {
      const value = transition.groups?.value;
      const duration = value === undefined ? null : DURATION.exec(value);
      const milliseconds = Number(duration?.groups?.milliseconds ?? NaN);
      expect(milliseconds).toBeGreaterThanOrEqual(150);
      expect(milliseconds).toBeLessThanOrEqual(220);
    }
  });

  it('leaves reduced motion to the token file, and opts nothing out of it', () => {
    // Every animation above is a CSS animation on a class, which is what makes
    // the global switch reach it. An inline `style` animation, or one driven
    // from JavaScript, would not be removed by anything.
    expect(STYLESHEET).not.toContain('@media (prefers-reduced-motion');
    expect(TOKENS).toContain('@media (prefers-reduced-motion: reduce)');
    expect(TOKENS).toContain('animation: none !important');
  });
});

/**
 * SPEC §7.6 gives these components props and nothing else, and the ticket's
 * sixth criterion says it in one line: props in, DOM out. A rendered chart
 * cannot demonstrate the absence of a fetch it never had a reason to make, so
 * this reads the sources.
 */
const COMPONENT_SOURCES = [
  'PulseTrendChart.tsx',
  'TrendPair.tsx',
  'WeekNav.tsx',
  'instructorReportTrendCopy.ts',
] as const;

const DATA_ACCESS = [
  /\bfetch\s*\(/,
  /XMLHttpRequest/,
  /localStorage/,
  /sessionStorage/,
  /document\.cookie/,
  /from '\.\.\/api/,
] as const;

describe('the trend family', () => {
  it('fetches nothing, imports no API client and reads no session state', () => {
    const reaches = (source: string): boolean =>
      DATA_ACCESS.some((pattern) => pattern.test(source));

    // The readers, on both sides, before the sources are read.
    expect(reaches("  const answer = await fetch('/api/instructor/report');")).toBe(true);
    expect(reaches("import { copy } from './instructorReportTrendCopy';")).toBe(false);
    expect(reaches('  const weeks = [...publishedWeeks].sort();')).toBe(false);

    for (const name of COMPONENT_SOURCES) {
      const source = readFileSync(join(HERE, name), 'utf8');
      expect(source.length, `${name} was read as an empty file`).toBeGreaterThan(0);
      expect(reaches(source), `${name} reaches for data a prop should have carried`).toBe(false);
    }
  });
});
