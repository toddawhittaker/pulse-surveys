import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { PolicyToggle } from './PolicyToggle';

afterEach(cleanup);

function mount(busy: boolean) {
  const onToggle = vi.fn();
  render(
    <PolicyToggle
      detail="Covers BIOL."
      ariaLabel="Response required"
      checked={false}
      busy={busy}
      onToggle={onToggle}
    />,
  );
  return { onToggle, toggle: screen.getByRole('switch') };
}

describe('the response-required switch', () => {
  it('is described by the sentence saying what on does', () => {
    const { toggle } = mount(false);
    const described = document.getElementById(toggle.getAttribute('aria-describedby') ?? '');
    expect(described?.textContent).toContain('student results for each week are held');
  });

  it('keeps focus and ignores presses while a change is in flight', () => {
    const { onToggle, toggle } = mount(true);
    toggle.focus();
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-disabled')).toBe('true');
    expect(toggle.hasAttribute('disabled')).toBe(false);
    expect(document.activeElement).toBe(toggle);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('toggles when idle', () => {
    const { onToggle, toggle } = mount(false);
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledWith(true);
  });
});
