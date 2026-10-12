import { useEffect, useState, type JSX } from 'react';

import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router';

import type { PublishedWeeksRead, ReportRead } from '../../api/instructor';
import {
  readDrillDownReport,
  readDrillDownWeeks,
  readLeadershipContext,
  type LeaderRoleView,
} from '../../api/leadership';
import { copy, fillCopy } from '../../copy/leadershipRollupCopy';
import { InstructorMondayReport, type ReportSource } from '../instructor/InstructorMondayReport';
import '../../components/leadershipRollup.css';
import { DRILL_DOWN_ROUTE } from '../paths';


/** Where a spec finds the drill-down, as opposed to the roll-up it was opened from. */
export const DRILL_DOWN_TESTID = 'pulse-leadership-drill-down';

/** The context bar, addressable from a test and from the end-to-end suite. */
export const DRILL_DOWN_CONTEXT_TESTID = 'pulse-drill-down-context';

/**
 * The gate's 403 for a session in another role, answered in this page's words
 * so the report page renders it as it renders any refusal with a sentence.
 */
function withRoleRefusal<T extends PublishedWeeksRead | ReportRead>(
  answer: T | { readonly kind: 'not-your-role' },
): T | { readonly kind: 'unavailable'; readonly detail: string } {
  return answer.kind === 'not-your-role'
    ? { kind: 'unavailable', detail: copy('leadership_rollup.not_your_role') }
    : answer;
}

/**
 * A leader's reads of one section's report (SPEC §5.5): the drill-down's own
 * routes, behind the reader's purview. A section with no published week has no
 * course label a leader's route answers, so the page keeps its own heading.
 */
const LEADERSHIP_SOURCE: ReportSource = {
  readWeeks: async (sectionId) => withRoleRefusal(await readDrillDownWeeks(sectionId)),
  readReport: async (sectionId, week) =>
    withRoleRefusal(await readDrillDownReport(sectionId, week)),
  readCourseLabel: () => Promise.resolve(null),
  readOnly: true,
  testid: DRILL_DOWN_TESTID,
};

/**
 * The drill-down: one section's Monday report, wholesale and read-only, under a
 * context bar naming whose view it is (SPEC §5.5: "Viewing as Dean ·
 * read-only").
 *
 * **It is the instructor's page, given the leader's reads.** Every component is
 * the instructor report's, so a leader reads exactly what the section's
 * instructor reads, the report's one confidentiality line included; the source
 * is read-only, so no card carries a moderation control and no composer is
 * drawn. The server's report carries no action either (ADR 0206).
 *
 * **The role named is the reader's highest**, from the context route, which
 * answers the session's own roles; until it answers, the bar says
 * "leadership", which is true of every reader this page admits.
 */
export function DrillDownRoute(): JSX.Element {
  const { sectionId } = useParams({ from: DRILL_DOWN_ROUTE });
  const { week } = useSearch({ from: DRILL_DOWN_ROUTE });
  const navigate = useNavigate();
  const [role, setRole] = useState<LeaderRoleView | null>(null);

  useEffect(() => {
    let live = true;
    void readLeadershipContext().then((answer) => {
      if (live && answer.kind === 'context') setRole(answer.context.roles[0] ?? null);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <InstructorMondayReport
      sectionId={sectionId}
      week={week ?? null}
      source={LEADERSHIP_SOURCE}
      onSelectWeek={(chosen) => {
        void navigate({ to: DRILL_DOWN_ROUTE, params: { sectionId }, search: { week: chosen } });
      }}
      contextBar={
        <div className="pulse-drill-down-bar">
          <span data-testid={DRILL_DOWN_CONTEXT_TESTID}>
            {fillCopy('leadership_rollup.drill_down.context', { role: roleName(role) })}
          </span>
          <Link className="pulse-rollup-link" to="/leadership">
            {copy('leadership_rollup.drill_down.back')}
          </Link>
        </div>
      }
    />
  );
}

/** A role's name as the context bar says it. */
function roleName(role: LeaderRoleView | null): string {
  if (role === null) return copy('leadership_rollup.role.unknown');
  return copy(`leadership_rollup.role.${role}`);
}
