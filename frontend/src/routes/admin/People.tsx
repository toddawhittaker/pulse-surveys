import { useEffect, useId, useRef, useState, type FormEvent, type JSX } from 'react';

import { GRANTABLE_ROLES, addPerson, readPeople, type PeoplePageView } from '../../api/admin';
import type { Order, PeopleSort } from '../../lib/adminTable';
import { copy, fillCopy } from '../../copy/adminPeople';
import { AdminPage, useGate, type Gate } from './AdminPage';
import { useAnnouncer } from './announcer';
import { useNodeLabels } from './nodeLabels';
import { ImportPanel } from './ImportPanel';
import { Field, PersonPanel, RefusalNote, roleLabel } from './PersonPanel';
import { describedBy, settle, useWriteRefusal } from './outcome';
import { Pager, SortHeader, nextOrder, sortedBy } from './tableParts';


/** Where a spec finds the page, and its table. */
export const PEOPLE_TESTID = 'pulse-admin-people';
export const PEOPLE_TABLE_TESTID = 'pulse-admin-people-table';

const HEADING_ID = 'pulse-admin-people-heading';
const CAPTION_ID = 'pulse-admin-people-caption';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error' }
  | { readonly kind: 'page'; readonly page: PeoplePageView };

/**
 * `/admin/people` — the People & reporting editor (SPEC §6.3).
 *
 * **The rows keep the server's order.** Names sort by last name with titles
 * stripped, and category by hierarchy rank; both are the server's, so nothing
 * here sorts, filters or groups what it was sent. A click on a header asks for
 * the other order and the page shows what comes back.
 */
export function PeopleRoute(): JSX.Element {
  const [sort, setSort] = useState<PeopleSort>('name');
  const [order, setOrder] = useState<Order>('asc');
  const [pageNumber, setPageNumber] = useState(1);
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [reloads, setReloads] = useState(0);
  const [announcement, announce] = useAnnouncer(copy('admin_people.page.loading'));
  const [gate, setGate] = useGate(announce);
  const [selected, setSelected] = useState<string | null>(null);
  const manageButtons = useRef(new Map<string, HTMLButtonElement>());
  const firstRead = useRef(true);
  const labels = useNodeLabels(announce, setGate);

  useEffect(() => {
    let live = true;
    void readPeople(sort, order, pageNumber).then((answer) => {
      if (!live) return;
      if (answer.kind === 'ok') {
        setLoad({ kind: 'page', page: answer.value });
        if (firstRead.current) {
          firstRead.current = false;
          announce('');
        }
      } else if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
        setGate(answer.kind);
      } else {
        setLoad({ kind: 'error' });
        announce(copy('admin_people.page.unavailable'));
      }
    });
    return () => {
      live = false;
    };
  }, [sort, order, pageNumber, reloads, announce, setGate]);

  const reload = (): void => setReloads((count) => count + 1);

  function sortBy(column: PeopleSort): void {
    const next = nextOrder(sort === column, order);
    setOrder(next);
    setSort(column);
    announce(sortedBy(column === 'name' ? 'admin_people.page.column_name' : 'admin_people.page.column_category', next));
    setPageNumber(1);
  }

  const people = load.kind === 'page' ? load.page.people : [];
  const chosen = people.find((person) => person.person_id === selected) ?? null;

  // The names of the places the page's assignments are held at.
  const heldRoles = [
    ...new Set(people.flatMap((person) => person.assignments.map((assignment) => assignment.role))),
  ].join();
  const { ensure } = labels;
  useEffect(() => {
    for (const role of heldRoles === '' ? [] : (heldRoles.split(',') as (typeof GRANTABLE_ROLES)[number][])) {
      ensure(role);
    }
  }, [ensure, heldRoles]);

  return (
    <AdminPage
      testid={PEOPLE_TESTID}
      headingId={HEADING_ID}
      heading={copy('admin_people.page.people_heading')}
      intro={copy('admin_people.page.people_intro')}
      announcement={announcement}
      gate={gate}
    >
      {load.kind === 'page' ? (
        <>
          <p className="pulse-admin-help">
            {fillCopy('admin_people.page.total_people', { total: String(load.page.total) })}
          </p>
          {people.length === 0 ? (
            <p className="pulse-admin-help">{copy('admin_people.page.people_empty')}</p>
          ) : (
            <div className="pulse-admin-scroll">
              <table className="pulse-admin-table" data-testid={PEOPLE_TABLE_TESTID}>
                <caption className="pulse-admin-caption" id={CAPTION_ID} tabIndex={-1}>
                  {copy('admin_people.page.people_table_label')}
                </caption>
                <thead>
                  <tr>
                    <SortHeader
                      label={copy('admin_people.page.column_name')}
                      active={sort === 'name'}
                      order={order}
                      onSort={() => sortBy('name')}
                    />
                    <SortHeader
                      label={copy('admin_people.page.column_category')}
                      active={sort === 'category'}
                      order={order}
                      onSort={() => sortBy('category')}
                    />
                    <th scope="col">{copy('admin_people.page.column_roles')}</th>
                    <th scope="col">{copy('admin_people.page.column_login')}</th>
                    <th scope="col">{copy('admin_people.page.column_actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {people.map((person) => (
                    <tr key={person.person_id}>
                      <th scope="row">{person.name}</th>
                      <td>{person.category}</td>
                      <td>
                        {person.assignments.length === 0 ? (
                          copy('admin_people.page.no_roles')
                        ) : (
                          <ul className="pulse-admin-assignments">
                            {person.assignments.map((assignment) => (
                              <li key={assignment.assignment_id}>
                                {assignment.scope_node_id === '' ||
                                labels.labelOf(assignment.scope_node_id) === null
                                  ? roleLabel(assignment.role)
                                  : fillCopy('admin_people.page.assignment_at', {
                                      role: roleLabel(assignment.role),
                                      place: labels.labelOf(assignment.scope_node_id) ?? '',
                                    })}
                                {' · '}
                                {assignment.reports_to_name === null ||
                                assignment.reports_to_role === null
                                  ? copy('admin_people.page.reports_to_nobody')
                                  : fillCopy('admin_people.page.reports_to', {
                                      name: assignment.reports_to_name,
                                      role: roleLabel(assignment.reports_to_role),
                                    })}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td>
                        {person.web_login_linked
                          ? copy('admin_people.page.login_linked')
                          : copy('admin_people.page.login_not_linked')}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="pulse-admin-button-plain"
                          ref={(button) => {
                            if (button === null) manageButtons.current.delete(person.person_id);
                            else manageButtons.current.set(person.person_id, button);
                          }}
                          onClick={() => setSelected(person.person_id)}
                        >
                          {fillCopy('admin_people.page.manage', { name: person.name })}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager
            page={load.page.page}
            pageSize={load.page.page_size}
            total={load.page.total}
            onPage={setPageNumber}
            announce={announce}
            captionId={CAPTION_ID}
          />
        </>
      ) : null}

      {chosen === null ? null : (
        <PersonPanel
          key={chosen.person_id}
          person={chosen}
          announce={announce}
          onGate={setGate}
          onChanged={reload}
          labels={labels}
          onClose={() => {
            // The Manage button that opened the panel is still in the table.
            manageButtons.current.get(chosen.person_id)?.focus();
            setSelected(null);
          }}
        />
      )}

      <AddPerson announce={announce} onGate={setGate} onAdded={reload} />
      <ImportPanel table="people" announce={announce} onGate={setGate} onApplied={reload} />
    </AdminPage>
  );
}

function AddPerson({
  announce,
  onGate,
  onAdded,
}: {
  readonly announce: (message: string) => void;
  readonly onGate: (gate: Exclude<Gate, null>) => void;
  readonly onAdded: () => void;
}): JSX.Element {
  const id = useId();
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const refusal = useWriteRefusal();

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    const answer = await addPerson(name, category);
    if (settle(answer, copy('admin_people.page.person_added'), announce, onGate, refusal)) {
      setName('');
      setCategory('');
      onAdded();
    }
  }

  return (
    <section className="pulse-admin-section" aria-labelledby={`${id}-heading`}>
      <h2 className="pulse-admin-subheading" id={`${id}-heading`}>
        {copy('admin_people.page.add_heading')}
      </h2>
      <form className="pulse-admin-form" onSubmit={(event) => void submit(event)}>
        <Field id={`${id}-name`} label={copy('admin_people.page.field_name')}>
          <input
            id={`${id}-name`}
            className="pulse-admin-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id={`${id}-category`} label={copy('admin_people.page.field_category')}>
          <input
            id={`${id}-category`}
            className="pulse-admin-input"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          />
        </Field>
        <button type="submit" className="pulse-admin-button" aria-describedby={describedBy(refusal)}>
          {copy('admin_people.page.add_submit')}
        </button>
        <RefusalNote refusal={refusal} />
      </form>
    </section>
  );
}
