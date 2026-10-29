import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import { routeTree } from '../../router';

/**
 * What the admin's two editors do (SPEC §6.3): the order and paging they show,
 * the roles they offer, the writes they send, the sentences they show for a
 * refusal, and the rule that an import is applied only after its dry run.
 *
 * The application's own route tree is mounted on a memory history, and `fetch`
 * is replaced by a function that answers by method and path, so each test says
 * which answers the server gave and reads what the page asked.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = 'pulse_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

const PEOPLE_PAGE = '/app/admin/people';
const MAPPINGS_PAGE = '/app/admin/lead-mappings';

interface Ask {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
  readonly headers: Headers;
}

type Handler = (ask: Ask) => Response | undefined;

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function none(): Response {
  return new Response(null, { status: 204 });
}

const NOT_YOUR_ROLE_HEADERS = { 'WWW-Authenticate': 'Bearer error="insufficient_scope"' };

/** Serve `handler`'s answers; a path it has none for fails the test loudly. */
function serving(handler: Handler): Ask[] {
  const asked: Ask[] = [];
  vi.stubGlobal('fetch', (input: string, init?: RequestInit) => {
    const ask: Ask = {
      method: init?.method ?? 'GET',
      path: input,
      body: typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : null,
      headers: new Headers(init?.headers),
    };
    asked.push(ask);
    const answer = handler(ask);
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${ask.method} ${ask.path}.`));
    }
    return Promise.resolve(answer);
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

const ZELLER_CHAIR = 'chair-1';
const ADAMS_ASSIGNMENT = 'adams-assignment';
const ZELLER_ASSIGNMENT_A = 'zeller-lead-a';
const ZELLER_ASSIGNMENT_B = 'zeller-lead-b';

function person(
  id: string,
  name: string,
  category: string,
  assignments: unknown[] = [],
  linked = false,
) {
  return { person_id: id, name, category, web_login_linked: linked, assignments };
}

function assignment(
  id: string,
  role: string,
  parent: { id: string; name: string; role: string } | null,
) {
  return {
    assignment_id: id,
    role,
    scope_node_id: `${id}-node`,
    reports_to: parent?.id ?? null,
    reports_to_name: parent?.name ?? null,
    reports_to_role: parent?.role ?? null,
  };
}

const THE_PEOPLE = [
  person('p-adams', 'Bo Adams', 'Faculty', [assignment(ADAMS_ASSIGNMENT, 'CHAIR', null)]),
  // Two lead assignments, each under its own chair (SPEC §2.1).
  person('p-zeller', 'Dr. Ana Zeller', 'Faculty', [
    assignment(ZELLER_ASSIGNMENT_A, 'LEAD_FACULTY', {
      id: ZELLER_CHAIR,
      name: 'Bo Adams',
      role: 'CHAIR',
    }),
    assignment(ZELLER_ASSIGNMENT_B, 'LEAD_FACULTY', {
      id: 'another-chair',
      name: 'Cy Chen',
      role: 'CHAIR',
    }),
  ]),
  person('p-zimmer', 'Prof. Cy Zimmer', 'Staff', [], true),
];

function peoplePage(people: unknown[], total = people.length, page = 1) {
  return { total, page, page_size: 25, people };
}

/** The reads every People page test needs, over `rows`. */
function peopleReads(rows: unknown[] = THE_PEOPLE): Handler {
  return (ask) => {
    if (ask.method === 'GET' && ask.path.startsWith('/admin/people?')) {
      return json(200, peoplePage(rows));
    }
    if (ask.method === 'GET' && ask.path.startsWith('/admin/reports-to-options')) {
      return json(200, { options: [] });
    }
    if (ask.method === 'GET' && ask.path.startsWith('/admin/org-nodes?')) {
      return json(200, { nodes: nodesFor(ask.path) });
    }
    return undefined;
  };
}

/** The nodes the server would answer for a role: the level is the server's, so each role gets its own. */
function nodesFor(path: string) {
  return path.endsWith('role=CARE')
    ? [{ node_id: 'inst-1', label: 'Pulse University', parent_label: null }]
    : [
        { node_id: 'dept-a', label: 'Biology', parent_label: 'Sciences' },
        { node_id: 'dept-b', label: 'Biology', parent_label: 'Health' },
      ];
}

/** The element a control's `aria-describedby` names, or `null`. */
function describing(control: HTMLElement): HTMLElement | null {
  const id = control.getAttribute('aria-describedby');
  return id === null ? null : document.getElementById(id);
}

function tableRowNames(): string[] {
  const table = screen.getByTestId('pulse-admin-people-table');
  return within(table)
    .getAllByRole('rowheader')
    .map((cell) => cell.textContent ?? '');
}

describe('/admin/people, the People & reporting table', () => {
  it('shows the people in the order the server sent them', async () => {
    // Last-name order with titles stripped is the server's. The rows here are in
    // an order no client sort of the shown text would produce.
    serving(peopleReads([THE_PEOPLE[2], THE_PEOPLE[0], THE_PEOPLE[1]]));
    mountAt(PEOPLE_PAGE);

    await screen.findByTestId('pulse-admin-people-table');
    expect(tableRowNames()).toEqual(['Prof. Cy Zimmer', 'Bo Adams', 'Dr. Ana Zeller']);
  });

  it('asks the server for the other order when a header is chosen, and shows what comes back', async () => {
    const asked = serving((ask) => {
      if (ask.path === '/admin/people?sort=name&order=asc&page=1') {
        return json(200, peoplePage([THE_PEOPLE[0], THE_PEOPLE[1], THE_PEOPLE[2]]));
      }
      if (ask.path === '/admin/people?sort=name&order=desc&page=1') {
        return json(200, peoplePage([THE_PEOPLE[2], THE_PEOPLE[1], THE_PEOPLE[0]]));
      }
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');

    const nameHeader = screen.getByRole('columnheader', { name: /Name/ });
    expect(nameHeader.getAttribute('aria-sort')).toBe('ascending');
    fireEvent.click(within(nameHeader).getByRole('button'));

    await waitFor(() => {
      expect(tableRowNames()).toEqual(['Prof. Cy Zimmer', 'Dr. Ana Zeller', 'Bo Adams']);
    });
    expect(asked.map((ask) => ask.path)).toContain('/admin/people?sort=name&order=desc&page=1');
    expect(screen.getByRole('columnheader', { name: /Name/ }).getAttribute('aria-sort')).toBe(
      'descending',
    );
  });

  it('sorts by category from its own header, starting ascending', async () => {
    const asked = serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');

    const category = screen.getByRole('columnheader', { name: /Category/ });
    expect(category.getAttribute('aria-sort')).toBe('none');
    fireEvent.click(within(category).getByRole('button'));

    await waitFor(() => {
      expect(asked.map((ask) => ask.path)).toContain(
        '/admin/people?sort=category&order=asc&page=1',
      );
    });
  });

  it('pages: the next page is a request for the next page, and the first has no previous', async () => {
    const asked = serving((ask) => {
      if (ask.path === '/admin/people?sort=name&order=asc&page=1') {
        return json(200, { total: 40, page: 1, page_size: 25, people: [THE_PEOPLE[0]] });
      }
      if (ask.path === '/admin/people?sort=name&order=asc&page=2') {
        return json(200, { total: 40, page: 2, page_size: 25, people: [THE_PEOPLE[2]] });
      }
      return undefined;
    });
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');

    const pager = screen.getByRole('navigation', { name: 'Pages' });
    expect(within(pager).getByText('Page 1 of 2')).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Previous page' }).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));

    await waitFor(() => {
      expect(tableRowNames()).toEqual(['Prof. Cy Zimmer']);
    });
    expect(within(pager).getByText('Page 2 of 2')).toBeTruthy();
    // The pager is also said aloud, and focus left the disabled control for the table.
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('Page 2 of 2');
    });
    expect(document.activeElement?.tagName).toBe('CAPTION');
    expect(asked.map((ask) => ask.path)).toContain('/admin/people?sort=name&order=asc&page=2');
  });

  it('shows both lead assignments of one person, each with its own chair', async () => {
    serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');

    const row = screen.getByRole('rowheader', { name: 'Dr. Ana Zeller' }).closest('tr');
    expect(row).not.toBeNull();
    const lines = within(row as HTMLElement).getAllByRole('listitem');
    expect(lines.map((line) => line.textContent)).toEqual([
      'Lead Faculty · reports to Bo Adams (Chair)',
      'Lead Faculty · reports to Cy Chen (Chair)',
    ]);
  });

  it('has its live region in the page before any refusal arrives', async () => {
    serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    const region = await screen.findByRole('status');
    await screen.findByTestId('pulse-admin-people-table');

    // Nothing has been refused, and the region is already there and empty.
    expect(region.textContent).toBe('');
    expect(screen.getAllByRole('status')).toHaveLength(1);
  });
});

/** Open the management panel for `name`. */
async function manage(name: string): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole('button', { name: `Manage ${name}` }));
  return screen.findByTestId('pulse-admin-person-panel');
}

describe('the person panel', () => {
  it('offers every Pulse-owned role, Care and Admin included, and no teaching role', async () => {
    serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');

    const role = within(panel).getByLabelText('Role');
    const offered = within(role)
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(offered).toEqual([
      'Lead Faculty',
      'Chair',
      'Assistant Dean',
      'Dean',
      'Vice President of Academics',
      'Care',
      'Admin',
    ]);
    expect(offered).not.toContain('Instructor');
  });

  it('offers the nodes the server answers for the role, namesakes told apart by their parent', async () => {
    const asked = serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');

    const select = await within(panel).findByLabelText<HTMLSelectElement>('Granted at');
    await within(select).findByRole('option', { name: 'Biology (Sciences)' });
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Choose where',
      'Biology (Sciences)',
      'Biology (Health)',
    ]);
    expect(asked.map((ask) => ask.path)).toContain('/admin/org-nodes?role=LEAD_FACULTY');

    fireEvent.change(within(panel).getByLabelText('Role'), { target: { value: 'CARE' } });
    await within(select).findByRole('option', { name: 'Pulse University' });
    expect(within(select).queryByRole('option', { name: /Biology/ })).toBeNull();
  });

  it('grants the chosen role at the chosen node and echoes the CSRF cookie', async () => {
    document.cookie = 'pulse_csrf=the-token';
    let granted = false;
    const asked = serving((ask) => {
      if (ask.method === 'POST' && ask.path === '/admin/people/p-adams/assignments') {
        granted = true;
        return json(201, { assignment_id: 'new-one' });
      }
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');

    fireEvent.change(within(panel).getByLabelText('Role'), { target: { value: 'CARE' } });
    const nodeSelect = await within(panel).findByLabelText<HTMLSelectElement>('Granted at');
    await within(nodeSelect).findByRole('option', { name: 'Pulse University' });
    fireEvent.change(nodeSelect, { target: { value: 'inst-1' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Grant role' }));

    await waitFor(() => {
      expect(granted).toBe(true);
    });
    const write = asked.find((ask) => ask.method === 'POST');
    expect(write?.body).toEqual({ role: 'CARE', scope_node_id: 'inst-1' });
    expect(write?.headers.get('X-Pulse-CSRF')).toBe('the-token');
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('Role granted.');
    });
  });

  it('says the server’s sentence for a refused grant in the live region that was already there', async () => {
    const SENTENCE = 'This role is granted at another level of the organization than the one chosen.';
    serving((ask) => {
      if (ask.method === 'POST') return json(409, { detail: SENTENCE });
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const region = await screen.findByRole('status');
    const panel = await manage('Bo Adams');
    const nodeSelect = await within(panel).findByLabelText<HTMLSelectElement>('Granted at');
    await within(nodeSelect).findByRole('option', { name: 'Biology (Sciences)' });
    fireEvent.change(nodeSelect, { target: { value: 'dept-a' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Grant role' }));

    await waitFor(() => {
      expect(region.textContent).toBe(SENTENCE);
    });
    // The very node that was in the page before the refusal, not a new one.
    expect(screen.getByRole('status')).toBe(region);
    // And beside the button that sent it, which names it.
    const note = describing(within(panel).getByRole('button', { name: 'Grant role' }));
    expect(note?.textContent).toBe(SENTENCE);
    expect(note).not.toBe(region);
  });

  it('clears a control’s refusal once a write from it lands', async () => {
    const SENTENCE = 'This role is granted at another level of the organization than the one chosen.';
    let grants = 0;
    serving((ask) => {
      if (ask.method === 'POST') {
        grants += 1;
        return grants === 1 ? json(409, { detail: SENTENCE }) : json(201, { assignment_id: 'new-one' });
      }
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');
    const nodeSelect = await within(panel).findByLabelText<HTMLSelectElement>('Granted at');
    await within(nodeSelect).findByRole('option', { name: 'Biology (Sciences)' });
    fireEvent.change(nodeSelect, { target: { value: 'dept-a' } });
    const grant = within(panel).getByRole('button', { name: 'Grant role' });
    fireEvent.click(grant);
    await waitFor(() => {
      expect(describing(grant)?.textContent).toBe(SENTENCE);
    });

    fireEvent.click(grant);
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('Role granted.');
    });
    expect(grant.hasAttribute('aria-describedby')).toBe(false);
    expect(within(panel).queryByText(SENTENCE)).toBeNull();
  });

  it('shows the server’s sentence for a revoke that has children, and removes nothing', async () => {
    const SENTENCE =
      'Assignments still reporting to this one: 2. Point each of them to another assignment before revoking this one.';
    const asked = serving((ask) => {
      if (ask.method === 'DELETE') return json(409, { detail: SENTENCE });
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');
    const readsBefore = asked.filter((ask) => ask.path.startsWith('/admin/people?')).length;

    fireEvent.click(within(panel).getByRole('button', { name: 'Revoke Chair' }));

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe(SENTENCE);
    });
    // The assignment is still listed, and the table was not read again as if it had changed.
    const revoke = within(panel).getByRole('button', { name: 'Revoke Chair' });
    expect(describing(revoke)?.textContent).toBe(SENTENCE);
    expect(asked.filter((ask) => ask.path.startsWith('/admin/people?'))).toHaveLength(readsBefore);
    expect(asked.filter((ask) => ask.method === 'DELETE').map((ask) => ask.path)).toEqual([
      `/admin/assignments/${ADAMS_ASSIGNMENT}`,
    ]);
  });

  it('revokes a childless assignment and reads the table again', async () => {
    let revoked = false;
    const asked = serving((ask) => {
      if (ask.method === 'DELETE') {
        revoked = true;
        return none();
      }
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');
    fireEvent.click(within(panel).getByRole('button', { name: 'Revoke Chair' }));

    await waitFor(() => {
      expect(revoked).toBe(true);
    });
    await waitFor(() => {
      expect(asked.filter((ask) => ask.path.startsWith('/admin/people?'))).toHaveLength(2);
    });
    expect(screen.getByRole('status').textContent).toBe('Role revoked.');
  });

  it('lists only the parents the server offers for the role, and sets the one chosen', async () => {
    const asked = serving((ask) => {
      if (ask.path === '/admin/reports-to-options?role=LEAD_FACULTY') {
        return json(200, {
          options: [
            { assignment_id: 'chair-1', person_id: 'p-adams', name: 'Bo Adams', role: 'CHAIR' },
            { assignment_id: 'dean-1', person_id: 'p-dean', name: 'Di Dean', role: 'DEAN' },
          ],
        });
      }
      if (ask.method === 'PUT') return none();
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Dr. Ana Zeller');

    const select = (
      await within(panel).findAllByLabelText('Reports to, for Lead Faculty')
    )[0] as HTMLSelectElement;
    await waitFor(() => {
      expect(select.disabled).toBe(false);
    });
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Nobody',
      'Bo Adams (Chair)',
      'Di Dean (Dean)',
    ]);

    fireEvent.change(select, { target: { value: 'dean-1' } });
    // Choosing writes nothing: the choice is sent by its own button (WCAG 3.2.2).
    expect(asked.some((ask) => ask.method === 'PUT')).toBe(false);
    fireEvent.click(
      within(panel).getAllByRole('button', { name: /^Save reporting line for Lead Faculty/ })[0] as HTMLElement,
    );
    await waitFor(() => {
      expect(
        asked.find((ask) => ask.method === 'PUT' && ask.path.endsWith('/reports-to'))?.body,
      ).toEqual({ reports_to: 'dean-1' });
    });
  });

  it('links a web login for a person without one, and unlinks one that has one', async () => {
    const asked = serving((ask) => {
      if (ask.method === 'PUT' || ask.method === 'DELETE') return none();
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);

    const panel = await manage('Bo Adams');
    expect(within(panel).queryByRole('button', { name: 'Unlink web login' })).toBeNull();
    fireEvent.change(within(panel).getByLabelText('Identity provider issuer'), {
      target: { value: 'https://idp.example' },
    });
    fireEvent.change(within(panel).getByLabelText('Identity provider subject'), {
      target: { value: 'sub-1' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Link web login' }));
    await waitFor(() => {
      expect(asked.find((ask) => ask.path === '/admin/people/p-adams/web-login')?.body).toEqual({
        idp_issuer: 'https://idp.example',
        idp_subject: 'sub-1',
      });
    });

    cleanup();
    const second = serving((ask) => {
      if (ask.method === 'DELETE') return none();
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const linked = await manage('Prof. Cy Zimmer');
    fireEvent.click(within(linked).getByRole('button', { name: 'Unlink web login' }));
    await waitFor(() => {
      expect(second.some((ask) => ask.method === 'DELETE')).toBe(true);
    });
  });

  it('adds a person from the form', async () => {
    const asked = serving((ask) => {
      if (ask.method === 'POST' && ask.path === '/admin/people') return json(201, { person_id: 'new' });
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');

    const form = screen.getByRole('heading', { name: 'Add a person' }).closest('section');
    fireEvent.change(within(form as HTMLElement).getByLabelText('Name'), {
      target: { value: 'Eve Ng' },
    });
    fireEvent.change(within(form as HTMLElement).getByLabelText('Category'), {
      target: { value: 'Staff' },
    });
    fireEvent.click(within(form as HTMLElement).getByRole('button', { name: 'Add person' }));

    await waitFor(() => {
      expect(asked.find((ask) => ask.method === 'POST')?.body).toEqual({
        name: 'Eve Ng',
        category: 'Staff',
      });
    });
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('Person added.');
    });
  });
});

describe('keyboard and screen-reader behaviour', () => {
  it('moves focus into the panel when it opens, and back to its Manage button when it closes', async () => {
    serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    const opener = await screen.findByRole('button', { name: 'Manage Bo Adams' });
    fireEvent.click(opener);
    const panel = await screen.findByTestId('pulse-admin-person-panel');

    expect(document.activeElement).toBe(within(panel).getByRole('heading', { name: 'Manage Bo Adams' }));
    fireEvent.click(within(panel).getByRole('button', { name: 'Close' }));
    expect(document.activeElement).toBe(opener);
  });

  it('says an identical outcome again: the same node is cleared and set for each announcement', async () => {
    const SENTENCE = 'Assignments still reporting to this one: 1. Point each of them to another assignment before revoking this one.';
    serving((ask) => {
      if (ask.method === 'DELETE') return json(409, { detail: SENTENCE });
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);
    const region = await screen.findByRole('status');
    const panel = await manage('Bo Adams');
    const revoke = within(panel).getByRole('button', { name: /^Revoke Chair/ });

    const seen: string[] = [];
    new MutationObserver(() => seen.push(region.textContent ?? '')).observe(region, {
      childList: true,
      characterData: true,
      subtree: true,
    });
    fireEvent.click(revoke);
    await waitFor(() => {
      expect(region.textContent).toBe(SENTENCE);
    });
    fireEvent.click(revoke);
    await waitFor(() => {
      expect(seen.filter((text) => text === SENTENCE)).toHaveLength(2);
    });
    // Between the two the region was emptied, which is what makes the second a change.
    expect(seen).toContain('');
    expect(screen.getByRole('status')).toBe(region);
  });

  it('puts focus on the roles heading after a revoke', async () => {
    serving((ask) => (ask.method === 'DELETE' ? none() : peopleReads()(ask)));
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');
    fireEvent.click(within(panel).getByRole('button', { name: /^Revoke Chair/ }));

    await waitFor(() => {
      expect(document.activeElement).toBe(within(panel).getByRole('heading', { name: 'Roles held' }));
    });
  });

  it('names where each assignment is held, in the row, the revoke button and the reports-to controls', async () => {
    const TWO_CHAIRS = person('p-two', 'Eve Ng', 'Faculty', [
      assignment('chair-bio', 'CHAIR', null),
      assignment('chair-chem', 'CHAIR', null),
    ]).assignments as ReturnType<typeof assignment>[];
    TWO_CHAIRS[0] = { ...TWO_CHAIRS[0], scope_node_id: 'dept-bio' } as never;
    TWO_CHAIRS[1] = { ...TWO_CHAIRS[1], scope_node_id: 'dept-chem' } as never;
    serving((ask) => {
      if (ask.path === '/admin/org-nodes?role=CHAIR') {
        return json(200, {
          nodes: [
            { node_id: 'dept-bio', label: 'Biology', parent_label: 'Sciences' },
            { node_id: 'dept-chem', label: 'Chemistry', parent_label: 'Sciences' },
          ],
        });
      }
      if (ask.method === 'GET' && ask.path.startsWith('/admin/people?')) {
        return json(200, peoplePage([person('p-two', 'Eve Ng', 'Faculty', TWO_CHAIRS)]));
      }
      return peopleReads()(ask);
    });
    mountAt(PEOPLE_PAGE);

    // The table row says where, so two Chair lines are not alike.
    const row = (await screen.findByRole('rowheader', { name: 'Eve Ng' })).closest('tr') as HTMLElement;
    await waitFor(() => {
      expect(within(row).getAllByRole('listitem').map((line) => line.textContent)).toEqual([
        'Chair at Biology (Sciences) · reports to nobody',
        'Chair at Chemistry (Sciences) · reports to nobody',
      ]);
    });

    fireEvent.click(within(row).getByRole('button', { name: 'Manage Eve Ng' }));
    const panel = await screen.findByTestId('pulse-admin-person-panel');
    expect(
      await within(panel).findByRole('button', { name: 'Revoke Chair at Biology (Sciences)' }),
    ).toBeTruthy();
    expect(within(panel).getByRole('button', { name: 'Revoke Chair at Chemistry (Sciences)' })).toBeTruthy();
    expect(within(panel).getByLabelText('Reports to, for Chair at Chemistry (Sciences)')).toBeTruthy();
  });

  it('announces the dry run’s counts, and puts focus on the import heading after cancelling', async () => {
    serving((ask) => {
      if (ask.path.startsWith('/admin/lead-mappings?')) return json(200, mappingRows([MAPPING]));
      if (ask.path === '/admin/lead-mappings/import/dry-run') return json(200, theDiff(THE_DIGEST));
      return undefined;
    });
    mountAt(MAPPINGS_PAGE);
    await screen.findByTestId('pulse-admin-mappings-table');
    await chooseFile(CSV);
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe(
        '1 added · 1 changed · 0 removed · 1 left without a lead',
      );
    });

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Import a CSV file' }));
  });
});

describe('what is said and where focus lands', () => {
  it('puts focus on the web-login heading after a successful link', async () => {
    serving((ask) => (ask.method === 'PUT' ? none() : peopleReads()(ask)));
    mountAt(PEOPLE_PAGE);
    const panel = await manage('Bo Adams');
    fireEvent.change(within(panel).getByLabelText('Identity provider issuer'), {
      target: { value: 'https://idp.example' },
    });
    fireEvent.change(within(panel).getByLabelText('Identity provider subject'), {
      target: { value: 'sub-1' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Link web login' }));

    await waitFor(() => {
      expect(document.activeElement).toBe(within(panel).getByRole('heading', { name: 'Web login' }));
    });
  });

  it('says the gate’s title aloud when the gate turns the page away', async () => {
    serving(() => json(403, { detail: 'not admin' }, NOT_YOUR_ROLE_HEADERS));
    mountAt(PEOPLE_PAGE);

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('This page is not part of your role');
    });
  });

  it('says the column and direction a sort now shows', async () => {
    serving(peopleReads());
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');

    fireEvent.click(within(screen.getByRole('columnheader', { name: /Name/ })).getByRole('button'));
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('Sorted by Name, descending');
    });
    fireEvent.click(within(screen.getByRole('columnheader', { name: /Category/ })).getByRole('button'));
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('Sorted by Category, ascending');
    });
  });
});

describe('a session that is not an admin, or not signed in', () => {
  it.each([
    ['the People table', PEOPLE_PAGE],
    ['the mapping table', MAPPINGS_PAGE],
  ])('turns %s away with the role sentence for the gate’s marked 403', async (_name, address) => {
    serving(() => json(403, { detail: 'not admin' }, NOT_YOUR_ROLE_HEADERS));
    mountAt(address);

    expect(await screen.findByText('This page is not part of your role')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText(/session/)).toBeNull();
  });

  it('says the session ended for a 401, not that the role is wrong', async () => {
    serving(() => json(401, { detail: 'no session' }));
    mountAt(PEOPLE_PAGE);

    expect(await screen.findByText('This page is not signed in')).toBeTruthy();
    expect(screen.queryByText('This page is not part of your role')).toBeNull();
  });

  it('does not call a 403 without the marking a wrong role', async () => {
    serving(() => json(403, { detail: 'Only somebody holding the Admin role may make this change.' }));
    mountAt(PEOPLE_PAGE);

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('could not be loaded');
    });
    expect(screen.queryByText('This page is not part of your role')).toBeNull();
  });
});

describe('the admin landing', () => {
  it('links to both editors by their addresses', async () => {
    serving(() => undefined);
    mountAt('/app/admin');

    const landing = await screen.findByTestId('pulse-landing-admin');
    const hrefs = within(landing)
      .getAllByRole('link')
      .map((link) => link.getAttribute('href'));
    expect(hrefs).toEqual([PEOPLE_PAGE, MAPPINGS_PAGE]);
  });
});

const MAPPING = {
  course_id: 'c-biol',
  course: 'BIOL 215',
  person_id: 'p-zeller',
  name: 'Dr. Ana Zeller',
};
const OTHER_MAPPING = { course_id: 'c-busa', course: 'BUSA 300', person_id: 'p-adams', name: 'Bo Adams' };

function mappingRows(rows: unknown[]) {
  return { total: rows.length, page: 1, page_size: 25, mappings: rows };
}

const THE_DIGEST = 'a'.repeat(64);
const THE_NEXT_DIGEST = 'b'.repeat(64);
const CSV = 'course,person\nBIOL 441,p-zeller\n';

function theDiff(digest: string) {
  return {
    digest,
    added: [{ ...MAPPING, course: 'BIOL 441', course_id: 'c-441' }],
    changed: [{ before: OTHER_MAPPING, after: { ...OTHER_MAPPING, name: 'Dr. Ana Zeller' } }],
    removed: [],
    unmapped: [
      {
        course_id: 'c-441b',
        course: 'BIOL 441',
        note: 'BIOL 441 is left without a lead and falls to its chair.',
      },
    ],
  };
}

async function chooseFile(csv: string): Promise<void> {
  const input = await screen.findByLabelText<HTMLInputElement>('CSV file');
  fireEvent.change(input, { target: { files: [new File([csv], 'mappings.csv', { type: 'text/csv' })] } });
}

function applyButton(): HTMLElement | null {
  return screen.queryByRole('button', { name: 'Apply these changes' });
}

describe('/admin/lead-mappings, the Lead Faculty mapping table and its import', () => {
  it('shows the mappings in the server’s order and asks for the other order from a header', async () => {
    const asked = serving((ask) => {
      if (ask.path === '/admin/lead-mappings?sort=course&order=asc&page=1') {
        return json(200, mappingRows([OTHER_MAPPING, MAPPING]));
      }
      if (ask.path === '/admin/lead-mappings?sort=name&order=asc&page=1') {
        return json(200, mappingRows([MAPPING, OTHER_MAPPING]));
      }
      return undefined;
    });
    mountAt(MAPPINGS_PAGE);

    const table = await screen.findByTestId('pulse-admin-mappings-table');
    expect(within(table).getAllByRole('rowheader').map((cell) => cell.textContent)).toEqual([
      'BUSA 300',
      'BIOL 215',
    ]);

    fireEvent.click(within(screen.getByRole('columnheader', { name: /Lead Faculty/ })).getByRole('button'));
    await waitFor(() => {
      expect(
        within(screen.getByTestId('pulse-admin-mappings-table'))
          .getAllByRole('rowheader')
          .map((cell) => cell.textContent),
      ).toEqual(['BIOL 215', 'BUSA 300']);
    });
    expect(asked.map((ask) => ask.path)).toContain('/admin/lead-mappings?sort=name&order=asc&page=1');
  });

  it('has no apply control before a dry run, and none after it is cancelled', async () => {
    const asked = serving((ask) => {
      if (ask.path.startsWith('/admin/lead-mappings?')) return json(200, mappingRows([MAPPING]));
      if (ask.path === '/admin/lead-mappings/import/dry-run') return json(200, theDiff(THE_DIGEST));
      return undefined;
    });
    mountAt(MAPPINGS_PAGE);
    await screen.findByTestId('pulse-admin-mappings-table');

    expect(applyButton()).toBeNull();
    await chooseFile(CSV);
    await screen.findByTestId('pulse-admin-import-diff');
    expect(applyButton()).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(applyButton()).toBeNull();
    expect(screen.queryByTestId('pulse-admin-import-diff')).toBeNull();
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe(
        'The import was cancelled and nothing was changed.',
      );
    });
    expect(asked.some((ask) => ask.path === '/admin/lead-mappings/import')).toBe(false);
  });

  it('reads the diff as tables, applies exactly the dry run’s file and digest, and reads the table again', async () => {
    let applied = false;
    const asked = serving((ask) => {
      if (ask.path.startsWith('/admin/lead-mappings?')) {
        return json(200, mappingRows(applied ? [MAPPING, OTHER_MAPPING] : [MAPPING]));
      }
      if (ask.path === '/admin/lead-mappings/import/dry-run') return json(200, theDiff(THE_DIGEST));
      if (ask.path === '/admin/lead-mappings/import') {
        applied = true;
        return json(200, theDiff(THE_DIGEST));
      }
      return undefined;
    });
    mountAt(MAPPINGS_PAGE);
    await screen.findByTestId('pulse-admin-mappings-table');

    await chooseFile(CSV);
    const diff = await screen.findByTestId('pulse-admin-import-diff');

    // The summary line, then the same facts as tables with captions and headers.
    expect(within(diff).getByText('1 added · 1 changed · 0 removed · 1 left without a lead')).toBeTruthy();
    for (const caption of ['Added', 'Changed', 'Left without a lead']) {
      expect(within(diff).getByRole('table', { name: caption })).toBeTruthy();
    }
    const unmapped = within(diff).getByRole('table', { name: 'Left without a lead' });
    expect(within(unmapped).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Course',
      'What happens',
    ]);
    expect(within(unmapped).getByText('BIOL 441 is left without a lead and falls to its chair.')).toBeTruthy();

    fireEvent.click(applyButton() as HTMLElement);

    await waitFor(() => {
      expect(within(screen.getByTestId('pulse-admin-mappings-table')).getByText('BUSA 300')).toBeTruthy();
    });
    const apply = asked.find((ask) => ask.path === '/admin/lead-mappings/import');
    expect(apply?.method).toBe('POST');
    expect(apply?.body).toEqual({ csv: CSV, digest: THE_DIGEST });
    expect(applyButton()).toBeNull();
    expect(screen.getByRole('status').textContent).toContain('The import was applied.');
  });

  it('shows the server’s sentence when the data changed, hides apply, and applies only a fresh dry run’s digest', async () => {
    const STALE =
      'The tables changed after this file’s dry run, so nothing was applied. Run the dry run again and review the new changes.';
    let dryRuns = 0;
    const asked = serving((ask) => {
      if (ask.path.startsWith('/admin/lead-mappings?')) return json(200, mappingRows([MAPPING]));
      if (ask.path === '/admin/lead-mappings/import/dry-run') {
        dryRuns += 1;
        return json(200, theDiff(dryRuns === 1 ? THE_DIGEST : THE_NEXT_DIGEST));
      }
      if (ask.path === '/admin/lead-mappings/import') {
        const digest = (ask.body as { digest: string }).digest;
        return digest === THE_NEXT_DIGEST ? json(200, theDiff(digest)) : json(409, { detail: STALE });
      }
      return undefined;
    });
    mountAt(MAPPINGS_PAGE);
    await screen.findByTestId('pulse-admin-mappings-table');

    await chooseFile(CSV);
    await screen.findByTestId('pulse-admin-import-diff');
    fireEvent.click(applyButton() as HTMLElement);

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe(STALE);
    });
    // The refusal took the apply control away; only a fresh dry run brings it back.
    // Its sentence is on the page itself, not only in the live region.
    expect(applyButton()).toBeNull();
    expect(within(screen.getByRole('main')).getAllByText(STALE).length).toBeGreaterThanOrEqual(2);
    const retry = screen.getByRole('button', { name: 'Check the file again' });
    expect(describing(retry)?.textContent).toBe(STALE);
    fireEvent.click(retry);
    await screen.findByTestId('pulse-admin-import-diff');
    expect(applyButton()).not.toBeNull();

    fireEvent.click(applyButton() as HTMLElement);
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('The import was applied.');
    });
    const applies = asked.filter((ask) => ask.path === '/admin/lead-mappings/import');
    expect(applies.map((ask) => (ask.body as { digest: string }).digest)).toEqual([
      THE_DIGEST,
      THE_NEXT_DIGEST,
    ]);
    // The fresh dry run was of the file already chosen: no second choosing.
    expect(
      asked.filter((ask) => ask.path === '/admin/lead-mappings/import/dry-run').map((ask) => ask.body),
    ).toEqual([{ csv: CSV }, { csv: CSV }]);
  });

  it('shows a refused dry run’s sentence and never offers to apply it', async () => {
    const LINE = 'Line 3 of the file cannot be imported, so nothing was changed. It names the same record as an earlier line.';
    serving((ask) => {
      if (ask.path.startsWith('/admin/lead-mappings?')) return json(200, mappingRows([MAPPING]));
      if (ask.path === '/admin/lead-mappings/import/dry-run') return json(422, { detail: LINE });
      return undefined;
    });
    mountAt(MAPPINGS_PAGE);
    await screen.findByTestId('pulse-admin-mappings-table');

    await chooseFile(CSV);
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe(LINE);
    });
    expect(applyButton()).toBeNull();
    expect(screen.queryByTestId('pulse-admin-import-diff')).toBeNull();
  });

  it('imports into the People table through its own addresses', async () => {
    const asked = serving((ask) => {
      if (ask.path.startsWith('/admin/people?')) return json(200, peoplePage(THE_PEOPLE));
      if (ask.path === '/admin/reports-to-options?role=LEAD_FACULTY') return json(200, { options: [] });
      if (ask.path === '/admin/people/import/dry-run') {
        return json(200, {
          digest: THE_DIGEST,
          added: [{ name: 'Eve Ng', category: 'Staff' }],
          changed: [
            {
              person_id: 'p-adams',
              before: { name: 'Bo Adams', category: 'Faculty' },
              after: { name: 'Bo Adams', category: 'Staff' },
            },
          ],
        });
      }
      if (ask.path === '/admin/people/import') return json(200, { digest: THE_DIGEST, added: [], changed: [] });
      return undefined;
    });
    mountAt(PEOPLE_PAGE);
    await screen.findByTestId('pulse-admin-people-table');
    expect(applyButton()).toBeNull();

    await chooseFile('name,category\nEve Ng,Staff\n');
    const diff = await screen.findByTestId('pulse-admin-import-diff');
    expect(within(diff).getByRole('table', { name: 'Added' })).toBeTruthy();
    expect(within(diff).getByRole('table', { name: 'Changed' })).toBeTruthy();
    fireEvent.click(applyButton() as HTMLElement);

    await waitFor(() => {
      expect(asked.some((ask) => ask.path === '/admin/people/import')).toBe(true);
    });
    expect(asked.find((ask) => ask.path === '/admin/people/import')?.body).toEqual({
      csv: 'name,category\nEve Ng,Staff\n',
      digest: THE_DIGEST,
    });
  });

  it('downloads the table’s CSV from the export address', async () => {
    const asked = serving((ask) => {
      if (ask.path.startsWith('/admin/lead-mappings?')) return json(200, mappingRows([MAPPING]));
      if (ask.path === '/admin/lead-mappings/export') {
        return new Response(CSV, { status: 200, headers: { 'Content-Type': 'text/csv' } });
      }
      return undefined;
    });
    const create = vi.fn(() => 'blob:the-file');
    const revoke = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    mountAt(MAPPINGS_PAGE);
    await screen.findByTestId('pulse-admin-mappings-table');

    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe('The file was downloaded.');
    });
    expect(asked.some((ask) => ask.path === '/admin/lead-mappings/export')).toBe(true);
    expect(create).toHaveBeenCalledTimes(1);
  });
});
