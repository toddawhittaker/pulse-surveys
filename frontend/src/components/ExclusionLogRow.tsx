import type { JSX } from 'react';

import type { LogRowView } from '../api/leadership';
import { copy, fillCopy, type LeadershipModerationCopyKey } from '../copy/leadershipModerationCopy';
import './exclusionLogRow.css';

/**
 * One decision in the exclusion log — SPEC §7.6's `ExclusionLogRow`, drawn from
 * `design/ExclusionLogRow.dc.html`.
 *
 * The mockup's four columns are kept, with one change SPEC §5.2 makes: where the
 * mockup prints the instructor's name, this prints **the role the decision was
 * made under**, because the log names a role and never a person. The other
 * three are the date, the excerpt, and the status with the reason under it. The
 * status line carries the decision's direction as well as the flag, because the
 * log shows keeps as plainly as exclusions.
 *
 * **The date is the date the server sent, as it sent it** (`YYYY-MM-DD`, in the
 * institution's zone). No `Date` is built from it, so no zone can move it a day
 * and no time of day can appear; the year stays because a record read across
 * terms needs it.
 *
 * **An undo reads as a reversal** (E6-09). Its row carries the state the undo
 * restored, so without `is_undo` an undone keep would read as a second
 * exclusion. The status line names it "Undo, back to …" instead.
 *
 * **A row with no excerpt says so.** The server withholds the excerpt when the
 * comment's own report does not show it (ADR 0190), and an empty quotation mark
 * would look like a comment with no words.
 *
 * **A row with no date says so too.** On a withheld row the server also drops
 * the date and the reason for every reader but the person who decided (ADR
 * 0206), because a reason beside a date would place the comment in its week.
 * The date column then reads "No date" rather than an empty cell, and the
 * reason line is left out, as it is for a decision made without one.
 */
export function ExclusionLogRow({ row }: { readonly row: LogRowView }): JSX.Element {
  return (
    <li className="pulse-log-row">
      {row.decided_on == null ? (
        <span className="pulse-log-row__date">{copy('leadership_moderation.log.no_date')}</span>
      ) : (
        <time className="pulse-log-row__date" dateTime={row.decided_on}>
          {row.decided_on}
        </time>
      )}
      <span className="pulse-log-row__role">{copy(ROLE_WORDS[row.decided_as])}</span>
      <span className="pulse-log-row__body">
        <span className="pulse-log-row__section">{row.section_label}</span>
        {row.excerpt == null ? (
          <span className="pulse-log-row__no-excerpt">
            {copy('leadership_moderation.log.no_excerpt')}
          </span>
        ) : (
          <q className="pulse-log-row__excerpt">{row.excerpt}</q>
        )}
      </span>
      <span className="pulse-log-row__outcome">
        <span className="pulse-log-row__status" data-flagged={row.flagged ? 'true' : 'false'}>
          {fillCopy('leadership_moderation.log.status', {
            decision: copy(
              row.is_undo ? UNDO_WORDS[row.decision] : DECISION_WORDS[row.decision],
            ),
            flag: copy(
              row.flagged
                ? 'leadership_moderation.log.ai_flagged'
                : 'leadership_moderation.log.unflagged',
            ),
          })}
        </span>
        {row.reason == null ? null : <span className="pulse-log-row__reason">{row.reason}</span>}
      </span>
    </li>
  );
}

/**
 * The word for a decision's stored state. A decision leaves only `EXCLUDED` or
 * `KEPT`; the other two states reach the log only on an undo, so they have no
 * word of their own here and fall back to the undo's.
 */
const DECISION_WORDS: Readonly<Record<LogRowView['decision'], LeadershipModerationCopyKey>> = {
  EXCLUDED: 'leadership_moderation.log.excluded',
  KEPT: 'leadership_moderation.log.kept',
  FLAGGED_COLLAPSED: 'leadership_moderation.log.undone_to_flagged',
  PUBLISHED: 'leadership_moderation.log.undone_to_published',
};

/** An undo, named by the state it restored, so it reads as a reversal. */
const UNDO_WORDS: Readonly<Record<LogRowView['decision'], LeadershipModerationCopyKey>> = {
  EXCLUDED: 'leadership_moderation.log.undone_to_excluded',
  KEPT: 'leadership_moderation.log.undone_to_kept',
  FLAGGED_COLLAPSED: 'leadership_moderation.log.undone_to_flagged',
  PUBLISHED: 'leadership_moderation.log.undone_to_published',
};

/** The plain word for each stored role token. */
const ROLE_WORDS: Readonly<Record<LogRowView['decided_as'], LeadershipModerationCopyKey>> = {
  INSTRUCTOR: 'leadership_moderation.log.role_instructor',
  LEAD_FACULTY: 'leadership_moderation.log.role_lead_faculty',
  CHAIR: 'leadership_moderation.log.role_chair',
};
