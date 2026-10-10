import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import {
  EXCLUSION_LOG_PATH,
  REVIEW_QUEUE_PATH,
  type LogRowView,
  type QueueItemView,
} from '../../api/leadership';
import { routeTree } from '../../router';
import { EXCLUSION_LOG_LIST_TESTID } from './ExclusionLog';
import { REVIEW_QUEUE_LIST_TESTID } from './ReviewQueue';

/**
 * How a reader reaches the review queue and the exclusion log (SPEC §5.2): from
 * the leadership landing, and not from the instructor's.
 *
 * Which leadership reader may read either page is the server's answer (ADR
 * 0190), driven in the two page tests beside this one; this file is about the
 * doors to them.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const LEADERSHIP_LANDING = 'pulse-landing-leadership';
const INSTRUCTOR_LANDING = 'pulse-landing-instructor';
const QUEUE_LINK = 'Comments awaiting your review';
const LOG_LINK = 'Exclusion log';

const A_BIOLOGY_ITEM: QueueItemView = {
  answer_id: '0b6c1f9e-3a52-4d0b-9a0e-6f1f2c3d4e51',
  text: 'The lab instructor is useless and should be fired before the next lab.',
  section_label: 'BIOL 215 R3WW — Principles of Ecology, Fall 2026',
};

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

function servingTheModerationReads(): void {
  vi.stubGlobal('fetch', (input: string) => {
    const body =
      input === REVIEW_QUEUE_PATH
        ? { items: [A_BIOLOGY_ITEM] }
        : input === EXCLUSION_LOG_PATH
          ? { rows: [AN_EXCLUSION_BY_A_LEAD] }
          : null;
    if (body === null) return Promise.reject(new Error(`No answer is served for ${input}.`));
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
}

function mountAt(address: string) {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: [address] }),
  });
  render(<RouterProvider router={router} />);
  return router;
}

describe('the leadership landing', () => {
  it('links to the review queue, and following the link opens it', async () => {
    servingTheModerationReads();
    const router = mountAt('/app/leadership');

    const landing = await screen.findByTestId(LEADERSHIP_LANDING);
    const link = within(landing).getByRole('link', { name: QUEUE_LINK });
    expect(link.getAttribute('href')).toBe('/app/leadership/review-queue');
    expect(link.classList.contains('pulse-set-link')).toBe(true);

    fireEvent.click(link);
    await screen.findByTestId(REVIEW_QUEUE_LIST_TESTID);
    expect(router.state.location.href).toBe('/leadership/review-queue');
  });

  it('links to the exclusion log, and following the link opens it', async () => {
    servingTheModerationReads();
    const router = mountAt('/app/leadership');

    const landing = await screen.findByTestId(LEADERSHIP_LANDING);
    const link = within(landing).getByRole('link', { name: LOG_LINK });
    expect(link.getAttribute('href')).toBe('/app/leadership/exclusion-log');
    expect(link.classList.contains('pulse-set-link')).toBe(true);

    fireEvent.click(link);
    await screen.findByTestId(EXCLUSION_LOG_LIST_TESTID);
    expect(router.state.location.href).toBe('/leadership/exclusion-log');
  });
});

describe('the instructor landing', () => {
  it('carries no link to either page', async () => {
    servingTheModerationReads();
    mountAt('/app/instructor');

    // The landing first, so the absence below is about a page that rendered.
    await screen.findByTestId(INSTRUCTOR_LANDING);
    expect(screen.queryByRole('link', { name: QUEUE_LINK })).toBeNull();
    expect(screen.queryByRole('link', { name: LOG_LINK })).toBeNull();
    for (const link of screen.queryAllByRole('link')) {
      expect(link.getAttribute('href') ?? '').not.toMatch(/review-queue|exclusion-log/);
    }
  });
});
