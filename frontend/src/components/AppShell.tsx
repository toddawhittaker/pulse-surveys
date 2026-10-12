import { useEffect, useRef, useState, type JSX, type ReactNode } from 'react';

import {
  logOut,
  readSessionLandings,
  switchSession,
  type LandingName,
  type SessionLandingsView,
} from '../api/session';
import { copy } from '../copy/landings';
import { forgetSessionToken, sessionToken, storeSessionToken } from '../lib/session';
import './leadershipRollup.css';

/** Where a spec finds the shell's controls. */
export const SHELL_TESTID = 'pulse-shell';
/** The signed-out state, which replaces every page once a sign-out has gone through. */
export const SIGNED_OUT_TESTID = 'pulse-signed-out';

const SIGNED_OUT_HEADING_ID = 'pulse-signed-out-heading';

/** Open a view's landing once a switch has issued its session: a fresh load, so no page keeps the old session's reads. */
function openLanding(role: LandingName): void {
  window.location.assign(`/app/${role}`);
}

/**
 * The app shell: the role switcher and logout (SPEC §2, ADR 0202), above
 * whatever page the address opens.
 *
 * **Drawn only for a session the server answers for.** A tab holding a session
 * asks `GET /session/landings` once; with no session there is nothing to
 * switch from or sign out of, and the page beneath renders exactly as it would
 * alone, without the shell asking anything.
 *
 * **The switcher lists exactly the views the server sent**, current one
 * included and marked, in the server's order; it decides nothing about which
 * views a person holds (§2.1 gives that to the server, which re-reads it on
 * every switch). Choosing one asks the server for a new session in it, holds
 * the new session for the Bearer carrier, and opens that view's landing on a
 * fresh load. A refused switch changes nothing and says so.
 *
 * **Logout** asks the server to end the session, forgets the tab's copy, and
 * shows the signed-out state in place of the page, so nothing read under the
 * ended session stays on screen. A refused logout says so and leaves the
 * session as it was.
 *
 * **Both refusals go into the shell's polite live region**, which exists from
 * the shell's first render, before any refusal can arrive. A pressed control
 * is marked `aria-disabled` rather than disabled while its request is out, so
 * focus stays on it and the refusal is heard where the reader is.
 */
export function AppShell({
  children,
  open = openLanding,
}: {
  readonly children: ReactNode;
  /** Opens a view's landing after a switch; a test passes its own. */
  readonly open?: (role: LandingName) => void;
}): JSX.Element {
  const [landings, setLandings] = useState<SessionLandingsView | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [refusal, setRefusal] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Both doors hand the tab its session in the address's fragment (ADR
    // 0089), so a tab holding none has nothing to switch from or sign out of,
    // and asks nothing.
    if (sessionToken() === null) return;
    let live = true;
    void readSessionLandings().then((answer) => {
      if (live && answer.kind === 'landings') setLandings(answer.landings);
    });
    return () => {
      live = false;
    };
  }, []);

  if (signedOut) {
    return <SignedOut />;
  }
  async function switchTo(role: LandingName): Promise<void> {
    setBusy(true);
    setRefusal('');
    const outcome = await switchSession(role);
    setBusy(false);
    if (outcome.kind === 'refused') {
      setRefusal(copy('landing.switcher.refused'));
      return;
    }
    storeSessionToken(outcome.switched.session);
    open(outcome.switched.role);
  }

  async function signOut(): Promise<void> {
    setBusy(true);
    setRefusal('');
    const outcome = await logOut();
    setBusy(false);
    if (outcome.kind === 'refused') {
      setRefusal(copy('landing.logout.refused'));
      return;
    }
    forgetSessionToken();
    setSignedOut(true);
  }

  return (
    <>
      {landings === null ? null : (
        <header className="pulse-shell-bar" data-testid={SHELL_TESTID}>
          {landings.landings.length > 1 ? (
            <Switcher landings={landings} busy={busy} onSwitch={switchTo} />
          ) : null}
          <button
            type="button"
            className="pulse-shell-button"
            aria-disabled={busy}
            onClick={() => {
              if (busy) return;
              void signOut();
            }}
          >
            {copy('landing.logout.label')}
          </button>
          <p className="pulse-shell-status" role="status">
            {refusal}
          </p>
        </header>
      )}
      {children}
    </>
  );
}

/**
 * The view list and the button that switches to the chosen one. Choosing in the
 * list changes nothing until the button is pressed, so moving through the list
 * with a keyboard never opens another view by itself (WCAG 2.2 SC 3.2.2).
 */
function Switcher({
  landings,
  busy,
  onSwitch,
}: {
  readonly landings: SessionLandingsView;
  readonly busy: boolean;
  readonly onSwitch: (role: LandingName) => Promise<void>;
}): JSX.Element {
  const [chosen, setChosen] = useState<LandingName>(landings.current);
  return (
    <form
      className="pulse-rollup-field"
      onSubmit={(event) => {
        event.preventDefault();
        if (!busy && chosen !== landings.current) void onSwitch(chosen);
      }}
    >
      <label className="pulse-rollup-field">
        {copy('landing.switcher.label')}
        <select
          className="pulse-rollup-select"
          value={chosen}
          aria-disabled={busy}
          onChange={(event) => {
            if (busy) return;
            const picked = landings.landings.find((name) => name === event.target.value);
            if (picked !== undefined) setChosen(picked);
          }}
        >
          {landings.landings.map((name) => (
            <option key={name} value={name}>
              {copy(`landing.view.${name}`)}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        className="pulse-shell-button"
        aria-disabled={busy || chosen === landings.current}
      >
        {copy('landing.switcher.submit')}
      </button>
    </form>
  );
}

/**
 * The signed-out state. Its heading takes focus when it arrives, because the
 * button that was pressed has gone and focus would otherwise fall to the page.
 */
function SignedOut(): JSX.Element {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  return (
    <main className="pulse-landing" data-testid={SIGNED_OUT_TESTID} aria-labelledby={SIGNED_OUT_HEADING_ID}>
      <h1 id={SIGNED_OUT_HEADING_ID} ref={heading} tabIndex={-1}>
        {copy('landing.signed_out.heading')}
      </h1>
      <p>{copy('landing.signed_out.body')}</p>
    </main>
  );
}
