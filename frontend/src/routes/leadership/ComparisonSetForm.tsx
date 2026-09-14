import { useEffect, useState, type JSX } from 'react';

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
 * **Changing the level in front of chosen courses is the one moment the form
 * takes something away**, and it says so. The courses whose level still matches
 * stay chosen; the rest leave, and a notice names how many left and which, until
 * the reader dismisses it or changes the level again. The alternative — dropping
 * them quietly — submits a set the reader did not compose, or asks the server to
 * refuse a body the form built.
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
const PAGE_HEADING_ID = 'pulse-leadership-sets-heading';

/** The value a select carries while nothing has been chosen. */
const UNCHOSEN = '';

/** What a level change took away, while the notice about it is still on screen. */
interface Removal {
  readonly labels: readonly string[];
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
  const [members, setMembers] = useState<readonly string[]>(editing?.member_course_ids ?? []);
  const [removal, setRemoval] = useState<Removal | null>(null);
  const [saving, setSaving] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

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
    // **The notice is replaced on every level change, never accumulated.** A
    // second change with nothing to remove clears the first change's sentence,
    // which would otherwise stand over a form it is no longer true of.
    setRemoval(leaving.length === 0 ? null : { labels: leaving.map((course) => course.label) });
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
      <h2 className="pulse-set-form-heading" id={FORM_HEADING_ID}>
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
        {removal === null ? null : (
          <div className="pulse-set-removed" data-testid={COMPARISON_SET_REMOVED_TESTID}>
            <p className="pulse-set-removed-body">
              {removal.labels.length === 1
                ? fillCopy('leadership_comparison_sets.members_removed_one', {
                    labels: removal.labels.join(', '),
                  })
                : fillCopy('leadership_comparison_sets.members_removed_many', {
                    count: String(removal.labels.length),
                    labels: removal.labels.join(', '),
                  })}
            </p>
            <button
              className="pulse-set-plain-button"
              type="button"
              onClick={() => {
                setRemoval(null);
              }}
            >
              {copy('leadership_comparison_sets.members_removed_dismiss')}
            </button>
          </div>
        )}
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
        <p className="pulse-set-help">{copy('leadership_comparison_sets.save_incomplete')}</p>
      )}

      <p className="pulse-set-actions">
        <button className="pulse-set-button" type="submit" disabled={!complete || saving}>
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

  function toTheList(): void {
    void navigate({ to: COMPARISON_SETS_ROUTE });
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
