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
  A_GRADUATE_SET,
  A_NEW_SET,
  A_SET_THIS_READER_DEFINED,
  A_NOT_THE_DEFINER_REFUSAL,
  A_NURSING_COURSE,
  A_PREVIEW_WITHOUT_A_SECTION_COUNT,
  A_PREVIEW_WITH_A_NULL_SECTION_COUNT,
  A_PREVIEW_WITH_BOTH_COUNTS,
  A_SECOND_GRADUATE_COURSE,
  A_SET_SOMEBODY_ELSE_DEFINED,
  A_SET_SUMMARY,
  THE_OPTIONS,
  THREE_SETS,
} from './comparisonSetFixtures';
import { routeTree } from '../../router';
import { COMPARISON_SET_DELETE_CONFIRM_TESTID, COMPARISON_SET_LIST_TESTID } from './ComparisonSets';
import { COMPARISON_SET_FORM_TESTID, LEADERSHIP_SETS_TESTID } from './ComparisonSetForm';

/**
 * What `/leadership/comparison-sets` renders, state by state — ticket E5-09,
 * criteria 3 and 4.
 *
 * The page is mounted on the application's **own** route tree over a memory
 * history, the way `routes/instructor/instructorRoutes.test.tsx` does it: a
 * second route table written for a test is a map that can agree with the test
 * and disagree with the application. Every case serves the stack one answer per
 * address, so what the page renders is what an API answered rather than what a
 * prop said.
 *
 * Governed copy is transcribed rather than imported (`docs/MISTAKES.md` entry
 * 19). The API's own refusal sentences come from the fixtures, which stand in
 * for the server that writes them.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const HEADING = 'Comparison sets';
const LOADING = 'Opening your comparison sets…';
const UNAVAILABLE = 'These sets could not be loaded just now. Reload the page to try again.';
const SESSION_ENDED = 'This page is not signed in';
const EMPTY_TITLE = 'No sets yet';
const NO_REPORT_YET =
  'No report shows a named set yet. Sets defined here are ready for the reports that will use them.';
const READ_ONLY = 'Read only';
const EDIT = 'Edit';
const DELETE = 'Delete';
const DELETE_CONFIRM = 'Delete this set';
const KEEP_IT = 'Keep it';
const DEFINE = 'Define a set';
const SAVE = 'Save this set';
const COUNTING = 'Counting what this set reaches…';
const PREVIEW_UNAVAILABLE = 'What this set reaches could not be counted just now.';
const SET_SAVED = 'Set saved.';
const SET_DELETED = 'Set deleted.';
const FORM_HEADING = 'Define a comparison set';
const CANCEL = 'Cancel';

/**
 * The one element a graphic may sit inside on this surface: `StateNotice`'s
 * root, which carries the design's pulse-line motif. Transcribed rather than
 * imported for the reason the copy is (`docs/MISTAKES.md` entry 19) — and if the
 * component renames it, this sweep reddens, which is the right way round: the
 * rule is that drawings live in exactly one place, and a rename is a change to
 * where that place is.
 */
const STATE_NOTICE_CLASS = 'pulse-state-notice';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A 204, which is what the delete route answers and which carries no body. */
function noContent(): Response {
  return new Response(null, { status: 204 });
}

interface Ask {
  readonly path: string;
  readonly method: string;
  readonly body: string | null;
  readonly headers: Headers;
}

/**
 * Serve the stack, one answer per address, and remember what was asked.
 *
 * An answer may be keyed by the address alone or by `METHOD address`, which is
 * what the two writes need: a create posts to the same address the list is read
 * from, and answering it with the list would be this harness agreeing with a
 * client that read the wrong body.
 */
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

/** The whole application, mounted at one address on a memory history. */
function mountAt(address: string) {
  const router = createRouter({
    routeTree,
    basepath: '/app',
    history: createMemoryHistory({ initialEntries: [address] }),
  });
  render(<RouterProvider router={router} />);
  return router;
}

/** The three sets, their choice lists, and one preview each. */
function servingThreeSets(): Ask[] {
  return serving({
    [COMPARISON_SETS_PATH]: () => json(200, { sets: THREE_SETS }),
    [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
    [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
      json(200, A_PREVIEW_WITH_BOTH_COUNTS),
    [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
      json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
    [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
  });
}

/** The row one set is listed in. */
function rowOf(name: string): HTMLElement {
  const row = screen
    .getAllByRole('listitem')
    .find((item) => within(item).queryByRole('heading', { name }) !== null);
  if (row === undefined) throw new Error(`No row is listed for ${name}.`);
  return row;
}

describe('the states the list can be in', () => {
  it('says it is opening while the read is on its way', async () => {
    vi.stubGlobal('fetch', () => new Promise<Response>(() => undefined));
    mountAt('/app/leadership/comparison-sets');

    // Found by its words, then asked its role: the page carries a second,
    // empty status line from its first render (the one a landed write is said
    // in), so "the status region" is no longer one element.
    expect((await screen.findByText(LOADING)).getAttribute('role')).toBe('status');
    expect(screen.queryByTestId(COMPARISON_SET_LIST_TESTID)).toBeNull();
  });

  it('says so calmly when no set has been defined yet', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: [] }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText(EMPTY_TITLE);
    expect(screen.queryByTestId(COMPARISON_SET_LIST_TESTID)).toBeNull();
    // An empty list is still a page somebody can define a set from.
    expect(screen.getByRole('button', { name: DEFINE })).toBeTruthy();
  });

  it('shows the API’s own sentence when the list was refused', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(403, { detail: A_NOT_THE_DEFINER_REFUSAL }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText(A_NOT_THE_DEFINER_REFUSAL);
    // Never the empty state: a read that failed is a different fact from a
    // reader who has defined nothing.
    expect(screen.queryByText(EMPTY_TITLE)).toBeNull();
  });

  it('falls back to its own words when a failed read carried no sentence', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(500, {}),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText(UNAVAILABLE);
  });

  it('says which door to use again when the session has ended', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(401, { detail: 'Not authenticated' }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(401, { detail: 'Not authenticated' }),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText(SESSION_ENDED);
    expect(screen.queryByTestId(COMPARISON_SET_LIST_TESTID)).toBeNull();
    expect(screen.queryByText(EMPTY_TITLE)).toBeNull();
  });
});

describe('the list of sets', () => {
  it('lists every set the API answered, in the order it answered them', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    const names = screen
      .getAllByRole('listitem')
      .map((item) => within(item).getByRole('heading').textContent);
    expect(names).toEqual([
      A_SET_SOMEBODY_ELSE_DEFINED.name,
      A_SET_SUMMARY.name,
      A_GRADUATE_SET.name,
    ]);
  });

  it('states each set’s declared length and level', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    // Three different lengths and three different levels, so a row rendering
    // its neighbour's facts prints a different line rather than the same one.
    expect(within(rowOf(A_SET_SUMMARY.name)).getByText('12 weeks · level UG')).toBeTruthy();
    expect(within(rowOf(A_GRADUATE_SET.name)).getByText('8 weeks · level GR')).toBeTruthy();
    expect(
      within(rowOf(A_SET_SOMEBODY_ELSE_DEFINED.name)).getByText('18 weeks · level DR'),
    ).toBeTruthy();
  });

  it('renders both preview counts when the preview answered both', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    // 3 and 11 are the preview's own numbers and neither is the summary's
    // `member_count` of 5, so a line built from the list rather than from the
    // preview reads differently.
    await within(rowOf(A_SET_SOMEBODY_ELSE_DEFINED.name)).findByText(
      '3 courses, 11 sections across retained terms',
    );
  });

  it('says the section count is missing rather than printing a zero', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    await within(rowOf(A_SET_SUMMARY.name)).findByText(
      '7 courses. The number of sections this set reaches is not available just now.',
    );
  });

  it('reads a section count of null the same way as an absent one', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: [A_SET_SUMMARY] }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, A_PREVIEW_WITH_A_NULL_SECTION_COUNT),
    });
    mountAt('/app/leadership/comparison-sets');

    // A guard written as `=== undefined` prints "null sections" here.
    await screen.findByText(
      '9 courses. The number of sections this set reaches is not available just now.',
    );
  });

  it('counts one course and one section in the singular', async () => {
    // The E5 boundary round's copy finding: the preview printed "1 courses".
    // Both nouns are counted, so both are driven to exactly one here.
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: [A_SET_SUMMARY] }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, { ...A_PREVIEW_WITH_BOTH_COUNTS, member_count: 1, section_count: 1 }),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText('1 course, 1 section across retained terms');
  });

  it('counts one course in the singular when the section count is missing', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: [A_SET_SUMMARY] }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, { ...A_PREVIEW_WITH_A_NULL_SECTION_COUNT, member_count: 1 }),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText(
      '1 course. The number of sections this set reaches is not available just now.',
    );
  });

  it('says when a preview could not be read at all', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    await within(rowOf(A_GRADUATE_SET.name)).findByText(PREVIEW_UNAVAILABLE);
  });

  it('says it is counting until a preview arrives', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: [A_SET_SUMMARY] }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () => {
        // A preview whose read never lands: the row stays on "counting", which
        // is what it says before any answer arrives.
        return new Promise<Response>(() => undefined) as unknown as Response;
      },
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    expect(within(rowOf(A_SET_SUMMARY.name)).getByText(COUNTING)).toBeTruthy();
  });

  it('offers edit and delete only for a set the API says is editable', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    const mine = within(rowOf(A_SET_SUMMARY.name));
    expect(mine.getByRole('link', { name: EDIT }).getAttribute('href')).toBe(
      `/app/leadership/comparison-sets/${A_SET_SUMMARY.id}`,
    );
    expect(mine.getByRole('button', { name: DELETE })).toBeTruthy();

    // `editable: false` shows neither control, and says why the row has none.
    const theirs = within(rowOf(A_SET_SOMEBODY_ELSE_DEFINED.name));
    expect(theirs.queryByRole('link')).toBeNull();
    expect(theirs.queryByRole('button')).toBeNull();
    expect(theirs.getByText(READ_ONLY)).toBeTruthy();
  });
});

describe('deleting a set', () => {
  it('asks first, naming the set and what will change', async () => {
    const asked = servingThreeSets();
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));

    const confirm = screen.getByTestId(COMPARISON_SET_DELETE_CONFIRM_TESTID);
    expect(within(confirm).getByText(`Delete “${A_SET_SUMMARY.name}”?`)).toBeTruthy();
    expect(
      within(confirm).getByText(
        'This removes the set for everyone who can read it. The courses in it are not changed, and nothing else about them is affected.',
      ),
    ).toBeTruthy();

    // Nothing has been deleted by asking.
    expect(asked.some((ask) => ask.method === 'DELETE')).toBe(false);
  });

  it('deletes nothing when the confirmation is declined', async () => {
    const asked = servingThreeSets();
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    fireEvent.click(screen.getByRole('button', { name: KEEP_IT }));

    expect(screen.queryByTestId(COMPARISON_SET_DELETE_CONFIRM_TESTID)).toBeNull();
    expect(asked.some((ask) => ask.method === 'DELETE')).toBe(false);
    expect(rowOf(A_SET_SUMMARY.name)).toBeTruthy();
  });

  it('deletes the set the confirmation named, and reads the list again', async () => {
    let deleted = false;
    const asked = serving({
      [COMPARISON_SETS_PATH]: () =>
        json(200, { sets: deleted ? [A_SET_SOMEBODY_ELSE_DEFINED] : THREE_SETS }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPath(A_SET_SUMMARY.id)]: () => {
        deleted = true;
        return noContent();
      },
      [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
        json(200, A_PREVIEW_WITH_BOTH_COUNTS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    fireEvent.click(screen.getByRole('button', { name: DELETE_CONFIRM }));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: A_SET_SUMMARY.name })).toBeNull();
    });

    const writes = asked.filter((ask) => ask.method === 'DELETE');
    expect(writes.map((ask) => ask.path)).toEqual([comparisonSetPath(A_SET_SUMMARY.id)]);
    // The list was read again afterwards rather than edited in the browser.
    expect(asked.filter((ask) => ask.path === COMPARISON_SETS_PATH)).toHaveLength(2);
  });

  it('shows the API’s sentence when the delete was refused', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: THREE_SETS }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPath(A_SET_SUMMARY.id)]: () =>
        json(403, { detail: A_NOT_THE_DEFINER_REFUSAL }),
      [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
        json(200, A_PREVIEW_WITH_BOTH_COUNTS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    fireEvent.click(screen.getByRole('button', { name: DELETE_CONFIRM }));

    await screen.findByText(A_NOT_THE_DEFINER_REFUSAL);
    // The set is still listed, because it is still there.
    expect(rowOf(A_SET_SUMMARY.name)).toBeTruthy();
  });
});

describe('defining a set from the list', () => {
  it('opens the form, sends what was composed, and reads the list again', async () => {
    let created = false;
    const asked = serving({
      [`GET ${COMPARISON_SETS_PATH}`]: () =>
        json(200, { sets: created ? [A_GRADUATE_SET] : [] }),
      [`POST ${COMPARISON_SETS_PATH}`]: () => {
        created = true;
        return json(201, A_NEW_SET);
      },
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(200, A_PREVIEW_WITH_BOTH_COUNTS),
    });
    mountAt('/app/leadership/comparison-sets');

    await screen.findByText(EMPTY_TITLE);
    fireEvent.click(screen.getByRole('button', { name: DEFINE }));

    const form = screen.getByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.change(within(form).getByLabelText('Set name'), {
      target: { value: A_NEW_SET.name },
    });
    fireEvent.change(within(form).getByLabelText('Course length'), { target: { value: '8' } });
    fireEvent.change(within(form).getByLabelText('Course level'), { target: { value: 'GR' } });
    fireEvent.click(within(form).getByLabelText(A_NURSING_COURSE.label));
    fireEvent.click(within(form).getByLabelText(A_SECOND_GRADUATE_COURSE.label));

    // The answer to the create is the set itself, and the list read that
    // follows it carries the set the server now holds.
    fireEvent.click(within(form).getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(screen.queryByTestId(COMPARISON_SET_FORM_TESTID)).toBeNull();
    });

    const posts = asked.filter((ask) => ask.method === 'POST');
    expect(posts.map((ask) => ask.path)).toEqual([COMPARISON_SETS_PATH]);
    expect(JSON.parse(posts[0]?.body ?? 'null')).toEqual({
      name: A_NEW_SET.name,
      length_weeks: 8,
      level: 'GR',
      member_course_ids: [A_NURSING_COURSE.id, A_SECOND_GRADUATE_COURSE.id],
    });
    await screen.findByRole('heading', { name: A_GRADUATE_SET.name });
  });
});

/**
 * Where focus goes when a control vanishes, and the one status line a landed
 * write is said in — the E5 boundary round's accessibility findings.
 *
 * Each case reads `document.activeElement` after the move, because what a
 * keyboard or screen-reader user meets next is exactly where focus landed. The
 * mutation each kills is the focus call (or the status sentence) removed; the
 * near miss is focus left on `document.body`, which is where a vanished
 * control drops it.
 */
describe('focus and status when controls come and go', () => {
  it('starts with an empty status line, so what arrives in it is announced', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    const lines = screen.getAllByRole('status');
    expect(lines).toHaveLength(1);
    expect(lines[0]?.textContent).toBe('');
  });

  it('moves focus into the confirmation when delete is asked, and back when the set is kept', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    const confirm = screen.getByTestId(COMPARISON_SET_DELETE_CONFIRM_TESTID);
    await waitFor(() => {
      expect(document.activeElement).toBe(confirm);
    });
    // Focus lands on a group named by its own question, so that is what is read.
    expect(screen.getByRole('group', { name: `Delete “${A_SET_SUMMARY.name}”?` })).toBe(confirm);

    fireEvent.click(screen.getByRole('button', { name: KEEP_IT }));
    await waitFor(() => {
      expect(document.activeElement).toBe(
        within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }),
      );
    });
  });

  it('says the set was deleted and puts focus on the page heading', async () => {
    let deleted = false;
    serving({
      [COMPARISON_SETS_PATH]: () =>
        json(200, { sets: deleted ? [A_SET_SOMEBODY_ELSE_DEFINED] : THREE_SETS }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPath(A_SET_SUMMARY.id)]: () => {
        deleted = true;
        return noContent();
      },
      [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
        json(200, A_PREVIEW_WITH_BOTH_COUNTS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
    });
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    fireEvent.click(screen.getByRole('button', { name: DELETE_CONFIRM }));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: A_SET_SUMMARY.name })).toBeNull();
    });
    expect(screen.getByRole('status').textContent).toBe(SET_DELETED);
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: HEADING }));
  });

  it('puts focus back on the delete button when the delete is refused', async () => {
    serving({
      [COMPARISON_SETS_PATH]: () => json(200, { sets: THREE_SETS }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPath(A_SET_SUMMARY.id)]: () =>
        json(403, { detail: A_NOT_THE_DEFINER_REFUSAL }),
      [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
        json(200, A_PREVIEW_WITH_BOTH_COUNTS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
    });
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    fireEvent.click(screen.getByRole('button', { name: DELETE_CONFIRM }));

    await screen.findByText(A_NOT_THE_DEFINER_REFUSAL);
    await waitFor(() => {
      expect(document.activeElement).toBe(
        within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }),
      );
    });
    // Nothing landed, so the status line says nothing.
    expect(screen.getByRole('status').textContent).toBe('');
  });

  it('moves focus to the form when it opens, and back to "Define a set" when it is cancelled', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    fireEvent.click(screen.getByRole('button', { name: DEFINE }));
    await waitFor(() => {
      expect(document.activeElement).toBe(
        screen.getByRole('heading', { level: 2, name: FORM_HEADING }),
      );
    });

    fireEvent.click(screen.getByRole('button', { name: CANCEL }));
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole('button', { name: DEFINE }));
    });
  });

  it('says the set was saved and puts focus back on "Define a set"', async () => {
    let created = false;
    serving({
      [`GET ${COMPARISON_SETS_PATH}`]: () =>
        json(200, { sets: created ? [A_GRADUATE_SET] : [] }),
      [`POST ${COMPARISON_SETS_PATH}`]: () => {
        created = true;
        return json(201, A_NEW_SET);
      },
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(200, A_PREVIEW_WITH_BOTH_COUNTS),
    });
    mountAt('/app/leadership/comparison-sets');
    await screen.findByText(EMPTY_TITLE);

    fireEvent.click(screen.getByRole('button', { name: DEFINE }));
    const form = screen.getByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.change(within(form).getByLabelText('Set name'), {
      target: { value: A_NEW_SET.name },
    });
    fireEvent.change(within(form).getByLabelText('Course length'), { target: { value: '8' } });
    fireEvent.change(within(form).getByLabelText('Course level'), { target: { value: 'GR' } });
    fireEvent.click(within(form).getByRole('button', { name: SAVE }));

    await screen.findByRole('heading', { name: A_GRADUATE_SET.name });
    expect(screen.getByRole('status').textContent).toBe(SET_SAVED);
    expect(document.activeElement).toBe(screen.getByRole('button', { name: DEFINE }));

    // Opening the form again starts a new write, so the line stops describing
    // the last one. The form brings a status region of its own (its removal
    // notice), so the page's line is the one outside the form.
    fireEvent.click(screen.getByRole('button', { name: DEFINE }));
    const pageLine = screen.getAllByRole('status').find((line) => line.closest('form') === null);
    expect(pageLine?.textContent).toBe('');
  });
});

describe('a status line that never outlives its write', () => {
  // The verifier's survivor FE09a: nothing failed when opening a delete
  // confirmation stopped clearing the line. A delete asked is a new write in
  // hand, so the sentence about the last one goes.
  it('clears "Set saved." when a delete confirmation opens', async () => {
    let created = false;
    serving({
      [`GET ${COMPARISON_SETS_PATH}`]: () =>
        json(200, { sets: created ? [A_SET_SUMMARY] : [] }),
      [`POST ${COMPARISON_SETS_PATH}`]: () => {
        created = true;
        return json(201, A_NEW_SET);
      },
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () => json(200, A_PREVIEW_WITH_BOTH_COUNTS),
    });
    mountAt('/app/leadership/comparison-sets');
    await screen.findByText(EMPTY_TITLE);

    fireEvent.click(screen.getByRole('button', { name: DEFINE }));
    const form = screen.getByTestId(COMPARISON_SET_FORM_TESTID);
    fireEvent.change(within(form).getByLabelText('Set name'), {
      target: { value: A_NEW_SET.name },
    });
    fireEvent.change(within(form).getByLabelText('Course length'), { target: { value: '8' } });
    fireEvent.change(within(form).getByLabelText('Course level'), { target: { value: 'GR' } });
    fireEvent.click(within(form).getByRole('button', { name: SAVE }));
    await screen.findByRole('heading', { name: A_SET_SUMMARY.name });
    expect(screen.getByRole('status').textContent).toBe(SET_SAVED);

    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    expect(screen.getByTestId(COMPARISON_SET_DELETE_CONFIRM_TESTID)).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe('');
  });

  it('clears "Set deleted." when the next delete confirmation opens', async () => {
    let deleted = false;
    serving({
      [COMPARISON_SETS_PATH]: () =>
        json(200, { sets: deleted ? [A_GRADUATE_SET] : THREE_SETS }),
      [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
      [comparisonSetPath(A_SET_SUMMARY.id)]: () => {
        deleted = true;
        return noContent();
      },
      [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
        json(200, A_PREVIEW_WITH_BOTH_COUNTS),
      [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
        json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
      [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
    });
    mountAt('/app/leadership/comparison-sets');
    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);

    fireEvent.click(within(rowOf(A_SET_SUMMARY.name)).getByRole('button', { name: DELETE }));
    fireEvent.click(screen.getByRole('button', { name: DELETE_CONFIRM }));
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: A_SET_SUMMARY.name })).toBeNull();
    });
    expect(screen.getByRole('status').textContent).toBe(SET_DELETED);

    fireEvent.click(within(rowOf(A_GRADUATE_SET.name)).getByRole('button', { name: DELETE }));
    expect(screen.getByTestId(COMPARISON_SET_DELETE_CONFIRM_TESTID)).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe('');
  });
});

describe('what this surface never renders', () => {
  it('says out loud that no report shows a named set yet', async () => {
    servingThreeSets();
    mountAt('/app/leadership/comparison-sets');

    await screen.findByTestId(COMPARISON_SET_LIST_TESTID);
    expect(screen.getByText(NO_REPORT_YET)).toBeTruthy();
  });

  it('renders no figure of any kind, in any state this surface has', async () => {
    // **Every state, not the one that happens to be easiest to reach.** A sweep
    // over the loaded list says nothing about the form, the empty state or the
    // three refused ones, and a figure would be just as wrong in any of them.
    // Each case below carries its own positive control, asserted in the same
    // pass as the sweep, so a case that rendered nothing at all — a mount that
    // failed, an address that resolved elsewhere — reds here rather than
    // reporting a clean page (`docs/MISTAKES.md` entry 3).
    const states: {
      readonly state: string;
      readonly address: string;
      readonly answers: Record<string, () => Response>;
      readonly control: string;
      readonly open?: () => void;
    }[] = [
      {
        state: 'the list, with its previews in',
        address: '/app/leadership/comparison-sets',
        answers: {
          [COMPARISON_SETS_PATH]: () => json(200, { sets: THREE_SETS }),
          [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
          [comparisonSetPreviewPath(A_SET_SOMEBODY_ELSE_DEFINED.id)]: () =>
            json(200, A_PREVIEW_WITH_BOTH_COUNTS),
          [comparisonSetPreviewPath(A_SET_SUMMARY.id)]: () =>
            json(200, A_PREVIEW_WITHOUT_A_SECTION_COUNT),
          [comparisonSetPreviewPath(A_GRADUATE_SET.id)]: () => json(500, {}),
        },
        control: '3 courses, 11 sections across retained terms',
      },
      {
        // A read that has not landed: the fetch never settles, so the page is
        // in the state it opens in rather than one an answer put it in.
        state: 'the read still on its way',
        address: '/app/leadership/comparison-sets',
        answers: {},
        control: LOADING,
      },
      {
        state: 'the empty state',
        address: '/app/leadership/comparison-sets',
        answers: {
          [COMPARISON_SETS_PATH]: () => json(200, { sets: [] }),
          [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
        },
        control: EMPTY_TITLE,
      },
      {
        state: 'the refused read',
        address: '/app/leadership/comparison-sets',
        answers: {
          [COMPARISON_SETS_PATH]: () => json(403, { detail: A_NOT_THE_DEFINER_REFUSAL }),
          [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
        },
        control: A_NOT_THE_DEFINER_REFUSAL,
      },
      {
        state: 'the ended session',
        address: '/app/leadership/comparison-sets',
        answers: {
          [COMPARISON_SETS_PATH]: () => json(401, { detail: 'Not authenticated' }),
          [COMPARISON_SET_OPTIONS_PATH]: () => json(401, { detail: 'Not authenticated' }),
        },
        control: SESSION_ENDED,
      },
      {
        state: 'the create form, open on the list',
        address: '/app/leadership/comparison-sets',
        answers: {
          [COMPARISON_SETS_PATH]: () => json(200, { sets: [] }),
          [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
        },
        control: 'Define a comparison set',
        open: () => {
          fireEvent.click(screen.getByRole('button', { name: DEFINE }));
        },
      },
      {
        state: 'the edit form, at a set’s own address',
        address: `/app/leadership/comparison-sets/${A_SET_THIS_READER_DEFINED.id}`,
        answers: {
          [COMPARISON_SET_OPTIONS_PATH]: () => json(200, THE_OPTIONS),
          [comparisonSetPath(A_SET_THIS_READER_DEFINED.id)]: () =>
            json(200, A_SET_THIS_READER_DEFINED),
        },
        control: 'Edit this comparison set',
      },
    ];

    for (const { state, address, answers, control, open } of states) {
      // An empty answer table is the never-answering stack the loading state
      // needs; anything else is served address by address.
      if (Object.keys(answers).length === 0) {
        vi.stubGlobal('fetch', () => new Promise<Response>(() => undefined));
      } else {
        serving(answers);
      }
      mountAt(address);
      if (open === undefined) {
        await screen.findByText(control);
      } else {
        await screen.findByText(EMPTY_TITLE);
        open();
        await screen.findByText(control);
      }

      const page = screen.getByTestId(LEADERSHIP_SETS_TESTID);
      const words = page.textContent ?? '';

      // The control: this state rendered, and it rendered the thing that names
      // it. Everything below is an absence, and an absence over a blank page is
      // satisfied perfectly by a page that never arrived.
      expect(words, state).toContain(HEADING);
      expect(words, state).toContain(control);

      // Criterion 4. A benchmark figure is a decimal, a percentage, or one of
      // the words a comparison figure is labelled with. This surface manages
      // sets; it never shows what a set measures.
      expect(words, state).not.toMatch(/\d+\.\d/);
      expect(words, state).not.toContain('%');
      for (const word of ['mean', 'median', 'average', 'benchmark', 'university', 'rating']) {
        expect(words.toLowerCase(), `${state}: ${word}`).not.toContain(word);
      }

      // Nothing drawn, either — and this is a closed set rather than a
      // property. "Every graphic is `aria-hidden`" is exactly what a decorative
      // chart carries, so it would admit the thing it exists to refuse; what is
      // asserted instead is **where** a graphic may be. This surface has one
      // legitimate drawing, the design's pulse-line motif, and it lives inside
      // `StateNotice` — so every `svg` on the page has to sit inside one, and an
      // `svg` anywhere else is a finding whatever attributes it carries.
      for (const drawing of page.querySelectorAll('svg')) {
        expect(drawing.closest(`.${STATE_NOTICE_CLASS}`), `${state}: ${drawing.outerHTML}`).not.toBeNull();
      }
      expect(page.querySelectorAll('canvas'), state).toHaveLength(0);
      expect(within(page).queryByRole('img'), state).toBeNull();

      cleanup();
      vi.unstubAllGlobals();
    }
  });
});
