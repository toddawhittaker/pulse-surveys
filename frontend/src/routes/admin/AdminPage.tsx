import { useEffect, useRef, type JSX, type ReactNode } from 'react';

import { StateNotice } from '../../components/StateNotice';
import { copy } from '../../copy/adminPeople';
import type { Announcement } from './announcer';
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
 * through `announcement`, the refusals the server sent included. It sticks to
 * the top of the window so an outcome stays in view while a long page scrolls.
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
  readonly announcement: Announcement;
  readonly gate: Gate;
  readonly children: ReactNode;
}): JSX.Element {
  const region = useRef<HTMLParagraphElement>(null);

  // The region is cleared and set again for each announcement, so one whose text
  // matches the last is still a change a screen reader says. The node is the same
  // one throughout; it is never replaced.
  useEffect(() => {
    const node = region.current;
    if (node === null) return undefined;
    node.textContent = '';
    const timer = window.setTimeout(() => {
      node.textContent = announcement.text;
    }, 0);
    return () => window.clearTimeout(timer);
  }, [announcement]);

  return (
    <main className="pulse-admin-page" data-testid={testid} aria-labelledby={headingId}>
      <h1 className="pulse-admin-title" id={headingId}>
        {heading}
      </h1>
      <p className="pulse-admin-intro">{intro}</p>
      <p ref={region} className="pulse-admin-announcement" role="status" aria-live="polite" />
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
