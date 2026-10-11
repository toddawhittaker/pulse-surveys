import type { JSX } from 'react';

import { Link } from '@tanstack/react-router';

import { LandingView } from '../../components/LandingView';
import { copy } from '../../copy/leadershipComparisonSetCopy';
import { copy as moderationCopy } from '../../copy/leadershipModerationCopy';
import { LANDINGS } from '../../lib/landings';
import { COMPARISON_SETS_ROUTE } from './ComparisonSetForm';
import { EXCLUSION_LOG_ROUTE } from './ExclusionLog';
import { REVIEW_QUEUE_ROUTE } from './ReviewQueue';
import './leadershipComparisonSets.css';

/**
 * The leadership area's landing view — SPEC §13's `routes/leadership/`.
 *
 * One route for the whole reporting chain, because it is one shape of screen: a
 * roll-up over whatever the holder supervises (SPEC §2.1). What differs per role
 * is purview, which the backend computes and E9 makes visible.
 *
 * **Three links, one per leadership surface built so far**: SPEC §5.1's
 * comparison sets, and SPEC §5.2's review queue and exclusion log. The roll-up
 * itself is E9's, so until then this page is the only door to them: a reader
 * who lands here would otherwise have to be handed the address. Each link
 * carries its page's own heading as its words, so a link and its page name the
 * same thing identically.
 *
 * **Every leadership role sees all three.** Which reader has a review grant is
 * the server's answer (ADR 0190): a Lead Faculty member and a chair read their
 * queue and log, and a dean, a vice president or an assistant dean who follows
 * the link is shown the server's sentence saying there is nothing for that role
 * to read. An instructor lands on the instructor's page, which carries none of
 * these links.
 *
 * **Each is dressed as a link.** The application's reset takes the browser's link
 * colour and underline away, and inside the landing's muted line an unstyled
 * link reads as one more sentence; each takes the set screen's own link rule.
 */
export function LeadershipLanding(): JSX.Element {
  return (
    <LandingView landing={LANDINGS.leadership}>
      <p>
        <Link className="pulse-set-link" to={COMPARISON_SETS_ROUTE}>
          {copy('leadership_comparison_sets.heading')}
        </Link>
      </p>
      <p>
        <Link className="pulse-set-link" to={REVIEW_QUEUE_ROUTE}>
          {moderationCopy('leadership_moderation.queue.heading')}
        </Link>
      </p>
      <p>
        <Link className="pulse-set-link" to={EXCLUSION_LOG_ROUTE}>
          {moderationCopy('leadership_moderation.log.heading')}
        </Link>
      </p>
    </LandingView>
  );
}
