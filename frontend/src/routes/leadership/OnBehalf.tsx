import { useEffect, useState, type JSX } from 'react';

import { Link, useParams } from '@tanstack/react-router';

import {
  readOnBehalfWeek,
  requestOnBehalfCheck,
  requestOnBehalfDraft,
  writeOnBehalfResponse,
  type OnBehalfRead,
  type OnBehalfStreamView,
  type OnBehalfWeekView,
} from '../../api/leadership';
import { AiPanel } from '../../components/AiPanel';
import { InstructorResponse, type ResponseActions } from '../../components/InstructorResponse';
import { RatingHistogram, type RatingDistribution } from '../../components/RatingHistogram';
import { StateNotice } from '../../components/StateNotice';
import { copy as statCopy } from '../../copy/instructorReportStatCopy';
import { copy, fillCopy } from '../../copy/leadershipResponseCopy';
import { ON_BEHALF_ROUTE, RESPONSES_OWED_ROUTE } from './ResponsesOwed';
import { ResponseRefusal } from './ResponseRefusal';
import './leadershipComparisonSets.css';
import './leadershipResponse.css';

/** Where a spec finds the page. */
export const ON_BEHALF_TESTID = 'pulse-leadership-on-behalf';

const HEADING_ID = 'pulse-on-behalf-heading';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'not-found' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | { readonly kind: 'week'; readonly week: OnBehalfWeekView };

/**
 * `/leadership/sections/:sectionId/weeks/:courseWeek/on-behalf` — a lead or chair
 * responds for a section whose instructor has not (SPEC §5.3, §5.6).
 *
 * **The page reads what the server stores and shows no comment.** Each stream is
 * its summary, or a calm line where none is served, and its rating
 * distribution. The composer is the instructor's own, pointed at the on-behalf
 * doors, so the card students will see carries the reader's name and role.
 *
 * **Every refusal is the one 404**, which renders as the not-found state and
 * names nothing of the section: the server gives this page no way to tell a
 * taught section from a sibling course, and it does not try.
 */
export function OnBehalfRoute(): JSX.Element {
  const params = useParams({ from: ON_BEHALF_ROUTE });
  // A week that is not a whole number is an address nothing opens; it gets the
  // not-found state without a call.
  const courseWeek = /^\d+$/.test(params.courseWeek) ? Number(params.courseWeek) : null;
  return <OnBehalfPage key={`${params.sectionId}#${params.courseWeek}`} sectionId={params.sectionId} courseWeek={courseWeek} />;
}

/** The page over an already-read address; a spec mounts this without a router. */
export function OnBehalfPage({
  sectionId,
  courseWeek,
}: {
  readonly sectionId: string;
  readonly courseWeek: number | null;
}): JSX.Element {
  const [read, setLoad] = useState<Load>({ kind: 'loading' });

  useEffect(() => {
    if (courseWeek === null) return;
    let live = true;
    void readOnBehalfWeek(sectionId, courseWeek).then((answer) => {
      if (live) setLoad(loadFrom(answer));
    });
    return () => {
      live = false;
    };
  }, [sectionId, courseWeek]);

  const load: Load = courseWeek === null ? { kind: 'not-found' } : read;

  return (
    <main className="pulse-set-page" data-testid={ON_BEHALF_TESTID} aria-labelledby={HEADING_ID}>
      <h1 className="pulse-set-title" id={HEADING_ID}>
        {copy('leadership_response.on_behalf.heading')}
      </h1>

      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_response.on_behalf.loading')}
        </p>
      ) : load.kind === 'session-ended' || load.kind === 'not-your-role' ? (
        <ResponseRefusal kind={load.kind} />
      ) : load.kind === 'not-found' ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_response.on_behalf.not_found_title')}
          body={copy('leadership_response.on_behalf.not_found_body')}
        >
          <p className="pulse-set-row-actions">
            <Link className="pulse-set-link" to={RESPONSES_OWED_ROUTE}>
              {copy('leadership_response.on_behalf.back')}
            </Link>
          </p>
        </StateNotice>
      ) : load.kind === 'error' ? (
        <StateNotice
          variant="flat"
          body={load.detail ?? copy('leadership_response.on_behalf.unavailable')}
        />
      ) : (
        <>
          <p className="pulse-set-intro">
            {fillCopy('leadership_response.on_behalf.week', {
              section: load.week.section_label,
              week: String(load.week.course_week),
            })}
          </p>
          <p className="pulse-set-intro">{copy('leadership_response.on_behalf.intro')}</p>
          {load.week.streams.map((stream) => (
            <StreamBlock key={stream.stream} stream={stream} />
          ))}
          <InstructorResponse
            onBehalf
            initial={{ state: 'unanswered', response: null }}
            actions={actionsFor(sectionId, load.week.course_week)}
          />
          <p className="pulse-set-row-actions">
            <Link className="pulse-set-link" to={RESPONSES_OWED_ROUTE}>
              {copy('leadership_response.on_behalf.back')}
            </Link>
          </p>
        </>
      )}
    </main>
  );
}

/** The composer's four calls, pointed at the on-behalf doors of one section-week. */
function actionsFor(sectionId: string, courseWeek: number): ResponseActions {
  return {
    draft: () => requestOnBehalfDraft(sectionId, courseWeek),
    check: (draft) => requestOnBehalfCheck(sectionId, courseWeek, draft),
    publish: (write) => writeOnBehalfResponse('POST', sectionId, courseWeek, write),
    edit: (write) => writeOnBehalfResponse('PUT', sectionId, courseWeek, write),
  };
}

/** One stream: its stored summary (or a calm line), the response count, the ratings. */
function StreamBlock({ stream }: { readonly stream: OnBehalfStreamView }): JSX.Element {
  const title = statCopy(
    stream.stream === 'instructor'
      ? 'instructor_report_stats.instructor_stream'
      : 'instructor_report_stats.course_stream',
  );
  const distribution: RatingDistribution = {
    '1': stream.rating_distribution['1'] ?? 0,
    '2': stream.rating_distribution['2'] ?? 0,
    '3': stream.rating_distribution['3'] ?? 0,
    '4': stream.rating_distribution['4'] ?? 0,
    '5': stream.rating_distribution['5'] ?? 0,
  };
  return (
    <section className="pulse-on-behalf-stream" aria-label={title}>
      {stream.summary_text === null ? (
        <p className="pulse-set-intro">{copy('leadership_response.on_behalf.no_summary')}</p>
      ) : (
        <AiPanel heading={title} text={stream.summary_text} responseCount={stream.response_count} />
      )}
      <p className="pulse-on-behalf-count">
        {stream.response_count === 1
          ? copy('leadership_response.on_behalf.responses_one')
          : fillCopy('leadership_response.on_behalf.responses', {
              count: String(stream.response_count),
            })}
      </p>
      <RatingHistogram stream={stream.stream} distribution={distribution} />
    </section>
  );
}

/** What a read of the week means for the page. */
function loadFrom(read: OnBehalfRead): Load {
  if (read.kind === 'unavailable') return { kind: 'error', detail: read.detail };
  if (read.kind === 'week') return { kind: 'week', week: read.week };
  return { kind: read.kind };
}
