import type { JSX } from 'react';

import { LandingView } from '../../components/LandingView';
import { LANDINGS } from '../../lib/landings';

/**
 * The leadership area's landing view — SPEC §13's `routes/leadership/`.
 *
 * One route for the whole reporting chain, because it is one shape of screen: a
 * roll-up over whatever the holder supervises (SPEC §2.1). What differs per role
 * is purview, which the backend computes and E9 makes visible.
 */
export function LeadershipLanding(): JSX.Element {
  return <LandingView landing={LANDINGS.leadership} />;
}
