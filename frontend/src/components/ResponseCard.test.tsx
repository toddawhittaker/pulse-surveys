import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';

import { ResponseCard } from './ResponseCard';

/** Governed copy is transcribed rather than imported (`docs/MISTAKES.md` entry 19). */

afterEach(cleanup);

// 02:30 UTC on 14 September is 22:30 on the 13th in New York, so the date shown
// tells the institution's zone from UTC and from the machine's.
const PUBLISHED = '2026-09-14T02:30:00Z';

function card(role: 'INSTRUCTOR' | 'LEAD_FACULTY' | 'CHAIR', timeZone?: string) {
  const { container } = render(
    <ResponseCard
      text={'Thank you.\nWe will slow down.'}
      authorName="Ada Lovelace"
      authorRole={role}
      publishedAt={PUBLISHED}
      timeZone={timeZone}
    />,
  );
  return container;
}

describe('ResponseCard', () => {
  it('names the instructor and nothing else about the author', () => {
    const byline = card('INSTRUCTOR', 'America/New_York').querySelector('.pulse-response-author');
    expect(byline?.textContent).toBe('Ada Lovelace');
  });

  it('names the lead and the role for a lead’s reply', () => {
    const byline = card('LEAD_FACULTY', 'America/New_York').querySelector('.pulse-response-author');
    expect(byline?.textContent).toBe('Ada Lovelace, Lead Faculty');
  });

  it('names the chair and the role for a chair’s reply', () => {
    const byline = card('CHAIR', 'America/New_York').querySelector('.pulse-response-author');
    expect(byline?.textContent).toBe('Ada Lovelace, Department Chair');
  });

  it('draws the three variants with the same structure and implies no discipline', () => {
    const shapes = (['INSTRUCTOR', 'LEAD_FACULTY', 'CHAIR'] as const).map((role) => {
      const container = card(role, 'America/New_York');
      const shape = [...container.querySelectorAll('*')].map((it) => `${it.tagName}.${it.className}`);
      const words = container.textContent ?? '';
      cleanup();
      return { shape, words };
    });
    expect(shapes[1]?.shape).toEqual(shapes[0]?.shape);
    expect(shapes[2]?.shape).toEqual(shapes[0]?.shape);
    for (const { words } of shapes) {
      expect(words).not.toMatch(/instead|missed|late|behalf|unable|failed/i);
    }
  });

  it('shows the reply as text, line breaks kept, and the date in the institution’s zone', () => {
    const container = card('INSTRUCTOR', 'America/New_York');
    expect(container.querySelector('.pulse-response-text')?.textContent).toBe(
      'Thank you.\nWe will slow down.',
    );
    expect(container.querySelector('.pulse-response-date')?.textContent).toBe(
      'Published Sunday, September 13',
    );
  });

  it('shows no date rather than a guessed one when the zone is unknown', () => {
    expect(card('INSTRUCTOR').querySelector('.pulse-response-date')).toBeNull();
    cleanup();
    expect(card('INSTRUCTOR', 'Not/AZone').querySelector('.pulse-response-date')).toBeNull();
  });
});
