import { useId, useState, type ChangeEvent, type JSX } from 'react';

import {
  applyImport,
  dryRun,
  exportCsv,
  type AdminOutcome,
  type DiffView,
  type MappingDiffView,
  type PeopleDiffView,
} from '../../api/admin';
import type { Table } from '../../lib/adminTable';
import { copy, fillCopy } from '../../copy/adminPeople';
import type { Gate } from './AdminPage';

/** The file name each table exports under, less its suffix (`api/admin.py`'s `Content-Disposition`). */
const EXPORT_STEM: Readonly<Record<Table, string>> = {
  people: 'people',
  mappings: 'lead-mappings',
};

/** Where a spec finds the dry run's diff, and the control that applies it. */
export const IMPORT_DIFF_TESTID = 'pulse-admin-import-diff';
export const IMPORT_APPLY_TESTID = 'pulse-admin-import-apply';

type Held =
  | { readonly kind: 'idle' }
  | { readonly kind: 'checking' }
  // A dry run has answered: this is the only state the apply control exists in.
  | { readonly kind: 'dry'; readonly csv: string; readonly diff: DiffView }
  | { readonly kind: 'applying'; readonly csv: string; readonly diff: DiffView }
  // The apply was refused. The file is kept so a fresh dry run needs no second choosing.
  | { readonly kind: 'stale'; readonly csv: string; readonly detail: string }
  // The dry run itself was refused (a bad line): only another file helps.
  | { readonly kind: 'refused'; readonly detail: string };

/**
 * Export and import for one table (SPEC §6.3).
 *
 * **An import is always a dry run first.** Choosing a file sends it for a dry
 * run and shows the diff it answered; the apply control is **not rendered**
 * until that answer is in hand, and it sends the file with that answer's digest
 * and nothing else. A control that was present and disabled could still be
 * reached by a keyboard or a script, so its absence is the rule. When the
 * server refuses the apply because the data moved since the dry run, the
 * sentence it sent is shown and the apply control is gone again until a fresh
 * dry run has answered.
 */
export function ImportPanel({
  table,
  announce,
  onGate,
  onApplied,
}: {
  readonly table: Table;
  readonly announce: (message: string) => void;
  readonly onGate: (gate: Exclude<Gate, null>) => void;
  readonly onApplied: () => void;
}): JSX.Element {
  const [held, setHeld] = useState<Held>({ kind: 'idle' });
  const fileId = useId();

  /** Whether `answer` was one the page cannot go on from; if so, say so. */
  function gated(answer: AdminOutcome<unknown>): boolean {
    if (answer.kind === 'session-ended' || answer.kind === 'not-your-role') {
      onGate(answer.kind);
      return true;
    }
    return false;
  }

  async function dryRunOf(csv: string): Promise<void> {
    setHeld({ kind: 'checking' });
    announce(copy('admin_people.page.import_reading'));
    const answer: AdminOutcome<DiffView> = await (table === 'people'
      ? dryRun('people', csv)
      : dryRun('mappings', csv));
    if (gated(answer)) return;
    if (answer.kind === 'ok') {
      setHeld({ kind: 'dry', csv, diff: answer.value });
      announce(copy('admin_people.page.diff_heading'));
    } else if (answer.kind === 'refused') {
      setHeld({ kind: 'refused', detail: answer.detail });
      announce(answer.detail);
    } else {
      setHeld({ kind: 'idle' });
      announce(copy('admin_people.page.write_unavailable'));
    }
  }

  async function choose(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const input = event.target;
    const file = input.files?.[0];
    if (file === undefined) return;
    let csv: string;
    try {
      csv = await file.text();
    } catch {
      announce(copy('admin_people.page.import_unreadable'));
      return;
    } finally {
      // The same file chosen again must still raise a change.
      input.value = '';
    }
    await dryRunOf(csv);
  }

  async function apply(csv: string, diff: DiffView): Promise<void> {
    setHeld({ kind: 'applying', csv, diff });
    announce(copy('admin_people.page.import_applying'));
    const answer: AdminOutcome<DiffView> = await (table === 'people'
      ? applyImport('people', csv, diff.digest)
      : applyImport('mappings', csv, diff.digest));
    if (gated(answer)) return;
    if (answer.kind === 'ok') {
      setHeld({ kind: 'idle' });
      announce(fillCopy('admin_people.page.import_applied', { summary: summaryOf(answer.value) }));
      onApplied();
    } else if (answer.kind === 'refused') {
      setHeld({ kind: 'stale', csv, detail: answer.detail });
      announce(answer.detail);
    } else {
      setHeld({ kind: 'dry', csv, diff });
      announce(copy('admin_people.page.write_unavailable'));
    }
  }

  async function download(): Promise<void> {
    const answer = await exportCsv(table);
    if (gated(answer)) return;
    if (answer.kind !== 'ok') {
      announce(answer.kind === 'refused' ? answer.detail : copy('admin_people.page.write_unavailable'));
      return;
    }
    const url = URL.createObjectURL(new Blob([answer.value], { type: 'text/csv' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${EXPORT_STEM[table]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    announce(copy('admin_people.page.exported'));
  }

  return (
    <section className="pulse-admin-section" aria-labelledby={`${fileId}-heading`}>
      <h2 className="pulse-admin-subheading" id={`${fileId}-heading`}>
        {copy('admin_people.page.import_heading')}
      </h2>
      <p className="pulse-admin-help">{copy('admin_people.page.import_intro')}</p>
      <div className="pulse-admin-row">
        <label className="pulse-admin-label" htmlFor={fileId}>
          {copy('admin_people.page.import_choose')}
        </label>
        <input
          id={fileId}
          className="pulse-admin-input"
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => void choose(event)}
        />
        <button type="button" className="pulse-admin-button-plain" onClick={() => void download()}>
          {copy('admin_people.page.export')}
        </button>
      </div>

      {held.kind === 'dry' || held.kind === 'applying' ? (
        <div data-testid={IMPORT_DIFF_TESTID}>
          <DiffTables table={table} diff={held.diff} />
          <div className="pulse-admin-row">
            {held.kind === 'dry' ? (
              <button
                type="button"
                className="pulse-admin-button"
                data-testid={IMPORT_APPLY_TESTID}
                onClick={() => void apply(held.csv, held.diff)}
              >
                {copy('admin_people.page.import_apply')}
              </button>
            ) : null}
            {held.kind === 'dry' ? (
              <button
                type="button"
                className="pulse-admin-button-plain"
                onClick={() => {
                  setHeld({ kind: 'idle' });
                  announce(copy('admin_people.page.import_cancelled'));
                }}
              >
                {copy('admin_people.page.import_cancel')}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {held.kind === 'stale' ? (
        <div className="pulse-admin-row">
          <button
            type="button"
            className="pulse-admin-button"
            onClick={() => void dryRunOf(held.csv)}
          >
            {copy('admin_people.page.import_retry')}
          </button>
          <button
            type="button"
            className="pulse-admin-button-plain"
            onClick={() => {
              setHeld({ kind: 'idle' });
              announce(copy('admin_people.page.import_cancelled'));
            }}
          >
            {copy('admin_people.page.import_cancel')}
          </button>
        </div>
      ) : null}
    </section>
  );
}

function isMappingDiff(diff: DiffView): diff is MappingDiffView {
  return 'unmapped' in diff;
}

/** "2 added · 1 changed · …", the counts of what a diff holds. */
export function summaryOf(diff: DiffView): string {
  const parts = [
    fillCopy('admin_people.page.diff_summary_added', { count: String(diff.added.length) }),
    fillCopy('admin_people.page.diff_summary_changed', { count: String(diff.changed.length) }),
  ];
  if (isMappingDiff(diff)) {
    parts.push(
      fillCopy('admin_people.page.diff_summary_removed', { count: String(diff.removed.length) }),
      fillCopy('admin_people.page.diff_summary_unmapped', { count: String(diff.unmapped.length) }),
    );
  }
  return parts.join(' · ');
}

/** The diff as tables, each with a caption, so a screen reader reads rows and columns. */
function DiffTables({
  table,
  diff,
}: {
  readonly table: Table;
  readonly diff: DiffView;
}): JSX.Element {
  const empty =
    diff.added.length === 0 &&
    diff.changed.length === 0 &&
    (!isMappingDiff(diff) || (diff.removed.length === 0 && diff.unmapped.length === 0));
  return (
    <div className="pulse-admin-diff">
      <h3 className="pulse-admin-diff-heading">{copy('admin_people.page.diff_heading')}</h3>
      <p className="pulse-admin-diff-summary">{summaryOf(diff)}</p>
      {empty ? <p className="pulse-admin-help">{copy('admin_people.page.diff_nothing')}</p> : null}
      {table === 'people' ? (
        <PeopleDiffTables diff={diff as PeopleDiffView} />
      ) : (
        <MappingDiffTables diff={diff as MappingDiffView} />
      )}
    </div>
  );
}

function PeopleDiffTables({ diff }: { readonly diff: PeopleDiffView }): JSX.Element {
  return (
    <>
      {diff.added.length === 0 ? null : (
        <table className="pulse-admin-table">
          <caption>{copy('admin_people.page.diff_added_caption')}</caption>
          <thead>
            <tr>
              <th scope="col">{copy('admin_people.page.column_name')}</th>
              <th scope="col">{copy('admin_people.page.column_category')}</th>
            </tr>
          </thead>
          <tbody>
            {diff.added.map((person, index) => (
              <tr key={index}>
                <td>{person.name}</td>
                <td>{person.category}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {diff.changed.length === 0 ? null : (
        <table className="pulse-admin-table">
          <caption>{copy('admin_people.page.diff_changed_caption')}</caption>
          <thead>
            <tr>
              <th scope="col">{copy('admin_people.page.diff_column_before')}</th>
              <th scope="col">{copy('admin_people.page.diff_column_after')}</th>
            </tr>
          </thead>
          <tbody>
            {diff.changed.map((change) => (
              <tr key={change.person_id}>
                <td>
                  {change.before.name} · {change.before.category}
                </td>
                <td>
                  {change.after.name} · {change.after.category}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function MappingDiffTables({ diff }: { readonly diff: MappingDiffView }): JSX.Element {
  return (
    <>
      <MappingLinesTable caption={copy('admin_people.page.diff_added_caption')} lines={diff.added} />
      <MappingLinesTable
        caption={copy('admin_people.page.diff_removed_caption')}
        lines={diff.removed}
      />
      {diff.changed.length === 0 ? null : (
        <table className="pulse-admin-table">
          <caption>{copy('admin_people.page.diff_changed_caption')}</caption>
          <thead>
            <tr>
              <th scope="col">{copy('admin_people.page.column_course')}</th>
              <th scope="col">{copy('admin_people.page.diff_column_before')}</th>
              <th scope="col">{copy('admin_people.page.diff_column_after')}</th>
            </tr>
          </thead>
          <tbody>
            {diff.changed.map((change) => (
              <tr key={change.after.course_id}>
                <td>{change.after.course}</td>
                <td>{change.before.name}</td>
                <td>{change.after.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {diff.unmapped.length === 0 ? null : (
        <table className="pulse-admin-table">
          <caption>{copy('admin_people.page.diff_unmapped_caption')}</caption>
          <thead>
            <tr>
              <th scope="col">{copy('admin_people.page.column_course')}</th>
              <th scope="col">{copy('admin_people.page.diff_column_note')}</th>
            </tr>
          </thead>
          <tbody>
            {diff.unmapped.map((course) => (
              <tr key={course.course_id}>
                <td>{course.course}</td>
                <td>{course.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function MappingLinesTable({
  caption,
  lines,
}: {
  readonly caption: string;
  readonly lines: MappingDiffView['added'];
}): JSX.Element | null {
  if (lines.length === 0) return null;
  return (
    <table className="pulse-admin-table">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">{copy('admin_people.page.column_course')}</th>
          <th scope="col">{copy('admin_people.page.column_lead')}</th>
        </tr>
      </thead>
      <tbody>
        {lines.map((line) => (
          <tr key={line.course_id}>
            <td>{line.course}</td>
            <td>{line.name}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
