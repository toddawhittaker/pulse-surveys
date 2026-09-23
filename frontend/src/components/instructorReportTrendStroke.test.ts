import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The two overlay lines keep their stroke weight at any chart width — the E5
 * boundary round's accessibility finding on `instructorReportTrend.css`.
 *
 * The plot scales its viewBox to the column, so without
 * `vector-effect: non-scaling-stroke` a 1.5-unit dashed line renders thinner
 * than a pixel on a narrow screen. jsdom applies no stylesheet, so this reads
 * the CSS source, the way `reportContrastTokens.test.ts` does. The mutation it
 * kills is the declaration dropped from either rule; the near miss it spares is
 * the hero line, which deliberately does not carry it (its draw-on dashes are
 * measured against `pathLength`).
 */

// vitest serves modules on its own scheme, so `import.meta.url` is not a file
// URL here; the workspace root (`frontend/`) is the process's cwd instead.
const TREND_CSS = readFileSync(
  resolve(process.cwd(), 'src/components/instructorReportTrend.css'),
  'utf8',
);

/** The first declaration block following this exact selector. */
function ruleFor(selector: string): string {
  const at = TREND_CSS.indexOf(`${selector} {`);
  if (at < 0) {
    throw new Error(`No rule for "${selector}". If the selector was renamed, move this pin with it.`);
  }
  return TREND_CSS.slice(at, TREND_CSS.indexOf('}', at));
}

describe('the overlay lines hold their weight when the chart is scaled', () => {
  it('the comparison-set line strokes in screen pixels', () => {
    expect(ruleFor('.pulse-trend-line-comparison')).toContain('vector-effect: non-scaling-stroke');
  });

  it('the university line strokes in screen pixels', () => {
    expect(ruleFor('.pulse-trend-line-university')).toContain('vector-effect: non-scaling-stroke');
  });

  it('the hero line does not, because its draw-on is measured against pathLength', () => {
    expect(ruleFor('.pulse-trend-line')).not.toContain('vector-effect');
  });
});
