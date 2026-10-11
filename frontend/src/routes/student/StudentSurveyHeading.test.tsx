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
