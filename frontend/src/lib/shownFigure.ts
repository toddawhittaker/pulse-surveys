import type { ComparisonFigureView } from '../api/instructor';

/**
 * The one benchmark figure type, passed on beside the check that reads it.
 *
 * The trend chart may not import from `api/` at all (its own test refuses any
 * such line, so that it can never reach for data a prop should carry), and it
 * takes the figure type from here instead of keeping a copy of it.
 */
export type { ComparisonFigureView };

/**
 * Whether one benchmark figure may be shown — **only if its own flag says
 * exactly `false` and its own number is a finite number**.
 *
 * The trend chart's overlays and the stat pair's comparison cells both ask
 * this, and both read it fail-closed. `ComparisonFigureView` is a shape over
 * JSON the client casts without parsing, so a flag that arrived renamed,
 * misspelled or missing is `undefined` here, and `undefined` is falsy: a
 * truthiness test would read a dropped `suppressed` as "not suppressed" and show
 * a figure SPEC §4.1 item 7 had suppressed. The whole class of payload slip
 * would resolve to "show the figure", which is the wrong direction for a
 * confidentiality rule to fail in.
 *
 * The second half is the same argument about the number. The server's rule is
 * that a suppressed figure carries none, so a value beside a raised flag is a
 * payload contradicting itself. `typeof === 'number'` refuses a string, a
 * `null` and an absent member; `Number.isFinite` refuses the `NaN` and the
 * infinities that arithmetic over nothing arrives as. Each reader once held one
 * of those two conditions, and this keeps both.
 *
 * The cost, named: a payload that stopped sending the flag would show withheld
 * notices everywhere rather than its comparison figures — loud, visible, and
 * withholding nothing a reader was entitled to.
 *
 * `null` and `undefined` are accepted because a member sent as JSON `null` is
 * one this must answer about (reading `suppressed` off it would throw), and a
 * member never sent is answered the same way.
 */
export function isShownFigure(
  figure: Partial<ComparisonFigureView> | null | undefined,
): figure is ComparisonFigureView & { readonly figure: number } {
  return (
    figure != null &&
    figure.suppressed === false &&
    typeof figure.figure === 'number' &&
    Number.isFinite(figure.figure)
  );
}
