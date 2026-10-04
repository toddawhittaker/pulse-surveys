import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { StudentSurveyView } from '../../api/student';
import { REFUSAL_TESTID, REVISE_TESTID, StudentWeeklySurvey } from './StudentWeeklySurvey';

/**
 * A refused revise, driven — ticket E5.1-05, criterion C1.
 *
 * Clearing a comment the classifier has already judged is refused, and since
 * E5.1-05 the refusal is a 422. The client reads every 409 as "this week has
 * closed" and takes the form away, so a 409 here told a student whose week was
 * still open that it had shut. These cases drive the screen the way a student
 * meets it: open the week already answered, choose to change the answers,
 * clear the comment, send, and read what is on the screen afterwards.
 *
 * The pair is the point. A 422 carrying a sentence keeps the form and shows
 * the sentence above it; a 409 still means "closed" and still replaces the
 * form with the sentence. A client that read both the same way fails one of
 * the two.
 *
 * Governed copy is transcribed rather than imported (`docs/MISTAKES.md` entry
 * 19), so a reworded sentence on either side is a failure here rather than a
 * test that follows it.
 */

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** `submit.comment_already_judged`, transcribed from `app.copy.submit`. */
const JUDGED =
  'A comment that has already been checked stays with the week it was written in. You can change what it says, and it cannot be taken back out.';
/** `submit.window_closed`, transcribed from `app.copy.submit`. */
const CLOSED =
  "This week's survey has closed, so it can no longer take a submission. The next one opens on its own schedule and nothing here is missed permanently.";
const CHANGE_THESE_ANSWERS = 'Change these answers';
const UPDATE = 'Update this week’s answers';

const SECTION_ID = '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f60';
const RATING_ID = '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f61';
const COMMENT_ID = '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f62';

/** One open week this student has already answered, comment included. */
const AN_ANSWERED_WEEK: StudentSurveyView = {
  institution_timezone: 'America/New_York',
  sections: [
    {
      section_id: SECTION_ID,
      section_code: 'E1FF',
      course_label: 'MATH 140 E1FF — College Algebra, Fall 2026',
      survey_is_open: true,
      next_window_opens_at: null,
      open_survey: {
        window_id: '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f63',
        course_week: 3,
        length_weeks: 12,
        term_week: 3,
        opens_at: '2026-09-11T18:00:00-04:00',
        closes_at: '2026-09-13T23:59:59-04:00',
        question_set_version: 1,
        questions: [
          {
            id: RATING_ID,
            position: 1,
            kind: 'likert',
            name: 'pace',
            prompt: 'How is the pace of this course?',
            required_if_position: null,
            required_if_at_most: null,
            minimum_value: '1',
            maximum_value: '5',
            step: '1',
          },
          {
            id: COMMENT_ID,
            position: 2,
            kind: 'comment',
            name: 'comment',
            prompt: 'Anything else?',
            required_if_position: 1,
            required_if_at_most: 2,
            minimum_value: null,
            maximum_value: null,
            step: null,
          },
        ],
        submission: {
          first_submitted_at: '2026-09-12T10:00:00-04:00',
          last_submitted_at: '2026-09-12T10:00:00-04:00',
          answers: [
            { question_id: RATING_ID, rating: 4, comment_text: null, workload_hours: null },
            {
              question_id: COMMENT_ID,
              rating: null,
              comment_text: 'The worked examples help.',
              workload_hours: null,
            },
          ],
        },
      },
    },
  ],
};

/** The read answers the week above; the write answers `status` with `body`. */
function serving(status: number, body: unknown): { posts: string[] } {
  const posts: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push(typeof init.body === 'string' ? init.body : '');
        return Promise.resolve(new Response(JSON.stringify(body), { status }));
      }
      return Promise.resolve(new Response(JSON.stringify(AN_ANSWERED_WEEK), { status: 200 }));
    }),
  );
  return { posts };
}

/** Open the answered week, choose to change it, clear the comment, and send. */
async function clearTheJudgedCommentAndSend(posts: string[]): Promise<void> {
  render(<StudentWeeklySurvey />);
  fireEvent.click(await screen.findByTestId(REVISE_TESTID));

  const comment = document.getElementById(`survey-${SECTION_ID}-q2`);
  expect(comment, 'the comment field is on the revised form').not.toBeNull();
  fireEvent.change(comment as HTMLElement, { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: UPDATE }));

  // The send happened, and without the comment: the refusal below is the
  // answer to clearing it, not to something else this form sent.
  await waitFor(() => {
    expect(posts).toHaveLength(1);
  });
  expect(posts[0]).not.toContain('comment_text');
}

describe('a revise that clears a judged comment (E5.1-05, C1)', () => {
  it('keeps the form and shows the server’s sentence above it on a 422', async () => {
    const { posts } = serving(422, { detail: JUDGED });
    await clearTheJudgedCommentAndSend(posts);

    expect(await screen.findByTestId(REFUSAL_TESTID)).toHaveProperty('textContent', JUDGED);
    // The form is still there to correct, and nothing says the week has shut.
    expect(screen.getByRole('button', { name: UPDATE })).toBeTruthy();
    expect(document.getElementById(`survey-${SECTION_ID}-q2`)).not.toBeNull();
    expect(screen.queryByText(CLOSED)).toBeNull();
  });

  it('still takes the form away and says the week has closed on a 409', async () => {
    const { posts } = serving(409, { detail: CLOSED });
    await clearTheJudgedCommentAndSend(posts);

    expect(await screen.findByText(CLOSED)).toBeTruthy();
    expect(screen.queryByRole('button', { name: UPDATE })).toBeNull();
    expect(screen.queryByTestId(REFUSAL_TESTID)).toBeNull();
    expect(screen.queryByText(CHANGE_THESE_ANSWERS)).toBeNull();
  });
});
