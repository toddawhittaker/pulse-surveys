import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import type { StudentWeekResults } from '../../api/student';
import { routeTree } from '../../router';

/**
 * The student's results page, mounted through the application's own route tree.
 * Governed copy is transcribed rather than imported (`docs/MISTAKES.md` entry 19).
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SECTION = '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f60';
const LATEST = `/student/sections/${SECTION}/results`;
const WEEK = (week: number) => `/student/sections/${SECTION}/weeks/${week}/results`;
const SURVEY = '/student/survey';

const NOTHING = 'There is nothing to show for this section yet.';
const AWAITING = 'There is no reply to show for this week yet.';
const UNANSWERED = 'There is no reply for this week.';

const AUTHOR = 'Ada Lovelace';
const REPLY = 'Thank you, we will slow the pace.';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function results(
  state: StudentWeekResults['state'],
  role: 'INSTRUCTOR' | 'LEAD_FACULTY' | 'CHAIR' | null,
  weeks = [1, 2, 3],
): StudentWeekResults {
  // The figures, comments and release group are E8-02's page to render; these
  // tests read only the state and the response, so they serve none of them.
  return {
    course_label: 'MATH 140',
    state,
    published_weeks: weeks,
    streams: null,
    workload_median: null,
    released: null,
    response:
      role === null
        ? null
        : {
            text: REPLY,
            author_name: AUTHOR,
            author_role: role,
            published_at: '2026-09-14T02:30:00Z',
          },
  };
}

function serving(answers: Record<string, () => Response>): string[] {
  const asked: string[] = [];
  vi.stubGlobal('fetch', (input: string) => {
    asked.push(input);
    const answer = answers[input];
    if (answer === undefined) return Promise.reject(new Error(`No answer for ${input}.`));
    return Promise.resolve(answer());
  });
  return asked;
}

const survey = () => json(200, { institution_timezone: 'America/New_York', sections: [] });

function mountAt(address: string) {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: [address] }),
  });
  render(<RouterProvider router={router} />);
  return router;
}

const page = () => screen.getByTestId('pulse-student-results');

describe('the four states', () => {
  it('published: the card names the instructor and the day in the institution’s zone', async () => {
    serving({ [LATEST]: () => json(200, results('published', 'INSTRUCTOR')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(REPLY);
    expect(page().textContent).toContain(AUTHOR);
    expect(page().textContent).not.toContain('Lead Faculty');
    await waitFor(() => expect(page().textContent).toContain('Published Sunday, September 13'));
  });

  it('on-behalf: the lead’s name and role, and never the instructor’s', async () => {
    serving({ [LATEST]: () => json(200, results('on-behalf', 'LEAD_FACULTY')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(REPLY);
    expect(page().textContent).toContain('Ada Lovelace, Lead Faculty');
  });

  it('on-behalf by the chair names the chair’s role', async () => {
    serving({ [LATEST]: () => json(200, results('on-behalf', 'CHAIR')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(REPLY);
    expect(page().textContent).toContain('Ada Lovelace, Department Chair');
  });

  it('unanswered: one calm line and no card', async () => {
    serving({ [LATEST]: () => json(200, results('unanswered', null)), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(UNANSWERED);
    expect(page().querySelector('.pulse-response-card')).toBeNull();
  });

  it('awaiting: one sentence, with no digit, name or response text anywhere on the page', async () => {
    // A hostile payload: a server that sent a response with a held week must
    // still not have it drawn.
    serving({ [LATEST]: () => json(200, results('awaiting', 'INSTRUCTOR')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(AWAITING);
    const text = page().textContent ?? '';
    expect(text).not.toMatch(/\d/);
    expect(text).not.toContain(AUTHOR);
    expect(text).not.toContain(REPLY);
    expect(page().querySelector('.pulse-response-card')).toBeNull();
  });
});

describe('refusals', () => {
  it('a 404 is one calm sentence with no detail', async () => {
    serving({ [LATEST]: () => json(404, { detail: 'secret reason' }), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(NOTHING);
    expect(page().textContent).not.toContain('secret reason');
  });

  it('an address naming no week asks the API nothing', async () => {
    const asked = serving({ [SURVEY]: survey });
    mountAt(`/app/student/sections/${SECTION}/weeks/banana/results`);
    await screen.findByText(NOTHING);
    expect(asked.filter((it) => it.includes('/results'))).toEqual([]);
  });

  it('a 401 says the session ended, not that there is nothing', async () => {
    serving({ [LATEST]: () => json(401, {}), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText('Your session has ended');
  });
});

describe('paging', () => {
  it('pages through published weeks only, and asks for the week it lands on', async () => {
    const asked = serving({
      [LATEST]: () => json(200, results('published', 'INSTRUCTOR', [1, 3])),
      [WEEK(1)]: () => json(200, results('unanswered', null, [1, 3])),
      [SURVEY]: survey,
    });
    const router = mountAt(`/app${LATEST}`);
    await screen.findByText('Week 3');
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Next week' }).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Previous week' }));
    await screen.findByText(UNANSWERED);
    expect(router.state.location.pathname).toBe(WEEK(1));
    expect(asked).toContain(WEEK(1));
    // The student's place is the page, not the button that is now disabled.
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));
    });
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Previous week' }).disabled).toBe(
      true,
    );
  });
});

describe('the student’s own posted score', () => {
  const SCORE = { score_text: '61.50', ledger_text: 'Week 1: 3 of 3 items; Week 2: 1 of 3 items' };
  const NOTE =
    'A comment counted when you submitted it can be re-checked later, so a week’s count can go down.';

  function withScore(state: StudentWeekResults['state'], role: 'INSTRUCTOR' | null) {
    return { ...results(state, role), participation: SCORE };
  }

  it.each([
    ['published', 'INSTRUCTOR'],
    ['on-behalf', 'INSTRUCTOR'],
    ['unanswered', null],
    ['awaiting', null],
  ] as const)('%s: shows the score and ledger as posted, with the sentence', async (state, role) => {
    serving({ [LATEST]: () => json(200, withScore(state, role)), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText('Score posted to your gradebook: 61.50');
    expect(page().textContent).toContain(SCORE.ledger_text);
    expect(page().textContent).toContain(NOTE);
  });

  it('awaiting still shows no reply, author or week number beside the score', async () => {
    serving({
      [LATEST]: () => json(200, { ...results('awaiting', 'INSTRUCTOR'), participation: SCORE }),
      [SURVEY]: survey,
    });
    mountAt(`/app${LATEST}`);
    await screen.findByText(AWAITING);
    await screen.findByText(NOTE);
    expect(page().textContent).not.toContain(REPLY);
    expect(page().textContent).not.toContain(AUTHOR);
    expect(page().textContent).not.toContain('Week 3');
  });

  it.each([['absent', results('published', 'INSTRUCTOR')], ['null', { ...results('published', 'INSTRUCTOR'), participation: null }]])(
    'shows nothing for a score that is %s: no zero, no placeholder, no sentence',
    async (_name, body) => {
      serving({ [LATEST]: () => json(200, body), [SURVEY]: survey });
      mountAt(`/app${LATEST}`);
      await screen.findByText(REPLY);
      expect(page().textContent).not.toContain('Score posted');
      expect(page().textContent).not.toContain(NOTE);
      expect(page().querySelector('.pulse-results-participation')).toBeNull();
    },
  );
});
