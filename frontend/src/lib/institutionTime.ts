/**
 * One instant in the institution's zone, as the two halves of the ruled sentence.
 *
 * "6:00PM EDT" and "Friday, September 4". **The zone abbreviation is derived and
 * never written down**, which is the whole point of the ruling: the same six
 * o'clock is EDT in October and EST in November, and a page carrying either
 * letter as a literal tells half the term's students the wrong hour.
 * `formatToParts` is what lets the abbreviation be taken from the format without
 * accepting the punctuation the locale would put around it — "6:00 PM" has a
 * space the ruled shape does not.
 *
 * **`en-US` deliberately, rather than the reader's locale.** The eyebrow's
 * closing instant follows the reader, because it is a bare time inside their own
 * day; this one is filled into an English sentence the owner ruled word for word,
 * and a date formatted to another locale's conventions inside it would read as
 * neither.
 *
 * **The zone is the institution's, not the browser's** (SPEC §8, §3.1). A survey
 * opens at six o'clock where the institution is; a student reading in another
 * zone is owed the institution's hour, which is the one the door will actually
 * open at.
 *
 * `null` when the instant will not parse or the zone is not one `Intl` knows —
 * `Intl.DateTimeFormat` throws a `RangeError` on an unknown zone — so the caller
 * falls back to the undated sentence rather than rendering "Invalid Date".
 */
export function institutionInstant(
  instant: string,
  timeZone: string,
): { readonly time: string; readonly day: string } | null {
  const when = new Date(instant);
  if (Number.isNaN(when.getTime())) return null;
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    }).formatToParts(when);
  } catch {
    return null;
  }
  const held = new Map(parts.map((part) => [part.type, part.value]));
  const named = ['hour', 'minute', 'dayPeriod', 'timeZoneName', 'weekday', 'month', 'day'] as const;
  if (named.some((type) => held.get(type) === undefined)) return null;
  return {
    time: `${held.get('hour')}:${held.get('minute')}${held.get('dayPeriod')} ${held.get('timeZoneName')}`,
    day: `${held.get('weekday')}, ${held.get('month')} ${held.get('day')}`,
  };
}
