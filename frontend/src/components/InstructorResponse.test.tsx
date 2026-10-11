import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import type {
  DraftCheckOutcome,
  ResponseDraftOutcome,
  ResponseWriteOutcome,
  WeekResponseRead,
} from '../api/instructor';
import {
  InstructorResponse,
  RESPONSE_MAX_LENGTH,
  type ResponseActions,
} from './InstructorResponse';

/**
 * The instructor's composer (SPEC §5.3), driven through the four calls it is
 * given. The sentences are written out rather than read from the copy module,
 * so a test cannot pass by agreeing with the words it checks.
 */

afterEach(cleanup);

const AWAITING: WeekResponseRead = { state: 'awaiting', response: null };
const UNANSWERED: WeekResponseRead = { state: 'unanswered', response: null };

function publishedBy(name: string, text: string, state: 'published' | 'on-behalf' = 'published') {
  return {
    state,
    response: {
      text,
      author_name: name,
      author_role: state === 'published' ? ('INSTRUCTOR' as const) : ('LEAD_FACULTY' as const),
      published_at: '2026-10-12T14:00:00Z',
    },
  } satisfies WeekResponseRead;
}

/** Calls that record themselves; every one answers the outcome it is given. */
function actions(
  overrides: Partial<{
    draft: ResponseDraftOutcome;
    check: DraftCheckOutcome;
    write: ResponseWriteOutcome;
  }> = {},
) {
  const calls = {
    draft: vi.fn<ResponseActions['draft']>(),
    check: vi.fn<ResponseActions['check']>(),
    publish: vi.fn<ResponseActions['publish']>(),
    edit: vi.fn<ResponseActions['edit']>(),
  };
  calls.draft.mockResolvedValue(overrides.draft ?? { kind: 'draft', text: 'Here is the draft.' });
  calls.check.mockResolvedValue(
    overrides.check ?? {
      kind: 'checked',
      unaddressed: [
        { label: 'Pacing of the readings', comment_count: 3 },
        { label: 'Lab equipment', comment_count: 1 },
        { label: 'Office hours', comment_count: null },
      ],
    },
  );
  const write = overrides.write ?? {
    kind: 'saved',
    view: publishedBy('Dr. Ada Marsh', 'What I will change.'),
  };
  calls.publish.mockResolvedValue(write);
  calls.edit.mockResolvedValue(write);
  return calls;
}

function open(initial: WeekResponseRead, calls = actions()) {
  render(<InstructorResponse initial={initial} actions={calls} />);
  return calls;
}

/** The editor, narrowed so its value and bound can be read. */
function editor(): HTMLTextAreaElement {
  const field = screen.getByRole('textbox', { name: 'Your response' });
  if (!(field instanceof HTMLTextAreaElement)) throw new Error('The editor is not a textarea.');
  return field;
}

/** Whether the named button is disabled. */
function disabled(name: string): boolean {
  return screen.getByRole('button', { name }).getAttribute('aria-disabled') === 'true';
}
const press = (name: string) => {
  fireEvent.click(screen.getByRole('button', { name }));
};
const type = (value: string) => {
  fireEvent.change(editor(), { target: { value } });
};

describe('nothing posts without the publish button', () => {
  it('uses a draft, runs a check and edits without publishing or editing anything', async () => {
    const calls = open(UNANSWERED);

    press('Draft with AI');
    await waitFor(() => {
      expect(editor().value).toBe('Here is the draft.');
    });
    type('Here is the draft, changed.');
    press('Check draft with AI');
    await screen.findByText('Pacing of the readings (3 comments)');

    expect(calls.draft).toHaveBeenCalledTimes(1);
    expect(calls.check).toHaveBeenCalledWith('Here is the draft, changed.');
    expect(calls.publish).not.toHaveBeenCalled();
    expect(calls.edit).not.toHaveBeenCalled();
  });

  it('publishes exactly once, when Publish is pressed', async () => {
    const calls = open(UNANSWERED);
    type('We heard you on pacing.');
    press('Publish');
    await screen.findByText('Dr. Ada Marsh');

    expect(calls.publish).toHaveBeenCalledTimes(1);
    expect(calls.publish).toHaveBeenCalledWith({
      text: 'We heard you on pacing.',
      ai_seeded: false,
    });
    expect(calls.edit).not.toHaveBeenCalled();
  });

  it('cannot publish or check an empty or blank editor', () => {
    open(UNANSWERED);
    expect(disabled('Publish')).toBe(true);
    expect(disabled('Check draft with AI')).toBe(true);
    type('   ');
    expect(disabled('Publish')).toBe(true);
  });
});

describe('the check', () => {
  it('lists themes with counts, and a held stream’s theme without one', async () => {
    open(UNANSWERED);
    type('A draft.');
    press('Check draft with AI');

    const panel = await screen.findByRole('region', {
      name: 'Themes your draft has not addressed',
    });
    expect(within(panel).getByText('AI')).toBeTruthy();
    expect(within(panel).getByText('Pacing of the readings (3 comments)')).toBeTruthy();
    expect(within(panel).getByText('Lab equipment (1 comment)')).toBeTruthy();
    // Null count: the theme is named and nothing is counted.
    expect(within(panel).getByText('Office hours')).toBeTruthy();
  });

  it('clears when one character changes, and a second run shows a fresh result', async () => {
    const calls = open(UNANSWERED);
    type('A draft.');
    press('Check draft with AI');
    await screen.findByRole('region', {
      name: 'Themes your draft has not addressed',
    });

    type('A draft!');
    expect(
      screen.queryByRole('region', {
        name: 'Themes your draft has not addressed',
      }),
    ).toBeNull();

    calls.check.mockResolvedValueOnce({ kind: 'checked', unaddressed: [] });
    press('Check draft with AI');
    await screen.findByText('Your draft addresses every theme in this week’s comments.');
    expect(calls.check).toHaveBeenCalledTimes(2);
    expect(calls.check).toHaveBeenLastCalledWith('A draft!');
  });

  it('is not shown beside text it was not run on when the answer arrives late', async () => {
    const calls = actions();
    let release: (outcome: DraftCheckOutcome) => void = () => undefined;
    calls.check.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    open(UNANSWERED, calls);
    type('First text.');
    press('Check draft with AI');
    type('Second text.');
    release({
      kind: 'checked',
      unaddressed: [{ label: 'Pacing', comment_count: 2 }],
    });

    await waitFor(() => {
      expect(disabled('Check draft with AI')).toBe(false);
    });
    expect(screen.queryByText('Pacing (2 comments)')).toBeNull();
  });

  it('never blocks publish', async () => {
    const calls = open(UNANSWERED);
    type('A draft.');
    press('Check draft with AI');
    await screen.findByText('Pacing of the readings (3 comments)');

    press('Publish');
    await waitFor(() => {
      expect(calls.publish).toHaveBeenCalledTimes(1);
    });
  });

  it('shows the server’s sentence calmly when the model’s answer was refused', async () => {
    const sentence = 'The assistant could not help with this just now.';
    open(UNANSWERED, actions({ check: { kind: 'refused', detail: sentence } }));
    type('A draft.');
    press('Check draft with AI');

    expect((await screen.findByText(sentence)).getAttribute('role')).toBe('status');
    expect(screen.queryByRole('alert')).toBeNull();
    // The failure leaves the editor, the text and Publish as they were.
    expect(editor().value).toBe('A draft.');
    expect(disabled('Publish')).toBe(false);
  });
});

describe('using a draft', () => {
  it('fills an empty editor without asking', async () => {
    open(UNANSWERED);
    press('Draft with AI');
    await waitFor(() => {
      expect(editor().value).toBe('Here is the draft.');
    });
    expect(screen.queryByText('Replace what you have written with the draft?')).toBeNull();
  });

  it('asks before replacing text the instructor wrote, and keeps it on “Keep mine”', async () => {
    open(UNANSWERED);
    type('My own words.');
    press('Draft with AI');

    await screen.findByText('Replace what you have written with the draft?');
    expect(editor().value).toBe('My own words.');
    press('Keep mine');
    expect(editor().value).toBe('My own words.');
    expect(screen.queryByText('Replace what you have written with the draft?')).toBeNull();
  });

  it('replaces on “Replace with draft”', async () => {
    open(UNANSWERED);
    type('My own words.');
    press('Draft with AI');
    await screen.findByText('Replace what you have written with the draft?');
    press('Replace with draft');
    expect(editor().value).toBe('Here is the draft.');
  });

  it('marks the publish as AI-seeded only while the text began as a draft', async () => {
    const calls = open(UNANSWERED);
    press('Draft with AI');
    await waitFor(() => {
      expect(editor().value).toBe('Here is the draft.');
    });
    press('Publish');
    await waitFor(() => {
      expect(calls.publish).toHaveBeenCalledWith({
        text: 'Here is the draft.',
        ai_seeded: true,
      });
    });
  });

  it('forgets that it was seeded once the editor is emptied', async () => {
    const calls = open(UNANSWERED);
    press('Draft with AI');
    await waitFor(() => {
      expect(editor().value).toBe('Here is the draft.');
    });
    type('');
    type('Written fresh.');
    press('Publish');
    await waitFor(() => {
      expect(calls.publish).toHaveBeenCalledWith({
        text: 'Written fresh.',
        ai_seeded: false,
      });
    });
  });

  it('shows a refused draft’s sentence and leaves the editor empty', async () => {
    const sentence = 'A draft could not be written for this week.';
    open(UNANSWERED, actions({ draft: { kind: 'refused', detail: sentence } }));
    press('Draft with AI');
    expect((await screen.findByText(sentence)).getAttribute('role')).toBe('status');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(editor().value).toBe('');
  });

  it('uses its own sentence when the failure carried none', async () => {
    open(UNANSWERED, actions({ draft: { kind: 'unavailable', detail: null } }));
    press('Draft with AI');
    expect(
      (
        await screen.findByText(
          'A draft could not be written just now. You can still write your own.',
        )
      ).getAttribute('role'),
    ).toBe('status');
  });
});

describe('the editor’s bound', () => {
  it('holds the response length the server accepts', () => {
    open(UNANSWERED);
    expect(editor().maxLength).toBe(RESPONSE_MAX_LENGTH);
    expect(screen.getByText(`${String(RESPONSE_MAX_LENGTH)} characters left`)).toBeTruthy();
    type('abcd');
    expect(screen.getByText(`${String(RESPONSE_MAX_LENGTH - 4)} characters left`)).toBeTruthy();
  });
});

describe('the held-results notice', () => {
  it('shows in an awaiting week only, and is gone once a response is published', async () => {
    const { unmount } = render(<InstructorResponse initial={UNANSWERED} actions={actions()} />);
    expect(screen.queryByText('Students will see this week’s results once you respond')).toBeNull();
    unmount();

    open(AWAITING);
    expect(screen.getByText('Students will see this week’s results once you respond')).toBeTruthy();

    type('A response.');
    press('Publish');
    await screen.findByText('Dr. Ada Marsh');
    expect(screen.queryByText('Students will see this week’s results once you respond')).toBeNull();
  });
});

describe('the published response', () => {
  it('shows the card with the instructor’s name, and Edit opens the composer on the text', async () => {
    const calls = open(publishedBy('Dr. Ada Marsh', 'What I will change.'));

    expect(screen.getByText('As students see it')).toBeTruthy();
    expect(screen.getByText('What I will change.')).toBeTruthy();
    expect(screen.getByText('Dr. Ada Marsh')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();

    press('Edit response');
    expect(editor().value).toBe('What I will change.');

    type('What I will change, revised.');
    calls.edit.mockResolvedValueOnce({
      kind: 'saved',
      view: publishedBy('Dr. Ada Marsh', 'What I will change, revised.'),
    });
    press('Publish changes');

    await screen.findByText('What I will change, revised.');
    expect(calls.edit).toHaveBeenCalledWith({
      text: 'What I will change, revised.',
      ai_seeded: false,
    });
    expect(calls.publish).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('leaves the card as it was when an edit is cancelled', () => {
    const calls = open(publishedBy('Dr. Ada Marsh', 'What I will change.'));
    press('Edit response');
    type('Something else entirely.');
    press('Cancel');

    expect(screen.getByText('What I will change.')).toBeTruthy();
    expect(calls.edit).not.toHaveBeenCalled();
  });

  it('offers no Edit on a response written on the instructor’s behalf', () => {
    open(publishedBy('Dr. Lee Park', 'Written by the lead.', 'on-behalf'));
    expect(screen.getByText('Written by the lead.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Edit response' })).toBeNull();
  });

  it('shows the server’s sentence when the edit is refused', async () => {
    const sentence = 'This response is not yours to edit.';
    open(
      publishedBy('Dr. Ada Marsh', 'What I will change.'),
      actions({ write: { kind: 'refused', detail: sentence } }),
    );
    press('Edit response');
    type('Changed.');
    press('Publish changes');

    expect((await screen.findByRole('alert')).textContent).toBe(sentence);
    expect(editor().value).toBe('Changed.');
  });

  it('announces a publish in a polite status region', async () => {
    open(UNANSWERED);
    type('A response.');
    press('Publish');
    await screen.findByText('Dr. Ada Marsh');
    const status = screen
      .getAllByRole('status')
      .find((region) => region.textContent === 'Response published. Students can now read it.');
    expect(status).toBeTruthy();
  });
});

describe('accessibility of the composer', () => {
  it('keeps its announcement region in the tree while empty', () => {
    open(UNANSWERED);
    const region = screen.getAllByRole('status').find((node) => node.classList.contains('sr-only'));
    expect(region).toBeDefined();
    expect(region?.textContent).toBe('');
  });

  it('announces the same message again as a new node', async () => {
    open(UNANSWERED);
    press('Draft with AI');
    await waitFor(() => {
      expect(editor().value).toBe('Here is the draft.');
    });
    const region = screen.getAllByRole('status').find((node) => node.classList.contains('sr-only'));
    const first = region?.firstElementChild;
    type('');
    press('Draft with AI');
    await waitFor(() => {
      expect(region?.firstElementChild).not.toBe(first);
    });
    expect(region?.textContent).toContain('The draft is in the editor.');
  });

  it('names the replace question and moves focus to its first button', async () => {
    open(UNANSWERED);
    type('My own words.');
    press('Draft with AI');
    const group = await screen.findByRole('group', {
      name: 'Replace what you have written with the draft?',
    });
    expect(document.activeElement).toBe(
      within(group).getByRole('button', { name: 'Replace with draft' }),
    );
  });

  it('keeps focus on a pressed control while the request is in flight and ignores a second press', async () => {
    const calls = actions();
    let release: (outcome: ResponseDraftOutcome) => void = () => undefined;
    calls.draft.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    open(UNANSWERED, calls);
    const button = screen.getByRole('button', { name: 'Draft with AI' });
    button.focus();
    fireEvent.click(button);
    await screen.findByText('Writing a draft…');
    expect(button.getAttribute('aria-disabled')).toBe('true');
    expect(button.hasAttribute('disabled')).toBe(false);
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(calls.draft).toHaveBeenCalledTimes(1);
    release({ kind: 'draft', text: 'x' });
    await waitFor(() => {
      expect(editor().value).toBe('x');
    });
  });

  it('marks the editor invalid only when a publish fails, never when advice does', async () => {
    const down = actions({ draft: { kind: 'unavailable', detail: null } });
    open(UNANSWERED, down);
    press('Draft with AI');
    await screen.findByText('A draft could not be written just now. You can still write your own.');
    expect(editor().getAttribute('aria-invalid')).toBe('false');
    cleanup();

    open(UNANSWERED, actions({ write: { kind: 'unavailable', detail: null } }));
    type('Words.');
    press('Publish');
    await waitFor(() => {
      expect(editor().getAttribute('aria-invalid')).toBe('true');
    });
    expect(screen.getByRole('alert')).toBeTruthy();
  });
});
