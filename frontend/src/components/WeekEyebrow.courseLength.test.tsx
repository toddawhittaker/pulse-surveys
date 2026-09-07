/**
 * E4-17 — the week eyebrow says how long the course runs.
 *
 * Acceptance criterion 3: "`WeekEyebrow` renders `COURSE WK 04 / 12, TERM WK 07`
 * — the total on the course-week half, the term-week label unchanged — with the
 * total filled from the API's number through `fillCopy` and never derived in the
 * component. Proven by a component test on E4-16's runner."
 *
 * Conventions are ADR 0151's, which E4-16 wrote for exactly this: vitest imported
 * explicitly (globals are off), rendering through `@testing-library/react`, and
 * assertions over what a reader sees rather than over a component's internals.
 *
 * **Why this is a second file beside `WeekEyebrow.test.tsx` rather than two more
 * cases inside it.** ADR 0151's convention is one test file beside its component,
 * and this is a deviation with a mechanical cause: the test author cannot read
 * anything under `frontend/src/`, so it cannot edit a file it cannot read, and
 * the implementer may not edit a `*.test.tsx` at all. Merging the two is a tidy-up
 * for whoever holds both permissions; nothing here depends on their staying apart.
 *
 * **E4-16's proof test asserts the pre-ruling string and this ticket breaks it.**
 * It renders the eyebrow and expects the course-week half to read `COURSE WK 04,`;
 * once the total lands that element reads `COURSE WK 04 / 12,` and the old
 * assertion is false — `docs/MISTAKES.md` entry 22, a ticket's new rule making an
 * earlier ticket's test unrunnable with the repair on the other side of the test
 * wall. It is named in E4-17's manifest as a blocker rather than worked around
 * here, because neither of the two agents this ticket runs through can edit it.
 *
 * **The assertion is over the eyebrow's whole text, normalised for whitespace,**
 * rather than over one element's exact text. What the owner ruled is a sentence a
 * reader reads; how many spans it is split across is the implementer's, and a
 * `getByText` on an exact element string would pin that choice. Normalising
 * collapses the whitespace a span boundary contributes.
 *
 * The `lengthWeeks` prop is this suite's transcription and **is not settled by
 * the ticket** — E4-17's Scope says only that the component "takes the count as a
 * prop and fills it". It is spelled to match the `courseWeek` and `termWeek`
 * props beside it and the field the same quantity rides on the wire. The gap is
 * reported in E4-17's manifest; if the owner spells it otherwise it is two lines
 * in this file.
 */
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';

import { WeekEyebrow } from './WeekEyebrow';

// An instant inside a Sunday close, so the eyebrow has something to say after the
// two week numbers. Nothing here asserts what it renders it as — that is ADR
// 0123's, and E4-16's proof test already covers it.
const CLOSES_AT = '2026-09-13T23:59:59Z';

/** Everything the eyebrow puts on the screen, with runs of whitespace collapsed. */
function shownIn(container: HTMLElement): string {
  return (container.textContent ?? '').replace(/\s+/g, ' ').trim();
}

describe('WeekEyebrow', () => {
  it('says how many weeks the course runs, on the course-week half', () => {
    // The ruled string of 2026-09-07, with three numbers no two of which are the
    // same: a fourth course week, a seventh term week, and a twelve-week section.
    //
    // **The mutations this kills.** The total absent, which is what ships today
    // and what this test is first red against. The total filled from the term
    // week — criterion 5's near miss — which reads `/ 07`. The total filled from
    // the course week, which reads `/ 04`. The total placed on the term-week half,
    // which the last assertion refuses outright and which would otherwise satisfy
    // a test that only looked for `/ 12` somewhere on the line. And the term-week
    // label dropped to make room for it, which the ruling explicitly does not do:
    // it "adds a total rather than removing an axis".
    const { container } = render(
      <WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={12} closesAt={CLOSES_AT} />,
    );

    const shown = shownIn(container);
    expect(shown).toContain('COURSE WK 04 / 12,');
    expect(shown).toContain('TERM WK 07');
    expect(shown).not.toContain('TERM WK 07 /');
  });

  it('pads a single-digit total to two digits, the way it pads a week', () => {
    // E4-17's known trap: "`padWeek` exists so week 7 and week 12 are the same
    // width down a column; the total goes through the same padding, or a
    // twelve-week section and a three-week one stop lining up."
    //
    // **The mutation this kills** is the total interpolated raw while the week
    // beside it goes through the padding — `COURSE WK 04 / 6,` — which no test
    // using a two-digit section can see, and which is invisible in review because
    // the twelve-week case (the common one, and the one the ruling's example
    // uses) renders correctly.
    const { container } = render(
      <WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={6} closesAt={CLOSES_AT} />,
    );

    expect(shownIn(container)).toContain('COURSE WK 04 / 06,');
  });
});
