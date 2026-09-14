import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import {
  COMPARISON_SETS_PATH,
  COMPARISON_SET_OPTIONS_PATH,
  comparisonSetPath,
  comparisonSetPreviewPath,
} from '../../api/leadership';
import {
  AN_UNKNOWN_SET_REFUSAL,
  A_BIOLOGY_COURSE,
  A_PREVIEW_WITH_BOTH_COUNTS,
  A_SET_SUMMARY,
  A_SET_THIS_READER_DEFINED,
  THE_OPTIONS,
} from '../../api/comparisonSetFixtures';
import { routeTree } from '../../router';
import { COMPARISON_SET_LIST_TESTID } from './ComparisonSets';
import { COMPARISON_SET_FORM_TESTID } from './ComparisonSetForm';

/**
 * What the leadership area's three addresses do — ticket E5-09.
 *
 * The states each page can be in are driven in the two files beside this one.
 * This file is the other half: which address opens which page, how a reader
 * reaches the set list from the landing they are sent to, and what an edit
 * address does with the set it names. It mounts the application's **own** route
 * tree on a memory history rather than a second table written for a test.
 *
 * It is also where the write headers are asserted, because a write only happens
 * at an address: `api/leadership.py`'s edit route is behind the same
 * double-submit check the student's submission is, and a client that did not
 * echo the cookie would be refused by the server and green here.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = 'pulse_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

const LANDING_TESTID = 'pulse-landing-leadership';
const SETS_LINK = 'Comparison sets';
const EDIT_HEADING = 'Edit this comparison set';
const FORM_LOADING = 'Opening this set…';
const SAVE = 'Save this set';
const CANCEL = 'Cancel';
const SESSION_ENDED = 'This page is not signed in';

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
    const answer = answers[`${method} ${input}`] ?? answers[input];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
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

/** The form's name field, typed so its value can be read. */
function nameField(): HTMLInputElement {
  return screen.getByLabelText('Set name');
}

function addressOf(router: ReturnType<typeof mountAt>): string {
  return router.state.location.href;
}

/** The stack an edit address reads: the choice lists and the set itself. */
function servingOneSet(): Ask[] {
  return serving({
    [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
    [`GET ${comparisonSetPath(A_SET_THIS_READER_DEFINED.id)}`]: () =>
      json(200, A_SET_THIS_READER_DEFINED),
    [`PUT ${comparisonSetPath(A_SET_THIS_READER_DEFINED.id)}`]: () =>
      json(200, A_SET_THIS_READER_DEFINED),
    [COMPARISON_SETS_PATH]: () => json(200, { sets: [A_SET_SUMMARY] }),
    [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () => json(200, A_PREVIEW_WITH_BOTH_COUNTS),
  });
}

describe('/leadership, the landing', () => {
  it('carries one link to the comparison sets, and following it opens them', async () => {
    servingOneSet();
    const router = mountAt('/app/leadership');

    // The landing is still the empty roll-up view E1 shipped; the link is what
    // E5-09 adds to it, and the testid nine end-to-end specs address is intact.
    const landing = await screen.findByTestId(LANDING_TESTID);
    const link = within(landing).getByRole('link', { name: SETS_LINK });
    expect(link.getAttribute('href')).toBe('/app/leadership/comparison-sets');

    fireEvent.click(link);
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    expect(addressOf(router)).toBe('/leadership/comparison-sets');
  });
});

describe('/leadership/comparison-sets/$setId, one set in the form', () => {
  it('says it is opening, then opens the set the address names', async () => {
    const asked = servingOneSet();
    mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    expect((await screen.findByRole('status')).textContent).toBe(FORM_LOADING);

    await screen.findByRole('heading', { name: EDIT_HEADING });
    expect(asked.map((ask) => ask.path)).toContain(
      comparisonSetPath(A_SET_THIS_READER_DEFINED.id),
    );
    expect(nameField().value).toBe(A_SET_THIS_READER_DEFINED.name);
  });

  it('sends the edit to that set’s own address and returns to the list', async () => {
    const asked = servingOneSet();
    const router = mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    const form = await screen.findByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.click(within(form).getByLabelText(A_BIOLOGY_COURSE.label));
    fireEvent.click(within(form).getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(addressOf(router)).toBe('/leadership/comparison-sets');
    });
    const writes = asked.filter((ask) => ask.method === 'PUT');
    expect(writes.map((ask) => ask.path)).toEqual([
      comparisonSetPath(A_SET_THIS_READER_DEFINED.id),
    ]);
  });

  it('returns to the list without writing anything when it is cancelled', async () => {
    const asked = servingOneSet();
    const router = mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    const form = await screen.findByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.click(within(form).getByRole('button', { name: CANCEL }));

    await waitFor(() => {
      expect(addressOf(router)).toBe('/leadership/comparison-sets');
    });
    expect(asked.every((ask) => ask.method === 'GET')).toBe(true);
  });

  it('mirrors the API on an address naming a set it will not answer for', async () => {
    serving({
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPath(A_SET_THIS_READER_DEFINED.id)]: () =>
        json(404, { detail: AN_UNKNOWN_SET_REFUSAL }),
    });
    mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    // The page asks and shows the refusal it was sent; it holds no list of the
    // sets that exist to have checked against first.
    await screen.findByText(AN_UNKNOWN_SET_REFUSAL);
    expect(screen.queryByTestId(COMPARISON_SET_FORM_TESTID)).toBeNull();
  });

  it('says the session ended rather than showing an empty form', async () => {
    serving({
      [COMPARISON_SET_OPTIONS_PATH]: () => json(401, { detail: 'Not authenticated' }),
      [comparisonSetPath(A_SET_THIS_READER_DEFINED.id)]: () =>
        json(401, { detail: 'Not authenticated' }),
    });
    mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    await screen.findByText(SESSION_ENDED);
    expect(screen.queryByTestId(COMPARISON_SET_FORM_TESTID)).toBeNull();
  });
});

describe('the headers a write carries', () => {
  it('echoes the double-submit cookie when the document can read it', async () => {
    document.cookie = 'pulse_csrf=a-token-the-server-set';
    const asked = servingOneSet();
    mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    const form = await screen.findByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.click(within(form).getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(asked.some((ask) => ask.method === 'PUT')).toBe(true);
    });
    const write = asked.find((ask) => ask.method === 'PUT');
    expect(write?.headers.get('X-Pulse-CSRF')).toBe('a-token-the-server-set');
    // And the reads carry no such header, because there is nothing to protect
    // on a read and the server requires none.
    const read = asked.find((ask) => ask.method === 'GET');
    expect(read?.headers.get('X-Pulse-CSRF')).toBeNull();
  });

  it('sends no such header when there is no cookie to echo', async () => {
    const asked = servingOneSet();
    mountAt(`/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`);

    const form = await screen.findByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.click(within(form).getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(asked.some((ask) => ask.method === 'PUT')).toBe(true);
    });
    // A value the cookie did not supply would be a double submit the server
    // cannot compare, which is a check that verifies nothing.
    expect(asked.find((ask) => ask.method === 'PUT')?.headers.get('X-Pulse-CSRF')).toBeNull();
  });
});
