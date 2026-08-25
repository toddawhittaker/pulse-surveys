import type { JSX } from 'react';

import { LandingView } from '../../components/LandingView';
import { LANDINGS } from '../../lib/landings';

/**
 * The admin area's landing view — SPEC §13's `routes/admin/`.
 *
 * Empty by design rather than unfinished: the observability console and the
 * configuration surface (SPEC §6.3) are what this route grows into.
 */
export function AdminLanding(): JSX.Element {
  return <LandingView landing={LANDINGS.admin} />;
}
