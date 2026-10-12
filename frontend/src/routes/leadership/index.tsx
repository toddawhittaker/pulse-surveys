import { useEffect, useRef, useState, type JSX, type ReactNode } from 'react';

import { Link } from '@tanstack/react-router';

import {
  readComparisonSets,
  readLeadershipContext,
  readRollupFigures,
  readRollupTree,
  readSetSeries,
  type AttentionCardView,
  type ComparisonSetSummaryView,
  type LeadershipContextView,
  type NamedSetSeriesView,
  type RollupCohortView,
  type RollupFiguresKind,
  type RollupFiguresView,
  type RollupNodeView,
  type RollupTermView,
  type RollupTreeView,
  type RollupWeekView,
} from '../../api/leadership';
import { AggregateHeader } from '../../components/AggregateHeader';
import { AttentionList } from '../../components/AttentionList';
import { HierarchyNav } from '../../components/HierarchyNav';
import { LiveStatus } from '../../components/LiveStatus';
import type { OverlaySeries, TrendPoint } from '../../components/PulseTrendChart';
import { ResponseRateBar } from '../../components/ResponseRateBar';
import { StatPair } from '../../components/StatPair';
import { TrendPair } from '../../components/TrendPair';
import { copy as landingCopy } from '../../copy/landings';
import { copy as setCopy } from '../../copy/leadershipComparisonSetCopy';
import { copy as moderationCopy } from '../../copy/leadershipModerationCopy';
import { copy as responseCopy } from '../../copy/leadershipResponseCopy';
import { copy, fillCopy } from '../../copy/leadershipRollupCopy';
import { LANDINGS } from '../../lib/landings';
import '../../components/leadershipRollup.css';
import './leadershipComparisonSets.css';
import { COMPARISON_SETS_ROUTE, DRILL_DOWN_ROUTE, EXCLUSION_LOG_ROUTE, RESPONSES_OWED_ROUTE, RESPONSE_POLICY_ROUTE, REVIEW_QUEUE_ROUTE } from '../paths';

/**
 * The leadership landing: SPEC §5.5's roll-up, one template for every
 * leadership role.
 *
 * `design/LeadershipRollup.dc.html` is the contract: the tree in a left pane,
 * the chosen node's figures in a right one, the two stacking at tablet width.
 * What differs by role is what the server sends, never what this page decides:
 * the tree's roots and labels, and whether by-lead mode is offered at all
 * (§2.1: chair and above). **The by-lead control is drawn only when the payload
 * carries the by-lead groups.**
 *
 * **Nothing on this page sorts.** The tree, the cohorts and the attention cards
 * arrive in the server's label order (§4.1 item 4: no score-sorting anywhere),
 * and every list below renders in the order it was sent.
 *
 * **The reads, in order.** The context first, for the term to open (the one
 * containing today, else the latest); then the tree for that term; then the
 * chosen node's figures; and a named set's series only when a reader asks for
 * one. Each answer is shown only while the question it answered is still the
 * one on screen.
 *
 * **Polite live regions that exist before their text arrives.** The page's
 * region, present from the first render, carries the context's and the tree's
 * loading lines and refusals; the content pane's, mounted with the tree, carries
 * a node's, ending on "Showing {name}" once its figures arrive; the named-set
 * control's carries the set's. Each mounts empty and is given its text a tick
 * later (`LiveStatus`), so the first loading line is heard too.
 *
 * **Focus.** Pressing a tree row leaves focus on the row, so a reader moving
 * through the tree keeps their place and hears the pane's status instead. A
 * breadcrumb press moves focus to the node's heading, because the button
 * pressed leaves the trail.
 *
 * **No comment appears here** (SPEC §5.5, settled at the E9 breakdown): the
 * roll-up carries figures and attention cards, and a section's comments are
 * read in its drill-down.
 *
 * The page keeps the landing's testid, heading and line, because the doors and
 * a row of end-to-end specs address them; and it keeps the links to the other
 * leadership pages, below the roll-up.
 */
export function LeadershipLanding(): JSX.Element {
  const [context, setContext] = useState<Answer<LeadershipContextView> | null>(null);
  const [termId, setTermId] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void readLeadershipContext().then((answer) => {
      if (!live) return;
      if (answer.kind === 'context') {
        setContext({ kind: 'ok', value: answer.context });
        setTermId(openingTerm(answer.context));
      } else {
        setContext(answer);
      }
    });
    return () => {
      live = false;
    };
  }, []);

  const tree = useKeyedRead<RollupTreeView>(termId, (id) =>
    readRollupTree(id).then((answer) =>
      answer.kind === 'tree' ? { kind: 'ok' as const, value: answer.tree } : answer,
    ),
  );

  const terms = context?.kind === 'ok' ? context.value.terms : [];
  const term = terms.find((candidate) => candidate.id === termId) ?? null;
  const status = pageStatus(context, termId, tree);
  const empty =
    context?.kind === 'session-ended' ||
    (context?.kind === 'ok' && termId === null) ||
    (tree?.kind === 'ok' && tree.value.hierarchy.length === 0);

  return (
    <main
      className="pulse-rollup"
      data-testid={LANDINGS.leadership.testid}
      aria-labelledby={HEADING_ID}
    >
      <h1 className="pulse-rollup-title" id={HEADING_ID}>
        {landingCopy(LANDINGS.leadership.heading)}
      </h1>
      <LiveStatus className="pulse-rollup-status" text={status} />
      {empty ? <p className="pulse-rollup-note">{landingCopy(LANDINGS.leadership.emptyState)}</p> : null}
      {terms.length > 0 && termId !== null ? (
        <div className="pulse-rollup-bar">
          <label className="pulse-rollup-field">
            {copy('leadership_rollup.term.label')}
            <select
              className="pulse-rollup-select"
              value={termId}
              onChange={(event) => {
                setTermId(event.target.value);
              }}
            >
              {terms.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
      {tree?.kind === 'ok' && term !== null && tree.value.hierarchy.length > 0 ? (
        <Rollup key={term.id} tree={tree.value} term={term} />
      ) : null}
      <nav className="pulse-rollup-more" aria-label={copy('leadership_rollup.more.label')}>
        <ul>
          <li>
            <Link className="pulse-set-link" to={COMPARISON_SETS_ROUTE}>
              {setCopy('leadership_comparison_sets.heading')}
            </Link>
          </li>
          <li>
            <Link className="pulse-set-link" to={REVIEW_QUEUE_ROUTE}>
              {moderationCopy('leadership_moderation.queue.heading')}
            </Link>
          </li>
          <li>
            <Link className="pulse-set-link" to={EXCLUSION_LOG_ROUTE}>
              {moderationCopy('leadership_moderation.log.heading')}
            </Link>
          </li>
          <li>
            <Link className="pulse-set-link" to={RESPONSE_POLICY_ROUTE}>
              {responseCopy('leadership_response.policy.heading')}
            </Link>
          </li>
          <li>
            <Link className="pulse-set-link" to={RESPONSES_OWED_ROUTE}>
              {responseCopy('leadership_response.owed.heading')}
            </Link>
          </li>
        </ul>
      </nav>
    </main>
  );
}

const HEADING_ID = 'pulse-rollup-heading';
const NODE_HEADING_ID = 'pulse-rollup-node-heading';

/** One read as the page holds it: the value, or one of the leadership reads' refusals. */
type Answer<T> =
  | { readonly kind: 'ok'; readonly value: T }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'unavailable'; readonly detail: string | null };

/**
 * One read keyed by the question it asks, answered only while that question is
 * still the one on screen: `null` while it is in flight or when there is nothing
 * to ask.
 */
function useKeyedRead<T>(
  key: string | null,
  read: (key: string) => Promise<Answer<T>>,
): Answer<T> | null {
  const [answered, setAnswered] = useState<{ readonly to: string; readonly answer: Answer<T> } | null>(
    null,
  );
  useEffect(() => {
    if (key === null) return;
    let live = true;
    void read(key).then((answer) => {
      if (live) setAnswered({ to: key, answer });
    });
    return () => {
      live = false;
    };
    // The read is the caller's closure over the key; the key is the question.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return answered !== null && answered.to === key ? answered.answer : null;
}

/** The term the page opens: the one containing today, else the latest that has begun, else the first. */
function openingTerm(context: LeadershipContextView): string | null {
  if (context.current_term_id !== null) return context.current_term_id;
  return context.terms.at(-1)?.id ?? null;
}

/** The live region's line for the page's own reads, or nothing. */
function pageStatus(
  context: Answer<LeadershipContextView> | null,
  termId: string | null,
  tree: Answer<RollupTreeView> | null,
): string {
  if (context === null) return copy('leadership_rollup.loading');
  if (context.kind !== 'ok') return refusalLine(context);
  if (termId === null) return copy('leadership_rollup.no_term');
  if (tree === null) return copy('leadership_rollup.loading');
  if (tree.kind !== 'ok') return refusalLine(tree);
  return '';
}

/** What a refused read says: the server's sentence where it wrote one, else this page's. */
function refusalLine(
  answer:
    | { readonly kind: 'session-ended' }
    | { readonly kind: 'not-your-role' }
    | { readonly kind: 'unavailable'; readonly detail: string | null },
  fallback: Parameters<typeof copy>[0] = 'leadership_rollup.unavailable',
): string {
  if (answer.kind === 'session-ended') return copy('leadership_rollup.session_ended');
  if (answer.kind === 'not-your-role') return copy('leadership_rollup.not_your_role');
  return answer.detail ?? copy(fallback);
}

type Mode = 'hierarchy' | 'by_lead';

/** The path from a root to the node with this kind and id, or `null`. */
function pathTo(
  nodes: readonly RollupNodeView[],
  kind: string,
  id: string,
): readonly RollupNodeView[] | null {
  for (const node of nodes) {
    if (node.kind === kind && node.id === id) return [node];
    const below = pathTo(node.children, kind, id);
    if (below !== null) return [node, ...below];
  }
  return null;
}

/** A node's figures may be asked for unless it is a section, whose figures are its report. */
function figuresKind(node: RollupNodeView): RollupFiguresKind | null {
  return node.kind === 'section' ? null : node.kind;
}

/** The two panes, for one term's tree. */
function Rollup({
  tree,
  term,
}: {
  readonly tree: RollupTreeView;
  readonly term: RollupTermView;
}): JSX.Element {
  const byLead = tree.by_lead;
  const [mode, setMode] = useState<Mode>('hierarchy');
  const roots = mode === 'by_lead' && byLead !== null ? byLead : tree.hierarchy;
  const [chosen, setChosen] = useState<{ readonly kind: string; readonly id: string } | null>(
    null,
  );
  const first = roots[0];
  const path =
    (chosen === null ? null : pathTo(roots, chosen.kind, chosen.id)) ??
    (first === undefined ? [] : [first]);
  const node = path.at(-1) ?? null;

  // A breadcrumb press unmounts the button pressed, so focus moves to the
  // chosen node's heading; a tree press leaves focus on its row.
  const focusTheHeading = useRef(false);
  function choose(next: RollupNodeView, moveFocus: boolean): void {
    focusTheHeading.current = moveFocus;
    setChosen({ kind: next.kind, id: next.id });
  }
  useEffect(() => {
    if (!focusTheHeading.current) return;
    focusTheHeading.current = false;
    document.getElementById(NODE_HEADING_ID)?.focus();
  }, [chosen]);

  const kind = node === null ? null : figuresKind(node);
  const figures = useKeyedRead<RollupFiguresView>(
    node === null || kind === null ? null : `${kind}/${node.id}`,
    () =>
      node === null || kind === null
        ? Promise.resolve({ kind: 'unavailable' as const, detail: null })
        : readRollupFigures(kind, node.id, term.id).then((answer) =>
            answer.kind === 'figures' ? { kind: 'ok' as const, value: answer.figures } : answer,
          ),
  );

  return (
    <div className="pulse-rollup-panes">
      <div className="pulse-rollup-tree-pane">
        {byLead === null ? null : (
          <div
            className="pulse-rollup-modes"
            role="group"
            aria-label={copy('leadership_rollup.mode.label')}
          >
            <button
              type="button"
              className="pulse-rollup-mode"
              aria-pressed={mode === 'hierarchy'}
              onClick={() => {
                setMode('hierarchy');
                setChosen(null);
              }}
            >
              {copy('leadership_rollup.mode.hierarchy')}
            </button>
            <button
              type="button"
              className="pulse-rollup-mode"
              aria-pressed={mode === 'by_lead'}
              onClick={() => {
                setMode('by_lead');
                setChosen(null);
              }}
            >
              {copy('leadership_rollup.mode.by_lead')}
            </button>
          </div>
        )}
        <HierarchyNav
          key={mode}
          roots={roots}
          selectedId={node?.id ?? null}
          onSelect={(next) => {
            choose(next, false);
          }}
          sectionLink={(section, children) => (
            <Link
              className="pulse-hierarchy-link"
              to={DRILL_DOWN_ROUTE}
              params={{ sectionId: section.id }}
              search={{}}
            >
              {children}
            </Link>
          )}
        />
      </div>
      <div className="pulse-rollup-content-pane">
        <nav aria-label={copy('leadership_rollup.breadcrumbs.label')}>
          <ol className="pulse-rollup-crumbs">
            {path.map((step, index) => (
              <li key={`${step.kind}:${step.id}`} className="pulse-rollup-crumb">
                {index === path.length - 1 ? (
                  <span className="pulse-rollup-crumb-current" aria-current="location">
                    {step.name}
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      className="pulse-rollup-crumb-button"
                      onClick={() => {
                        choose(step, true);
                      }}
                    >
                      {step.name}
                    </button>
                    <span aria-hidden="true">›</span>
                  </>
                )}
              </li>
            ))}
          </ol>
        </nav>
        <LiveStatus
          className="pulse-rollup-status"
          text={
            node === null
              ? ''
              : figures === null
                ? copy('leadership_rollup.figures.loading')
                : figures.kind === 'ok'
                  ? fillCopy('leadership_rollup.figures.showing', { name: node.name })
                  : refusalLine(figures, 'leadership_rollup.figures.unavailable')
          }
        />
        {node === null ? null : (
          <NodeFigures
            key={`${node.kind}:${node.id}`}
            node={node}
            term={term}
            figures={figures?.kind === 'ok' ? figures.value : null}
          />
        )}
      </div>
    </div>
  );
}

/** One node's figures: its trend per start cohort, workload, participation and attention. */
function NodeFigures({
  node,
  term,
  figures,
}: {
  readonly node: RollupNodeView;
  readonly term: RollupTermView;
  readonly figures: RollupFiguresView | null;
}): JSX.Element {
  return (
    <article className="pulse-rollup-article" aria-labelledby={NODE_HEADING_ID}>
      <AggregateHeader headingId={NODE_HEADING_ID} name={node.name} scopeLine={node.label} />
      {figures === null ? null : <Figures figures={figures} term={term} />}
    </article>
  );
}

/** The cohort chip that shows every start cohort at once: the default (SPEC §2.2). */
const ALL_STARTS = 'all';

function Figures({
  figures,
  term,
}: {
  readonly figures: RollupFiguresView;
  readonly term: RollupTermView;
}): JSX.Element {
  const [picked, setPicked] = useState<string>(ALL_STARTS);
  const chosen = figures.cohorts.filter((cohort) => cohort.section_start_date === picked);
  const shown = chosen.length > 0 ? chosen : figures.cohorts;

  return (
    <>
      {figures.cohorts.length === 0 ? (
        <p className="pulse-rollup-note">{copy('leadership_rollup.figures.no_cohorts')}</p>
      ) : (
        <CohortFigures
          cohorts={figures.cohorts}
          shown={shown}
          picked={chosen.length > 0 ? picked : ALL_STARTS}
          onPick={setPicked}
          term={term}
        />
      )}
      <h3 className="pulse-rollup-heading">{copy('leadership_rollup.attention.heading')}</h3>
      <AttentionList
        cards={figures.attention}
        empty={figures.attention_empty}
        reportLink={(card: AttentionCardView, children: ReactNode, label: string) => (
          <Link
            aria-label={label}
            className="pulse-attention-link"
            to={DRILL_DOWN_ROUTE}
            params={{ sectionId: card.section_id }}
            search={{ week: card.course_week }}
          >
            {children}
          </Link>
        )}
      />
    </>
  );
}

/**
 * The trend, workload and participation for the start cohorts the chips show.
 *
 * "All starts" draws every cohort's line on the one term axis; a cohort chip
 * draws that cohort alone, and only then is the named set's line drawn beside
 * it, because a set's line beside several cohorts would not say which one it
 * compares. Workload and participation follow the chips, one block per cohort
 * shown, each named by its cohort when there is more than one.
 */
function CohortFigures({
  cohorts,
  shown,
  picked,
  onPick,
  term,
}: {
  readonly cohorts: readonly RollupCohortView[];
  readonly shown: readonly RollupCohortView[];
  readonly picked: string;
  readonly onPick: (key: string) => void;
  readonly term: RollupTermView;
}): JSX.Element {
  const [sets, setSets] = useState<readonly ComparisonSetSummaryView[]>([]);
  const [setId, setSetId] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void readComparisonSets().then((answer) => {
      if (live && answer.kind === 'sets') setSets(answer.sets);
    });
    return () => {
      live = false;
    };
  }, []);

  const series = useKeyedRead<NamedSetSeriesView>(setId, (id) =>
    readSetSeries(id, term.id).then((answer) =>
      answer.kind === 'series' ? { kind: 'ok' as const, value: answer.series } : answer,
    ),
  );
  const chosenSet = sets.find((candidate) => candidate.id === setId) ?? null;
  const single = shown.length === 1 ? (shown[0] ?? null) : null;
  const setLine = chosenSet === null || single === null ? null : namedSetLines(series, single);
  const named = shown.length > 1;

  return (
    <>
      <h3 className="pulse-rollup-heading">{copy('leadership_rollup.trend.heading')}</h3>
      {single === null ? (
        <TrendPair
          axis="term"
          lengthWeeks={term.length_weeks}
          instructor={[]}
          course={[]}
          cohorts={shown.map((cohort) => ({
            label: cohort.label,
            instructor: termAxis(cohort.weeks, 'instructor_mean'),
            course: termAxis(cohort.weeks, 'course_mean'),
          }))}
        />
      ) : (
        <TrendPair
          axis="term"
          lengthWeeks={term.length_weeks}
          instructor={termAxis(single.weeks, 'instructor_mean')}
          course={termAxis(single.weeks, 'course_mean')}
          heroLabel={copy('leadership_rollup.trend.legend_node')}
          instructorBenchmark={setLine === null ? undefined : { comparison: setLine.instructor }}
          courseBenchmark={setLine === null ? undefined : { comparison: setLine.course }}
          {...(chosenSet === null
            ? {}
            : {
                comparisonLabel: chosenSet.name,
                comparisonSuppressed: fillCopy('leadership_rollup.set.suppressed', {
                  name: chosenSet.name,
                }),
              })}
        />
      )}
      <div className="pulse-rollup-choices">
        <div role="group" aria-label={copy('leadership_rollup.cohort.label')} className="pulse-rollup-field">
          <button
            type="button"
            className="pulse-rollup-mode"
            aria-pressed={picked === ALL_STARTS}
            onClick={() => {
              onPick(ALL_STARTS);
            }}
          >
            {copy('leadership_rollup.cohort.all')}
          </button>
          {cohorts.map((candidate) => (
            <button
              key={candidate.section_start_date}
              type="button"
              className="pulse-rollup-mode"
              aria-pressed={picked === candidate.section_start_date}
              onClick={() => {
                onPick(candidate.section_start_date);
              }}
            >
              {candidate.label}
            </button>
          ))}
        </div>
        <label className="pulse-rollup-field">
          {copy('leadership_rollup.set.label')}
          <select
            className="pulse-rollup-select"
            value={setId ?? ''}
            onChange={(event) => {
              setSetId(event.target.value === '' ? null : event.target.value);
            }}
          >
            <option value="">{copy('leadership_rollup.set.none')}</option>
            {sets.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {chosenSet !== null && single === null ? (
        <p className="pulse-rollup-note">
          {fillCopy('leadership_rollup.set.choose_one', { name: chosenSet.name })}
        </p>
      ) : null}
      <LiveStatus
        className="pulse-rollup-status"
        text={
          setId === null
            ? ''
            : series === null
              ? copy('leadership_rollup.set.loading')
              : series.kind !== 'ok'
                ? refusalLine(series, 'leadership_rollup.set.unavailable')
                : chosenSet !== null && single === null
                  ? fillCopy('leadership_rollup.set.choose_one', { name: chosenSet.name })
                  : ''
        }
      />

      <h3 className="pulse-rollup-heading">{copy('leadership_rollup.workload.heading')}</h3>
      {shown.map((cohort) => (
        <CohortWorkload key={cohort.section_start_date} cohort={cohort} named={named} />
      ))}

      <h3 className="pulse-rollup-heading">{copy('leadership_rollup.participation.heading')}</h3>
      {shown.map((cohort) => (
        <CohortParticipation key={cohort.section_start_date} cohort={cohort} named={named} />
      ))}
    </>
  );
}

/** One cohort's latest workload, under its label when several are shown. */
function CohortWorkload({
  cohort,
  named,
}: {
  readonly cohort: RollupCohortView;
  readonly named: boolean;
}): JSX.Element {
  const latest = latestWorkload(cohort.weeks);
  return (
    <>
      {named ? <h4 className="pulse-rollup-subheading">{cohort.label}</h4> : null}
      {latest === null ? (
        <p className="pulse-rollup-note">{copy('leadership_rollup.workload.absent')}</p>
      ) : (
        <StatPair median={latest.median} mean={latest.mean} />
      )}
    </>
  );
}

/** One cohort's latest participation, under its label when several are shown. */
function CohortParticipation({
  cohort,
  named,
}: {
  readonly cohort: RollupCohortView;
  readonly named: boolean;
}): JSX.Element {
  const participation = cohort.participation;
  return (
    <>
      {named ? <h4 className="pulse-rollup-subheading">{cohort.label}</h4> : null}
      {participation === null || participation.response_rate === null ? (
        <p className="pulse-rollup-note">{copy('leadership_rollup.participation.absent')}</p>
      ) : (
        <>
          <ResponseRateBar
            response={{ rate: participation.response_rate }}
            {...(participation.validity_rate === null
              ? {}
              : { validity: { rate: participation.validity_rate } })}
          />
          <p className="pulse-rollup-note">
            {fillCopy('leadership_rollup.participation.week', {
              week: String(participation.course_week),
            })}
          </p>
        </>
      )}
    </>
  );
}

/** A decimal the wire carries as a string, as a number, or `null` for a week nobody answered. */
function decimal(value: string | null): number | null {
  if (value === null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/**
 * One stream of a cohort on the term axis. Each point's place is the server's
 * term week (SPEC §2.2), handed to the chart as its week; nothing is derived.
 */
function termAxis(
  weeks: readonly RollupWeekView[],
  member: 'instructor_mean' | 'course_mean',
): TrendPoint[] {
  return weeks.map((week) => ({ courseWeek: week.term_week, termWeek: null, mean: decimal(week[member]) }));
}

/** The cohort's most recent week with a workload figure, or `null`. */
function latestWorkload(
  weeks: readonly RollupWeekView[],
): { readonly mean: number | null; readonly median: number | null } | null {
  for (const week of [...weeks].reverse()) {
    const mean = decimal(week.workload_mean);
    const median = decimal(week.workload_median);
    if (mean !== null || median !== null) return { mean, median };
  }
  return null;
}

/**
 * The named set's two lines for this cohort, or `null` while there is nothing
 * to draw yet.
 *
 * A series that answered and holds no cohort starting when this one did is a
 * line with no week: the chart then says the line is withheld, which is what
 * the payload is saying. Each week's figure is the server's sealed one, read by
 * the chart through `isShownFigure`.
 */
function namedSetLines(
  series: Answer<NamedSetSeriesView> | null,
  cohort: RollupCohortView,
): { readonly instructor: OverlaySeries; readonly course: OverlaySeries } | null {
  if (series === null || series.kind !== 'ok') return null;
  const matching = series.value.cohorts.find(
    (candidate) => candidate.section_start_date === cohort.section_start_date,
  );
  const weeks = matching?.weeks ?? [];
  return {
    instructor: { points: weeks.map((week) => ({ course_week: week.term_week, mean: week.instructor_mean })) },
    course: { points: weeks.map((week) => ({ course_week: week.term_week, mean: week.course_mean })) },
  };
}
