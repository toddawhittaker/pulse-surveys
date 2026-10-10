import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Every text input's boundary reaches WCAG 2.2 SC 1.4.11's 3:1 against the
 * surface it sits on — SPEC §14.2's accessibility item, measured from
 * `design/tokens.css` rather than from a hex written here.
 *
 * jsdom applies no stylesheet, so this reads the CSS source, the way
 * `reportContrastTokens.test.ts` does: the token's ratio is computed from the
 * values `tokens.css` declares, and each input's rule must draw its border in
 * that token. The mutations it kills are an input reverting to `--hairline`
 * (1.30:1 on paper) and the token's value drifting under 3:1.
 */

// vitest's cwd is the workspace root (`frontend/`).
const read = (path: string): string => readFileSync(resolve(process.cwd(), path), 'utf8');

const TOKENS_CSS = read('../design/tokens.css');

/** Every text input in the product, by the stylesheet and selector that draws its border. */
const TEXT_INPUTS: readonly (readonly [file: string, selector: string])[] = [
  ['src/styles.css', '.pulse-comment textarea'],
  ['src/routes/leadership/leadershipComparisonSets.css', '.pulse-set-input'],
  ['src/components/instructorReportComments.css', '.pulse-comment-card__reason-field'],
];

/** The value `tokens.css` declares for one custom property. */
function tokenValue(name: string): string {
  const found = new RegExp(`${name}:\\s*(?<value>#[0-9a-f]{6})\\b`, 'i').exec(TOKENS_CSS);
  const value = found?.groups?.value;
  if (value === undefined) throw new Error(`design/tokens.css declares no hex value for ${name}`);
  return value;
}

/** WCAG 2.2's relative luminance of a six-digit hex colour. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((at) => Number.parseInt(hex.slice(at, at + 2), 16) / 255);
  const [r = 0, g = 0, b = 0] = channels.map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.2's contrast ratio between two tokens. */
function contrast(a: string, b: string): number {
  const [low, high] = [luminance(tokenValue(a)), luminance(tokenValue(b))].sort((x, y) => x - y);
  return ((high ?? 0) + 0.05) / ((low ?? 0) + 0.05);
}

/** The first declaration block following this exact selector. */
function ruleFor(css: string, selector: string): string {
  const at = css.indexOf(`${selector} {`);
  if (at < 0) throw new Error(`No rule for "${selector}" — the pin must move with a rename.`);
  return css.slice(at, css.indexOf('}', at));
}

describe('the input boundary token (design/tokens.css)', () => {
  it('measures the rejected hairline under 3:1, so the measurement can fail', () => {
    // The canary: the same arithmetic over the token this ticket moved inputs
    // off must say it fails, or a passing ratio below means nothing.
    expect(contrast('--hairline', '--paper')).toBeLessThan(3);
  });

  it('reaches 3:1 against both surfaces an input sits on', () => {
    expect(contrast('--input-edge', '--paper')).toBeGreaterThanOrEqual(3);
    expect(contrast('--input-edge', '--chalk')).toBeGreaterThanOrEqual(3);
  });
});

describe('every text input draws its boundary in the token', () => {
  it.each(TEXT_INPUTS)('%s %s', (file, selector) => {
    const rule = ruleFor(read(file), selector);
    expect(rule).toContain('border: 1px solid var(--input-edge)');
    expect(rule).not.toContain('var(--hairline)');
  });

  it("keeps the survey comment's required and bounce states over 3:1", () => {
    // The bare accent is 2.2:1 on paper; the deep value is the measured one.
    expect(contrast('--marigold', '--paper')).toBeLessThan(3);
    expect(contrast('--marigold-deep', '--paper')).toBeGreaterThanOrEqual(3);
    const rule = ruleFor(read('src/styles.css'), ".pulse-comment[data-state='bounce'] textarea");
    expect(rule).toContain('border-color: var(--marigold-deep)');
  });
});
