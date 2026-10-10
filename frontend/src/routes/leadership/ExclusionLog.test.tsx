import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import { EXCLUSION_LOG_PATH } from '../../api/leadership';
import { routeTree } from '../../router';
import {
  AN_EXCLUSION_BY_A_LEAD,
  AN_UNFLAGGED_EXCLUSION,
  A_KEEP_WITH_NO_EXCERPT,
  NO_REVIEW_GRANT,
  PLANTED,
} from './moderationFixtures';
import { EXCLUSION_LOG_LIST_TESTID } from './ExclusionLog';

/**
 * What `/leadership/exclusion-log` renders (SPEC §5.2), row by row against
 * `design/ExclusionLogRow.dc.html`: the date, the decider, the excerpt, and the
 * status with the reason under it — with the decider a role, never a name.
 *
 * Governed copy is transcribed rather than imported (`docs/MISTAKES.md`
 * entry 19).
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const HEADING = 'Exclusion log';
const EMPTY_TITLE = 'No decisions yet';
const NO_EXCERPT =
  'No excerpt. This comment is not shown in its section’s report, so the log does not quote it.';

function serving(status: number, body: unknown): void {
  vi.stubGlobal('fetch', (input: string) => {
    if (input !== EXCLUSION_LOG_PATH) {
      return Promise.reject(new Error(`This test serves no answer for ${input}.`));
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
}

function mountTheLog(): void {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: ['/app/leadership/exclusion-log'] }),
  });
  render(<RouterProvider router={router} />);
}

async function rows(): Promise<HTMLElement[]> {
  const list = await screen.findByTestId(EXCLUSION_LOG_LIST_TESTID);
  return within(list).getAllByRole('listitem');
}

/** One row's four columns, in the mockup's order. */
function columns(row: HTMLElement): string[] {
  return Array.from(row.children).map((cell) => cell.textContent);
}

describe('the exclusion log', () => {
  it('draws each row as the mockup does: date, role, section and excerpt, status and reason', async () => {
    serving(200, { rows: [AN_EXCLUSION_BY_A_LEAD, AN_UNFLAGGED_EXCLUSION] });
    mountTheLog();

    expect((await screen.findByRole('heading', { level: 1 })).textContent).toBe(HEADING);
    const [lead, instructor] = await rows();
    if (lead === undefined || instructor === undefined) throw new Error('Two rows were served.');

    expect(columns(lead)).toEqual([
      '2026-10-20',
      'Lead Faculty',
      `${AN_EXCLUSION_BY_A_LEAD.section_label}${AN_EXCLUSION_BY_A_LEAD.excerpt ?? ''}`,
      'Excluded · AI-flagged',
    ]);
    expect(lead.querySelector('time')?.getAttribute('dateTime')).toBe('2026-10-20');
    expect(lead.querySelector('q')?.textContent).toBe(AN_EXCLUSION_BY_A_LEAD.excerpt);

    expect(columns(instructor)).toEqual([
      '2026-10-13',
      'Instructor',
      `${AN_UNFLAGGED_EXCLUSION.section_label}${AN_UNFLAGGED_EXCLUSION.excerpt ?? ''}`,
      `Excluded · Unflagged, reason given${AN_UNFLAGGED_EXCLUSION.reason ?? ''}`,
    ]);
  });

  it('shows a keep as plainly as an exclusion, and says so when no excerpt was sent', async () => {
    serving(200, { rows: [A_KEEP_WITH_NO_EXCERPT] });
    mountTheLog();

    const [keep] = await rows();
    if (keep === undefined) throw new Error('One row was served.');
    expect(columns(keep)).toEqual([
      '2026-09-28',
      'Chair',
      `${A_KEEP_WITH_NO_EXCERPT.section_label}${NO_EXCERPT}`,
      'Kept · AI-flagged',
    ]);
    expect(keep.querySelector('q')).toBeNull();
  });

  it('keeps the server’s order, newest first, rather than grouping or sorting', async () => {
    // Served with the chair's row between the two exclusions: a page that
    // grouped by direction, role or section would move it.
    serving(200, {
      rows: [AN_EXCLUSION_BY_A_LEAD, A_KEEP_WITH_NO_EXCERPT, AN_UNFLAGGED_EXCLUSION],
    });
    mountTheLog();

    const shown = await rows();
    expect(shown.map((row) => row.querySelector('time')?.textContent)).toEqual([
      '2026-10-20',
      '2026-09-28',
      '2026-10-13',
    ]);
  });

  it('shows the server’s sentence for a reader with no review grant, not the empty state', async () => {
    serving(403, { detail: NO_REVIEW_GRANT });
    mountTheLog();

    expect(await screen.findByText(NO_REVIEW_GRANT)).toBeTruthy();
    expect(screen.queryByText(EMPTY_TITLE)).toBeNull();
  });

  it('says so when no decision has been made yet', async () => {
    serving(200, { rows: [] });
    mountTheLog();

    expect(await screen.findByText(EMPTY_TITLE)).toBeTruthy();
  });
});

describe('the exclusion log shows no name, no week and no time of day', () => {
  it('renders none of the members a payload might carry beside the seven it means to show', async () => {
    serving(200, {
      rows: [
        { ...AN_EXCLUSION_BY_A_LEAD, ...PLANTED },
        { ...A_KEEP_WITH_NO_EXCERPT, ...PLANTED },
      ],
    });
    mountTheLog();

    // The rows first (`docs/MISTAKES.md` entry 3).
    expect(await rows()).toHaveLength(2);
    expect(screen.getByText('Lead Faculty')).toBeTruthy();

    const page = document.body.textContent ?? '';
    for (const planted of Object.values(PLANTED)) {
      if (typeof planted === 'string') expect(page).not.toContain(planted);
    }
    expect(page).not.toMatch(/\bweeks?\b/i);
    expect(page).not.toMatch(/\bwk\b/i);
    expect(page).not.toMatch(/\d{1,2}:\d{2}/);
    expect(page).not.toMatch(/\b[AP]M\b/);
  });
});
