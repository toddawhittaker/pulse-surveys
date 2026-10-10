import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import { EXCLUSION_LOG_PATH, type LogRowView } from '../../api/leadership';
import { routeTree } from '../../router';
import { EXCLUSION_LOG_LIST_TESTID } from './ExclusionLog';

/**
 * What `/leadership/exclusion-log` renders (SPEC §5.2), row by row against
 * `design/ExclusionLogRow.dc.html`: the date, the decider, the excerpt, and the
 * status with the reason under it — with the decider a role, never a name.
 *
 * Governed copy is transcribed rather than imported (`docs/MISTAKES.md`
 * entry 19).
 */

// What `api/leadership.py`'s moderation routes answer, written here rather than
// in a support module beside the route: a module in the route tree that is not a
// test ships its strings as far as the ungoverned-string sweep can tell. The
// section labels are in `section_codes.course_label`'s section form, and the
// refusal sentences are transcribed from `app/copy/leadership_moderation.py`.

/** An exclusion of an AI-flagged comment, by its Lead Faculty, with an excerpt. */
const AN_EXCLUSION_BY_A_LEAD: LogRowView = {
  section_label: 'BIOL 215 R3WW — Principles of Ecology, Fall 2026',
  decision: 'EXCLUDED',
  decided_as: 'LEAD_FACULTY',
  flagged: true,
  reason: null,
  decided_on: '2026-10-20',
  excerpt: 'This professor is clueless and should not be allowed near a classroom.',
};

/** An instructor's exclusion of an unflagged comment, with the reason SPEC §5.2 requires. */
const AN_UNFLAGGED_EXCLUSION: LogRowView = {
  section_label: 'MATH 140 E1FF — College Algebra, Fall 2026',
  decision: 'EXCLUDED',
  decided_as: 'INSTRUCTOR',
  flagged: false,
  reason: 'Personal attack with no actionable content.',
  decided_on: '2026-10-13',
  excerpt: 'The pace is fine but the grader is a joke.',
};

/** A chair's keep, whose excerpt the server withheld (ADR 0190). */
const A_KEEP_WITH_NO_EXCERPT: LogRowView = {
  section_label: 'BUSA 300 F1WW — Operations Management, Fall 2026',
  decision: 'KEPT',
  decided_as: 'CHAIR',
  flagged: true,
  reason: null,
  decided_on: '2026-09-28',
  excerpt: null,
};

const NO_REVIEW_GRANT = 'This leadership role has no review queue or exclusion log to read.';

/**
 * Members the wire never carries, planted beside the real ones.
 *
 * A page that rendered what it was sent rather than the members it means to
 * show would print these, so a test that serves them and finds none of them on
 * screen proves the page chooses its members (SPEC §4: no name, no week, no
 * time beside a comment).
 */
const PLANTED = {
  instructor_name: 'Dr. M. Ellison',
  decided_by: 'Margaret Ellison',
  course_week: 4,
  week_label: 'COURSE WK 04',
  submitted_at: '2026-10-02T19:42:00-04:00',
  decided_at: '2026-10-20T14:32:00-04:00',
} as const;

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
      'Decided by lead faculty',
      `${AN_EXCLUSION_BY_A_LEAD.section_label}${AN_EXCLUSION_BY_A_LEAD.excerpt ?? ''}`,
      'Excluded · AI-flagged',
    ]);
    expect(lead.querySelector('time')?.getAttribute('dateTime')).toBe('2026-10-20');
    expect(lead.querySelector('q')?.textContent).toBe(AN_EXCLUSION_BY_A_LEAD.excerpt);

    expect(columns(instructor)).toEqual([
      '2026-10-13',
      'Decided by the instructor',
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
      'Decided by the chair',
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
    expect(screen.getByText('Decided by lead faculty')).toBeTruthy();

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
