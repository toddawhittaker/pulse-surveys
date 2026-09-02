import type { JSX } from 'react';

import { StudentWeeklySurvey } from './StudentWeeklySurvey';

/**
 * The student area — SPEC §13's `routes/student/`, which that tree describes as
 * "survey form, results + response".
 *
 * It was an empty landing view through E1 ("E2 builds the weekly survey that
 * goes here"); this is that survey. The results view is E8's and joins this
 * route when there is a published instructor response to show.
 *
 * The exported name does not change: `router.tsx` maps `/student` to
 * `StudentLanding`, and what the route table needs to say is which component
 * answers which path.
 */
export function StudentLanding(): JSX.Element {
  return <StudentWeeklySurvey />;
}
