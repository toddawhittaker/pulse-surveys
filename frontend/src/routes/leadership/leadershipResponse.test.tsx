import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import {
  RESPONSE_POLICY_PATH,
  RESPONSES_OWED_PATH,
  onBehalfPath,
  responsePolicyPrefixPath,
} from '../../api/leadership';
import { routeTree } from '../../router';
import { RESPONSES_OWED_LIST_TESTID } from './ResponsesOwed';

/**
 * What the three leadership response pages render and send (SPEC §5.3, §5.6).
 *
 * Mounted on the application's own route tree over a memory history with one
 * served answer per address. The sentences are written out rather than read
 * from the copy module, so a test cannot pass by agreeing with the words it
 * checks.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = 'pulse_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

const SECTION_ID = '5b6e0c1a-2d3f-4a5b-8c9d-0e1f2a3b4c5d';
const BIOLOGY_SECTION = 'BIOL 215 R3WW — Principles of Ecology, Fall 2026';
const ON_BEHALF = onBehalfPath(SECTION_ID, 4);

interface Ask {
  readonly path: string;
  readonly method: string;
  readonly body: string | null;
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
    asked.push({ path: input, method, body: typeof init?.body === 'string' ? init.body : null });
    const answer = answers[`${method} ${input}`];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${method} ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
}

function mountAt(path: string): void {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: [`/app${path}`] }),
  });
  render(<RouterProvider router={router} />);
}

const PREFIX_ID = '0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d';

function course(
  id: string,
  label: string,
  mode: 'REQUIRED' | 'ENCOURAGED',
  can_set: boolean,
  set_by_role: 'LEAD_FACULTY' | 'CHAIR' | null = null,
) {
  return { course_id: id, course_label: label, mode, can_set, set_by_role };
}

const LEAD_VIEW = {
  prefixes: [
    {
      prefix_id: PREFIX_ID,
      prefix_code: 'BIOL',
      courses: [course('c1', 'BIOL 215 Principles of Ecology', 'ENCOURAGED', true)],
    },
  ],
};

describe('the response policy page', () => {
  it('switches the prefix to required and shows what the server answered', async () => {
    const asked = serving({
      [`GET ${RESPONSE_POLICY_PATH}`]: () => json(200, LEAD_VIEW),
      [`PUT ${responsePolicyPrefixPath(PREFIX_ID)}`]: () =>
        json(200, {
          prefixes: [
            {
              ...LEAD_VIEW.prefixes[0],
              courses: [course('c1', 'BIOL 215 Principles of Ecology', 'REQUIRED', true)],
            },
          ],
        }),
    });
    mountAt('/leadership/response-policy');

    const toggle = await screen.findByRole('switch', {
      name: 'Response required for BIOL courses you set',
    });
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(
        screen.getByRole('switch', { name: 'Response required for BIOL courses you set' }).getAttribute(
          'aria-checked',
        ),
      ).toBe('true');
    });
    const put = asked.find((ask) => ask.method === 'PUT');
    expect(put?.body).toBe(JSON.stringify({ mode: 'REQUIRED' }));
    expect(screen.getByText('Response required', { selector: '.pulse-policy-course-mode' })).toBeTruthy();
  });

  it('says a change applies from the next week’s report', async () => {
    serving({ [`GET ${RESPONSE_POLICY_PATH}`]: () => json(200, LEAD_VIEW) });
    mountAt('/leadership/response-policy');
    await screen.findByRole('switch');
    expect(
      screen.getByText(
        'A change applies from the next week’s report. A week that is already open keeps the setting it opened with.',
      ),
    ).toBeTruthy();
  });

  it('shows a course the reader cannot set as text with the setter’s role and no switch', async () => {
    serving({
      [`GET ${RESPONSE_POLICY_PATH}`]: () =>
        json(200, {
          prefixes: [
            {
              prefix_id: PREFIX_ID,
              prefix_code: 'BIOL',
              courses: [
                course('c1', 'BIOL 215 Principles of Ecology', 'REQUIRED', false, 'LEAD_FACULTY'),
              ],
            },
          ],
        }),
    });
    mountAt('/leadership/response-policy');

    await screen.findByText('BIOL 215 Principles of Ecology');
    expect(screen.queryByRole('switch')).toBeNull();
    expect(
      screen.getByText('Set by the course’s Lead Faculty. Read-only at your role.'),
    ).toBeTruthy();
  });

  it('offers a switch for the courses with no lead and text for the led one, in one prefix', async () => {
    serving({
      [`GET ${RESPONSE_POLICY_PATH}`]: () =>
        json(200, {
          prefixes: [
            {
              prefix_id: PREFIX_ID,
              prefix_code: 'BIOL',
              courses: [
                course('c1', 'BIOL 215 Principles of Ecology', 'REQUIRED', false, 'LEAD_FACULTY'),
                course('c2', 'BIOL 301 Genetics', 'ENCOURAGED', true),
              ],
            },
          ],
        }),
    });
    mountAt('/leadership/response-policy');

    expect((await screen.findAllByRole('switch')).length).toBe(1);
    // The switch's state follows the course the reader sets, not the led one.
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('keeps the server’s sentence when a change is refused, and the switch where it was', async () => {
    serving({
      [`GET ${RESPONSE_POLICY_PATH}`]: () => json(200, LEAD_VIEW),
      [`PUT ${responsePolicyPrefixPath(PREFIX_ID)}`]: () =>
        json(404, { detail: 'There is no response policy for you to set here.' }),
    });
    mountAt('/leadership/response-policy');
    fireEvent.click(await screen.findByRole('switch'));

    expect((await screen.findByRole('alert')).textContent).toBe(
      'There is no response policy for you to set here.',
    );
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('shows a calm empty state for a reader with no courses', async () => {
    serving({ [`GET ${RESPONSE_POLICY_PATH}`]: () => json(200, { prefixes: [] }) });
    mountAt('/leadership/response-policy');
    expect(await screen.findByText('No courses to show')).toBeTruthy();
  });

  it('tells a signed-in reader in another role the page is not theirs', async () => {
    serving({
      [`GET ${RESPONSE_POLICY_PATH}`]: () =>
        new Response('{"detail":"x"}', {
          status: 403,
          headers: {
            'Content-Type': 'application/json',
            'WWW-Authenticate': 'Bearer error="insufficient_scope"',
          },
        }),
    });
    mountAt('/leadership/response-policy');
    expect(await screen.findByText('This page is not part of your role')).toBeTruthy();
  });
});

describe('the responses owed page', () => {
  it('lists each section-week, with a way in only where the on-behalf door is open', async () => {
    serving({
      [`GET ${RESPONSES_OWED_PATH}`]: () =>
        json(200, [
          { section_id: SECTION_ID, section_label: BIOLOGY_SECTION, course_week: 4, on_behalf_open: true },
          {
            section_id: '9c8d7e6f-5a4b-4c3d-8e2f-1a0b9c8d7e6f',
            section_label: 'MATH 140 E1FF — College Algebra, Fall 2026',
            course_week: 2,
            on_behalf_open: false,
          },
        ]),
    });
    mountAt('/leadership/responses-owed');

    const list = await screen.findByTestId(RESPONSES_OWED_LIST_TESTID);
    const rows = within(list).getAllByRole('listitem');
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain('Week 4');
    expect(within(rows[0] as HTMLElement).getByRole('link').getAttribute('href')).toBe(
      `/app/leadership/sections/${SECTION_ID}/weeks/4/on-behalf`,
    );
    expect(within(rows[1] as HTMLElement).queryByRole('link')).toBeNull();
    expect(rows[1]?.textContent).toContain('Week 2');
  });

  it('writes nothing that ranks or blames, and names no instructor', async () => {
    serving({
      [`GET ${RESPONSES_OWED_PATH}`]: () =>
        json(200, [
          {
            section_id: SECTION_ID,
            section_label: BIOLOGY_SECTION,
            course_week: 4,
            on_behalf_open: true,
            instructor_name: 'Dr. M. Ellison',
          },
        ]),
    });
    mountAt('/leadership/responses-owed');
    await screen.findByTestId(RESPONSES_OWED_LIST_TESTID);

    const page = document.body.textContent;
    expect(page).not.toMatch(/delinquent|late|overdue|worst|rank/i);
    expect(page).not.toContain('Ellison');
  });

  it('shows a calm empty state when nothing is owed', async () => {
    serving({ [`GET ${RESPONSES_OWED_PATH}`]: () => json(200, []) });
    mountAt('/leadership/responses-owed');
    expect(await screen.findByText('No responses are owed')).toBeTruthy();
  });
});

const WEEK = {
  section_label: BIOLOGY_SECTION,
  course_week: 4,
  streams: [
    {
      stream: 'instructor',
      summary_text: 'Students found the lab demonstrations clear.',
      response_count: 12,
      rating_distribution: { '1': 0, '2': 1, '3': 2, '4': 5, '5': 4 },
    },
    {
      stream: 'course',
      summary_text: null,
      response_count: 1,
      rating_distribution: { '1': 0, '2': 0, '3': 0, '4': 1, '5': 0 },
    },
  ],
  response: null,
};

describe('responding on behalf', () => {
  it('shows the summaries and ratings and no comment, however the wire is shaped', async () => {
    serving({
      [`GET ${ON_BEHALF}`]: () =>
        json(200, {
          ...WEEK,
          comments: [{ text: 'PLANTED-COMMENT-7731' }],
          streams: WEEK.streams.map((stream) => ({ ...stream, comments: ['PLANTED-COMMENT-7731'] })),
        }),
    });
    mountAt(`/leadership/sections/${SECTION_ID}/weeks/4/on-behalf`);

    expect(await screen.findByText('Students found the lab demonstrations clear.')).toBeTruthy();
    expect(screen.getByText('12 responses')).toBeTruthy();
    expect(screen.getByText('No summary is shown for this stream this week.')).toBeTruthy();
    expect(document.body.textContent).not.toContain('PLANTED-COMMENT-7731');
  });

  it('publishes through the on-behalf door and shows the reader’s own name and role', async () => {
    const asked = serving({
      [`GET ${ON_BEHALF}`]: () => json(200, WEEK),
      [`POST ${ON_BEHALF}/response`]: () =>
        json(200, {
          state: 'on-behalf',
          response: {
            text: 'We heard you on pacing.',
            author_name: 'Dr. Lena Park',
            author_role: 'LEAD_FACULTY',
            published_at: '2026-10-20T14:00:00Z',
          },
          can_edit: true,
        }),
    });
    mountAt(`/leadership/sections/${SECTION_ID}/weeks/4/on-behalf`);

    fireEvent.change(await screen.findByRole('textbox', { name: 'Your response' }), {
      target: { value: 'We heard you on pacing.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    await screen.findByText('We heard you on pacing.', { selector: '.pulse-response-text' });
    expect(document.body.textContent).toContain('Dr. Lena Park');
    expect(document.body.textContent).toContain('Lead Faculty');
    expect(asked.filter((ask) => ask.method === 'POST')).toEqual([
      {
        path: `${ON_BEHALF}/response`,
        method: 'POST',
        body: JSON.stringify({ text: 'We heard you on pacing.', ai_seeded: false }),
      },
    ]);
    // What was published can be changed, through the on-behalf door.
    expect(screen.getByRole('button', { name: 'Edit response' })).toBeTruthy();
  });

  it('draws the draft and the check from the on-behalf doors', async () => {
    const asked = serving({
      [`GET ${ON_BEHALF}`]: () => json(200, WEEK),
      [`POST ${ON_BEHALF}/response-draft`]: () => json(200, { text: 'A draft.' }),
      [`POST ${ON_BEHALF}/draft-check`]: () => json(200, { unaddressed: [] }),
    });
    mountAt(`/leadership/sections/${SECTION_ID}/weeks/4/on-behalf`);

    fireEvent.click(await screen.findByRole('button', { name: 'Draft with AI' }));
    await waitFor(() => {
      expect(screen.getByRole('textbox')).toHaveProperty('value', 'A draft.');
    });
    fireEvent.click(screen.getByRole('button', { name: 'Check draft with AI' }));
    await screen.findByText('Your draft addresses every theme in this week’s comments.');
    expect(asked.map((ask) => `${ask.method} ${ask.path}`)).toEqual([
      `GET ${ON_BEHALF}`,
      `POST ${ON_BEHALF}/response-draft`,
      `POST ${ON_BEHALF}/draft-check`,
    ]);
  });

  it('renders the one 404 as the not-found state and nothing of the section', async () => {
    serving({
      [`GET ${ON_BEHALF}`]: () => json(404, { detail: 'That week is not open for you to respond to.' }),
    });
    mountAt(`/leadership/sections/${SECTION_ID}/weeks/4/on-behalf`);

    expect(await screen.findByText('Nothing to respond to here')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(document.body.textContent).not.toContain('BIOL');
  });

  it('opens the not-found state for a week that is not a number, without asking the server', async () => {
    const asked = serving({});
    mountAt(`/leadership/sections/${SECTION_ID}/weeks/four/on-behalf`);

    expect(await screen.findByText('Nothing to respond to here')).toBeTruthy();
    expect(asked).toEqual([]);
  });
});

describe('a lead coming back to a week they answered', () => {
  it('shows their published response with Edit and no open composer', async () => {
    serving({
      [`GET ${ON_BEHALF}`]: () =>
        json(200, {
          ...WEEK,
          response: {
            state: 'on-behalf',
            response: {
              text: 'We heard you on pacing.',
              author_name: 'Dr. Lena Park',
              author_role: 'LEAD_FACULTY',
              published_at: '2026-10-20T14:00:00Z',
            },
            can_edit: true,
          },
        }),
    });
    mountAt(`/leadership/sections/${SECTION_ID}/weeks/4/on-behalf`);

    expect(await screen.findByText('We heard you on pacing.', { selector: '.pulse-response-text' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Edit response' })).toBeTruthy();
    expect(screen.queryByRole('textbox', { name: 'Your response' })).toBeNull();
  });
});

describe('the leadership landing', () => {
  it('links to the policy and the responses owed', async () => {
    serving({});
    mountAt('/leadership');
    expect((await screen.findByRole('link', { name: 'Response policy' })).getAttribute('href')).toBe(
      '/app/leadership/response-policy',
    );
    expect(screen.getByRole('link', { name: 'Responses owed' }).getAttribute('href')).toBe(
      '/app/leadership/responses-owed',
    );
  });
});
