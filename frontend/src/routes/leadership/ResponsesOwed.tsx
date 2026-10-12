import { useEffect, useState, type JSX } from 'react';

import { Link } from '@tanstack/react-router';

import { readResponsesOwed, type OwedWeekView, type ResponsesOwedRead } from '../../api/leadership';
import { StateNotice } from '../../components/StateNotice';
import { copy, fillCopy } from '../../copy/leadershipResponseCopy';
import { ResponseRefusal } from './ResponseRefusal';
import './leadershipComparisonSets.css';
import './leadershipResponse.css';
import { ON_BEHALF_ROUTE } from '../paths';


/** Where a spec finds the page. */
export const RESPONSES_OWED_TESTID = 'pulse-leadership-responses-owed';

/** Where a spec finds the list itself, as opposed to one of the page's states. */
export const RESPONSES_OWED_LIST_TESTID = 'pulse-leadership-responses-owed-list';


const HEADING_ID = 'pulse-responses-owed-heading';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | { readonly kind: 'owed'; readonly weeks: readonly OwedWeekView[] };

/**
 * `/leadership/responses-owed` — the section-weeks in the reader's courses whose
 * required response is 48 hours or more past report open (SPEC §5.6 rule 4).
 *
 * **Each row is the section's label and the course week, and a way in once the
 * on-behalf door is open.** No instructor name, no count and no ordering of
 * the server's: this is a list of work for the reader, not a ranking of anyone
 * (SPEC §4.1 item 4). The words say a response is owed.
 */
export function ResponsesOwedRoute(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });

  useEffect(() => {
    let live = true;
    void readResponsesOwed().then((read) => {
      if (live) setLoad(loadFrom(read));
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="pulse-set-page" data-testid={RESPONSES_OWED_TESTID} aria-labelledby={HEADING_ID}>
      <h1 className="pulse-set-title" id={HEADING_ID}>
        {copy('leadership_response.owed.heading')}
      </h1>
      <p className="pulse-set-intro">{copy('leadership_response.owed.intro')}</p>

      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_response.owed.loading')}
        </p>
      ) : load.kind === 'session-ended' || load.kind === 'not-your-role' ? (
        <ResponseRefusal kind={load.kind} />
      ) : load.kind === 'error' ? (
        <StateNotice variant="flat" body={load.detail ?? copy('leadership_response.owed.unavailable')} />
      ) : load.weeks.length === 0 ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_response.owed.empty_title')}
          body={copy('leadership_response.owed.empty_body')}
        />
      ) : (
        <ul
          className="pulse-owed-list"
          data-testid={RESPONSES_OWED_LIST_TESTID}
          aria-label={copy('leadership_response.owed.list_label')}
        >
          {load.weeks.map((owed) => (
            <li className="pulse-owed-item" key={`${owed.section_id}#${String(owed.course_week)}`}>
              <p className="pulse-owed-section">{owed.section_label}</p>
              <p className="pulse-owed-week">
                {fillCopy('leadership_response.owed.week', { week: String(owed.course_week) })}
              </p>
              {owed.on_behalf_open ? (
                <p className="pulse-set-row-actions">
                  <Link
                    className="pulse-set-link"
                    to={ON_BEHALF_ROUTE}
                    params={{ sectionId: owed.section_id, courseWeek: String(owed.course_week) }}
                    aria-label={fillCopy('leadership_response.owed.respond_aria', {
                      section: owed.section_label,
                      week: String(owed.course_week),
                    })}
                  >
                    {copy('leadership_response.owed.respond')}
                  </Link>
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

/** What a read of the list means for the page. */
function loadFrom(read: ResponsesOwedRead): Load {
  if (read.kind === 'session-ended') return { kind: 'session-ended' };
  if (read.kind === 'not-your-role') return { kind: 'not-your-role' };
  if (read.kind === 'unavailable') return { kind: 'error', detail: read.detail };
  return { kind: 'owed', weeks: read.weeks };
}
