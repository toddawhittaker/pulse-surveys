import type { JSX } from 'react';

import { LandingView } from '../../components/LandingView';
import { LANDINGS } from '../../lib/landings';

/**
 * The Care area's landing view — SPEC §13's `routes/care/`.
 *
 * SPEC §6.2 keeps this surface to the threat queue and nothing else, and there
 * is no queue yet. `docs/DESIGN_BRIEF.md` gives this screen no motion at all;
 * none of the five landings has any, so that is not yet a distinction this
 * component has to draw.
 */
export function CareLanding(): JSX.Element {
  return <LandingView landing={LANDINGS.care} />;
}
