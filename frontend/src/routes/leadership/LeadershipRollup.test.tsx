import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { RouterProvider, createMemoryHistory, createRouter } from '@tanstack/react-router';

import {
  COMPARISON_SETS_PATH,
  LEADERSHIP_CONTEXT_PATH,
  rollupFiguresPath,
  rollupTreePath,
  setSeriesPath,
  type LeadershipContextView,
  type NamedSetSeriesView,
  type RollupFiguresView,
  type RollupNodeView,
  type RollupTreeView,
} from '../../api/leadership';
import type { ComparisonFigureView } from '../../api/instructor';
import { routeTree } from '../../router';
import { A_SET_SUMMARY } from './comparisonSetFixtures';

/**
 * The roll-up page (SPEC §5.5) over the application's own route tree: by-lead
 * mode only when the payload offers it, the server's order kept, the term
 * axis with one line per start cohort and its selector, and the named set's
 * line beside the node's with its withheld state.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TERM = 'term-fall';

const CONTEXT: LeadershipContextView = {
  roles: ['CHAIR'],
  terms: [
    {
      id: TERM,
      name: 'Fall 2026',
      start_date: '2026-08-17',
      end_date: '2026-12-19',
      length_weeks: 18,
    },
  ],
  current_term_id: TERM,
};

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

/**
 * Roots whose section counts fall (9, 5, 2) and whose names are in no
 * alphabetical order. The page must show them exactly as sent.
 */
const HIERARCHY: RollupNodeView[] = [
  node('prefix', 'pre-mars', 'MARS', '3 courses · 9 sections', 9, [
    node('course', 'crs-mars', 'MARS 2210', '9 sections', 9),
  ]),
  node('prefix', 'pre-biol', 'BIOL', '2 courses · 5 sections', 5),
  node('prefix', 'pre-chem', 'CHEM', '1 course · 2 sections', 2),
];

const BY_LEAD: RollupNodeView[] = [
  node('lead', 'lead-rivera', 'Dr. Rivera', '2 courses · 6 sections', 6),
  node('no_lead', 'dept-bio', 'No Lead Faculty: Biology', '1 course · 1 section', 1),
];

const A_LEADS_TREE: RollupTreeView = { term_id: TERM, hierarchy: HIERARCHY, by_lead: null };
const A_CHAIRS_TREE: RollupTreeView = { term_id: TERM, hierarchy: HIERARCHY, by_lead: BY_LEAD };

function week(termWeek: number, instructor: string, course: string) {
  return {
    course_week: termWeek,
    term_week: termWeek,
    instructor_mean: instructor,
    course_mean: course,
    workload_mean: '5.5',
    workload_median: '5.0',
  };
}

/**
 * Two cohorts, in the server's order by start date. U started in term week 1
 * and has three weeks; R started in term week 4 and has one. Their labels are
 * not alphabetical (U before R), so a page that sorted would swap the chips.
 */
const FIGURES: RollupFiguresView = {
  kind: 'prefix',
  id: 'pre-mars',
  term_id: TERM,
  cohorts: [
    {
      section_start_date: '2026-08-17',
      label: 'U sections · started 8/17',
      weeks: [week(1, '4.1', '3.9'), week(2, '3.8', '3.6'), week(3, '3.6', '3.4')],
      participation: { course_week: 3, response_rate: 0.62, validity_rate: 0.9 },
    },
    {
      section_start_date: '2026-09-07',
      label: 'R sections · started 9/7',
      weeks: [week(4, '3.2', '3.0')],
      participation: null,
    },
  ],
  attention: [],
  attention_empty: 'Nothing needs attention this week',
};

const SHOWN = (figure: number): ComparisonFigureView => ({
  suppressed: false,
  reason: null,
  figure,
});
const WITHHELD: ComparisonFigureView = { suppressed: true, reason: 'below-minimum', figure: null };

function setWeek(termWeek: number, mean: ComparisonFigureView) {
  return {
    course_week: termWeek,
    term_week: termWeek,
    instructor_mean: mean,
    course_mean: mean,
    workload_mean: mean,
    workload_median: mean,
  };
}

const A_SHOWN_SERIES: NamedSetSeriesView = {
  cohorts: [
    { section_start_date: '2026-08-17', weeks: [setWeek(1, SHOWN(3.7)), setWeek(2, SHOWN(3.5))] },
  ],
};

const A_WITHHELD_SERIES: NamedSetSeriesView = {
  cohorts: [
    { section_start_date: '2026-08-17', weeks: [setWeek(1, WITHHELD), setWeek(2, WITHHELD)] },
  ],
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function serving(answers: Record<string, () => Response>): string[] {
  const asked: string[] = [];
  vi.stubGlobal('fetch', (input: string) => {
    asked.push(input);
    const answer = answers[input];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
}

function aRollup(tree: RollupTreeView, series: NamedSetSeriesView = A_SHOWN_SERIES): string[] {
  return serving({
    [LEADERSHIP_CONTEXT_PATH]: () => json(200, CONTEXT),
    [rollupTreePath(TERM)]: () => json(200, tree),
    [rollupFiguresPath('prefix', 'pre-mars', TERM)]: () => json(200, FIGURES),
    [rollupFiguresPath('course', 'crs-mars', TERM)]: () =>
      json(200, { ...FIGURES, kind: 'course', id: 'crs-mars' }),
    [rollupFiguresPath('lead', 'lead-rivera', TERM)]: () => json(200, { ...FIGURES, kind: 'lead' }),
    [COMPARISON_SETS_PATH]: () => json(200, { sets: [A_SET_SUMMARY] }),
    [setSeriesPath(A_SET_SUMMARY.id, TERM)]: () => json(200, series),
  });
}

function mount(): void {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: ['/app/leadership'] }),
  });
  render(<RouterProvider router={router} />);
}

/** The visible names of the tree's rows, top to bottom. */
function treeNames(): (string | null)[] {
  return Array.from(document.querySelectorAll('.pulse-hierarchy-select .pulse-hierarchy-name')).map(
    (element) => element.textContent,
  );
}

/** The rows of one panel's ratings table, as their week labels. */
function tableWeeks(stream: string): string[] {
  const table = screen.getByRole('table', { name: `Weekly ratings: ${stream}` });
  return within(table)
    .getAllByRole('rowheader')
    .map((cell) => cell.textContent ?? '');
}

describe('/leadership, the roll-up', () => {
  it('offers a lead no by-lead control', async () => {
    aRollup(A_LEADS_TREE);
    mount();
    await screen.findByRole('heading', { level: 2, name: 'MARS' });
    expect(screen.queryByRole('button', { name: 'Lead faculty' })).toBeNull();
    expect(screen.queryByRole('group', { name: 'Group the tree by' })).toBeNull();
  });

  it('offers a chair the by-lead control, which switches the tree to the lead groups', async () => {
    aRollup(A_CHAIRS_TREE);
    mount();
    const byLead = await screen.findByRole('button', { name: 'Lead faculty' });
    expect(byLead.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(byLead);
    expect(byLead.getAttribute('aria-pressed')).toBe('true');
    expect(treeNames()).toEqual(['Dr. Rivera', 'No Lead Faculty: Biology']);
    await screen.findByRole('heading', { level: 2, name: 'Dr. Rivera' });
  });

  it('keeps the server’s order of the tree and of the cohorts, whatever their figures', async () => {
    aRollup(A_LEADS_TREE);
    mount();
    await screen.findByRole('heading', { level: 2, name: 'MARS' });
    expect(treeNames()).toEqual(['MARS', 'BIOL', 'CHEM']);
    const chips = within(await screen.findByRole('group', { name: 'Start cohort' }))
      .getAllByRole('button')
      .map((chip) => chip.textContent);
    expect(chips).toEqual(['U sections · started 8/17', 'R sections · started 9/7']);
  });

  it('plots the term axis, one start cohort at a time, switched by the cohort selector', async () => {
    aRollup(A_LEADS_TREE);
    mount();
    await screen.findByRole('group', { name: 'Start cohort' });
    expect(screen.getAllByRole('columnheader', { name: 'Term week' }).length).toBeGreaterThan(0);
    expect(tableWeeks('Instructor')).toEqual(['TERM 01', 'TERM 02', 'TERM 03']);
    // The axis is the term's 18 weeks, labelled from TERM 01.
    expect(screen.getAllByText('TERM 01').length).toBeGreaterThan(0);
    expect(document.querySelectorAll('.pulse-trend-tick').length).toBe(2 * 9);

    fireEvent.click(screen.getByRole('button', { name: 'R sections · started 9/7' }));
    expect(tableWeeks('Instructor')).toEqual(['TERM 04']);
    expect(
      screen.getByRole('button', { name: 'R sections · started 9/7' }).getAttribute('aria-pressed'),
    ).toBe('true');
  });

  it('draws a named set’s line beside the node’s, under the set’s own name', async () => {
    const asked = aRollup(A_LEADS_TREE);
    mount();
    const choice = await screen.findByRole('combobox', { name: 'Compare with a named set' });
    await screen.findByRole('option', { name: A_SET_SUMMARY.name });
    fireEvent.change(choice, { target: { value: A_SET_SUMMARY.id } });
    await waitFor(() => {
      expect(screen.getAllByTestId('trend-line-comparison').length).toBe(2);
    });
    expect(asked).toContain(setSeriesPath(A_SET_SUMMARY.id, TERM));
    expect(screen.getByTestId('trend-legend-comparison').textContent).toContain(A_SET_SUMMARY.name);
  });

  it('says the named set’s line is withheld when the payload withholds every week of it', async () => {
    aRollup(A_LEADS_TREE, A_WITHHELD_SERIES);
    mount();
    const choice = await screen.findByRole('combobox', { name: 'Compare with a named set' });
    await screen.findByRole('option', { name: A_SET_SUMMARY.name });
    fireEvent.change(choice, { target: { value: A_SET_SUMMARY.id } });
    const notices = await screen.findAllByText(
      `The ${A_SET_SUMMARY.name} line is withheld: too few sections or respondents in your purview stand behind it this term.`,
    );
    expect(notices.length).toBe(2);
    expect(screen.queryByTestId('trend-line-comparison')).toBeNull();
  });

  it('shows the participation rates without a count, and the calm attention line', async () => {
    aRollup(A_LEADS_TREE);
    mount();
    await screen.findByRole('group', { name: 'Start cohort' });
    expect(screen.getByRole('img', { name: 'Response rate: 62%.' })).toBeTruthy();
    expect(screen.getByRole('img', { name: 'Validity rate: 90%.' })).toBeTruthy();
    expect(screen.getByText('Nothing needs attention this week')).toBeTruthy();
  });

  it('says the session ended, under the landing’s own line, when the context is refused 401', async () => {
    serving({ [LEADERSHIP_CONTEXT_PATH]: () => json(401, { detail: 'No session.' }) });
    mount();
    await waitFor(() => {
      expect(screen.getAllByRole('status')[0]?.textContent).toBe(
        'The session this page was opened with has ended. Open Pulse Surveys again to read your roll-up.',
      );
    });
    expect(
      screen.getByText(
        'There is nothing to roll up yet. Sections you oversee appear here once they report.',
      ),
    ).toBeTruthy();
    expect(screen.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual([
      'Your roll-up',
    ]);
  });

  it('keeps focus on a pressed tree row and says what is shown; a breadcrumb moves it to the heading', async () => {
    aRollup(A_LEADS_TREE);
    mount();
    await screen.findByRole('heading', { level: 2, name: 'MARS' });
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    const row = screen.getByRole('button', { name: /^MARS 2210/ });
    row.focus();
    fireEvent.click(row);
    await screen.findByRole('heading', { level: 2, name: 'MARS 2210' });
    const pane = document.querySelector('.pulse-rollup-content-pane > [role="status"]');
    await waitFor(() => {
      expect(pane?.textContent).toBe('Showing MARS 2210');
    });
    expect(document.activeElement).toBe(row);

    const crumbs = screen.getByRole('navigation', { name: 'Where you are in the tree' });
    fireEvent.click(within(crumbs).getByRole('button', { name: 'MARS' }));
    await waitFor(() => {
      expect(document.activeElement?.textContent).toBe('MARS');
    });
    expect(document.activeElement?.tagName).toBe('H2');
  });

  it('keeps one figures status region mounted across choices, and announces the read in it', async () => {
    aRollup(A_LEADS_TREE);
    mount();
    await screen.findByRole('group', { name: 'Start cohort' });
    const pane = document.querySelector('.pulse-rollup-content-pane');
    const region = pane?.querySelector(':scope > [role="status"]');
    expect(region).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /^CHEM/ }));
    // CHEM's figures are not served, so the same region says so.
    await waitFor(() => {
      expect(region?.textContent).toBe(
        'The figures for this part of the tree could not be loaded just now. Choose it again to retry.',
      );
    });
    expect(pane?.querySelector(':scope > [role="status"]')).toBe(region);
  });
});
