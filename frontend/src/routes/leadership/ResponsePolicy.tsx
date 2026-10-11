import { useEffect, useState, type JSX } from 'react';

import {
  readResponsePolicy,
  setResponsePolicy,
  type PolicyPrefixView,
  type ResponsePolicyRead,
  type ResponsePolicyView,
} from '../../api/leadership';
import { PolicyToggle } from '../../components/PolicyToggle';
import { StateNotice } from '../../components/StateNotice';
import { copy, fillCopy } from '../../copy/leadershipResponseCopy';
import { ResponseRefusal } from './ResponseRefusal';
import './leadershipComparisonSets.css';
import './leadershipResponse.css';

/** The address of the response policy page, under the leadership area. */
export const RESPONSE_POLICY_ROUTE = '/leadership/response-policy';

/** Where a spec finds the page. */
export const RESPONSE_POLICY_TESTID = 'pulse-leadership-response-policy';

const HEADING_ID = 'pulse-response-policy-heading';

type Load =
  | { readonly kind: 'loading' }
  | { readonly kind: 'session-ended' }
  | { readonly kind: 'not-your-role' }
  | { readonly kind: 'error'; readonly detail: string | null }
  | { readonly kind: 'policy'; readonly policy: ResponsePolicyView };

/**
 * `/leadership/response-policy` — whether a response is required, per prefix
 * (SPEC §5.3, §5.6).
 *
 * **The switch covers the courses the reader sets, and the server decides which
 * those are** (`can_set` on each course). A course the reader may not set is
 * text with the setter's role and no control, so the page never offers a switch
 * the server would refuse. The page says plainly that a change applies from the
 * next week's report and not to a week already open.
 */
export function ResponsePolicyRoute(): JSX.Element {
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [busyPrefix, setBusyPrefix] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void readResponsePolicy().then((read) => {
      if (live) setLoad(loadFrom(read));
    });
    return () => {
      live = false;
    };
  }, []);

  async function toggle(prefix: PolicyPrefixView, required: boolean): Promise<void> {
    setBusyPrefix(prefix.prefix_id);
    setAnnouncement(null);
    setProblem(null);
    const outcome = await setResponsePolicy(prefix.prefix_id, required ? 'REQUIRED' : 'ENCOURAGED');
    setBusyPrefix(null);
    if (outcome.kind === 'saved') {
      setLoad({ kind: 'policy', policy: outcome.policy });
      setAnnouncement(fillCopy('leadership_response.policy.saved', { prefix: prefix.prefix_code }));
    } else if (outcome.kind === 'session-ended') {
      setLoad({ kind: 'session-ended' });
    } else if (outcome.kind === 'not-your-role') {
      setLoad({ kind: 'not-your-role' });
    } else {
      setProblem(
        (outcome.kind === 'refused' ? outcome.detail : null) ??
          copy('leadership_response.policy.save_unavailable'),
      );
    }
  }

  return (
    <main className="pulse-set-page" data-testid={RESPONSE_POLICY_TESTID} aria-labelledby={HEADING_ID}>
      <h1 className="pulse-set-title" id={HEADING_ID}>
        {copy('leadership_response.policy.heading')}
      </h1>
      <p className="pulse-set-intro">{copy('leadership_response.policy.intro')}</p>
      <p className="pulse-set-intro">{copy('leadership_response.policy.timing')}</p>
      <p className="pulse-set-announcement" role="status">
        {announcement}
      </p>
      {problem === null ? null : (
        <p className="pulse-set-refusal" role="alert">
          {problem}
        </p>
      )}

      {load.kind === 'loading' ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_response.policy.loading')}
        </p>
      ) : load.kind === 'session-ended' || load.kind === 'not-your-role' ? (
        <ResponseRefusal kind={load.kind} />
      ) : load.kind === 'error' ? (
        <StateNotice
          variant="flat"
          body={load.detail ?? copy('leadership_response.policy.unavailable')}
        />
      ) : load.policy.prefixes.length === 0 ? (
        <StateNotice
          variant="flat"
          title={copy('leadership_response.policy.empty_title')}
          body={copy('leadership_response.policy.empty_body')}
        />
      ) : (
        load.policy.prefixes.map((prefix) => (
          <PrefixSection
            key={prefix.prefix_id}
            prefix={prefix}
            busy={busyPrefix === prefix.prefix_id}
            onToggle={(required) => void toggle(prefix, required)}
          />
        ))
      )}
    </main>
  );
}

function PrefixSection({
  prefix,
  busy,
  onToggle,
}: {
  readonly prefix: PolicyPrefixView;
  readonly busy: boolean;
  readonly onToggle: (required: boolean) => void;
}): JSX.Element {
  const settable = prefix.courses.filter((course) => course.can_set);
  const required = settable.length > 0 && settable.every((course) => course.mode === 'REQUIRED');
  const titleId = `pulse-policy-prefix-${prefix.prefix_id}`;
  return (
    <section className="pulse-policy-prefix" aria-labelledby={titleId}>
      <h2 className="pulse-policy-prefix-title" id={titleId}>
        {prefix.prefix_code}
      </h2>
      {settable.length === 0 ? null : (
        <PolicyToggle
          detail={fillCopy('leadership_response.policy.toggle_detail', { prefix: prefix.prefix_code })}
          ariaLabel={fillCopy('leadership_response.policy.toggle_aria', { prefix: prefix.prefix_code })}
          checked={required}
          busy={busy}
          onToggle={onToggle}
        />
      )}
      {busy ? (
        <p className="pulse-set-status" role="status">
          {copy('leadership_response.policy.saving')}
        </p>
      ) : null}
      <ul
        className="pulse-policy-courses"
        aria-label={fillCopy('leadership_response.policy.list_label', { prefix: prefix.prefix_code })}
      >
        {prefix.courses.map((course) => (
          <li className="pulse-policy-course" key={course.course_id}>
            <p className="pulse-policy-course-label">{course.course_label}</p>
            <p className="pulse-policy-course-mode">
              {copy(
                course.mode === 'REQUIRED'
                  ? 'leadership_response.policy.mode_required'
                  : 'leadership_response.policy.mode_encouraged',
              )}
            </p>
            {course.can_set || course.set_by_role === null ? null : (
              <p className="pulse-policy-course-note">
                {copy(
                  course.set_by_role === 'LEAD_FACULTY'
                    ? 'leadership_response.policy.set_by_lead_faculty'
                    : 'leadership_response.policy.set_by_chair',
                )}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** What a read of the policy means for the page. */
function loadFrom(read: ResponsePolicyRead): Load {
  if (read.kind === 'session-ended') return { kind: 'session-ended' };
  if (read.kind === 'not-your-role') return { kind: 'not-your-role' };
  if (read.kind === 'unavailable') return { kind: 'error', detail: read.detail };
  return { kind: 'policy', policy: read.policy };
}
