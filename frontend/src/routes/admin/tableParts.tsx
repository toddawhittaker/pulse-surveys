import type { JSX } from 'react';

import type { Order } from '../../lib/adminTable';
import { copy, fillCopy } from '../../copy/adminPeople';

/**
 * A column header that sorts: a button inside a `th` that carries `aria-sort`,
 * so the sort is operable from the keyboard and announced as a property of the
 * column. The order itself is the server's; this only asks for it.
 */
export function SortHeader({
  label,
  active,
  order,
  onSort,
}: {
  readonly label: string;
  readonly active: boolean;
  readonly order: Order;
  readonly onSort: () => void;
}): JSX.Element {
  const ariaSort = active ? (order === 'asc' ? 'ascending' : 'descending') : 'none';
  return (
    <th scope="col" aria-sort={ariaSort}>
      <button
        type="button"
        className="pulse-admin-sort"
        aria-label={fillCopy('admin_people.page.sort_by', { column: label })}
        onClick={onSort}
      >
        {label}
        <span aria-hidden="true">{active ? (order === 'asc' ? ' ▲' : ' ▼') : ''}</span>
      </button>
    </th>
  );
}

/** Previous and next, and which page of how many. A page past the end is the server's empty one. */
export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  readonly page: number;
  readonly pageSize: number;
  readonly total: number;
  readonly onPage: (page: number) => void;
}): JSX.Element {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pulse-admin-pager" aria-label={copy('admin_people.page.pager_label')}>
      <button
        type="button"
        className="pulse-admin-button-plain"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        {copy('admin_people.page.previous_page')}
      </button>
      <span className="pulse-admin-pager-place">
        {fillCopy('admin_people.page.page_of', { page: String(page), pages: String(pages) })}
      </span>
      <button
        type="button"
        className="pulse-admin-button-plain"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        {copy('admin_people.page.next_page')}
      </button>
    </nav>
  );
}

/** The order a click on a column asks for: the other way on the column showing, ascending on a new one. */
export function nextOrder(sameColumn: boolean, order: Order): Order {
  return sameColumn && order === 'asc' ? 'desc' : 'asc';
}
