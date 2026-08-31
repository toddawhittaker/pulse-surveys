import type { JSX } from 'react';

import { LandingView } from '../../components/LandingView';
import { LANDINGS } from '../../lib/landings';

/**
 * The student area's landing view — SPEC §13's `routes/student/`.
 *
 * Empty by design rather than unfinished: E1 lands a person on the right screen
 * and E2 builds the weekly survey that goes here.
 */
export function StudentLanding(): JSX.Element {
  return <LandingView landing={LANDINGS.student} />;
}
