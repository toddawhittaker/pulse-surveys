import type { JSX, ReactNode } from 'react';

import { StateNotice } from '../../components/StateNotice';
import { copy } from '../../copy/adminPeople';
import './adminPeople.css';

/** What a page does when the gate turned its read away. */
export type Gate = 'session-ended' | 'not-your-role' | null;

/**
 * The frame both admin pages share: a landmark, a heading, a line of intro, and
 * the one polite live region every outcome is said in.
 *
 * **The live region is in the page from the first render, empty.** A screen
 * reader announces a change to a region that was already there, and often
 * nothing for one inserted with its text, so a refusal rendered into a node
 * created at that moment would be said to nobody. Every write's outcome goes
 * through `announcement`, the refusals the server sent included.
 *
 * **A page the gate turned away shows only the gate's sentence.** The admin
 * routes answer a verified session in another role with a 403 marked
 * `insufficient_scope` (ADR 0196), and the page says so in the same words the
 * leadership pages use, rather than the ended-session words.
 */
export function AdminPage({
  testid,
  headingId,
  heading,
  intro,
  announcement,
  gate,
  children,
}: {
  readonly testid: string;
  readonly headingId: string;
  readonly heading: string;
  readonly intro: string;
  readonly announcement: string;
  readonly gate: Gate;
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <main className="pulse-admin-page" data-testid={testid} aria-labelledby={headingId}>
      <h1 className="pulse-admin-title" id={headingId}>
        {heading}
      </h1>
      <p className="pulse-admin-intro">{intro}</p>
      <p className="pulse-admin-announcement" role="status" aria-live="polite">
        {announcement}
      </p>
      {gate === 'session-ended' ? (
        <StateNotice
          variant="flat"
          title={copy('admin_people.page.session_ended_title')}
          body={copy('admin_people.page.session_ended_body')}
        />
      ) : gate === 'not-your-role' ? (
        <StateNotice
          variant="flat"
          title={copy('admin_people.page.not_your_role_title')}
          body={copy('admin_people.page.not_your_role_body')}
        />
      ) : (
        children
      )}
    </main>
  );
}
