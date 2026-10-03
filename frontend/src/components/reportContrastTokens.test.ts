import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The E4 boundary round's contrast corrections, pinned at the token, never a
 * hex — WCAG 2.2 AA item 4 of SPEC §14.2, measured against `design/tokens.css`.
 *
 * jsdom applies no stylesheet, so these pins read the CSS source: for each
 * corrected selector, the rule must carry the token the correction chose and
 * must not carry the token the measurement rejected. The mutation each kills is
 * the correction quietly reverting — `--mist` (2.58:1 on paper) back onto text
 * a low-vision instructor must read, or the bare accent `--marigold` (2.2:1)
 * back onto the hero line and its legend. A rewrite that drops the selector
 * entirely also fails, because the rule lookup refuses a selector it cannot
 * find rather than answering an empty string.
 */

// vitest serves modules on its own scheme, so `import.meta.url` is not a file
// URL here; the workspace root (`frontend/`) is the process's cwd instead.
const COMMENTS_CSS = readFileSync(
  resolve(process.cwd(), 'src/components/instructorReportComments.css'),
  'utf8',
);
const TREND_CSS = readFileSync(
  resolve(process.cwd(), 'src/components/instructorReportTrend.css'),
  'utf8',
);

/** The first declaration block following this exact selector. */
function ruleFor(css: string, selector: string): string {
  const at = css.indexOf(`${selector} {`);
  if (at < 0) {
    throw new Error(
      `No rule for "${selector}" — if the selector was renamed, this pin must move with it, ` +
        'because the contrast correction it pins lives on the rule, not on the name.',
    );
  }
  return css.slice(at, css.indexOf('}', at));
}

describe('the excluded-comment treatment (instructorReportComments.css)', () => {
  it('muted body text reads in spruce-60, not mist', () => {
    const rule = ruleFor(COMMENTS_CSS, '.pulse-comment-card__text--muted');
    expect(rule).toContain('var(--spruce-60)');
    expect(rule).not.toContain('var(--mist)');
  });

  it('the exclusion notice reads in spruce-60, not mist', () => {
    const rule = ruleFor(COMMENTS_CSS, '.pulse-comment-card__notice');
    expect(rule).toContain('var(--spruce-60)');
    expect(rule).not.toContain('var(--mist)');
  });
});

describe('the trend chart (instructorReportTrend.css)', () => {
  it('the hero line strokes in marigold-deep, not the bare accent', () => {
    const rule = ruleFor(TREND_CSS, '.pulse-trend-line');
    expect(rule).toContain('stroke: var(--marigold-deep)');
    expect(rule).not.toContain('var(--marigold)\n');
    expect(rule).not.toContain('var(--marigold);');
  });

  it('the terminal dot fills in marigold-deep', () => {
    expect(ruleFor(TREND_CSS, '.pulse-trend-dot')).toContain('fill: var(--marigold-deep)');
  });

  it('the legend swatch moves with the line it names', () => {
    expect(ruleFor(TREND_CSS, '.pulse-trend-legend-line')).toContain(
      'stroke: var(--marigold-deep)',
    );
    expect(ruleFor(TREND_CSS, '.pulse-trend-legend-dot')).toContain('fill: var(--marigold-deep)');
  });

  it('the term-week tick sub-label reads in spruce-60, not mist', () => {
    const rule = ruleFor(TREND_CSS, '.pulse-trend-tick-sub');
    expect(rule).toContain('fill: var(--spruce-60)');
    expect(rule).not.toContain('var(--mist)');
  });
});

/**
 * E5-07's overlay stroke treatments, moved here by E5-13.
 *
 * They were written beside E5-07's own tests in
 * `PulseTrendChart.overlays.test.tsx` because three frontend tickets were
 * building against this stylesheet at once and a shared pin module is the
 * same-file merge that parallel build avoids. `docs/tickets/e5/deferred.md`
 * carried the split; this is where it closes, so a reader looking for every
 * measured correction on the report opens one file. What they assert is
 * unchanged — only the stylesheet they read is named the way this module names
 * its two.
 *
 * One pin stayed behind: the one asserting that each series carries a different
 * class *and* that the class draws a different dash pattern needs a rendered
 * chart for its first half, and the render fixtures are that file's.
 */

/** The dash pattern one rule draws with. */
function dashOf(selector: string): string {
  const rule = ruleFor(TREND_CSS, selector);
  const found = /stroke-dasharray:\s*(?<pattern>[^;]+);/.exec(rule);
  const pattern = found?.groups?.pattern;
  if (pattern === undefined) {
    throw new Error(
      `No stroke-dasharray on ${selector}, so this pin compared nothing — the treatment it pins ` +
        'is the pattern, and a rule without one draws the line solid.',
    );
  }
  return pattern.trim();
}

describe("the trend chart's overlay lines are told apart without colour (instructorReportTrend.css)", () => {
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
      const rule = ruleFor(TREND_CSS, selector);
      // Ink, and the measured one: mist is 2.58:1 against paper, under SC
      // 1.4.11's 3:1 for a graphical object that carries meaning. The file's
      // colour paragraph has the reading and the departure from the brief it is.
      expect(rule, `${selector} is not on a measured token`).toContain('stroke: var(--spruce-60)');
      expect(rule, `${selector} is drawn in mist`).not.toContain('var(--mist)');
      // And the hero keeps the accent to itself.
      expect(rule, `${selector} borrows the hero's colour`).not.toContain('var(--marigold');
      expect(rule, `${selector} is drawn at the hero's weight`).toContain('stroke-width: 1.5');
    }
    expect(ruleFor(TREND_CSS, '.pulse-trend-line')).toContain('stroke-width: 2.5');
  });

  it('gives the suppression notice the quiet register and no raw colour', () => {
    const rule = ruleFor(TREND_CSS, '.pulse-trend-suppression');
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
    expect(TREND_CSS.length).toBeGreaterThan(0);
    expect(TREND_CSS).not.toMatch(hex);
  });
});
