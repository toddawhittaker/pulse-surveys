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
  // The state tests below serve no figures; the data tests use `withFigures`.
  return {
    course_label: 'MATH 140',
    lead_name: null,
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
    // The course's name is the one thing a held week shows, and it carries digits.
    const text = (page().textContent ?? '').replace('MATH 140', '');
    expect(text).not.toMatch(/\d/);
    expect(text).not.toContain(AUTHOR);
    expect(text).not.toContain(REPLY);
    expect(page().querySelector('.pulse-response-card')).toBeNull();
  });
});

describe('the Lead Faculty in the header (SPEC §2.1)', () => {
  const LEAD = 'Grace Hopper';
  const LEAD_LINE = `Lead Faculty: ${LEAD}`;
  const led = (state: StudentWeekResults['state']): StudentWeekResults => ({
    ...results(state, state === 'awaiting' || state === 'unanswered' ? null : 'INSTRUCTOR'),
    lead_name: LEAD,
  });

  it('names the lead under the course label on a released week', async () => {
    serving({ [LATEST]: () => json(200, led('published')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(REPLY);
    expect(screen.getByTestId('pulse-results-lead').textContent).toBe(LEAD_LINE);
    // The response's author is the instructor, and the byline does not borrow the lead.
    expect(page().textContent).toContain(AUTHOR);
  });

  it('names the lead on the closed door too: a staff name is not a figure about the week', async () => {
    serving({ [LATEST]: () => json(200, led('awaiting')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(AWAITING);
    expect(screen.getByTestId('pulse-results-lead').textContent).toBe(LEAD_LINE);
    expect(page().querySelector('.pulse-response-card')).toBeNull();
  });

  it('shows no Lead Faculty line on a released week of a course nobody leads', async () => {
    serving({ [LATEST]: () => json(200, results('published', 'INSTRUCTOR')), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(REPLY);
    expect(screen.queryByTestId('pulse-results-lead')).toBeNull();
    expect(page().textContent).not.toContain('Lead Faculty');
  });

  it('shows no Lead Faculty line on the closed door of a course nobody leads', async () => {
    serving({ [LATEST]: () => json(200, results('awaiting', null)), [SURVEY]: survey });
    mountAt(`/app${LATEST}`);
    await screen.findByText(AWAITING);
    expect(screen.queryByTestId('pulse-results-lead')).toBeNull();
    expect(page().textContent).not.toContain('Lead Faculty');
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
  const SCORE = { score_text: '61.50', ledger_text: 'Week 1: 3 of 3 items\nWeek 2: 1 of 3 items' };
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
    await screen.findByText('Your participation: 61.50%');
    // One list item per ledger line, as the server joins them with a newline.
    const lines = Array.from(page().querySelectorAll('.pulse-results-ledger li')).map(
      (item) => item.textContent,
    );
    expect(lines).toEqual(SCORE.ledger_text.split('\n'));
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
      expect(page().textContent).not.toContain('Your participation');
      expect(page().textContent).not.toContain(NOTE);
      expect(page().querySelector('.pulse-results-participation')).toBeNull();
    },
  );
});

const INSTRUCTOR_COMMENT = 'Explains the proofs clearly.';
const COURSE_COMMENT = 'The reading load is heavy.';
const RELEASED_COMMENT = 'Office hours helped a lot.';

function stream(
  which: 'instructor' | 'course',
  options: { small?: boolean; comments?: string[] } = {},
): NonNullable<StudentWeekResults['streams']>[number] {
  const small = options.small ?? false;
  return {
    stream: which,
    trend: [
      { course_week: 1, mean: 3.5 },
      { course_week: 2, mean: null },
      { course_week: 3, mean: 4.2 },
    ],
    shares: small ? null : { '1': 0, '2': 10, '3': 20, '4': 40, '5': 30 },
    small_n: small,
    comments: small ? [] : (options.comments ?? []).map((text) => ({ text })),
  };
}

function withFigures(
  state: StudentWeekResults['state'],
  overrides: Partial<StudentWeekResults> = {},
): StudentWeekResults {
  return {
    ...results(state, state === 'unanswered' ? null : 'INSTRUCTOR'),
    streams: [
      stream('instructor', { comments: [INSTRUCTOR_COMMENT] }),
      stream('course', { comments: [COURSE_COMMENT] }),
    ],
    workload_median: 4.5,
    released: [{ text: RELEASED_COMMENT, stream: 'course' }],
    participation: { score_text: '61.50', ledger_text: 'Week 1: 3 of 3 items' },
    ...overrides,
  };
}

const CONFIDENTIALITY = 'Comments are shown without the names of the students who wrote them.';

async function mountWith(body: StudentWeekResults): Promise<void> {
  serving({ [LATEST]: () => json(200, body), [SURVEY]: survey });
  mountAt(`/app${LATEST}`);
  await screen.findByText('MATH 140');
}

describe('the released page', () => {
  it.each(['published', 'on-behalf', 'unanswered'] as const)(
    '%s: the page reads in order, from the course to the confidentiality line',
    async (state) => {
      await mountWith(withFigures(state));
      await screen.findByText(CONFIDENTIALITY);
      const html = page().innerHTML;
      const at = (marker: string): number => {
        const found = html.indexOf(marker);
        expect(found, `${marker} is on the page`).toBeGreaterThan(-1);
        return found;
      };
      const order = [
        at('pulse-results-course'),
        at(state === 'unanswered' ? UNANSWERED : REPLY),
        at('pulse-results-participation'),
        at('pulse-trend-duo'),
        at('pulse-stat-histogram"'),
        at('Class median: 4.5 hours on this course'),
        at(INSTRUCTOR_COMMENT),
        at(COURSE_COMMENT),
        at('Comments from earlier weeks'),
        at(CONFIDENTIALITY),
      ];
      expect(order).toEqual([...order].sort((left, right) => left - right));
    },
  );

  it('shows the confidentiality line once, with no shield or lock', async () => {
    await mountWith(withFigures('published'));
    await screen.findByText(CONFIDENTIALITY);
    expect(page().textContent?.split(CONFIDENTIALITY).length).toBe(2);
    expect(page().textContent).not.toMatch(/[\u{1F510}-\u{1F513}\u{1F6E1}]/u);
  });

  it('draws one line per stream and no comparison, in its chart, text or labels', async () => {
    await mountWith(withFigures('published'));
    await screen.findByText(CONFIDENTIALITY);
    const duo = screen.getByTestId('pulse-trend-duo');
    expect(duo.querySelectorAll('path.pulse-trend-line')).toHaveLength(2);
    expect(duo.querySelector('[data-testid^="trend-"]')).toBeNull();
    const labels = Array.from(page().querySelectorAll('[aria-label]'))
      .map((node) => node.getAttribute('aria-label'))
      .join(' ');
    const everything = `${page().textContent ?? ''} ${labels} ${page().innerHTML}`;
    expect(everything).not.toMatch(/compar|universit|benchmark|average|percentile|other sections/i);
  });

  it('gives the numbers behind the trend as a table, with no term-week column', async () => {
    await mountWith(withFigures('published'));
    await screen.findByText(CONFIDENTIALITY);
    const tables = screen.getByTestId('pulse-trend-duo').querySelectorAll('table');
    expect(tables).toHaveLength(2);
    const headers = Array.from(tables[0]?.querySelectorAll('th[scope="col"]') ?? []).map(
      (node) => node.textContent,
    );
    expect(headers).toEqual(['Course week', 'Mean rating']);
  });

  it('holds only the small stream: its notice with no number, the other stream’s comments', async () => {
    await mountWith(
      withFigures('published', {
        streams: [
          stream('instructor', { small: true }),
          stream('course', { comments: [COURSE_COMMENT] }),
        ],
      }),
    );
    await screen.findByText(COURSE_COMMENT);
    const groups = page().querySelectorAll('.pulse-comment-group');
    expect(groups).toHaveLength(2);
    const [first, second] = Array.from(groups);
    expect(first?.querySelector('.pulse-small-n-notice')).not.toBeNull();
    expect(first?.textContent).not.toMatch(/\d/);
    expect(first?.textContent).toContain('Comments in this group are not shown this week');
    expect(second?.querySelector('.pulse-small-n-notice')).toBeNull();
    expect(second?.textContent).toContain(COURSE_COMMENT);
  });

  it('draws no comment from a stream the payload marks small, whatever its array holds', async () => {
    const hostile = { ...stream('instructor', { small: true }), comments: [{ text: 'LEAK' }] };
    await mountWith(
      withFigures('published', { streams: [hostile, stream('course', { comments: [] })] }),
    );
    await screen.findByText(CONFIDENTIALITY);
    expect(page().textContent).not.toContain('LEAK');
  });

  it('shows a stream with no comments as one line and not as a hold', async () => {
    await mountWith(
      withFigures('published', { streams: [stream('instructor'), stream('course')] }),
    );
    await screen.findByText(CONFIDENTIALITY);
    expect(page().querySelector('.pulse-small-n-notice')).toBeNull();
    expect(screen.getAllByText('No comments this week.')).toHaveLength(2);
  });

  it('shows comments with no time and no status, and earlier-week comments with no week', async () => {
    await mountWith(withFigures('published'));
    await screen.findByText(RELEASED_COMMENT);
    const cards = page().querySelectorAll('.pulse-comment-card');
    expect(cards).toHaveLength(3);
    expect(Array.from(cards).map((card) => card.textContent?.trim())).toEqual([
      INSTRUCTOR_COMMENT,
      COURSE_COMMENT,
      // An earlier-week comment carries its stream's chip and nothing else.
      `Course${RELEASED_COMMENT}`,
    ]);
    const released = page().querySelector('.pulse-results-released');
    expect(released?.textContent).not.toMatch(/week \d|\d/i);
  });

  it('draws nothing for members the payload sends as null', async () => {
    await mountWith(
      withFigures('published', { streams: null, workload_median: null, released: null }),
    );
    await screen.findByText(REPLY);
    expect(page().querySelector('[data-testid="pulse-trend-duo"]')).toBeNull();
    expect(page().querySelector('.pulse-stat-histogram')).toBeNull();
    expect(page().querySelector('.pulse-comment-group')).toBeNull();
    expect(page().querySelector('.pulse-results-released')).toBeNull();
    expect(page().textContent).not.toContain('Class median');
    // A released week carries the page's one line whatever else it holds.
    expect(page().textContent).toContain(CONFIDENTIALITY);
  });
});

describe('the closed door', () => {
  it('shows the course, the door and the participation block, and teases nothing', async () => {
    // A hostile payload: every member filled, as a server that forgot the hold would send.
    await mountWith(withFigures('awaiting'));
    await screen.findByText(AWAITING);
    expect(screen.getByTestId('pulse-results-course').textContent).toBe('MATH 140');
    expect(page().querySelector('.pulse-results-participation')).not.toBeNull();
    for (const selector of [
      '[data-testid="pulse-trend-duo"]',
      '.pulse-stat-histogram',
      '.pulse-comment-group',
      '.pulse-comment-card',
      '.pulse-small-n-notice',
      '.pulse-results-released',
      '.pulse-results-workload',
      '.pulse-response-card',
    ]) {
      expect(page().querySelector(selector), selector).toBeNull();
    }
    const text = page().textContent ?? '';
    for (const leaked of [INSTRUCTOR_COMMENT, COURSE_COMMENT, RELEASED_COMMENT, 'Class median']) {
      expect(text).not.toContain(leaked);
    }
    expect(text).not.toContain(CONFIDENTIALITY);
  });
});

describe('ratings as shares', () => {
  it('draws percentages and no count, total or mean', async () => {
    await mountWith(withFigures('published'));
    await screen.findByText(CONFIDENTIALITY);
    const histograms = page().querySelectorAll('.pulse-stat-histogram');
    expect(histograms).toHaveLength(2);
    const first = histograms[0];
    expect(first?.textContent).toContain('40%');
    const label = first?.querySelector('[role="img"]')?.getAttribute('aria-label');
    expect(label).toContain('0%, 10%, 20%, 40%, 30%');
    expect(label).not.toMatch(/responses|mean/);
    expect(first?.querySelector('.pulse-stat-histogram-summary')).toBeNull();
  });

  it('puts the student notice in place of a stream’s chart when shares are null', async () => {
    await mountWith(
      withFigures('published', {
        streams: [stream('instructor', { small: true }), stream('course', { comments: [] })],
      }),
    );
    await screen.findByText(CONFIDENTIALITY);
    expect(page().querySelectorAll('.pulse-stat-histogram')).toHaveLength(1);
    const held = page().querySelector('.pulse-results-held-chart');
    expect(held?.querySelector('.pulse-small-n-notice')).not.toBeNull();
    expect(held?.textContent).not.toMatch(/\d|too few/);
    expect(held?.textContent).toContain('Ratings about the instructor are not shown this week');
    expect(held?.textContent).not.toMatch(/comment/i);
  });

  it('tells the held ratings slot from the held comments slot, and one never speaks for the other', async () => {
    // Ratings held, comments shown: nothing says comments are hidden.
    const ratingsOnly = {
      ...stream('instructor', { comments: [INSTRUCTOR_COMMENT] }),
      shares: null,
    };
    await mountWith(withFigures('published', { streams: [ratingsOnly, stream('course', { comments: [] })] }));
    await screen.findByText(INSTRUCTOR_COMMENT);
    expect(page().textContent).toContain('Ratings about the instructor are not shown this week');
    expect(page().textContent).not.toContain('Comments in this group are not shown');
    cleanup();
    // Comments held, ratings shown: nothing says ratings are hidden.
    const commentsOnly = { ...stream('instructor', { small: true }), shares: { '1': 0, '2': 10, '3': 20, '4': 40, '5': 30 } };
    await mountWith(withFigures('published', { streams: [commentsOnly, stream('course', { comments: [] })] }));
    await screen.findByText(CONFIDENTIALITY);
    expect(page().textContent).toContain('Comments in this group are not shown');
    expect(page().textContent).not.toContain('Ratings about the instructor are not shown');
  });

  it('says a week with no mean has no figure, with no number or reason', async () => {
    await mountWith(withFigures('published'));
    await screen.findByText(CONFIDENTIALITY);
    const cells = Array.from(page().querySelectorAll('tbody td')).map((cell) => cell.textContent);
    expect(cells).toContain('No figure for this week');
    expect(page().textContent).not.toMatch(/no responses|too few/i);
  });
});
