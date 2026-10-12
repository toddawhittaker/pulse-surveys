import { useEffect, useState, type JSX } from 'react';

/**
 * A polite live region whose text arrives a tick after it does.
 *
 * A screen reader announces a change to a region already in the document, and
 * often nothing for one inserted with its text: a loading line rendered into a
 * region on the region's own first render is said to nobody. This mounts the
 * region empty and sets each text on the next tick, so the first line is a
 * change like every later one.
 */
export function LiveStatus({
  text,
  className,
}: {
  readonly text: string;
  readonly className?: string;
}): JSX.Element {
  const [shown, setShown] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setShown(text);
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [text]);
  return (
    <p className={className} role="status">
      {shown}
    </p>
  );
}
