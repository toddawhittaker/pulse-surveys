import { useCallback, useState } from 'react';

/** One thing the page says in its live region; a new `id` makes an identical `text` count as new. */
export type Announcement = { readonly id: number; readonly text: string };

/**
 * The page's announcement and the stable function that makes one.
 *
 * **Every call is a new announcement even when its text repeats.** A live
 * region says nothing for a change that leaves its text as it was, so a second
 * refusal in the same words would be silent; the counter lets `AdminPage` clear
 * and re-set the region it already has.
 */
export function useAnnouncer(first: string): readonly [Announcement, (text: string) => void] {
  const [announcement, setAnnouncement] = useState<Announcement>({ id: 0, text: first });
  const announce = useCallback((text: string): void => {
    setAnnouncement((previous) => ({ id: previous.id + 1, text }));
  }, []);
  return [announcement, announce];
}
