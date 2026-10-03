import type { JSX } from 'react';

import { Link } from '@tanstack/react-router';

import { LandingView } from '../../components/LandingView';
import { copy } from '../../copy/leadershipComparisonSetCopy';
import { LANDINGS } from '../../lib/landings';
import { COMPARISON_SETS_ROUTE } from './ComparisonSetForm';
import './leadershipComparisonSets.css';

/**
 * The leadership area's landing view — SPEC §13's `routes/leadership/`.
 *
 * One route for the whole reporting chain, because it is one shape of screen: a
 * roll-up over whatever the holder supervises (SPEC §2.1). What differs per role
 * is purview, which the backend computes and E9 makes visible.
 *
 * **The one link is E5-09's.** SPEC §5.1's comparison sets are a leadership
 * surface and the roll-up itself is E9's, so until then this page is the only
 * door to them: a reader who lands here would otherwise have to be handed the
 * address. It is a link rather than a menu — there is one destination — and it
 * carries the set screen's own heading as its words, so the two surfaces name
 * the same thing identically.
 *
 * **It is dressed as a link.** The application's reset takes the browser's link
 * colour and underline away, and inside the landing's muted line an unstyled
 * link reads as one more sentence; it takes the set screen's own link rule.
 */
export function LeadershipLanding(): JSX.Element {
  return (
    <LandingView landing={LANDINGS.leadership}>
      <p>
        <Link className="pulse-set-link" to={COMPARISON_SETS_ROUTE}>
          {copy('leadership_comparison_sets.heading')}
        </Link>
      </p>
    </LandingView>
  );
}
