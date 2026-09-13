import type { JSX } from 'react';

import { LandingView } from '../../components/LandingView';
import { LANDINGS } from '../../lib/landings';

/**
 * The Care area's landing view — SPEC §13's `routes/care/`.
 *
 * SPEC §6.2 keeps this surface to the threat queue and nothing else, and there
 * is no queue yet. `docs/DESIGN_BRIEF.md` gives this screen no motion at all,
 * and none of the four landing views — admin, care, instructor, leadership —
 * has any, so stillness is not yet a distinction this component has to draw
 * against its siblings. The tree is not motionless: E2-10 replaced what was the
 * fifth landing with the student weekly survey, and that screen is the one
 * surface with motion today.
 */
export function CareLanding(): JSX.Element {
  return <LandingView landing={LANDINGS.care} />;
}
