import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { WeekEyebrow } from './WeekEyebrow';

/**
 * The eyebrow's past-tense close note — ticket E5-02, criterion 5.
 *
 * > 5. The eyebrow renders the close note in the mockup's form; absent
 * >    `closesAt` (older fixtures) renders the eyebrow unchanged, no crash.
 *
 * `design/InstructorMondayReport.dc.html` reads `responses closed Sun 11:59 PM`
 * and nothing supplied the instant behind it until this ticket put it on the
 * payload. The note is a new prop path beside the student surface's "closes"
 * span, which is unchanged and is pinned by `WeekEyebrow.test.tsx` — a separate
 * file, untouched here, so the two variants cannot be confused for one.
 *
 * **The zone is the institution's and is asserted across a DST boundary.** A
 * close instant read in the wrong zone — the browser's, or the institution's with
 * one offset used for the whole term — is invisible on every week except the one
 * the clocks change in, where it names the Monday instead of the Sunday. So one
 * case below sits exactly there, and its expected string is written out rather
 * than recomputed with the same `Intl` call the component makes: a test that
 * rebuilt the expectation the way the component builds it would agree with any
 * zone the component chose (`docs/MISTAKES.md` entry 30).
 */

afterEach(cleanup);

/**
 * The institution's zone in these cases. Not `America/New_York`: that is the
 * development stack's, so a component hard-coding it would pass against that one
 * for the wrong reason.
 */
const INSTITUTION_ZONE = 'America/Chicago';

/**
 * A Sunday close in central daylight time — 2026-10-04 at 23:59:59 local, which
 * is five hours behind UTC, SPEC §3.1's wall clock for the end of a window.
 */
const AN_ORDINARY_CLOSE = '2026-10-05T04:59:59+00:00';

/**
 * The same wall clock on **2026-11-01**, the Sunday the clocks go back. Standard
 * time by then, so six hours behind UTC rather than five. Read with the summer
 * offset this instant is 12:59 AM on the Monday, which is the mistake this pair
 * of cases exists to catch.
 */
const A_FALL_BACK_CLOSE = '2026-11-02T05:59:59+00:00';

describe('WeekEyebrow with a week that has closed', () => {
  it('states the close in the mockup’s past tense, in the institution’s zone', () => {
    render(
      <WeekEyebrow
        courseWeek={4}
        termWeek={7}
        lengthWeeks={12}
        closedAt={AN_ORDINARY_CLOSE}
        timeZone={INSTITUTION_ZONE}
      />,
    );

    // Written out rather than formatted here, so the expectation is the mockup's
    // sentence and not a second call to whatever the component calls.
    expect(screen.getByText('responses closed Sun 11:59 PM')).toBeTruthy();
    // And the week axes are still there: a variant that replaced the eyebrow
    // rather than adding to it would satisfy the line above on its own.
    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(screen.getByText('TERM WK 07')).toBeTruthy();
  });

  it('reads the close in the institution’s zone across the fall-back boundary', () => {
    // **The mutation this kills:** a conversion with one fixed offset for the
    // whole term, which puts this close at 12:59 AM on the Monday — a report
    // telling an instructor her week ended a day after it did. Every other week
    // in the term renders identically either way, which is why this one is here.
    const { container } = render(
      <WeekEyebrow
        courseWeek={8}
        termWeek={11}
        lengthWeeks={12}
        closedAt={A_FALL_BACK_CLOSE}
        timeZone={INSTITUTION_ZONE}
      />,
    );

    expect(screen.getByText('responses closed Sun 11:59 PM')).toBeTruthy();
    expect(container.textContent).not.toContain('Mon');
    expect(container.textContent).not.toContain('12:59');
  });

  it('says nothing about closing when the payload carries no instant', () => {
    // Criterion 5's absent half, and the state every report built before E5-02 is
    // in. Neither sentence is printed, and neither is a broken one.
    const { container } = render(<WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={12} />);

    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(container.textContent).not.toContain('closed');
    expect(container.textContent).not.toContain('closes');
    expect(container.textContent).not.toContain('Invalid Date');
    expect(container.textContent).not.toContain('undefined');
  });

  it('says nothing rather than guessing when one half of the pair is missing', () => {
    // The instant without a zone is the defect this component is built to make
    // impossible: `Intl` would fall back to the machine's own zone, which reads
    // correctly on a developer's laptop and names the wrong day for a reader one
    // timezone east. Nothing is printed instead.
    const { container } = render(
      <WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={12} closedAt={AN_ORDINARY_CLOSE} />,
    );

    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(container.textContent).not.toContain('closed');
    expect(container.textContent).not.toContain('11:59');
  });

  it('prints no note at all for an instant or a zone it cannot read', () => {
    // A half-formed sentence about when a week ended is worse than no sentence,
    // so neither "responses closed Invalid Date" nor a thrown `RangeError` from
    // an unknown zone reaches a page. Both are asserted, because `Intl` fails
    // differently for each: an unparseable date formats to a string, an unknown
    // zone throws.
    const unparseable = render(
      <WeekEyebrow
        courseWeek={4}
        termWeek={7}
        lengthWeeks={12}
        closedAt="not-a-date"
        timeZone={INSTITUTION_ZONE}
      />,
    );
    expect(unparseable.container.textContent).not.toContain('closed');
    expect(unparseable.container.textContent).not.toContain('Invalid Date');
    cleanup();

    const unknownZone = render(
      <WeekEyebrow
        courseWeek={4}
        termWeek={7}
        lengthWeeks={12}
        closedAt={AN_ORDINARY_CLOSE}
        timeZone="Mars/Olympus_Mons"
      />,
    );
    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(unknownZone.container.textContent).not.toContain('closed');
  });
});
