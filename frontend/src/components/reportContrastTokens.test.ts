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
