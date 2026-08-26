import type { JSX } from 'react';

import { LandingView } from '../../components/LandingView';
import { LANDINGS } from '../../lib/landings';

/**
 * The instructor area's landing view — SPEC §13's `routes/instructor/`.
 *
 * Empty by design rather than unfinished: the Monday report (SPEC §5.1) is what
 * this route grows into.
 */
export function InstructorLanding(): JSX.Element {
  return <LandingView landing={LANDINGS.instructor} />;
}
