import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The parts of E4-21 that live only in a stylesheet, pinned at the rule.
 *
 * jsdom applies no CSS, so nothing a rendered component can be asked will see
 * the card, the arrow size, the separator or the face a comment is set in. Each
 * of them is a measurement `design/InstructorMondayReport.dc.html` and its
 * component files settle, and each would revert silently — a tidy-up that puts
 * the reading column back at 720px, a rule that returns the display face to a
 * comment card — with every other test in this package still green. So these
 * read the sources, the way `reportContrastTokens.test.ts` reads them for the
 * boundary round's contrast corrections.
 *
 * **What is asserted is the token or the mockup's own number**, never a hex and
 * never a colour computed here. Where the mockup writes a bare pixel value that
 * is not on the ramp — the 96px bar box, the 28px arrows — that value is what
 * the rule must carry.
 *
 * `ruleFor` is a copy of the neighbouring module's five lines rather than an
 * import: that one is scoped to a contrast correction and is documented as such,
 * and a shared reader would have to live in a non-test module, which the
 * component-string sweep reads as shipped source.
 */

// vitest serves modules on its own scheme, so `import.meta.url` is not a file
// URL here; the workspace root (`frontend/`) is the process's cwd instead.
const read = (name: string): string =>
  readFileSync(resolve(process.cwd(), `src/components/${name}`), 'utf8');

const PAGE_CSS = read('instructorReportPage.css');
const STATS_CSS = read('instructorReportStats.css');
const COMMENTS_CSS = read('instructorReportComments.css');
const TREND_CSS = read('instructorReportTrend.css');

/** The first declaration block following this exact selector. */
function ruleFor(css: string, selector: string): string {
  const at = css.indexOf(`${selector} {`);
  if (at < 0) {
    throw new Error(
      `No rule for "${selector}" — if the selector was renamed, this pin must move with it, ` +
        'because the fidelity item it pins lives on the rule, not on the name.',
    );
  }
  return css.slice(at, css.indexOf('}', at));
}

describe('the report is a white card on the chalk page', () => {
  it('is paper, hairline-bordered, card-radiused and carries the one shadow', () => {
    // `design/InstructorMondayReport.dc.html:12`. Rendering straight onto the
    // chalk page is the state this replaces.
    const rule = ruleFor(PAGE_CSS, '.pulse-report');
    expect(rule).toContain('background: var(--paper)');
    expect(rule).toContain('border: 1px solid var(--hairline)');
    expect(rule).toContain('border-radius: var(--radius-card)');
    expect(rule).toContain('box-shadow: var(--shadow-card)');
  });

  it('is 760px wide, which is the mockup and not the brief’s rule of thumb', () => {
    const rule = ruleFor(PAGE_CSS, '.pulse-report');
    expect(rule).toContain('760px');
    expect(rule).not.toContain('720px');
  });
});

describe('the header row', () => {
  it('lays the eyebrow and the week arrows out as one row', () => {
    const rule = ruleFor(PAGE_CSS, '.pulse-report-eyebrow-row');
    expect(rule).toContain('display: flex');
    expect(rule).toContain('justify-content: space-between');
  });

  it('drops the second separator the eyebrow used to render', () => {
    // The course-week half of the eyebrow ends in a comma (governed copy since
    // FIX-01) and `styles.css` prepends a middot to every quiet segment, so the
    // first quiet segment rendered both. Only the segment that follows the
    // course-week half loses it: anything after that keeps the middot, which is
    // the separator the ruling of 2026-09-07 puts before the closing instant.
    const selector = '.pulse-report .pulse-eyebrow-week + .pulse-eyebrow-quiet::before';
    expect(ruleFor(PAGE_CSS, selector)).toContain('content: none');

    // Every eyebrow rule in this file is scoped to the report, because the
    // student survey renders the same spans from the same copy and its eyebrow
    // is not this ticket's to change.
    const eyebrowSelectors = [...PAGE_CSS.matchAll(/(?<selector>[^{}]*)\{/g)]
      .map((rule) => (rule.groups?.selector ?? '').split('\n').slice(-1).join('').trim())
      .filter((found) => found.includes('.pulse-eyebrow'));
    expect(eyebrowSelectors.length).toBeGreaterThan(0);
    for (const found of eyebrowSelectors) {
      expect(found.startsWith('.pulse-report'), `${found} reaches outside the report`).toBe(true);
    }
  });

  it('gives the arrows the mockup’s 28px square and 14px glyph', () => {
    const rule = ruleFor(TREND_CSS, '.pulse-week-nav-button');
    expect(rule).toContain('width: 28px');
    expect(rule).toContain('height: 28px');
    expect(rule).toContain('font-size: 14px');
  });

  it('spaces the pulse divider as the mockup does', () => {
    // `margin: 16px 0 32px` in the mockup, which is space-4 and space-6 on the
    // ramp. The survey's own divider rule is what wins without this one.
    expect(ruleFor(PAGE_CSS, '.pulse-report .pulse-line-divider')).toContain(
      'margin: var(--space-4) 0 var(--space-6)',
    );
  });
});

describe('the histogram’s two boxes', () => {
  it('gives the bars row the whole 96px and the ticks a row of their own', () => {
    const bars = ruleFor(STATS_CSS, '.pulse-stat-histogram-bars');
    expect(bars).toContain('height: 96px');
    expect(bars).toContain('align-items: flex-end');

    // The bucket fills that row rather than declaring a second 96px of its own,
    // which is the layout that pushed a tall bucket's count out of the chart.
    const bucket = ruleFor(STATS_CSS, '.pulse-stat-histogram-bucket');
    expect(bucket).toContain('height: 100%');
    expect(bucket).not.toContain('96px');
  });

  it('draws one continuous rule under the bars, not one per bucket', () => {
    expect(ruleFor(STATS_CSS, '.pulse-stat-histogram-ticks')).toContain(
      'border-top: 1px solid var(--hairline)',
    );
    expect(ruleFor(STATS_CSS, '.pulse-stat-histogram-tick')).not.toContain('border-top');
  });

  it('sets the mean’s figure in full ink', () => {
    expect(ruleFor(STATS_CSS, '.pulse-stat-histogram-mean')).toContain('color: var(--spruce)');
  });
});

describe('a student’s comment', () => {
  it('is set in the body face, as the owner ruled on 2026-09-13', () => {
    const rule = ruleFor(COMMENTS_CSS, '.pulse-comment-card__text');
    expect(rule).toContain('font-family: var(--font-body)');
    expect(rule).not.toContain('var(--font-display)');
  });
});
