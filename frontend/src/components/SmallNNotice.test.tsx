import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { SmallNNotice } from './SmallNNotice';
import { SMALL_N_THRESHOLD } from './instructorReportCommentFixtures';

afterEach(cleanup);

const TITLE = 'No raw comments are shown here this week';

describe('SmallNNotice', () => {
  it('says plainly what is hidden and why, as a named region', () => {
    render(<SmallNNotice threshold={SMALL_N_THRESHOLD} />);

    // SPEC §4 hides one stream's raw comments below the threshold of distinct
    // commenters and the brief asks for an honest explanation of why; §4.1
    // item 5 asks for plain words and no shield or lock iconography — the only
    // mark here is the flat pulse line, and it is hidden from assistive
    // technology because the words say what it says.
    //
    // The sentence is E5.1-01's (work order D6): the rule, where held comments
    // go, and which summary the group still has. The identity promise is in the
    // body only.
    expect(screen.getByRole('region', { name: TITLE })).toBeTruthy();
    expect(
      screen.getByText(
        `To keep individual voices unidentifiable, raw comments in this group are shown only when at least ${String(SMALL_N_THRESHOLD)} students comment in it in the same week. Comments held back may appear later among comments from earlier weeks, with no week named. The AI summary above draws on everything received so far.`,
      ),
    ).toBeTruthy();
  });

  it('states the configured threshold rather than a five written into the component', () => {
    render(<SmallNNotice threshold={8} />);

    expect(screen.getByText(/at least 8 students comment in it/)).toBeTruthy();
    expect(screen.queryByText(/at least 5 students/)).toBeNull();
  });

  it('counts nobody: the threshold is the only number it says', () => {
    const { container } = render(<SmallNNotice threshold={SMALL_N_THRESHOLD} />);

    // §5.2 forbids a count below the threshold — "no chip, no count, no
    // flag-type hint" — and since E5.1-01 the notice sits inside one group,
    // where any count reads as that group's: in a stream of one commenter a
    // count of commenters is the whole disclosure. So the one run of digits a
    // reader sees is the configured threshold, which is a setting and not a
    // count of anybody. The mutation this kills is E4-21's "Only N of M
    // students have responded" coming back, or any count joining the
    // threshold.
    const digits = (container.textContent ?? '').match(/\d+/g) ?? [];

    expect(digits).toEqual([String(SMALL_N_THRESHOLD)]);
  });
});
