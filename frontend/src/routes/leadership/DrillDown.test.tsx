import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import {
  LEADERSHIP_CONTEXT_PATH,
  drillDownPath,
  drillDownWeeksPath,
  type LeadershipContextView,
} from '../../api/leadership';
import { routeTree } from '../../router';
import {
  A_SMALL_N_WEEK,
  A_WEEK_WITH_A_HELD_COMMENT,
  PUBLISHED_WEEKS,
  SECTION_ID,
} from '../instructor/instructorReportFixtures';
import { DRILL_DOWN_CONTEXT_TESTID, DRILL_DOWN_TESTID } from './DrillDown';

/**
 * The drill-down (SPEC §5.5): the instructor's report, wholesale and
 * read-only, under a context bar naming the reader's role. Mounted on the
 * application's own route tree, over a payload carrying a held comment the
 * instructor herself could exclude or keep.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const A_DEAN_WHO_LEADS: LeadershipContextView = {
  roles: ['DEAN', 'LEAD_FACULTY'],
  terms: [],
  current_term_id: null,
};

const COMMENTS_NOTE = 'Shown in random order. No names, no timestamps.';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function serving(answers: Record<string, () => Response>): string[] {
  const asked: string[] = [];
  vi.stubGlobal('fetch', (input: string, init?: RequestInit) => {
    asked.push(`${init?.method ?? 'GET'} ${input}`);
    const answer = answers[input];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
}

function mountAt(address: string): void {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: [address] }),
  });
  render(<RouterProvider router={router} />);
}

describe('/leadership/sections/:id, the drill-down', () => {
  it('names the reader’s highest role in a read-only context bar', async () => {
    serving({
      [LEADERSHIP_CONTEXT_PATH]: () => json(200, A_DEAN_WHO_LEADS),
      [drillDownWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [drillDownPath(SECTION_ID, 7)]: () => json(200, A_WEEK_WITH_A_HELD_COMMENT),
    });
    mountAt(`/app/leadership/sections/${SECTION_ID}?week=7`);
    await screen.findByTestId(DRILL_DOWN_TESTID);
    await waitFor(() => {
      expect(screen.getByTestId(DRILL_DOWN_CONTEXT_TESTID).textContent).toBe(
        'Viewing as Dean · read-only',
      );
    });
  });

  it('carries no moderation control and no composer, and the report’s line once', async () => {
    const asked = serving({
      [LEADERSHIP_CONTEXT_PATH]: () => json(200, A_DEAN_WHO_LEADS),
      [drillDownWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [drillDownPath(SECTION_ID, 7)]: () => json(200, A_WEEK_WITH_A_HELD_COMMENT),
    });
    mountAt(`/app/leadership/sections/${SECTION_ID}?week=7`);
    await screen.findByText(COMMENTS_NOTE);

    // The payload holds a flagged comment, whose card offers the instructor
    // exclude and keep; on the drill-down it offers neither.
    for (const name of [/exclude/i, /keep for students/i, /^undo$/i]) {
      expect(screen.queryByRole('button', { name })).toBeNull();
    }
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.getAllByText(COMMENTS_NOTE)).toHaveLength(1);
    // Nothing was asked of the instructor's routes or of any write.
    expect(asked.filter((request) => request.includes('/instructor/'))).toEqual([]);
    expect(asked.filter((request) => !request.startsWith('GET '))).toEqual([]);
  });

  it('opens the latest published week when the address names none', async () => {
    const asked = serving({
      [LEADERSHIP_CONTEXT_PATH]: () => json(200, A_DEAN_WHO_LEADS),
      [drillDownWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [drillDownPath(SECTION_ID, 7)]: () => json(200, A_WEEK_WITH_A_HELD_COMMENT),
    });
    mountAt(`/app/leadership/sections/${SECTION_ID}`);
    await screen.findByText(COMMENTS_NOTE);
    expect(asked).toContain(`GET ${drillDownPath(SECTION_ID, 7)}`);
  });

  it('puts no count of anybody beside a small-N notice', async () => {
    serving({
      [LEADERSHIP_CONTEXT_PATH]: () => json(200, A_DEAN_WHO_LEADS),
      [drillDownWeeksPath(SECTION_ID)]: () => json(200, { published_weeks: PUBLISHED_WEEKS }),
      [drillDownPath(SECTION_ID, 7)]: () => json(200, A_SMALL_N_WEEK),
    });
    mountAt(`/app/leadership/sections/${SECTION_ID}?week=7`);
    await screen.findByText(COMMENTS_NOTE);
    const notices = Array.from(document.querySelectorAll('.pulse-small-n-notice'));
    expect(notices.length).toBe(2);
    const { responses, enrolled } = A_SMALL_N_WEEK.rates;
    for (const notice of notices) {
      const words = notice.textContent ?? '';
      expect(words).not.toContain(String(responses));
      expect(words).not.toContain(String(enrolled));
    }
  });

  it('shows the server’s sentence for a section outside the purview', async () => {
    serving({
      [LEADERSHIP_CONTEXT_PATH]: () => json(200, A_DEAN_WHO_LEADS),
      [drillDownWeeksPath(SECTION_ID)]: () => json(404, { detail: 'There is no report here.' }),
    });
    mountAt(`/app/leadership/sections/${SECTION_ID}`);
    expect(await screen.findByText('There is no report here.')).toBeTruthy();
  });
});

describe('the roll-up mockup', () => {
  it('passes its small-N notice no count of anybody', () => {
    // vitest's cwd is the workspace root (`frontend/`).
    const mockup = readFileSync(
      resolve(process.cwd(), '../design/LeadershipRollup.dc.html'),
      'utf8',
    );
    const notices = mockup.match(/<dc-import name="SmallNNotice"[^>]*>/g) ?? [];
    expect(notices.length).toBe(1);
    for (const notice of notices) {
      expect(notice).not.toMatch(/responded=|total=/);
    }
  });
});
