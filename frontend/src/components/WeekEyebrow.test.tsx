import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WeekEyebrow } from './WeekEyebrow';

describe('WeekEyebrow', () => {
  it('names both week axes in words and states the closing instant', () => {
    const closesAt = '2026-09-10T18:00:00Z';

    render(<WeekEyebrow courseWeek={4} termWeek={7} lengthWeeks={12} closesAt={closesAt} />);

    expect(screen.getByText('COURSE WK 04 / 12,')).toBeTruthy();
    expect(screen.getByText('TERM WK 07')).toBeTruthy();

    const expectedClose = new Intl.DateTimeFormat(undefined, {
      weekday: 'short',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(closesAt));

    expect(screen.getByText(`closes ${expectedClose}`)).toBeTruthy();
  });

  it('shows the closing instant as it arrived when it cannot be parsed', () => {
    render(<WeekEyebrow courseWeek={1} termWeek={1} lengthWeeks={12} closesAt="not-a-date" />);

    expect(screen.getByText('closes not-a-date')).toBeTruthy();
  });
});
