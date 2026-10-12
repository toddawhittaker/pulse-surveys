import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { copy, fillCopy } from '../copy/instructorReportCommentCopy';
import { SmallNNotice } from './SmallNNotice';
import { SMALL_N_THRESHOLD } from './instructorReportCommentFixtures';

afterEach(cleanup);

// The instructor's notice is built by `CommentGroup`; these are its governed words.
const instructorWords = (threshold: number) => ({
  title: copy('instructor_report_comments.small_n.title'),
  body: fillCopy('instructor_report_comments.small_n.body', { threshold: String(threshold) }),
});

const TITLE = 'No raw comments are shown here this week';

describe('SmallNNotice', () => {
  it('says plainly what is hidden and why, without becoming a landmark', () => {
    render(<SmallNNotice {...instructorWords(SMALL_N_THRESHOLD)} />);

    // SPEC §4 hides one stream's raw comments below the threshold of distinct
    // commenters and the brief asks for an honest explanation of why; §4.1
    // item 5 asks for plain words and no shield or lock iconography — the only
    // mark here is the flat pulse line, and it is hidden from assistive
    // technology because the words say what it says.
    //
    // The sentence is E5.1-01's (work order D6): the rule, where held comments
    // go, and which summary the group still has. The identity promise is in the
    // body only.
    expect(screen.getByText(TITLE)).toBeTruthy();
    expect(screen.queryByRole('region')).toBeNull();
    expect(
      screen.getByText(
        `To keep individual voices unidentifiable, raw comments in this group are shown only when at least ${String(SMALL_N_THRESHOLD)} students comment in it in the same week. Comments held back may appear later among comments from earlier weeks, with no week named. The AI summary above draws on everything received so far.`,
      ),
    ).toBeTruthy();
  });

  it('states the configured threshold rather than a five written into the component', () => {
    render(<SmallNNotice {...instructorWords(8)} />);

    expect(screen.getByText(/at least 8 students comment in it/)).toBeTruthy();
    expect(screen.queryByText(/at least 5 students/)).toBeNull();
  });

  it('counts nobody: the threshold is the only number it says', () => {
    const { container } = render(<SmallNNotice {...instructorWords(SMALL_N_THRESHOLD)} />);

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

describe('SmallNNotice, student words', () => {
  it('shows the words it is given and states no number when none is given', () => {
    const { container } = render(
      <SmallNNotice
        title="Comments in this group are not shown this week"
        body="They may appear here later."
      />,
    );

    expect(screen.getByText('Comments in this group are not shown this week')).toBeTruthy();
    expect(container.textContent).not.toMatch(/\d/);
    expect(screen.queryByRole('region')).toBeNull();
  });
});
