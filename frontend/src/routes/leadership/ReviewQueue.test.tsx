import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import {
  REVIEW_QUEUE_PATH,
  queuedCommentDecisionPath,
  type QueueItemView,
} from '../../api/leadership';
import { routeTree } from '../../router';
import { REVIEW_QUEUE_LIST_TESTID } from './ReviewQueue';

/**
 * What `/leadership/review-queue` renders and sends (SPEC §5.2).
 *
 * Mounted on the application's own route tree over a memory history, with one
 * served answer per address, as the comparison-set tests do. Governed copy is
 * transcribed rather than imported (`docs/MISTAKES.md` entry 19).
 */

// What `api/leadership.py`'s moderation routes answer, written here rather than
// in a support module beside the route: a module in the route tree that is not a
// test ships its strings as far as the ungoverned-string sweep can tell. The
// section labels are in `section_codes.course_label`'s section form, and the
// refusal sentences are transcribed from `app/copy/leadership_moderation.py`.

const A_BIOLOGY_ITEM: QueueItemView = {
  answer_id: '0b6c1f9e-3a52-4d0b-9a0e-6f1f2c3d4e51',
  text: 'The lab instructor is useless and should be fired before the next lab.',
  section_label: 'BIOL 215 R3WW — Principles of Ecology, Fall 2026',
};

const A_MATHEMATICS_ITEM: QueueItemView = {
  answer_id: '7d2e8a14-5c63-4f1e-8b2d-0a1b2c3d4e52',
  text: 'Nobody in this class respects how badly the worksheets are written.',
  section_label: 'MATH 140 E1FF — College Algebra, Fall 2026',
};

const NO_REVIEW_GRANT = 'This leadership role has no review queue or exclusion log to read.';
const NOT_IN_QUEUE = 'There is no comment awaiting your review here. Nothing was changed.';

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
  document.cookie = 'pulse_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

const HEADING = 'Comments awaiting your review';
const EMPTY_TITLE = 'Nothing awaits your review';
const REVIEW = 'Review comment';
const EXCLUDE = 'Exclude from student view';
const KEEP = 'Keep for students';
const UNDO = 'Undo';
const EXCLUDED = 'Comment excluded. The exclusion log records it.';
const KEPT = 'Comment kept. The exclusion log records it.';
const FLAG_CHIP = 'Flagged: harmful';

interface Ask {
  readonly path: string;
  readonly method: string;
  readonly body: string | null;
  readonly headers: Headers;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function serving(answers: Record<string, () => Response>): Ask[] {
  const asked: Ask[] = [];
  vi.stubGlobal('fetch', (input: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    asked.push({
      path: input,
      method,
      body: typeof init?.body === 'string' ? init.body : null,
      headers: new Headers(init?.headers),
    });
    const answer = answers[`${method} ${input}`];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${method} ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
}

function mountTheQueue(): void {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: ['/app/leadership/review-queue'] }),
  });
  render(<RouterProvider router={router} />);
}

/** The queue's items, in the order they are on screen. */
async function items(): Promise<HTMLElement[]> {
  const list = await screen.findByTestId(REVIEW_QUEUE_LIST_TESTID);
  return within(list).getAllByRole('listitem');
}

/** Open one item's flagged card and press one of its two controls. */
function decideOn(item: HTMLElement, control: string): void {
  fireEvent.click(within(item).getByRole('button', { name: REVIEW }));
  fireEvent.click(within(item).getByRole('button', { name: control }));
}

const NO_CONTENT = (): Response => new Response(null, { status: 204 });

describe('the review queue', () => {
  it('lists each queued comment with its section and its words, in the order served', async () => {
    serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () =>
        json(200, { items: [A_MATHEMATICS_ITEM, A_BIOLOGY_ITEM] }),
    });
    mountTheQueue();

    expect(await screen.findByRole('heading', { level: 1 })).toHaveProperty('textContent', HEADING);
    const shown = await items();
    expect(shown).toHaveLength(2);
    expect(shown[0]?.textContent).toContain(A_MATHEMATICS_ITEM.section_label);
    expect(shown[1]?.textContent).toContain(A_BIOLOGY_ITEM.section_label);
    expect(shown[0]?.textContent).toContain(FLAG_CHIP);

    // The words appear when the card is opened, as on the instructor's report.
    for (const [index, item] of shown.entries()) {
      fireEvent.click(within(item).getByRole('button', { name: REVIEW }));
      const expected = index === 0 ? A_MATHEMATICS_ITEM.text : A_BIOLOGY_ITEM.text;
      expect(within(item).getByText(expected)).toBeTruthy();
      expect(within(item).getByRole('button', { name: EXCLUDE })).toBeTruthy();
      expect(within(item).getByRole('button', { name: KEEP })).toBeTruthy();
      expect(within(item).queryByRole('button', { name: UNDO })).toBeNull();
    }
  });

  it('keeps the server’s order rather than one of its own', async () => {
    // The same two items the other way round: a page that sorted by section or
    // by text would render this list as it rendered the one above.
    serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () =>
        json(200, { items: [A_BIOLOGY_ITEM, A_MATHEMATICS_ITEM] }),
    });
    mountTheQueue();

    const shown = await items();
    expect(
      shown.map((item) => item.querySelector('.pulse-moderation-section')?.textContent),
    ).toEqual([A_BIOLOGY_ITEM.section_label, A_MATHEMATICS_ITEM.section_label]);
  });

  it('excludes with no reason, behind the CSRF echo, and removes only that item', async () => {
    document.cookie = 'pulse_csrf=a-token-the-server-set';
    const asked = serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () =>
        json(200, { items: [A_BIOLOGY_ITEM, A_MATHEMATICS_ITEM] }),
      [`POST ${queuedCommentDecisionPath(A_BIOLOGY_ITEM.answer_id)}`]: NO_CONTENT,
    });
    mountTheQueue();

    const [biology] = await items();
    if (biology === undefined) throw new Error('The queue rendered no items.');
    decideOn(biology, EXCLUDE);

    await waitFor(() => {
      expect(screen.getAllByRole('status')[0]?.textContent).toBe(EXCLUDED);
    });
    const left = await items();
    expect(left).toHaveLength(1);
    expect(left[0]?.textContent).toContain(A_MATHEMATICS_ITEM.section_label);
    expect(screen.queryByText(A_BIOLOGY_ITEM.text)).toBeNull();

    const writes = asked.filter((ask) => ask.method === 'POST');
    expect(writes.map((ask) => ask.path)).toEqual([
      queuedCommentDecisionPath(A_BIOLOGY_ITEM.answer_id),
    ]);
    expect(JSON.parse(writes[0]?.body ?? 'null')).toEqual({ action: 'exclude', reason: null });
    expect(writes[0]?.headers.get('X-Pulse-CSRF')).toBe('a-token-the-server-set');
    // Focus leaves with the pressed control, so it goes to the heading.
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));
  });

  it('keeps, and removes the item the same way', async () => {
    const asked = serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () => json(200, { items: [A_BIOLOGY_ITEM] }),
      [`POST ${queuedCommentDecisionPath(A_BIOLOGY_ITEM.answer_id)}`]: NO_CONTENT,
    });
    mountTheQueue();

    const [biology] = await items();
    if (biology === undefined) throw new Error('The queue rendered no items.');
    decideOn(biology, KEEP);

    await waitFor(() => {
      expect(screen.getAllByRole('status')[0]?.textContent).toBe(KEPT);
    });
    expect(await screen.findByText(EMPTY_TITLE)).toBeTruthy();
    const write = asked.find((ask) => ask.method === 'POST');
    expect(JSON.parse(write?.body ?? 'null')).toEqual({ action: 'keep', reason: null });
  });

  it('shows a refused decision’s sentence inline and removes nothing', async () => {
    serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () => json(200, { items: [A_BIOLOGY_ITEM] }),
      [`POST ${queuedCommentDecisionPath(A_BIOLOGY_ITEM.answer_id)}`]: () =>
        json(404, { detail: NOT_IN_QUEUE }),
    });
    mountTheQueue();

    const [biology] = await items();
    if (biology === undefined) throw new Error('The queue rendered no items.');
    decideOn(biology, EXCLUDE);

    const alert = await within(biology).findByRole('alert');
    expect(alert.textContent).toBe(NOT_IN_QUEUE);
    expect(await items()).toHaveLength(1);
    expect(within(biology).getByText(A_BIOLOGY_ITEM.text)).toBeTruthy();
    expect(screen.getAllByRole('status')[0]?.textContent).toBe('');
  });

  it('shows the server’s sentence for a reader with no review grant, not the empty state', async () => {
    serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () => json(403, { detail: NO_REVIEW_GRANT }),
    });
    mountTheQueue();

    expect(await screen.findByText(NO_REVIEW_GRANT)).toBeTruthy();
    expect(screen.queryByText(EMPTY_TITLE)).toBeNull();
  });

  it('says so when nothing awaits review', async () => {
    serving({ [`GET ${REVIEW_QUEUE_PATH}`]: () => json(200, { items: [] }) });
    mountTheQueue();

    expect(await screen.findByText(EMPTY_TITLE)).toBeTruthy();
    expect(screen.queryByTestId(REVIEW_QUEUE_LIST_TESTID)).toBeNull();
  });
});

describe('the review queue shows no name, no week, no time and no count', () => {
  it('renders none of the members a payload might carry beside the three it means to show', async () => {
    serving({
      [`GET ${REVIEW_QUEUE_PATH}`]: () =>
        json(200, {
          items: [
            { ...A_BIOLOGY_ITEM, ...PLANTED },
            { ...A_MATHEMATICS_ITEM, ...PLANTED },
          ],
          count: 2,
          held_count: 7,
        }),
    });
    mountTheQueue();

    // The rows first (`docs/MISTAKES.md` entry 3): an absence asserted over a
    // page that rendered nothing proves nothing.
    const shown = await items();
    expect(shown).toHaveLength(2);
    for (const item of shown) {
      fireEvent.click(within(item).getByRole('button', { name: REVIEW }));
    }
    expect(screen.getByText(A_BIOLOGY_ITEM.text)).toBeTruthy();

    const page = document.body.textContent ?? '';
    // The planted strings; the planted week number is a digit that course
    // numbers carry too, so the week is checked by its words below instead.
    for (const planted of Object.values(PLANTED)) {
      if (typeof planted === 'string') expect(page).not.toContain(planted);
    }
    expect(page).not.toMatch(/\bweeks?\b/i);
    expect(page).not.toMatch(/\bwk\b/i);
    expect(page).not.toMatch(/\d{1,2}:\d{2}/);
    expect(page).not.toMatch(/\b[AP]M\b/);
    // No count of the items, in figures or in words. The section labels carry
    // course numbers and codes, so the check is on the two counts served.
    expect(page).not.toMatch(/\b2 comments?\b/i);
    expect(page).not.toMatch(/\b7\b/);
    expect(page).not.toMatch(/\btwo comments\b/i);
  });
});
