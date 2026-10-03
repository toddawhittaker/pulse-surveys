import { useEffect, useLayoutEffect, useRef, useState, type JSX } from 'react';

import { Link, useRouter } from '@tanstack/react-router';

import {
  createComparisonSet,
  deleteComparisonSet,
  readComparisonSetOptions,
  readComparisonSetPreview,
  readComparisonSets,
  type ComparisonSetOptionsRead,
  type ComparisonSetOptionsView,
  type ComparisonSetPreviewView,
  type ComparisonSetSummaryView,
  type ComparisonSetsRead,
} from '../../api/leadership';
import { StateNotice } from '../../components/StateNotice';
import {
  copy,
  fillCopy,
  type LeadershipComparisonSetCopyKey,
} from '../../copy/leadershipComparisonSetCopy';
import {
  COMPARISON_SET_EDIT_ROUTE,
  COMPARISON_SETS_ROUTE,
  ComparisonSetForm,
  LEADERSHIP_SETS_TESTID,
  PAGE_HEADING_ID,
} from './ComparisonSetForm';
import './leadershipComparisonSets.css';

/**
 * `/leadership/comparison-sets` — the sets this reader may read, and what each
 * one reaches (SPEC §5.1, ticket E5-09).
 *
 * The page does three things: it lists the sets, it says what each reaches, and
 * it is where a set is defined, edited or deleted. Everything about **which**
 * sets these are belongs to the server — `api/leadership.py` scopes the list and
 * answers `editable` per set — so nothing here filters, sorts or decides what a
 * reader may change.
 *
 * **No figure of any kind renders on this screen.** A comparison set is what a
 * benchmark is computed from, and this is the surface that manages sets rather
 * than one that shows what they measure: the two counts below are a count of
 * courses and a count of sections, which is the aggregate language §4.1 item 4
 * asks for, and there is no mean, no median, no rate and no chart anywhere on
 * the page. That is the ticket's fourth criterion, and it is a property of the
 * page rather than of a suppression rule — item 7's chokepoint governs figures,
 * and the way this screen satisfies it is by having none to govern.
 *
 * **The preview is one read per set**, because the API answers one set at a
 * time. A set whose preview has not arrived says so, and a set whose preview
 * answered without a section count says that instead of printing a zero (E5-06's
 * scope note allows the answer, and a zero would state something the server did
 * not).
 *
 * **Deleting states what it will change.** `design/Usage Rules.md` §4 rules out
 * "Are you sure?" for a wide-effect change and asks for the consequence in
 * words, so the confirmation names the set and says what survives it.
 *
 * **Focus never stays on a control that has just gone.** Opening the form or
 * the delete confirmation takes away the button that opened it, and closing
 * either takes away the controls inside it, so each move says where focus goes
 * next: into the confirmation when it opens, back to the row's delete button
 * when it is kept, to the page heading when the set is gone, and back to
 * "Define a set" when the form closes. A save or a delete that landed is also
 * said once, in one status line, because the change it made is otherwise a row
 * appearing or disappearing somewhere a reader may not be looking.
 */

export { LEADERSHIP_SETS_TESTID };

/** Where a spec finds the list itself, as opposed to one of the page's states. */
export const COMPARISON_SET_LIST_TESTID = 'pulse-leadership-set-list';

/** Where a spec finds the confirmation a delete waits behind. */
export const COMPARISON_SET_DELETE_CONFIRM_TESTID = 'pulse-leadership-set-delete-confirm';

/** What the page has been able to read so far. */
type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | {
      readonly kind: 'sets';
      readonly sets: readonly ComparisonSetSummaryView[];
      /** Absent when the choice lists were refused: the form cannot be offered. */
      readonly options: ComparisonSetOptionsView | null;
    };

/** What one set's preview read answered, while the page holds it. */
type Preview =
  | { readonly kind: 'counting' }
  | { readonly kind: 'counted'; readonly preview: ComparisonSetPreviewView }
  | { readonly kind: 'unavailable' };

export function ComparisonSetsRoute(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [previews, setPreviews] = useState<Readonly<Record<string, Preview>>>({});
  const [defining, setDefining] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleteRefusal, setDeleteRefusal] = useState<string | null>(null);
  // What the last write did, said once in the status line. Cleared when the
  // reader starts another, so the line never describes a write before the one
  // in hand.
  const [announcement, setAnnouncement] = useState<string | null>(null);

  // **A save made on the edit page is said here, once.** That page hands this
  // one `pulseSetSaved` in the navigation state. It is consumed by replacing the
  // history entry with one that does not carry it, and only once the
  // replacement has landed does the line say "Set saved.": a reload, or a
  // return to this entry, finds nothing to replay. The sentence arrives after
  // the first render on purpose, so the status region is already in the page
  // when it changes and a screen reader announces it.
  const router = useRouter();
  useEffect(() => {
    if (router.state.location.state.pulseSetSaved !== true) return;
    let live = true;
    void router.navigate({ to: COMPARISON_SETS_ROUTE, replace: true, state: {} }).then(() => {
      if (live) setAnnouncement(copy('leadership_comparison_sets.set_saved'));
    });
    return () => {
      live = false;
    };
  }, [router]);

  // Where focus goes once the render that took a control away has landed. A
  // request rather than a focus call in the handler, because the element it
  // names (the heading, or a "Define a set" button that is not mounted yet)
  // exists only after that render. A ref, not state: asking for focus is not
  // something the page draws, and every handler that asks also changes state,
  // so the render that answers it follows anyway. The effect runs after every
  // render and does nothing unless a request is waiting.
  //
  // **A layout effect, not a passive one, and that is load-bearing.** A passive
  // effect from an earlier, unrelated render (a preview answer landing) can
  // still be pending when the reader clicks. React runs it before the click's
  // render, and a passive effect here would consume the new request there,
  // while the form still stood and "Define a set" did not exist. Focus then
  // fell to the body. A layout effect runs inside its own commit, so the only
  // run that can see a request is the one in the commit the handler caused.
  // The row's effect below is a layout effect for the same reason, and so that
  // the row's move and this one keep their order (child first, then page).
  const focusNext = useRef<'heading' | 'define' | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const defineRef = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (focusNext.current === null) return;
    (focusNext.current === 'heading' ? headingRef : defineRef).current?.focus();
    focusNext.current = null;
  });

  // **A write asks for the list again by bumping this**, rather than by calling a
  // reading function from an event handler. One effect does every read of the
  // list, so there is one place that decides what an answer means, and a create
  // or a delete says "read it again" rather than carrying a second copy of that
  // decision.
  const [reads, setReads] = useState(0);

  useEffect(() => {
    let live = true;
    void Promise.all([readComparisonSets(), readComparisonSetOptions()]).then(
      ([setsRead, optionsRead]) => {
        if (!live) return;
        setLoad(loadFrom(setsRead, optionsRead));
      },
    );
    return () => {
      live = false;
    };
  }, [reads]);

  // The previews, one read per listed set. They are read after the list rather
  // than with it because there is nothing to ask about until the list names the
  // sets, and each answer lands on its own row.
  //
  // **A set with no entry yet is counting**, which is the render's default
  // rather than a value written here: an effect that first wrote a row of
  // "counting" entries and then replaced them would be two renders saying the
  // same thing, and the absence already means exactly that.
  const listed = load.kind === 'sets' ? load.sets : null;
  useEffect(() => {
    if (listed === null) return;
    let live = true;
    for (const set of listed) {
      void readComparisonSetPreview(set.id).then((answer) => {
        if (!live) return;
        setPreviews((held) => ({
          ...held,
          [set.id]:
            answer.kind === 'preview'
              ? { kind: 'counted', preview: answer.preview }
              : { kind: 'unavailable' },
        }));
      });
    }
    return () => {
      live = false;
    };
  }, [listed]);

  return (
    <main
      className="pulse-set-page"
      data-testid={LEADERSHIP_SETS_TESTID}
      aria-labelledby={PAGE_HEADING_ID}
    >
      <h1 className="pulse-set-title" id={PAGE_HEADING_ID} ref={headingRef} tabIndex={-1}>
        {copy('leadership_comparison_sets.heading')}
      </h1>
      <p className="pulse-set-intro">{copy('leadership_comparison_sets.intro')}</p>
      <p className="pulse-set-intro">{copy('leadership_comparison_sets.no_report_yet')}</p>
      {/* In the page from the first render, so the sentence is announced when
          it arrives rather than mounted together with its region. */}
      <p className="pulse-set-announcement" role="status">
        {announcement}
      </p>

      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_comparison_sets.loading')}
        </p>
      ) : load.kind === 'session-ended' ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_comparison_sets.session_ended_title')}
          body={copy('leadership_comparison_sets.session_ended_body')}
        />
      ) : load.kind === 'error' ? (
        <StateNotice
          variant="flat"
          body={load.detail ?? copy('leadership_comparison_sets.unavailable')}
        />
      ) : (
        <>
          {load.sets.length === 0 ? (
            <StateNotice
              variant="flat"
              title={copy('leadership_comparison_sets.empty_title')}
              body={copy('leadership_comparison_sets.empty_body')}
            />
          ) : (
            <ul
              className="pulse-set-list"
              data-testid={COMPARISON_SET_LIST_TESTID}
              aria-label={copy('leadership_comparison_sets.list_label')}
            >
              {load.sets.map((set) => (
                <SetRow
                  key={set.id}
                  set={set}
                  preview={previews[set.id] ?? { kind: 'counting' }}
                  confirming={confirming === set.id}
                  onDeleteAsked={() => {
                    setDeleteRefusal(null);
                    setAnnouncement(null);
                    setConfirming(set.id);
                  }}
                  onDeleteCancelled={() => {
                    setConfirming(null);
                  }}
                  onDeleteConfirmed={() => {
                    void deleteComparisonSet(set.id).then((outcome) => {
                      setConfirming(null);
                      if (outcome.kind === 'deleted') {
                        // The row is about to go, and its delete button with
                        // it, so focus goes to the heading rather than back.
                        setAnnouncement(copy('leadership_comparison_sets.set_deleted'));
                        focusNext.current = 'heading';
                        setReads((asked) => asked + 1);
                        return;
                      }
                      setDeleteRefusal(
                        outcome.kind === 'refused'
                          ? (outcome.detail ??
                              copy('leadership_comparison_sets.delete_unavailable'))
                          : copy('leadership_comparison_sets.delete_unavailable'),
                      );
                    });
                  }}
                />
              ))}
            </ul>
          )}

          {deleteRefusal === null ? null : (
            <p className="pulse-set-refusal" role="alert">
              {deleteRefusal}
            </p>
          )}

          {load.options === null ? (
            <p className="pulse-set-help">{copy('leadership_comparison_sets.unavailable')}</p>
          ) : defining ? (
            <ComparisonSetForm
              options={load.options}
              onSave={async (write) => {
                const outcome = await createComparisonSet(write);
                if (outcome.kind === 'saved') {
                  setDefining(false);
                  setAnnouncement(copy('leadership_comparison_sets.set_saved'));
                  focusNext.current = 'define';
                  setReads((asked) => asked + 1);
                }
                return outcome;
              }}
              onCancel={() => {
                setDefining(false);
                focusNext.current = 'define';
              }}
            />
          ) : (
            <p className="pulse-set-actions">
              <button
                className="pulse-set-button"
                type="button"
                ref={defineRef}
                onClick={() => {
                  setAnnouncement(null);
                  setDefining(true);
                }}
              >
                {copy('leadership_comparison_sets.define')}
              </button>
            </p>
          )}
        </>
      )}
    </main>
  );
}

/**
 * What the two reads together mean for the page.
 *
 * A function of the two answers rather than a sequence of `setLoad` calls, so
 * the whole decision is one expression the effect applies once: a refused
 * session on either read is a session that ended; a refused list is an error and
 * never the empty state, because "you have defined no sets" is a claim about
 * this reader that a failed read does not entitle the page to make; and refused
 * choice lists leave the list readable with no form to offer.
 */
function loadFrom(setsRead: ComparisonSetsRead, optionsRead: ComparisonSetOptionsRead): Load {
  if (setsRead.kind === 'session-ended' || optionsRead.kind === 'session-ended') {
    return { kind: 'session-ended' };
  }
  if (setsRead.kind !== 'sets') return { kind: 'error', detail: setsRead.detail };
  return {
    kind: 'sets',
    sets: setsRead.sets,
    options: optionsRead.kind === 'options' ? optionsRead.options : null,
  };
}

/** One set in the list: its name, its two declared facts, what it reaches, its controls. */
function SetRow({
  set,
  preview,
  confirming,
  onDeleteAsked,
  onDeleteCancelled,
  onDeleteConfirmed,
}: {
  readonly set: ComparisonSetSummaryView;
  readonly preview: Preview;
  readonly confirming: boolean;
  readonly onDeleteAsked: () => void;
  readonly onDeleteCancelled: () => void;
  readonly onDeleteConfirmed: () => void;
}): JSX.Element {
  // Opening the confirmation takes the delete button away, so focus goes into
  // the confirmation, which is labelled by its own question. Keeping the set —
  // or a delete the server refused — brings the button back, and focus with it.
  // Only a change of `confirming` moves focus; a row's first render never does.
  const confirmRef = useRef<HTMLDivElement>(null);
  const deleteRef = useRef<HTMLButtonElement>(null);
  const wasConfirming = useRef(confirming);
  useLayoutEffect(() => {
    if (confirming === wasConfirming.current) return;
    wasConfirming.current = confirming;
    (confirming ? confirmRef : deleteRef).current?.focus();
  }, [confirming]);
  const confirmTitleId = `pulse-leadership-set-delete-title-${set.id}`;

  return (
    <li className="pulse-set-row">
      <h2 className="pulse-set-name">{set.name}</h2>
      <p className="pulse-set-facts">
        {fillCopy('leadership_comparison_sets.set_facts', {
          length: fillCopy('leadership_comparison_sets.length_option', {
            weeks: String(set.length_weeks),
          }),
          level: set.level,
        })}
      </p>
      <p className="pulse-set-preview">{previewLine(preview)}</p>
      {confirming ? (
        <div
          className="pulse-set-confirm"
          data-testid={COMPARISON_SET_DELETE_CONFIRM_TESTID}
          role="group"
          aria-labelledby={confirmTitleId}
          ref={confirmRef}
          tabIndex={-1}
        >
          <p className="pulse-set-confirm-title" id={confirmTitleId}>
            {fillCopy('leadership_comparison_sets.delete_confirm_title', { name: set.name })}
          </p>
          <p className="pulse-set-confirm-body">
            {copy('leadership_comparison_sets.delete_confirm_body')}
          </p>
          <button className="pulse-set-button" type="button" onClick={onDeleteConfirmed}>
            {copy('leadership_comparison_sets.delete_confirm')}
          </button>
          <button className="pulse-set-plain-button" type="button" onClick={onDeleteCancelled}>
            {copy('leadership_comparison_sets.delete_cancel')}
          </button>
        </div>
      ) : set.editable ? (
        <p className="pulse-set-row-actions">
          <Link
            className="pulse-set-link"
            to={COMPARISON_SET_EDIT_ROUTE}
            params={{ setId: set.id }}
          >
            {copy('leadership_comparison_sets.edit')}
          </Link>
          <button
            className="pulse-set-plain-button"
            type="button"
            ref={deleteRef}
            onClick={onDeleteAsked}
          >
            {copy('leadership_comparison_sets.delete')}
          </button>
        </p>
      ) : (
        // Neither control, and a word saying the absence is deliberate. The flag
        // is the server's answer about this reader and this set; the page draws
        // what it was told rather than deciding for itself.
        <p className="pulse-set-row-actions">{copy('leadership_comparison_sets.read_only')}</p>
      )}
    </li>
  );
}

/** What one set reaches, in whichever of the three shapes its preview answered. */
function previewLine(preview: Preview): string {
  if (preview.kind === 'counting') return copy('leadership_comparison_sets.preview_counting');
  if (preview.kind === 'unavailable') return copy('leadership_comparison_sets.preview_unavailable');
  const sections = preview.preview.section_count;
  const courses = counted(
    preview.preview.member_count,
    'leadership_comparison_sets.count_courses_one',
    'leadership_comparison_sets.count_courses_many',
  );
  // `== null` rather than `=== undefined`: the wire carries the absence both as
  // a missing member and as a JSON null, and a guard reading only one of them
  // prints "null sections" for the other.
  if (sections == null) {
    return fillCopy('leadership_comparison_sets.preview_courses_only', { courses });
  }
  return fillCopy('leadership_comparison_sets.preview_counts', {
    courses,
    sections: counted(
      sections,
      'leadership_comparison_sets.count_sections_one',
      'leadership_comparison_sets.count_sections_many',
    ),
  });
}

/** A count with its noun, singular for exactly one. */
function counted(
  count: number,
  one: LeadershipComparisonSetCopyKey,
  many: LeadershipComparisonSetCopyKey,
): string {
  return count === 1 ? copy(one) : fillCopy(many, { count: String(count) });
}
