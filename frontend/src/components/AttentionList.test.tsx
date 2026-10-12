import type { ReactNode } from 'react';

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import type { AttentionCardView } from '../api/leadership';
import { AttentionList } from './AttentionList';

afterEach(cleanup);

function card(
  rule: AttentionCardView['rule'],
  ruleName: string,
  stream: AttentionCardView['stream'],
  section: string,
  course: string,
): AttentionCardView {
  return {
    rule,
    rule_name: ruleName,
    stream,
    section_id: `id-${section}`,
    section_code: section,
    course_name: course,
    course_week: 7,
  };
}

/** Three cards in the server's order: by course, then section, then rule. */
const CARDS: AttentionCardView[] = [
  card('response_owed', 'Response required, not yet published after 48 hours', null, 'U2WW', 'CHEM 1210'),
  card('instructor_trend_down', 'Instructor trend down', 'INSTRUCTOR', 'R1WW', 'BIOL 3200'),
  card('response_rate_low', 'Response rate under 40%', null, 'R2WW', 'BIOL 2150'),
];

function link(attention: AttentionCardView, children: ReactNode, label: string) {
  return (
    <a
      aria-label={label}
      href={`/app/leadership/sections/${attention.section_id}?week=${String(attention.course_week)}`}>
      {children}
    </a>
  );
}

describe('AttentionList', () => {
  it('renders the cards in the order they were sent, each naming its rule and linking its report', () => {
    render(<AttentionList cards={CARDS} empty={null} reportLink={link} />);
    const sections = Array.from(document.querySelectorAll('.pulse-attention-section')).map(
      (element) => element.textContent,
    );
    expect(sections).toEqual(['CHEM 1210 · U2WW', 'BIOL 3200 · R1WW', 'BIOL 2150 · R2WW']);
    expect(screen.getByText('Response rate under 40%')).toBeTruthy();
    const links = screen.getAllByRole('link', { name: /^Open the Monday report: / });
    expect(links.map((element) => element.getAttribute('href'))).toEqual([
      '/app/leadership/sections/id-U2WW?week=7',
      '/app/leadership/sections/id-R1WW?week=7',
      '/app/leadership/sections/id-R2WW?week=7',
    ]);
  });

  it('names each link by its section and week, and draws no raw stream token', () => {
    render(<AttentionList cards={CARDS} empty={null} reportLink={link} />);
    expect(
      screen.getByRole('link', { name: 'Open the Monday report: BIOL 3200 · R1WW, week 7' }),
    ).toBeTruthy();
    expect(screen.queryByText('INSTRUCTOR')).toBeNull();
  });

  it('shows the server’s calm sentence when no card is due', () => {
    render(
      <AttentionList cards={[]} empty="Nothing needs attention this week" reportLink={link} />,
    );
    expect(screen.getByText('Nothing needs attention this week')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
  });
});
