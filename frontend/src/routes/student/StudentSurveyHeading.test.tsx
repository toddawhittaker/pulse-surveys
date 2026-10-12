import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';

import type { StudentSurveyView } from '../../api/student';
import { StudentWeeklySurvey } from './StudentWeeklySurvey';

/**
 * The survey's section heading names who teaches the section and links to the
 * reply. Governed copy is transcribed rather than imported
 * (`docs/MISTAKES.md` entry 19).
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FIRST_ID = '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f60';
const SECOND_ID = '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f70';

function closedSection(id: string, code: string, instructors: string[]) {
  return {
    section_id: id,
    section_code: code,
    course_label: `Course ${code}`,
    survey_is_open: false,
    next_window_opens_at: null,
    instructors,
    open_survey: null,
  };
}

async function showing(sections: StudentSurveyView['sections']) {
  const view: StudentSurveyView = { institution_timezone: 'America/New_York', sections };
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      new Response(JSON.stringify(view), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  render(<StudentWeeklySurvey />);
  await screen.findByTestId('survey-section-AAAA');
}

describe('the section heading', () => {
  it('names the instructor, and every co-teaching instructor, in the heading area', async () => {
    await showing([
      closedSection(FIRST_ID, 'AAAA', ['Grace Hopper']),
      closedSection(SECOND_ID, 'BBBB', ['Ada Lovelace', 'Alan Turing']),
    ]);
    const one = within(screen.getByTestId('survey-section-AAAA'));
    const two = within(screen.getByTestId('survey-section-BBBB'));
    expect(one.getByText('with Grace Hopper')).toBeTruthy();
    expect(two.getByText('with Ada Lovelace, Alan Turing')).toBeTruthy();
  });

  it('shows no name and no placeholder for a section with no instructor', async () => {
    await showing([closedSection(FIRST_ID, 'AAAA', [])]);
    const block = screen.getByTestId('survey-section-AAAA');
    expect(block.textContent ?? '').not.toMatch(/\bwith\b/i);
    expect(block.querySelector('.pulse-section-instructors')).toBeNull();
  });

  it('links each section to its own latest results', async () => {
    await showing([
      closedSection(FIRST_ID, 'AAAA', []),
      closedSection(SECOND_ID, 'BBBB', ['Ada Lovelace']),
    ]);
    const first = within(screen.getByTestId('survey-section-AAAA')).getByRole('link', {
      name: 'See your instructor’s reply for Course AAAA',
    });
    const second = within(screen.getByTestId('survey-section-BBBB')).getByRole('link', {
      name: 'See your instructor’s reply for Course BBBB',
    });
    // The visible text is the start of the accessible name (WCAG 2.5.3).
    expect(first.textContent).toBe('See your instructor’s reply');
    expect(first.getAttribute('href')).toBe(`/app/student/sections/${FIRST_ID}/results`);
    expect(second.getAttribute('href')).toBe(`/app/student/sections/${SECOND_ID}/results`);
  });
});

describe('the lead for a section with no survey open', () => {
  const RESULTS_OF = (id: string) => `/student/sections/${id}/results`;

  function results(state: string, weeks: number[]) {
    return { state, response: null, published_weeks: weeks, lead_name: null };
  }

  async function landingWith(sections: StudentSurveyView['sections'], latest: () => Response) {
    const view: StudentSurveyView = { institution_timezone: 'America/New_York', sections };
    const asked: string[] = [];
    vi.stubGlobal('fetch', (input: string) => {
      asked.push(input);
      return Promise.resolve(
        input === '/student/survey'
          ? new Response(JSON.stringify(view), { status: 200 })
          : latest(),
      );
    });
    render(<StudentWeeklySurvey />);
    await screen.findByTestId('survey-section-AAAA');
    return asked;
  }

  const answer = (body: unknown, status = 200) => () =>
    new Response(JSON.stringify(body), { status });

  it('leads with the newest released week and links to that week', async () => {
    await landingWith([closedSection(FIRST_ID, 'AAAA', [])], answer(results('published', [1, 2, 3])));
    const block = within(screen.getByTestId('survey-section-AAAA'));
    expect(await block.findByText('Week 3 results are in')).toBeTruthy();
    const link = block.getByRole('link', { name: 'See Week 3 results for Course AAAA' });
    expect(link.textContent).toBe('See Week 3 results');
    expect(link.getAttribute('href')).toBe(`/app/student/sections/${FIRST_ID}/weeks/3/results`);
    // One link to the page, not two.
    expect(block.queryByRole('link', { name: /See your instructor/ })).toBeNull();
  });

  it.each(['on-behalf', 'unanswered'])('leads for a %s week too', async (state) => {
    await landingWith([closedSection(FIRST_ID, 'AAAA', [])], answer(results(state, [2])));
    expect(await screen.findByText('Week 2 results are in')).toBeTruthy();
  });

  // A second section whose lead does show is the control: the test waits for
  // it, so "the first has no lead" is read after the page has had its say and
  // not before the reads came back.
  async function twoSections(firstAnswer: () => Response) {
    const view: StudentSurveyView = {
      institution_timezone: 'America/New_York',
      sections: [closedSection(FIRST_ID, 'AAAA', []), closedSection(SECOND_ID, 'BBBB', [])],
    };
    vi.stubGlobal('fetch', (input: string) =>
      Promise.resolve(
        input === '/student/survey'
          ? new Response(JSON.stringify(view), { status: 200 })
          : input === RESULTS_OF(FIRST_ID)
            ? firstAnswer()
            : new Response(JSON.stringify(results('published', [1, 2])), { status: 200 }),
      ),
    );
    render(<StudentWeeklySurvey />);
    await screen.findByTestId('survey-section-AAAA');
    const second = within(screen.getByTestId('survey-section-BBBB'));
    await second.findByText('Week 2 results are in');
    return within(screen.getByTestId('survey-section-AAAA'));
  }

  it('shows no lead when the newest week is awaiting, and keeps the reply link', async () => {
    const first = await twoSections(answer(results('awaiting', [1, 2])));
    expect(first.queryByText(/results are in/)).toBeNull();
    expect(first.queryByTestId('pulse-results-lead')).toBeNull();
    expect(first.getByRole('link', { name: /See your instructor/ })).toBeTruthy();
  });

  it('shows no lead when the section has no published week', async () => {
    const first = await twoSections(answer({}, 404));
    expect(first.queryByText(/results are in/)).toBeNull();
  });

  it('leads with the survey, and asks nothing about results, when a survey is open', async () => {
    const asked: string[] = [];
    const open = {
      ...closedSection(FIRST_ID, 'AAAA', []),
      survey_is_open: true,
      open_survey: {
        window_id: '5e0c1d2a-6b7f-4c3e-9a1d-0b2c3d4e5f63',
        course_week: 3,
        length_weeks: 12,
        term_week: 3,
        opens_at: '2026-09-11T18:00:00-04:00',
        closes_at: '2026-09-13T23:59:59-04:00',
        question_set_version: 1,
        questions: [],
        submission: null,
      },
    };
    const view: StudentSurveyView = {
      institution_timezone: 'America/New_York',
      sections: [open],
    };
    vi.stubGlobal('fetch', (input: string) => {
      asked.push(input);
      return Promise.resolve(new Response(JSON.stringify(view), { status: 200 }));
    });
    render(<StudentWeeklySurvey />);
    await screen.findByTestId('survey-section-AAAA');
    expect(screen.queryByText(/results are in/)).toBeNull();
    expect(asked.filter((it) => it.includes('/results'))).toEqual([]);
  });
});
