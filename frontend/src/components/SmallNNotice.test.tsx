import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { SmallNNotice } from './SmallNNotice';
import { SMALL_N_THRESHOLD } from './instructorReportCommentFixtures';

afterEach(cleanup);

/** A quiet week, as the mockup's own example has it: three of nine answered. */
const RESPONDED = 3;
const ENROLLED = 9;

describe('SmallNNotice', () => {
  it('says plainly what is hidden and why, as a named region', () => {
    render(
      <SmallNNotice responded={RESPONDED} enrolled={ENROLLED} threshold={SMALL_N_THRESHOLD} />,
    );

    // SPEC §4 hides raw comments below the threshold and the brief asks for an
    // honest explanation of why; §4.1 item 5 asks for plain words and no shield
    // or lock iconography — the only mark here is the flat pulse line, and it is
    // hidden from assistive technology because the words say what it says.
    //
    // The sentence is `design/SmallNNotice.dc.html:31-33`'s, restored whole by
    // E4-21: the leading count of who answered, then the rule, then which
    // summary the week still has. The two halves this pins that the shipped
    // wording had lost are the first sentence and the word "AI" in the last.
    expect(screen.getByRole('region', { name: 'Comments are hidden this week' })).toBeTruthy();
    expect(
      screen.getByText(
        'Only 3 of 9 students have responded. To keep individual voices unidentifiable, raw comments stay hidden until at least 5 responses arrive. The AI summary above draws on everything received so far.',
      ),
    ).toBeTruthy();
  });

  it('states the configured threshold rather than a five written into the component', () => {
    render(<SmallNNotice responded={RESPONDED} enrolled={ENROLLED} threshold={8} />);

    expect(screen.getByText(/at least 8 responses arrive/)).toBeTruthy();
    expect(screen.queryByText(/at least 5 responses arrive/)).toBeNull();
  });

  it('states the week’s own counts rather than any others', () => {
    // The pair is the payload's — `rates.responses` and `rates.enrolled` — and
    // the mutation this kills is either of them read from the other's place, or
    // the threshold rendered where a count belongs. Different numbers on all
    // three holes, so no two of them can be swapped without changing the text.
    render(<SmallNNotice responded={2} enrolled={17} threshold={6} />);

    expect(screen.getByText(/Only 2 of 17 students have responded/)).toBeTruthy();
  });

  it('counts nothing that was withheld', () => {
    const { container } = render(
      <SmallNNotice responded={RESPONDED} enrolled={ENROLLED} threshold={SMALL_N_THRESHOLD} />,
    );

    // §5.2 forbids a count or a flag hint below the threshold — "no chip, no
    // count, no flag-type hint". The three numbers this notice may say are the
    // two participation counts it was given and the configured threshold, in
    // that order; every run of digits a reader sees is required to be exactly
    // those, so a count of hidden comments could not join them unnoticed. None
    // of the three is a fact about the comments: two are of students, and the
    // third is a configured setting.
    const digits = (container.textContent ?? '').match(/\d+/g) ?? [];

    expect(digits).toEqual([String(RESPONDED), String(ENROLLED), String(SMALL_N_THRESHOLD)]);
  });
});
