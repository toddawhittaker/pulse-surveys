import { useEffect, useRef, useState, type JSX } from 'react';

import { useNavigate, useParams } from '@tanstack/react-router';

import {
  readComparisonSet,
  readComparisonSetOptions,
  updateComparisonSet,
  type ComparisonSetCourseView,
  type ComparisonSetDetailView,
  type ComparisonSetOptionsView,
  type ComparisonSetWrite,
  type ComparisonSetWriteOutcome,
} from '../../api/leadership';
import { StateNotice } from '../../components/StateNotice';
import { copy, fillCopy } from '../../copy/leadershipComparisonSetCopy';
import './leadershipComparisonSets.css';

/**
 * The set-definition form, and the address that opens one set in it — E5-09.
 *
 * SPEC §5.1's one hard sentence about this screen is that "set-definition UI
 * makes invalid combinations impossible rather than erroring on them", and the
 * whole of this file is that sentence. There is no free text for a length and
 * none for a level: both are chosen from the lists
 * `GET /leadership/comparison-sets/options` answered with, and a course may be
 * chosen only while its level is the level the form is on. A person using this
 * form cannot express the combination the database refuses, so the refusal is
 * something the races reach — a course withdrawn while the form stood open, a
 * name somebody else took first — rather than something a reader meets on the
 * way to their first set.
 *
 * **What it deliberately does not do is validate.** The server owns every rule
 * about a set, and a second copy of one here would be right until the first time
 * either changed. The form holds no list of lengths, no list of levels and no
 * opinion about which courses belong together; it holds the three choices a
 * reader has made and the courses those choices leave available.
 *
 * **The form takes something away in two places, and says so in both.**
 * Changing the level keeps the chosen courses whose level still matches and
 * removes the rest, naming them. And opening a stored set whose membership this
 * form cannot draw — a course withdrawn or moved out of this reader's purview
 * while nobody was looking, or one stored against a level the set no longer
 * declares — removes those members as the form opens and counts them, because a
 * course this screen cannot offer is one the reader cannot see or uncheck, and a
 * member that survives invisibly into the saved body is a set nobody composed.
 * Dropping either quietly is the failure both notices exist to prevent.
 *
 * **The notice keeps every removal until the reader dismisses it.** A reader
 * arrowing through the level list changes the level once per keypress, and a
 * notice replaced on each change would lose the courses the first step removed
 * one keypress later, before anybody had read it. So each removal adds a
 * sentence and nothing but the dismiss control takes one away. The notice is a
 * polite live region, so a reader who cannot see it is told as it grows.
 *
 * **Focus moves to the form's heading when the form opens.** On the list page
 * the control that opened it has just vanished, and on the edit address the
 * form is what the page was waiting for; in both, a focus left where it was is
 * a focus on nothing.
 */

/** The list this form returns to, and the address that opens one set in it. */
export const COMPARISON_SETS_ROUTE = '/leadership/comparison-sets';
export const COMPARISON_SET_EDIT_ROUTE = '/leadership/comparison-sets/$setId';

/**
 * The landmark testid both leadership set addresses carry.
 *
 * Declared here and re-exported by the list, because the edit address is a page
 * of the same surface and a spec looking for "the comparison-set screen" should
 * find it at either address.
 */
export const LEADERSHIP_SETS_TESTID = 'pulse-leadership-comparison-sets';

/** Where a spec finds the form itself, as opposed to one of the page's states. */
export const COMPARISON_SET_FORM_TESTID = 'pulse-leadership-set-form';

/** Where a spec finds the notice that names the courses a level change removed. */
export const COMPARISON_SET_REMOVED_TESTID = 'pulse-leadership-set-removed';

/** Where a spec finds the sentence the API refused a save with. */
export const COMPARISON_SET_REFUSAL_TESTID = 'pulse-leadership-set-refusal';

const NAME_FIELD_ID = 'pulse-leadership-set-name';
const LENGTH_FIELD_ID = 'pulse-leadership-set-length';
const LEVEL_FIELD_ID = 'pulse-leadership-set-level';
const FORM_HEADING_ID = 'pulse-leadership-set-form-heading';
const SAVE_HELP_ID = 'pulse-leadership-set-save-help';

/**
 * The page heading both leadership set addresses carry, so a move between them
 * can put focus on the heading of the page it arrives at.
 */
export const PAGE_HEADING_ID = 'pulse-leadership-sets-heading';

/** The value a select carries while nothing has been chosen. */
const UNCHOSEN = '';

/**
 * What the form took out of the set, while the notice about it is on screen.
 *
 * Two shapes, because two different things are known. A level change removes
 * courses the form was offering a moment ago, so it can name them. A course
 * that is in the stored set and not in the options answer has no label
 * anywhere on this screen, so the notice counts rather than names — and it is
 * still a removal the reader is told about, because the alternative is a
 * member they cannot see being saved on their behalf.
 */
type Removal =
  | { readonly kind: 'level-changed'; readonly labels: readonly string[] }
  | { readonly kind: 'withdrawn'; readonly count: number };

/**
 * The member ids of `initial` this form can actually offer.
 *
 * **Filtered against the courses of the set's own level, not the whole
 * catalogue.** The picker only ever draws courses of the level the form is on,
 * so a stored member of some other level has no box either — it is as invisible
 * as a course that left the catalogue, and for the reader's purposes it is the
 * same fact. Filtering on catalogue membership alone would leave it in the
 * form's state, unrenderable and saved on a submit that never touched the
 * level, which is the defect this whole filter exists to stop.
 */
function membersStillOffered(
  options: ComparisonSetOptionsView,
  initial: ComparisonSetDetailView | null,
): readonly string[] {
  if (initial === null) return [];
  const offered = new Set(
    options.courses.filter((course) => course.level === initial.level).map((course) => course.id),
  );
  return initial.member_course_ids.filter((id) => offered.has(id));
}

export function ComparisonSetForm({
  options,
  initial,
  onSave,
  onCancel,
}: {
  readonly options: ComparisonSetOptionsView;
  /** The set being edited, or null when this form is defining a new one. */
  readonly initial?: ComparisonSetDetailView | null;
  readonly onSave: (write: ComparisonSetWrite) => Promise<ComparisonSetWriteOutcome>;
  readonly onCancel: () => void;
}): JSX.Element {
  const editing = initial ?? null;
  const [name, setName] = useState(editing?.name ?? '');
  const [length, setLength] = useState<number | null>(editing?.length_weeks ?? null);
  const [level, setLevel] = useState<string | null>(editing?.level ?? null);
  // **The set is filtered against the choice lists as the form opens**, and the
  // difference is announced rather than absorbed. A stored member the options
  // answer does not carry cannot be rendered, unchecked or reasoned about by
  // the person editing the set, so leaving it in the form's state would save a
  // member they never chose and could not see — invisible on the way in and
  // invisible on the way out. Lazy initialisers, so the filter runs once, on
  // the props the form opened with.
  const [members, setMembers] = useState<readonly string[]>(() =>
    membersStillOffered(options, editing),
  );
  const [removals, setRemovals] = useState<readonly Removal[]>(() => {
    const withdrawn =
      (editing?.member_course_ids.length ?? 0) - membersStillOffered(options, editing).length;
    return withdrawn === 0 ? [] : [{ kind: 'withdrawn', count: withdrawn }];
  });
  const [saving, setSaving] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // The courses this level leaves available. The filter is the form's whole
  // opinion about membership, and it runs on the level that is chosen now
  // rather than on the one the set was loaded with.
  const offered: readonly ComparisonSetCourseView[] =
    level === null ? [] : options.courses.filter((course) => course.level === level);

  function chooseLevel(chosen: string): void {
    const staying = options.courses.filter(
      (course) => course.level === chosen && members.includes(course.id),
    );
    const leaving = options.courses.filter(
      (course) => course.level !== chosen && members.includes(course.id),
    );
    setLevel(chosen);
    setMembers(staying.map((course) => course.id));
    // **A removal adds to the notice; a change that removes nothing leaves it
    // alone.** Every sentence in it stays true — those courses did leave the
    // set — so nothing but the reader's dismissal takes one away.
    if (leaving.length === 0) return;
    setRemovals((told) => [
      ...told,
      { kind: 'level-changed', labels: leaving.map((course) => course.label) },
    ]);
  }

  function toggleMember(courseId: string): void {
    setMembers((chosen) =>
      chosen.includes(courseId)
        ? chosen.filter((member) => member !== courseId)
        : [...chosen, courseId],
    );
  }

  const complete = name.trim().length > 0 && length !== null && level !== null;

  function submit(): void {
    if (!complete || saving) return;
    setSaving(true);
    setRefusal(null);
    void onSave({
      name: name.trim(),
      length_weeks: length,
      level,
      member_course_ids: members,
    }).then((outcome) => {
      setSaving(false);
      if (outcome.kind === 'saved') return;
      // Every refusal is shown in the API's own words. Where there is no
      // sentence — a network failure, a gateway with no body — the screen falls
      // back to its own, which says the save did not land and nothing else.
      setRefusal(
        outcome.kind === 'refused'
          ? (outcome.detail ?? copy('leadership_comparison_sets.save_unavailable'))
          : copy('leadership_comparison_sets.save_unavailable'),
      );
    });
  }

  return (
    <form
      className="pulse-set-form"
      data-testid={COMPARISON_SET_FORM_TESTID}
      aria-labelledby={FORM_HEADING_ID}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <h2 className="pulse-set-form-heading" id={FORM_HEADING_ID} ref={headingRef} tabIndex={-1}>
        {copy(
          editing === null
            ? 'leadership_comparison_sets.form_create_heading'
            : 'leadership_comparison_sets.form_edit_heading',
        )}
      </h2>

      <p className="pulse-set-field">
        <label className="pulse-set-label" htmlFor={NAME_FIELD_ID}>
          {copy('leadership_comparison_sets.name_label')}
        </label>
        <input
          className="pulse-set-input"
          id={NAME_FIELD_ID}
          type="text"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </p>

      <p className="pulse-set-field">
        <label className="pulse-set-label" htmlFor={LENGTH_FIELD_ID}>
          {copy('leadership_comparison_sets.length_label')}
        </label>
        <select
          className="pulse-set-input"
          id={LENGTH_FIELD_ID}
          value={length === null ? UNCHOSEN : String(length)}
          onChange={(event) => {
            setLength(event.target.value === UNCHOSEN ? null : Number(event.target.value));
          }}
        >
          <option value={UNCHOSEN}>{copy('leadership_comparison_sets.length_unchosen')}</option>
          {options.lengths.map((weeks) => (
            <option key={weeks} value={String(weeks)}>
              {fillCopy('leadership_comparison_sets.length_option', { weeks: String(weeks) })}
            </option>
          ))}
        </select>
      </p>

      <p className="pulse-set-field">
        <label className="pulse-set-label" htmlFor={LEVEL_FIELD_ID}>
          {copy('leadership_comparison_sets.level_label')}
        </label>
        <select
          className="pulse-set-input"
          id={LEVEL_FIELD_ID}
          value={level ?? UNCHOSEN}
          onChange={(event) => {
            if (event.target.value === UNCHOSEN) return;
            chooseLevel(event.target.value);
          }}
        >
          <option value={UNCHOSEN}>{copy('leadership_comparison_sets.level_unchosen')}</option>
          {options.levels.map((band) => (
            <option key={band} value={band}>
              {band}
            </option>
          ))}
        </select>
      </p>

      <fieldset className="pulse-set-members">
        <legend className="pulse-set-label">
          {copy('leadership_comparison_sets.members_label')}
        </legend>
        {/* The live region is always in the page, empty or not: a region that
            arrives together with its first sentence is one most screen readers
            never announce. */}
        <div role="status">
          {removals.length === 0 ? null : (
            <div className="pulse-set-removed" data-testid={COMPARISON_SET_REMOVED_TESTID}>
              {removals.map((removal, at) => (
                // The index is the identity: removals are only ever appended,
                // and all of them leave together.
                <p className="pulse-set-removed-body" key={at}>
                  {removalSentence(removal)}
                </p>
              ))}
              <button
                className="pulse-set-plain-button"
                type="button"
                onClick={() => {
                  setRemovals([]);
                }}
              >
                {copy('leadership_comparison_sets.members_removed_dismiss')}
              </button>
            </div>
          )}
        </div>
        {level === null ? (
          <p className="pulse-set-help">{copy('leadership_comparison_sets.members_await_level')}</p>
        ) : offered.length === 0 ? (
          <p className="pulse-set-help">{copy('leadership_comparison_sets.members_none')}</p>
        ) : (
          <ul className="pulse-set-member-list">
            {offered.map((course) => (
              <li key={course.id}>
                <label className="pulse-set-member">
                  <input
                    type="checkbox"
                    checked={members.includes(course.id)}
                    onChange={() => {
                      toggleMember(course.id);
                    }}
                  />
                  {course.label}
                </label>
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      {refusal === null ? null : (
        <p
          className="pulse-set-refusal"
          data-testid={COMPARISON_SET_REFUSAL_TESTID}
          role="alert"
        >
          {refusal}
        </p>
      )}

      {complete ? null : (
        <p className="pulse-set-help" id={SAVE_HELP_ID}>
          {copy('leadership_comparison_sets.save_incomplete')}
        </p>
      )}

      <p className="pulse-set-actions">
        <button
          className="pulse-set-button"
          type="submit"
          disabled={!complete || saving}
          // A disabled control says nothing about why; the sentence above does,
          // so the button points at it for as long as it is there.
          aria-describedby={complete ? undefined : SAVE_HELP_ID}
        >
          {copy(
            saving ? 'leadership_comparison_sets.saving' : 'leadership_comparison_sets.save',
          )}
        </button>
        <button className="pulse-set-plain-button" type="button" onClick={onCancel}>
          {copy('leadership_comparison_sets.cancel')}
        </button>
      </p>
    </form>
  );
}

/** The sentence one removal is told in. */
function removalSentence(removal: Removal): string {
  if (removal.kind === 'withdrawn') {
    return removal.count === 1
      ? copy('leadership_comparison_sets.members_withdrawn_one')
      : fillCopy('leadership_comparison_sets.members_withdrawn_many', {
          count: String(removal.count),
        });
  }
  return removal.labels.length === 1
    ? fillCopy('leadership_comparison_sets.members_removed_one', {
        labels: removal.labels.join(', '),
      })
    : fillCopy('leadership_comparison_sets.members_removed_many', {
        count: String(removal.labels.length),
        labels: removal.labels.join(', '),
      });
}

/** What the edit address has been able to read so far. */
type EditLoad =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | {
      readonly kind: 'ready';
      readonly options: ComparisonSetOptionsView;
      readonly set: ComparisonSetDetailView;
    };

/**
 * `/leadership/comparison-sets/$setId` — one set, open in the form.
 *
 * Two reads, because the form needs both the choice lists and the set: a form
 * built from the set alone could offer no courses, and one built from the
 * options alone would be a create form at an edit address. A refusal of either
 * is the page's state, shown in the API's words where it sent any.
 */
export function ComparisonSetEditRoute(): JSX.Element {
  const { setId } = useParams({ from: COMPARISON_SET_EDIT_ROUTE });
  const navigate = useNavigate();
  const [load, setLoad] = useState<EditLoad>({ kind: 'loading' });

  useEffect(() => {
    let live = true;
    void Promise.all([readComparisonSetOptions(), readComparisonSet(setId)]).then(
      ([optionsRead, setRead]) => {
        if (!live) return;
        if (optionsRead.kind === 'session-ended' || setRead.kind === 'session-ended') {
          setLoad({ kind: 'session-ended' });
          return;
        }
        if (optionsRead.kind !== 'options') {
          setLoad({ kind: 'error', detail: optionsRead.detail });
          return;
        }
        if (setRead.kind !== 'set') {
          setLoad({ kind: 'error', detail: setRead.detail });
          return;
        }
        setLoad({ kind: 'ready', options: optionsRead.options, set: setRead.set });
      },
    );
    return () => {
      live = false;
    };
  }, [setId]);

  // Leaving for the list takes every control on this page away, so focus goes
  // to the heading of the page that arrives: it names where the reader now is.
  function toTheList(): void {
    void navigate({ to: COMPARISON_SETS_ROUTE }).then(() => {
      document.getElementById(PAGE_HEADING_ID)?.focus();
    });
  }

  return (
    <main
      className="pulse-set-page"
      data-testid={LEADERSHIP_SETS_TESTID}
      aria-labelledby={PAGE_HEADING_ID}
    >
      <h1 className="pulse-set-title" id={PAGE_HEADING_ID}>
        {copy('leadership_comparison_sets.heading')}
      </h1>
      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_comparison_sets.form_loading')}
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
        <ComparisonSetForm
          options={load.options}
          initial={load.set}
          onSave={async (write) => {
            const outcome = await updateComparisonSet(load.set.id, write);
            if (outcome.kind === 'saved') toTheList();
            return outcome;
          }}
          onCancel={toTheList}
        />
      )}
    </main>
  );
}
