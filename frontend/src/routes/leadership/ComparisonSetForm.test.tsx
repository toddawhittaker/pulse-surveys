import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import type { ComparisonSetWrite, ComparisonSetWriteOutcome } from '../../api/leadership';
import {
  A_BIOLOGY_COURSE,
  A_CHEMISTRY_COURSE,
  A_DEVELOPMENTAL_COURSE,
  A_DUAL_CREDIT_COURSE,
  A_DUPLICATE_NAME_REFUSAL,
  A_NEW_SET,
  A_NURSING_COURSE,
  A_SECOND_GRADUATE_COURSE,
  A_SET_THIS_READER_DEFINED,
  THE_OPTIONS,
} from '../../api/comparisonSetFixtures';
import {
  COMPARISON_SET_REFUSAL_TESTID,
  COMPARISON_SET_REMOVED_TESTID,
  ComparisonSetForm,
} from './ComparisonSetForm';

/**
 * The set-definition form, driven — ticket E5-09, criteria 1 and 2.
 *
 * Both criteria say the same thing about how they are to be asserted: by
 * driving the form rather than by reading its props. So every case below
 * chooses a length, chooses a level and ticks a course the way a person would,
 * and reads what is on the screen afterwards — never the component's state and
 * never the arguments it was rendered with.
 *
 * **The closed sets are the fixture's, which stands in for the server.** The
 * form is handed `THE_OPTIONS` and offers exactly what that answer carries, so
 * a form that had grown its own list of lengths or levels would show a choice
 * this file never served and fail here.
 *
 * Governed copy is transcribed rather than imported (`docs/MISTAKES.md` entry
 * 19): a test that asked the copy module what the form says would pass over any
 * rewording, including a wrong one.
 */

// `globals` is off (ADR 0151), so `@testing-library/react` finds no global
// `afterEach` to register its own cleanup with.
afterEach(cleanup);

const NAME_LABEL = 'Set name';
const LENGTH_LABEL = 'Course length';
const LEVEL_LABEL = 'Course level';
const MEMBERS_LABEL = 'Courses in this set';
const AWAIT_LEVEL = 'Choose a level first. The courses of that level appear here.';
const NO_COURSES = 'There are no courses of this level for you to choose from.';
const SAVE = 'Save this set';
const DISMISS = 'Dismiss';
const INCOMPLETE = 'A set needs a name, a length and a level before it can be saved.';
const SAVE_UNAVAILABLE = 'This set could not be saved just now. Try again in a moment.';

/** The two sentences a level change writes, transcribed. */
const ONE_REMOVED = (labels: string) => `The level changed, so one course left this set: ${labels}.`;
const MANY_REMOVED = (count: number, labels: string) =>
  `The level changed, so ${String(count)} courses left this set: ${labels}.`;

/** A save that always succeeds, and the writes it was handed. */
function acceptingSaves(): { writes: ComparisonSetWrite[]; save: SaveHandler } {
  const writes: ComparisonSetWrite[] = [];
  return {
    writes,
    save: (write) => {
      writes.push(write);
      return Promise.resolve({ kind: 'saved', set: A_NEW_SET });
    },
  };
}

type SaveHandler = (write: ComparisonSetWrite) => Promise<ComparisonSetWriteOutcome>;

/** The form, rendered the way both of its callers render it. */
function renderForm(
  save: SaveHandler = () => Promise.resolve({ kind: 'saved', set: A_NEW_SET }),
  initial: typeof A_SET_THIS_READER_DEFINED | null = null,
) {
  const cancelled = vi.fn();
  render(
    <ComparisonSetForm
      options={THE_OPTIONS}
      initial={initial}
      onSave={save}
      onCancel={cancelled}
    />,
  );
  return { cancelled };
}

const nameField = (): HTMLInputElement => screen.getByLabelText(NAME_LABEL);
/** One course's tick box, typed so its `checked` can be read. */
const boxFor = (label: string): HTMLInputElement => screen.getByLabelText(label);
const lengthField = (): HTMLSelectElement => screen.getByLabelText(LENGTH_LABEL);
const levelField = (): HTMLSelectElement => screen.getByLabelText(LEVEL_LABEL);

/** Every course the picker is offering right now, by the label on its box. */
function offeredCourses(): string[] {
  return within(screen.getByRole('group', { name: MEMBERS_LABEL }))
    .queryAllByRole('checkbox')
    .map((box) => (box.closest('label')?.textContent ?? '').trim());
}

function type(field: HTMLElement, value: string): void {
  fireEvent.change(field, { target: { value } });
}

describe('the form cannot express an invalid combination', () => {
  it('offers the served lengths and levels and no way to type either', () => {
    renderForm();

    // Every option on both controls is one the fixture served, plus the
    // unchosen placeholder each starts on. A form carrying its own list would
    // offer something this test never supplied.
    const lengths = within(lengthField())
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(lengths).toEqual([
      'Choose a length',
      ...THE_OPTIONS.lengths.map((weeks) => `${String(weeks)} weeks`),
    ]);

    const levels = within(levelField())
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(levels).toEqual(['Choose a level', ...THE_OPTIONS.levels]);

    // And neither is a text field: the name is the only thing typed on this
    // form, so there is no free-text length and no free-text level to give.
    const typed = screen.getAllByRole('textbox');
    expect(typed).toEqual([nameField()]);
  });

  it('offers no course at all until a level is chosen', () => {
    renderForm();

    expect(offeredCourses()).toEqual([]);
    expect(screen.getByText(AWAIT_LEVEL)).toBeTruthy();
  });

  it('never offers a course of another level', () => {
    renderForm();

    type(levelField(), 'UG');
    // The two undergraduate courses and neither graduate one, neither the
    // developmental one nor the dual-credit one — all four of which the
    // fixture served in the same answer.
    expect(offeredCourses()).toEqual([A_BIOLOGY_COURSE.label, A_CHEMISTRY_COURSE.label]);

    type(levelField(), 'GR');
    expect(offeredCourses()).toEqual([A_NURSING_COURSE.label, A_SECOND_GRADUATE_COURSE.label]);

    type(levelField(), 'DEV');
    expect(offeredCourses()).toEqual([A_DEVELOPMENTAL_COURSE.label]);

    type(levelField(), 'UGGR');
    expect(offeredCourses()).toEqual([A_DUAL_CREDIT_COURSE.label]);
  });

  it('says so plainly for a level whose courses this reader has none of', () => {
    renderForm();

    // `DR` is one of the five bands the options answer carries and no course in
    // that answer is doctoral, which is an ordinary state rather than a fault.
    type(levelField(), 'DR');
    expect(offeredCourses()).toEqual([]);
    expect(screen.getByText(NO_COURSES)).toBeTruthy();
  });

  it('sends exactly the three choices and the courses that were ticked', async () => {
    const { writes, save } = acceptingSaves();
    renderForm(save);

    type(nameField(), '  Graduate nursing, eight weeks  ');
    type(lengthField(), '8');
    type(levelField(), 'GR');
    fireEvent.click(screen.getByLabelText(A_NURSING_COURSE.label));
    fireEvent.click(screen.getByLabelText(A_SECOND_GRADUATE_COURSE.label));
    fireEvent.click(screen.getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(writes).toEqual([
        {
          name: 'Graduate nursing, eight weeks',
          length_weeks: 8,
          level: 'GR',
          member_course_ids: [A_NURSING_COURSE.id, A_SECOND_GRADUATE_COURSE.id],
        },
      ]);
    });
  });

  it('will not save until the name, the length and the level are all there', () => {
    renderForm();

    const save = (): HTMLButtonElement => screen.getByRole('button', { name: SAVE });
    expect(save().disabled).toBe(true);
    expect(screen.getByText(INCOMPLETE)).toBeTruthy();

    type(nameField(), 'Fall biology cohort');
    expect(save().disabled).toBe(true);
    type(lengthField(), '12');
    expect(save().disabled).toBe(true);
    type(levelField(), 'UG');
    expect(save().disabled).toBe(false);
    expect(screen.queryByText(INCOMPLETE)).toBeNull();
  });
});

describe('changing the level in front of chosen courses', () => {
  it('keeps every course whose level still matches, and says nothing', () => {
    renderForm();

    type(levelField(), 'UG');
    fireEvent.click(screen.getByLabelText(A_BIOLOGY_COURSE.label));
    fireEvent.click(screen.getByLabelText(A_CHEMISTRY_COURSE.label));

    // The level is chosen again and it is the same level, so every chosen
    // course matches it. This is the surviving half of the rule, and it is the
    // half a filter written as "empty the list on any change" would fail.
    type(levelField(), 'UG');

    expect(boxFor(A_BIOLOGY_COURSE.label).checked).toBe(true);
    expect(boxFor(A_CHEMISTRY_COURSE.label).checked).toBe(
      true,
    );
    expect(screen.queryByTestId(COMPARISON_SET_REMOVED_TESTID)).toBeNull();
  });

  it('removes the courses that no longer match, and names them', () => {
    renderForm();

    type(levelField(), 'UG');
    fireEvent.click(screen.getByLabelText(A_BIOLOGY_COURSE.label));
    fireEvent.click(screen.getByLabelText(A_CHEMISTRY_COURSE.label));
    type(levelField(), 'GR');

    const notice = screen.getByTestId(COMPARISON_SET_REMOVED_TESTID);
    expect(within(notice).getByText(
      MANY_REMOVED(2, `${A_BIOLOGY_COURSE.label}, ${A_CHEMISTRY_COURSE.label}`),
    )).toBeTruthy();

    // And they are gone from the form as well as named in the notice: the
    // graduate level offers its own two courses, neither of them ticked.
    expect(offeredCourses()).toEqual([A_NURSING_COURSE.label, A_SECOND_GRADUATE_COURSE.label]);
    expect(boxFor(A_NURSING_COURSE.label).checked).toBe(false);
  });

  it('counts one removal in the singular', () => {
    renderForm();

    type(levelField(), 'UG');
    fireEvent.click(screen.getByLabelText(A_BIOLOGY_COURSE.label));
    type(levelField(), 'DEV');

    expect(
      within(screen.getByTestId(COMPARISON_SET_REMOVED_TESTID)).getByText(
        ONE_REMOVED(A_BIOLOGY_COURSE.label),
      ),
    ).toBeTruthy();
  });

  it('never submits a course the level change removed', async () => {
    const { writes, save } = acceptingSaves();
    renderForm(save);

    type(nameField(), 'Graduate nursing');
    type(lengthField(), '8');
    type(levelField(), 'UG');
    fireEvent.click(screen.getByLabelText(A_BIOLOGY_COURSE.label));
    type(levelField(), 'GR');
    fireEvent.click(screen.getByLabelText(A_NURSING_COURSE.label));
    fireEvent.click(screen.getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(writes).toHaveLength(1);
    });
    expect(writes[0]?.member_course_ids).toEqual([A_NURSING_COURSE.id]);
    expect(writes[0]?.level).toBe('GR');
  });

  it('takes the notice away when it is dismissed, and again on a change that removes nothing', () => {
    renderForm();

    type(levelField(), 'UG');
    fireEvent.click(screen.getByLabelText(A_BIOLOGY_COURSE.label));
    type(levelField(), 'GR');
    fireEvent.click(screen.getByRole('button', { name: DISMISS }));
    expect(screen.queryByTestId(COMPARISON_SET_REMOVED_TESTID)).toBeNull();

    // A second change with nothing chosen removes nothing, so no notice
    // returns — a notice that accumulated would stand over a form it is no
    // longer true of.
    type(levelField(), 'UG');
    expect(screen.queryByTestId(COMPARISON_SET_REMOVED_TESTID)).toBeNull();
  });
});

describe('the form opened on a set that already exists', () => {
  it('opens on the set’s own name, length, level and courses', () => {
    renderForm(undefined, A_SET_THIS_READER_DEFINED);

    expect(nameField().value).toBe(A_SET_THIS_READER_DEFINED.name);
    expect(lengthField().value).toBe(String(A_SET_THIS_READER_DEFINED.length_weeks));
    expect(levelField().value).toBe(A_SET_THIS_READER_DEFINED.level);
    expect(offeredCourses()).toEqual([A_BIOLOGY_COURSE.label, A_CHEMISTRY_COURSE.label]);
    expect(boxFor(A_BIOLOGY_COURSE.label).checked).toBe(true);
    expect(boxFor(A_CHEMISTRY_COURSE.label).checked).toBe(
      true,
    );
  });

  it('sends the edited set when it is saved', async () => {
    const { writes, save } = acceptingSaves();
    renderForm(save, A_SET_THIS_READER_DEFINED);

    fireEvent.click(screen.getByLabelText(A_CHEMISTRY_COURSE.label));
    fireEvent.click(screen.getByRole('button', { name: SAVE }));

    await waitFor(() => {
      expect(writes[0]?.member_course_ids).toEqual([A_BIOLOGY_COURSE.id]);
    });
    expect(writes[0]?.name).toBe(A_SET_THIS_READER_DEFINED.name);
  });
});

describe('a refused save', () => {
  it('shows the API’s own sentence, word for word', async () => {
    renderForm(() => Promise.resolve({ kind: 'refused', detail: A_DUPLICATE_NAME_REFUSAL }));

    type(nameField(), 'Fall biology cohort');
    type(lengthField(), '12');
    type(levelField(), 'UG');
    fireEvent.click(screen.getByRole('button', { name: SAVE }));

    const refusal = await screen.findByTestId(COMPARISON_SET_REFUSAL_TESTID);
    expect(refusal.textContent).toBe(A_DUPLICATE_NAME_REFUSAL);
    // The form is still there, with what the reader wrote still in it: the
    // refusal is about the set, not about the page.
    expect(nameField().value).toBe('Fall biology cohort');
  });

  it('falls back to its own words when the refusal carried no sentence', async () => {
    renderForm(() => Promise.resolve({ kind: 'refused', detail: null }));

    type(nameField(), 'Fall biology cohort');
    type(lengthField(), '12');
    type(levelField(), 'UG');
    fireEvent.click(screen.getByRole('button', { name: SAVE }));

    const refusal = await screen.findByTestId(COMPARISON_SET_REFUSAL_TESTID);
    expect(refusal.textContent).toBe(SAVE_UNAVAILABLE);
  });

  it('says the same when the write never reached the server', async () => {
    renderForm(() => Promise.resolve({ kind: 'unavailable', detail: null }));

    type(nameField(), 'Fall biology cohort');
    type(lengthField(), '12');
    type(levelField(), 'UG');
    fireEvent.click(screen.getByRole('button', { name: SAVE }));

    const refusal = await screen.findByTestId(COMPARISON_SET_REFUSAL_TESTID);
    expect(refusal.textContent).toBe(SAVE_UNAVAILABLE);
  });
});
