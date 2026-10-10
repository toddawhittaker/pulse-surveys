import { useEffect, useState, type JSX } from 'react';

import { readExclusionLog, type ExclusionLogRead, type LogRowView } from '../../api/leadership';
import { ExclusionLogRow } from '../../components/ExclusionLogRow';
import { StateNotice } from '../../components/StateNotice';
import { copy } from '../../copy/leadershipModerationCopy';
import './leadershipComparisonSets.css';
import './leadershipModeration.css';

/** The address of the exclusion log, under the leadership area. */
export const EXCLUSION_LOG_ROUTE = '/leadership/exclusion-log';

/** Where a spec finds the page. */
export const EXCLUSION_LOG_TESTID = 'pulse-leadership-exclusion-log';

/** Where a spec finds the rows, as opposed to one of the page's states. */
export const EXCLUSION_LOG_LIST_TESTID = 'pulse-leadership-exclusion-log-list';

const HEADING_ID = 'pulse-exclusion-log-heading';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | { readonly kind: 'log'; readonly rows: readonly LogRowView[] };

/**
 * `/leadership/exclusion-log` — every exclusion and keep made inside the
 * reader's own grant (SPEC §5.2).
 *
 * **The rows keep the server's order**, newest decision first. Nothing here
 * sorts, groups or counts them: a log ordered by how often somebody excluded,
 * or grouped by instructor, would be a ranking (SPEC §4.1 item 4). Each row
 * names the role a decision was made under and never a person.
 */
export function ExclusionLogRoute(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });

  useEffect(() => {
    let live = true;
    void readExclusionLog().then((read) => {
      if (live) setLoad(loadFrom(read));
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <main
      className="pulse-set-page"
      data-testid={EXCLUSION_LOG_TESTID}
      aria-labelledby={HEADING_ID}
    >
      <h1 className="pulse-set-title" id={HEADING_ID}>
        {copy('leadership_moderation.log.heading')}
      </h1>
      <p className="pulse-set-intro">{copy('leadership_moderation.log.intro')}</p>

      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_moderation.log.loading')}
        </p>
      ) : load.kind === 'session-ended' ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_moderation.session_ended_title')}
          body={copy('leadership_moderation.session_ended_body')}
        />
      ) : load.kind === 'error' ? (
        <StateNotice
          variant="flat"
          body={load.detail ?? copy('leadership_moderation.log.unavailable')}
        />
      ) : load.rows.length === 0 ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_moderation.log.empty_title')}
          body={copy('leadership_moderation.log.empty_body')}
        />
      ) : (
        <ul
          className="pulse-moderation-log"
          data-testid={EXCLUSION_LOG_LIST_TESTID}
          aria-label={copy('leadership_moderation.log.list_label')}
        >
          {load.rows.map((row, index) => (
            // The wire gives a row no key of its own, and the list is never
            // reordered once read, so its position is a stable key.
            <ExclusionLogRow key={index} row={row} />
          ))}
        </ul>
      )}
    </main>
  );
}

/** What a read of the log means for the page. A refusal is never the empty state. */
function loadFrom(read: ExclusionLogRead): Load {
  if (read.kind === 'session-ended') return { kind: 'session-ended' };
  if (read.kind === 'unavailable') return { kind: 'error', detail: read.detail };
  return { kind: 'log', rows: read.rows };
}
