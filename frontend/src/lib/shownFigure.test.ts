import { describe, expect, it } from 'vitest';

import { isShownFigure } from './shownFigure';

/**
 * The fail-closed reading of one benchmark figure (SPEC §4.1 item 7). The
 * figures arrive cast rather than parsed, so each malformed shape below is one
 * a payload slip could produce, and every one of them has to withhold.
 */
describe('isShownFigure', () => {
  it('shows an unsuppressed figure with a number', () => {
    expect(isShownFigure({ suppressed: false, figure: 3.5 })).toBe(true);
    expect(isShownFigure({ suppressed: false, reason: null, figure: 0 })).toBe(true);
  });

  it.each([
    ['a raised flag', { suppressed: true, figure: 3.5 }],
    ['a missing flag', { figure: 3.5 }],
    ['a flag sent as the string "false"', { suppressed: 'false', figure: 3.5 }],
    ['a null figure', { suppressed: false, figure: null }],
    ['a missing figure', { suppressed: false }],
    ['a figure sent as a string', { suppressed: false, figure: '3.5' }],
    ['a NaN figure', { suppressed: false, figure: Number.NaN }],
    ['an infinite figure', { suppressed: false, figure: Number.POSITIVE_INFINITY }],
    ['a member sent as null', null],
    ['a member never sent', undefined],
  ])('withholds %s', (_case, figure) => {
    expect(isShownFigure(figure as Parameters<typeof isShownFigure>[0])).toBe(false);
  });
});
