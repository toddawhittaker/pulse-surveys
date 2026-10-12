import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { LOGOUT_PATH, SESSION_LANDINGS_PATH, SESSION_SWITCH_PATH } from '../api/session';
import { sessionToken } from '../lib/session';
import { AppShell, SHELL_TESTID, SIGNED_OUT_TESTID } from './AppShell';

/**
 * The app shell's role switcher and logout (SPEC §2, ADR 0202), over E9-04's
 * three routes: the list the server sends, a switch through the
 * double-submit-checked route, and a logout that leaves the signed-out state.
 */

const STORAGE_KEY = 'pulse.session';

beforeEach(() => {
  window.sessionStorage.setItem(STORAGE_KEY, 'the-old-session');
  document.cookie = 'pulse_csrf=the-csrf-token';
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  document.cookie = 'pulse_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

interface Ask {
  readonly path: string;
  readonly method: string;
  readonly body: string | null;
  readonly headers: Headers;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function serving(answers: Record<string, () => Response>): Ask[] {
  const asked: Ask[] = [];
  vi.stubGlobal('fetch', (input: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    asked.push({
      path: input,
      method,
      body: typeof init?.body === 'string' ? init.body : null,
      headers: new Headers(init?.headers),
    });
    const answer = answers[`${method} ${input}`];
    if (answer === undefined) {
      return Promise.reject(new Error(`This test serves no answer for ${method} ${input}.`));
    }
    return Promise.resolve(answer());
  });
  return asked;
}

const TWO_VIEWS = { current: 'leadership', landings: ['leadership', 'instructor'] };

function renderShell(open = vi.fn()) {
  render(
    <AppShell open={open}>
      <main>
        <h1>The page</h1>
      </main>
    </AppShell>,
  );
  return open;
}

describe('AppShell', () => {
  it('lists exactly the views the server sent, the current one chosen', async () => {
    serving({ [`GET ${SESSION_LANDINGS_PATH}`]: () => json(200, TWO_VIEWS) });
    renderShell();
    const list = await screen.findByRole('combobox', { name: 'Switch view' });
    const options = Array.from((list as HTMLSelectElement).options).map((option) => [
      option.value,
      option.textContent,
    ]);
    expect(options).toEqual([
      ['leadership', 'Leadership'],
      ['instructor', 'Instructor'],
    ]);
    expect((list as HTMLSelectElement).value).toBe('leadership');
    expect(screen.getByRole('button', { name: 'Switch' }).hasAttribute('disabled')).toBe(true);
  });

  it('switches through the double-submit route, holds the new session, and opens its view', async () => {
    const asked = serving({
      [`GET ${SESSION_LANDINGS_PATH}`]: () => json(200, TWO_VIEWS),
      [`POST ${SESSION_SWITCH_PATH}`]: () =>
        json(200, { role: 'instructor', session: 'the-new-session' }),
    });
    const open = renderShell();
    const list = await screen.findByRole('combobox', { name: 'Switch view' });
    fireEvent.change(list, { target: { value: 'instructor' } });
    // Choosing alone opens nothing (WCAG 2.2 SC 3.2.2); the button does.
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));

    await waitFor(() => {
      expect(open).toHaveBeenCalledWith('instructor');
    });
    const sent = asked.find((ask) => ask.method === 'POST');
    expect(sent?.path).toBe(SESSION_SWITCH_PATH);
    expect(sent?.body).toBe(JSON.stringify({ role: 'instructor' }));
    expect(sent?.headers.get('X-Pulse-CSRF')).toBe('the-csrf-token');
    expect(sessionToken()).toBe('the-new-session');
  });

  it('says a refused switch changed nothing, in the live region that was already there', async () => {
    serving({
      [`GET ${SESSION_LANDINGS_PATH}`]: () => json(200, TWO_VIEWS),
      [`POST ${SESSION_SWITCH_PATH}`]: () => json(403, { detail: 'That view is not yours.' }),
    });
    const open = renderShell();
    const list = await screen.findByRole('combobox', { name: 'Switch view' });
    const region = screen.getByRole('status');
    expect(region.textContent).toBe('');
    fireEvent.change(list, { target: { value: 'instructor' } });
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));
    await waitFor(() => {
      expect(region.textContent).toBe(
        'That view could not be opened. Your current view is unchanged.',
      );
    });
    expect(open).not.toHaveBeenCalled();
    expect(sessionToken()).toBe('the-old-session');
  });

  it('offers no switcher for one view, and logs out to the signed-out state', async () => {
    const asked = serving({
      [`GET ${SESSION_LANDINGS_PATH}`]: () => json(200, { current: 'leadership', landings: ['leadership'] }),
      [`POST ${LOGOUT_PATH}`]: () => new Response(null, { status: 204 }),
    });
    renderShell();
    const signOut = await screen.findByRole('button', { name: 'Sign out' });
    expect(screen.queryByRole('combobox', { name: 'Switch view' })).toBeNull();
    fireEvent.click(signOut);

    expect(await screen.findByTestId(SIGNED_OUT_TESTID)).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('You are signed out');
    expect(screen.queryByText('The page')).toBeNull();
    expect(sessionToken()).toBeNull();
    const sent = asked.find((ask) => ask.method === 'POST');
    expect(sent?.path).toBe(LOGOUT_PATH);
    expect(sent?.headers.get('X-Pulse-CSRF')).toBe('the-csrf-token');
  });

  it('says a refused logout did not go through, and keeps the session', async () => {
    serving({
      [`GET ${SESSION_LANDINGS_PATH}`]: () => json(200, TWO_VIEWS),
      [`POST ${LOGOUT_PATH}`]: () => json(403, { detail: 'No.' }),
    });
    renderShell();
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toBe(
        'Signing out did not go through. Please try again.',
      );
    });
    expect(screen.getByText('The page')).toBeTruthy();
    expect(sessionToken()).toBe('the-old-session');
  });

  it('draws nothing and asks nothing in a tab with no session', () => {
    window.sessionStorage.clear();
    const asked = serving({});
    renderShell();
    expect(screen.queryByTestId(SHELL_TESTID)).toBeNull();
    expect(screen.getByText('The page')).toBeTruthy();
    expect(asked).toEqual([]);
  });
});
