import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { SmallNNotice } from './SmallNNotice';
import { SMALL_N_THRESHOLD } from './instructorReportCommentFixtures';

afterEach(cleanup);

describe('SmallNNotice', () => {
  it('says plainly what is hidden and why, as a named region', () => {
    render(<SmallNNotice threshold={SMALL_N_THRESHOLD} />);

    // SPEC §4 hides raw comments below the threshold and the brief asks for an
    // honest explanation of why; §4.1 item 5 asks for plain words and no shield
    // or lock iconography — the only mark here is the flat pulse line, and it is
    // hidden from assistive technology because the words say what it says.
    expect(screen.getByRole('region', { name: 'Comments are hidden this week' })).toBeTruthy();
    expect(
      screen.getByText(
        'To keep individual voices unidentifiable, raw comments stay hidden until at least 5 responses arrive. The summary above draws on everything received so far.',
      ),
    ).toBeTruthy();
  });

  it('states the configured threshold rather than a five written into the component', () => {
    render(<SmallNNotice threshold={8} />);

    expect(screen.getByText(/at least 8 responses arrive/)).toBeTruthy();
    expect(screen.queryByText(/at least 5 responses arrive/)).toBeNull();
  });

  it('counts nothing that was withheld', () => {
    const { container } = render(<SmallNNotice threshold={SMALL_N_THRESHOLD} />);

    // §5.2 forbids a count or a flag hint below the threshold — "no chip, no
    // count, no flag-type hint". The only number this notice may say is the
    // threshold it was given, so every run of digits in what a reader sees is
    // required to be exactly that one.
    const digits = (container.textContent ?? '').match(/\d+/g) ?? [];

    expect(digits).toEqual([String(SMALL_N_THRESHOLD)]);
  });
});
