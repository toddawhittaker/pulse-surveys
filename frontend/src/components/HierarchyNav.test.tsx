import type { ReactNode } from 'react';

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import type { RollupNodeView } from '../api/leadership';
import { HierarchyNav } from './HierarchyNav';

afterEach(cleanup);

function node(
  kind: RollupNodeView['kind'],
  id: string,
  name: string,
  label: string,
  sectionCount: number,
  children: RollupNodeView[] = [],
): RollupNodeView {
  return {
    kind,
    id,
    name,
    label,
    section_count: sectionCount,
    course_count: null,
    prefix_count: null,
    department_count: null,
    staff_name: null,
    instructor_names: [],
    children,
  };
}

const SECTION = node('section', 'sec-r3', 'R3WW', 'R3WW · Dr. M. Ellison', 1);
const COURSE = node('course', 'crs-2150', 'BIOL 2150', '1 section · Lead: Dr. Rivera', 1, [SECTION]);

/**
 * Three roots whose section counts fall (9, 5, 2) while their names are in no
 * alphabetical order: the order the server sent, which the tree keeps.
 */
const ROOTS: RollupNodeView[] = [
  node('prefix', 'pre-mars', 'MARS', '3 courses · 9 sections', 9),
  node('prefix', 'pre-biol', 'BIOL', '1 course · 5 sections', 5, [COURSE]),
  node('prefix', 'pre-chem', 'CHEM', '1 course · 2 sections', 2),
];

function link(section: RollupNodeView, children: ReactNode) {
  return <a href={`/app/leadership/sections/${section.id}`}>{children}</a>;
}

function renderTree(onSelect = vi.fn(), selectedId: string | null = null) {
  render(
    <HierarchyNav roots={ROOTS} selectedId={selectedId} onSelect={onSelect} sectionLink={link} />,
  );
  return onSelect;
}

describe('HierarchyNav', () => {
  it('is a labelled navigation that starts fully collapsed', () => {
    renderTree();
    const nav = screen.getByRole('navigation', { name: 'Your purview' });
    expect(within(nav).getByText('MARS')).toBeTruthy();
    // BIOL's course is beneath a closed disclosure.
    expect(screen.queryByText('BIOL 2150')).toBeNull();
    const toggle = screen.getByRole('button', { name: 'What BIOL holds' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('keeps the roots in the order the server sent, not by any figure', () => {
    renderTree();
    const names = Array.from(document.querySelectorAll('.pulse-hierarchy-select .pulse-hierarchy-name')).map(
      (element) => element.textContent,
    );
    expect(names).toEqual(['MARS', 'BIOL', 'CHEM']);
  });

  it('opens and closes one node, and expands and collapses all', () => {
    renderTree();
    const toggle = screen.getByRole('button', { name: 'What BIOL holds' });
    fireEvent.click(toggle);
    expect(screen.getByText('BIOL 2150')).toBeTruthy();
    // One name for the control; its state is aria-expanded's.
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    // The course is still closed: one press opens one level.
    expect(screen.queryByText('R3WW · Dr. M. Ellison')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    expect(screen.getByText('R3WW · Dr. M. Ellison')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }));
    expect(screen.queryByText('BIOL 2150')).toBeNull();
  });

  it('selects a node by its row, and marks the one shown', () => {
    const onSelect = renderTree(vi.fn(), 'pre-biol');
    const biol = screen.getByRole('button', { name: /^BIOL/ });
    expect(biol.getAttribute('aria-current')).toBe('true');
    expect(screen.getByRole('button', { name: /^MARS/ }).getAttribute('aria-current')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /^CHEM/ }));
    expect(onSelect).toHaveBeenCalledWith(ROOTS[2]);
  });

  it('draws a section row as the link it is given, never as a select button', () => {
    renderTree();
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    const section = screen.getByRole('link', { name: 'R3WW · Dr. M. Ellison' });
    expect(section.getAttribute('href')).toBe('/app/leadership/sections/sec-r3');
    expect(screen.queryByRole('button', { name: /R3WW/ })).toBeNull();
  });

  it('opens the way down to the node shown, so the shown row is in the document', () => {
    render(
      <HierarchyNav roots={ROOTS} selectedId="crs-2150" onSelect={vi.fn()} sectionLink={link} />,
    );
    expect(screen.getByRole('button', { name: /^BIOL 2150/ }).getAttribute('aria-current')).toBe(
      'true',
    );
    expect(screen.queryByText('R3WW · Dr. M. Ellison')).toBeNull();
  });
});
