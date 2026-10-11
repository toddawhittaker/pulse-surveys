import { useEffect, useState, type JSX } from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';

import {
  readStudentResults,
  readStudentSurvey,
  type EnrolledSection,
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
 * The survey read is made beside the results one for two things the results do
 * not carry — the institution's time zone, which the date on the card is shown
 * in, and the course's label for the heading. Neither is needed to draw the
 * reply, so a failed survey read costs the page a date and a label, not a reply.
 */

/** The two addresses this page answers, relative to the router's `/app` mount. */
export const LATEST_RESULTS_ROUTE = '/student/sections/$sectionId/results';
export const WEEK_RESULTS_ROUTE = '/student/sections/$sectionId/weeks/$courseWeek/results';

const HEADING_ID = 'pulse-student-results-heading';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'read'; readonly answer: Exclude<ResultsRead, { kind: 'results' }> }
  | { readonly kind: 'results'; readonly results: StudentWeekResults; readonly week: number | null };

/** What the survey read adds: the zone and the section's label. */
interface Context {
  readonly timeZone: string | undefined;
  readonly section: EnrolledSection | undefined;
}

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
  const [context, setContext] = useState<Context>({ timeZone: undefined, section: undefined });

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
      setContext({
        timeZone: answer.view.institution_timezone,
        section: answer.view.sections.find((it) => it.section_id === sectionId),
      });
    });
    return () => {
      live = false;
    };
  }, [sectionId]);

  return (
    <main className="pulse-survey" data-testid="pulse-student-results" aria-labelledby={HEADING_ID}>
      <h1 id={HEADING_ID}>{copy('student_results.heading')}</h1>
      {context.section === undefined ? null : (
        <p className="pulse-section-instructors">{context.section.course_label}</p>
      )}
      <PulseDivider />
      <Body load={load} timeZone={context.timeZone} onSelectWeek={onSelectWeek} />
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
        {copy('student_results.loading')}
      </p>
    );
  }
  if (load.kind === 'read') {
    if (load.answer.kind === 'session-ended') {
      return (
        <StateNotice
          variant="flat"
          title={copy('student_results.session_ended_title')}
          body={copy('student_results.session_ended_body')}
        />
      );
    }
    return (
      <StateNotice
        variant="flat"
        body={copy(
          load.answer.kind === 'nothing'
            ? 'student_results.nothing_to_show'
            : 'student_results.unavailable',
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
          <p className="pulse-eyebrow">{fillCopy('student_results.week_label', { week: String(current) })}</p>
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
    return <StateNotice variant="flat" body={copy('student_results.awaiting')} />;
  }
  if (results.state === 'unanswered' || results.response === null) {
    return <StateNotice variant="flat" body={copy('student_results.unanswered')} />;
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
