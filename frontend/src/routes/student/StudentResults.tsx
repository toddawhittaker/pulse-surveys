import { useEffect, useState, type JSX } from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';

import {
  readStudentResults,
  readStudentSurvey,
  type ResultsRead,
  type StudentWeekResults,
} from '../../api/student';
import { PulseDivider } from '../../components/PulseDivider';
import { ResponseCard } from '../../components/ResponseCard';
import { StateNotice } from '../../components/StateNotice';
import { WeekNav } from '../../components/WeekNav';
import { copy, fillCopy } from '../../copy/studentResults';

/**
 * SPEC §7.6's `StudentResults` — the shell: one section's reply for one
 * published week, and the way back through the published weeks (SPEC §5.4).
 *
 * **The response leads the page.** Aggregates, comments and the small-group
 * notice are a later ticket's; this page leaves room for them and shows none.
 *
 * **The page asks and draws.** Which weeks exist, which state the week is in and
 * who wrote the reply are the API's answers; a week the API refuses is the same
 * single calm sentence as any other refusal, and nothing here distinguishes
 * "not yours" from "not yet" because the server does not.
 *
 * **`awaiting` is a closed door.** One sentence: no number, date, countdown,
 * name or response text, because the week is held and anything more would tease
 * it.
 *
 * The survey read is made beside the results one for the one thing the results
 * do not carry: the institution's time zone, which the date on the card is shown
 * in. A failed survey read costs the card its date, not the page its reply.
 * The page names no course: a course label carries a number, and `awaiting` may
 * show none.
 */

/** The two addresses this page answers, relative to the router's `/app` mount. */
export const LATEST_RESULTS_ROUTE = '/student/sections/$sectionId/results';
export const WEEK_RESULTS_ROUTE = '/student/sections/$sectionId/weeks/$courseWeek/results';

const HEADING_ID = 'pulse-student-results-heading';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'read'; readonly answer: Exclude<ResultsRead, { kind: 'results' }> }
  | { readonly kind: 'results'; readonly results: StudentWeekResults; readonly week: number | null };

/** A course week from an address, or `null` for anything that is not a positive whole number. */
function weekOfAddress(raw: string | undefined): number | null | undefined {
  if (raw === undefined) return undefined;
  const asked = Number(raw);
  return Number.isInteger(asked) && asked > 0 ? asked : null;
}

export function StudentResults({
  sectionId,
  courseWeek,
  onSelectWeek,
}: {
  readonly sectionId: string;
  /** `undefined` opens the latest published week; `null` is an address that names no week. */
  readonly courseWeek: number | null | undefined;
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [timeZone, setTimeZone] = useState<string | undefined>(undefined);

  useEffect(() => {
    let live = true;
    if (courseWeek === null) {
      // An address naming no week asks nothing of the API.
      void Promise.resolve().then(() => {
        if (live) setLoad({ kind: 'read', answer: { kind: 'nothing' } });
      });
      return () => {
        live = false;
      };
    }
    void readStudentResults(sectionId, courseWeek).then((answer) => {
      if (!live) return;
      setLoad(
        answer.kind === 'results'
          ? { kind: 'results', results: answer.results, week: courseWeek ?? null }
          : { kind: 'read', answer },
      );
    });
    return () => {
      live = false;
    };
  }, [sectionId, courseWeek]);

  useEffect(() => {
    let live = true;
    void readStudentSurvey().then((answer) => {
      if (!live || answer.kind !== 'view') return;
      setTimeZone(answer.view.institution_timezone);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <main className="pulse-survey" data-testid="pulse-student-results" aria-labelledby={HEADING_ID}>
      <h1 id={HEADING_ID}>{copy('student_survey.results_heading')}</h1>
      <PulseDivider />
      <Body load={load} timeZone={timeZone} onSelectWeek={onSelectWeek} />
    </main>
  );
}

function Body({
  load,
  timeZone,
  onSelectWeek,
}: {
  readonly load: Load;
  readonly timeZone: string | undefined;
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  if (load.kind === 'loading') {
    return (
      <p className="pulse-survey-status" role="status">
        {copy('student_survey.results_loading')}
      </p>
    );
  }
  if (load.kind === 'read') {
    if (load.answer.kind === 'session-ended') {
      return (
        <StateNotice
          variant="flat"
          title={copy('student_survey.results_session_ended_title')}
          body={copy('student_survey.results_session_ended_body')}
        />
      );
    }
    return (
      <StateNotice
        variant="flat"
        body={copy(
          load.answer.kind === 'nothing'
            ? 'student_survey.results_nothing_to_show'
            : 'student_survey.results_unavailable',
        )}
      />
    );
  }

  const { results } = load;
  // The week the reply belongs to is the one asked for; for "the latest" it is
  // the last published week, which the payload lists in ascending order.
  const current = load.week ?? results.published_weeks.at(-1) ?? null;
  return (
    <>
      {current === null ? null : (
        <div className="pulse-results-week">
          {/* A held week shows no number, not even its own week's. */}
          {results.state === 'awaiting' ? null : (
            <p className="pulse-eyebrow">
              {fillCopy('student_survey.results_week_label', { week: String(current) })}
            </p>
          )}
          <WeekNav
            publishedWeeks={results.published_weeks}
            currentWeek={current}
            onSelectWeek={onSelectWeek}
          />
        </div>
      )}
      <Reply results={results} timeZone={timeZone} />
    </>
  );
}

function Reply({
  results,
  timeZone,
}: {
  readonly results: StudentWeekResults;
  readonly timeZone: string | undefined;
}): JSX.Element {
  if (results.state === 'awaiting') {
    return <StateNotice variant="flat" body={copy('student_survey.results_awaiting')} />;
  }
  if (results.state === 'unanswered' || results.response === null) {
    return <StateNotice variant="flat" body={copy('student_survey.results_unanswered')} />;
  }
  return (
    <ResponseCard
      text={results.response.text}
      authorName={results.response.author_name}
      authorRole={results.response.author_role}
      publishedAt={results.response.published_at}
      timeZone={timeZone}
    />
  );
}

/** Route glue: the address in, a navigation out. */
export function StudentResultsRoute(): JSX.Element {
  const { sectionId, courseWeek } = useParams({ strict: false });
  const navigate = useNavigate();
  return (
    <StudentResults
      key={`${sectionId ?? ''}:${courseWeek ?? 'latest'}`}
      sectionId={sectionId ?? ''}
      courseWeek={weekOfAddress(courseWeek)}
      onSelectWeek={(week) => {
        void navigate({
          to: WEEK_RESULTS_ROUTE,
          params: { sectionId: sectionId ?? '', courseWeek: String(week) },
        });
      }}
    />
  );
}
