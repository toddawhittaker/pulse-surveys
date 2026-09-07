import type { JSX } from 'react';

import { copy } from './instructorReportTrendCopy';
import './instructorReportTrend.css';

/**
 * The instructor report's week navigation — ticket E4-08.
 *
 * "Week navigation pages across published weeks" (SPEC §5.1), and a published
 * week is a course week whose survey window has closed. Which weeks those are
 * is the report payload's `published_weeks`, so this control asks nothing and
 * computes nothing: it steps to the neighbouring **published** week, which is
 * not always the neighbouring number. A section whose week 3 opened late has a
 * gap in that list, and a control that stepped by one would offer a week the
 * report cannot answer for.
 *
 * The treatment is the prototype's (`design/InstructorMondayReport.dc.html`):
 * two small mono buttons beside the week eyebrow, back and forward, each
 * disabled at the end of the list rather than hidden — a control that
 * disappears moves everything beside it. Each button is named in words, so what
 * a screen reader announces is "Previous week" rather than an arrow.
 *
 * **Props in, DOM out.** The weeks arrive as a prop and the choice leaves
 * through `onSelectWeek`; this component fetches nothing, stores nothing and
 * knows nothing about routing. E4-11 is the ticket that wires it to the page.
 */
export function WeekNav({
  publishedWeeks,
  currentWeek,
  onSelectWeek,
}: {
  /** Every course week whose survey window has closed, as the payload lists them. */
  readonly publishedWeeks: readonly number[];
  /** The week the report is showing. */
  readonly currentWeek: number;
  /** Told which published week the reader asked for. */
  readonly onSelectWeek: (week: number) => void;
}): JSX.Element {
  const weeks = [...publishedWeeks].sort((left, right) => left - right);
  const previous = weeks.filter((week) => week < currentWeek).at(-1) ?? null;
  const next = weeks.find((week) => week > currentWeek) ?? null;

  return (
    <nav className="pulse-week-nav" aria-label={copy('instructor_report_trend.week_nav_label')}>
      <button
        type="button"
        className="pulse-week-nav-button"
        aria-label={copy('instructor_report_trend.week_nav_previous')}
        disabled={previous === null}
        onClick={() => {
          if (previous !== null) onSelectWeek(previous);
        }}
      >
        {copy('instructor_report_trend.week_nav_previous_glyph')}
      </button>
      <button
        type="button"
        className="pulse-week-nav-button"
        aria-label={copy('instructor_report_trend.week_nav_next')}
        disabled={next === null}
        onClick={() => {
          if (next !== null) onSelectWeek(next);
        }}
      >
        {copy('instructor_report_trend.week_nav_next_glyph')}
      </button>
    </nav>
  );
}
