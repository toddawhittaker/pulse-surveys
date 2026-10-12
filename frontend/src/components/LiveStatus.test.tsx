import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import { LiveStatus } from './LiveStatus';

afterEach(cleanup);

describe('LiveStatus', () => {
  it('mounts its region empty and gives it the text a tick later', async () => {
    render(<LiveStatus text="Opening the page…" />);
    const region = screen.getByRole('status');
    expect(region.textContent).toBe('');
    await waitFor(() => {
      expect(region.textContent).toBe('Opening the page…');
    });
  });

  it('keeps one region across changes of text', async () => {
    const { rerender } = render(<LiveStatus text="Opening…" />);
    const region = screen.getByRole('status');
    await waitFor(() => {
      expect(region.textContent).toBe('Opening…');
    });
    rerender(<LiveStatus text="Showing MARS" />);
    await waitFor(() => {
      expect(region.textContent).toBe('Showing MARS');
    });
    expect(screen.getByRole('status')).toBe(region);
  });
});
