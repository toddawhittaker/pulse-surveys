import { useId } from 'react';
import type { JSX } from 'react';

import './instructorReportComments.css';
import { copy, fillCopy } from './instructorReportCommentCopy';

/**
 * The AI summary leading a comment group — SPEC §7.6's `AiPanel`.
 *
 * `docs/DESIGN_BRIEF.md` gives AI-generated content one treatment everywhere it
 * appears: "a chalk-tinted inset panel with a small mono 'AI' label in
 * spruce-60 — one consistent treatment, so provenance is legible at a glance
 * and never mistaken for a human voice". That is what this is, and the label is
 * not optional.
 *
 * **The response count is the payload's number.** SPEC §5.1 requires a summary
 * to state the count it draws from, and ADR 0148 settles who supplies it: the
 * caller, from data, never the model — "an instructor reading 'drawn from 12
 * responses' under a week of five is the only person who could notice, and
 * cannot". So this component states `responseCount` and derives nothing: it
 * does not count comments (§3.2 makes a comment optional, so the two numbers
 * differ), and it has no comment list to count.
 *
 * **The held note appears exactly when the payload populates it.** §5.1 lets a
 * summary note "one comment is held for review" with the type only, and §5.2
 * makes that a decision about the threshold and the week — the payload's
 * decision. There is no threshold logic here and no rule about when the note is
 * appropriate: a non-null `heldNote` renders the sentence, a null one renders
 * nothing.
 *
 * The panel is a labelled region, named by its own heading, so it is reachable
 * and announced rather than being an unnamed box of prose.
 */
export function AiPanel({
  heading,
  text,
  responseCount,
  heldNote,
}: {
  readonly heading: string;
  readonly text: string;
  readonly responseCount: number;
  /**
   * The type of a comment held for review, per ADR 0148's `held_note_type` —
   * `null` whenever the payload holds none, which is every E4 week (E6 writes
   * the moderation states that populate it).
   */
  readonly heldNote: string | null;
}): JSX.Element {
  const headingId = useId();

  return (
    <section className="pulse-ai-panel" aria-labelledby={headingId}>
      <div className="pulse-ai-panel__provenance">
        <span className="pulse-ai-panel__label">{copy('instructor_report_comments.ai.label')}</span>
        <p className="pulse-ai-panel__heading" id={headingId}>
          {heading}
        </p>
      </div>
      <p className="pulse-ai-panel__text">{text}</p>
      <p className="pulse-ai-panel__meta">
        {responseCount === 1
          ? copy('instructor_report_comments.ai.drawn_from_one')
          : fillCopy('instructor_report_comments.ai.drawn_from', {
              count: String(responseCount),
            })}
      </p>
      {heldNote === null ? null : (
        <p className="pulse-ai-panel__meta">
          {fillCopy('instructor_report_comments.ai.held_note', { type: heldNote })}
        </p>
      )}
    </section>
  );
}
