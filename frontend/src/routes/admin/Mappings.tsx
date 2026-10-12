import { useEffect, useRef, useState, type JSX } from 'react';

import { readMappings, type MappingPageView } from '../../api/admin';
import type { MappingSort, Order } from '../../lib/adminTable';
import { copy, fillCopy } from '../../copy/adminPeople';
import { AdminPage, useGate } from './AdminPage';
import { useAnnouncer } from './announcer';
import { ImportPanel } from './ImportPanel';
import { Pager, SortHeader, nextOrder, sortedBy } from './tableParts';


/** Where a spec finds the page, and its table. */
export const MAPPINGS_TESTID = 'pulse-admin-mappings';
export const MAPPINGS_TABLE_TESTID = 'pulse-admin-mappings-table';

const HEADING_ID = 'pulse-admin-mappings-heading';
const CAPTION_ID = 'pulse-admin-mappings-caption';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error' }
  | { readonly kind: 'page'; readonly page: MappingPageView };

/**
 * `/admin/lead-mappings` — which person leads each course (SPEC §6.3).
 *
 * The rows are the server's, in the server's order; a course with no lead has
 * no row, and falls to its chair, which the intro says and the import's diff
 * names course by course.
 */
export function MappingsRoute(): JSX.Element {
  const [sort, setSort] = useState<MappingSort>('course');
  const [order, setOrder] = useState<Order>('asc');
  const [pageNumber, setPageNumber] = useState(1);
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [reloads, setReloads] = useState(0);
  const [announcement, announce] = useAnnouncer(copy('admin_people.page.loading'));
  const [gate, setGate] = useGate(announce);
  const firstRead = useRef(true);

  useEffect(() => {
    let live = true;
    void readMappings(sort, order, pageNumber).then((answer) => {
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

  function sortBy(column: MappingSort): void {
    const next = nextOrder(sort === column, order);
    setOrder(next);
    setSort(column);
    announce(sortedBy(column === 'course' ? 'admin_people.page.column_course' : 'admin_people.page.column_lead', next));
    setPageNumber(1);
  }

  return (
    <AdminPage
      testid={MAPPINGS_TESTID}
      headingId={HEADING_ID}
      heading={copy('admin_people.page.mappings_heading')}
      intro={copy('admin_people.page.mappings_intro')}
      announcement={announcement}
      gate={gate}
    >
      {load.kind === 'page' ? (
        <>
          <p className="pulse-admin-help">
            {fillCopy('admin_people.page.total_mappings', { total: String(load.page.total) })}
          </p>
          {load.page.mappings.length === 0 ? (
            <p className="pulse-admin-help">{copy('admin_people.page.mappings_empty')}</p>
          ) : (
            <div className="pulse-admin-scroll">
              <table className="pulse-admin-table" data-testid={MAPPINGS_TABLE_TESTID}>
                <caption className="pulse-admin-caption" id={CAPTION_ID} tabIndex={-1}>
                  {copy('admin_people.page.mappings_table_label')}
                </caption>
                <thead>
                  <tr>
                    <SortHeader
                      label={copy('admin_people.page.column_course')}
                      active={sort === 'course'}
                      order={order}
                      onSort={() => sortBy('course')}
                    />
                    <SortHeader
                      label={copy('admin_people.page.column_lead')}
                      active={sort === 'name'}
                      order={order}
                      onSort={() => sortBy('name')}
                    />
                  </tr>
                </thead>
                <tbody>
                  {load.page.mappings.map((line) => (
                    <tr key={line.course_id}>
                      <th scope="row">{line.course}</th>
                      <td>{line.name}</td>
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

      <ImportPanel
        table="mappings"
        announce={announce}
        onGate={setGate}
        onApplied={() => setReloads((count) => count + 1)}
      />
    </AdminPage>
  );
}
