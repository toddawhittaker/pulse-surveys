import { useEffect, useId, useRef, useState } from 'react';
import type { JSX } from 'react';

import type {
  CheckThemeView,
  DraftCheckOutcome,
  ResponseDraftOutcome,
  ResponseWriteOutcome,
  ResponseWriteView,
  WeekResponseRead,
} from '../api/instructor';
import { copy, fillCopy } from '../copy/instructorReportPageCopy';
import { copy as leadershipCopy } from '../copy/leadershipResponseCopy';
import { AiPanel } from './AiPanel';
import { ResponseCard } from './ResponseCard';
import { StateNotice } from './StateNotice';
import './instructorResponse.css';

/**
 * The longest response the server accepts, in characters
 * (`app.models.loop.RESPONSE_TEXT_MAX`). The wire schema carries the bound only
 * as a JSON Schema keyword the generated types drop, so it is written here once
 * and a unit test fails when it and the backend's differ.
 */
export const RESPONSE_MAX_LENGTH = 4000;

/**
 * The four calls the composer makes, supplied by the page so that a second
 * surface can point the same composer at its own doors.
 *
 * **Only `publish` and `edit` post anything.** `draft` and `check` are advisory:
 * the server stores neither the draft nor the check (SPEC §5.3).
 */
export type ResponseActions = {
  readonly draft: () => Promise<ResponseDraftOutcome>;
  readonly check: (draft: string) => Promise<DraftCheckOutcome>;
  readonly publish: (write: ResponseWriteView) => Promise<ResponseWriteOutcome>;
  readonly edit: (write: ResponseWriteView) => Promise<ResponseWriteOutcome>;
};

type Busy = 'draft' | 'check' | 'write' | null;

/**
 * The instructor's response to one week — SPEC §5.3.
 *
 * **Nothing posts but the publish button.** Using a draft puts text in the
 * editor, a check lists themes, and typing changes the editor; none of those
 * calls a write. The server's draft and check are advisory (SPEC §5.3).
 *
 * **A check shows only for the text it ran on.** The result is stored with the
 * text it was run against and drawn only while the editor still holds exactly
 * that text, so changing one character removes it, and an answer that arrives
 * after the text moved on is never shown beside a draft it was not about.
 *
 * **Replacing needs a yes.** A draft fills an empty editor; over text the
 * instructor wrote it waits behind an inline question. Whether the text began
 * as a draft is what `ai_seeded` records, and emptying the editor ends it.
 *
 * After publishing, the page shows the response as students read it, with an
 * Edit path for the person who first published it. Whether a response exists,
 * whether the week is held, and whether this reader may edit are the server's
 * answers (`state`, `can_edit`), never worked out here.
 */
export function InstructorResponse({
  initial,
  actions,
  timeZone,
  onBehalf = false,
}: {
  /** The week's state and response, as the instructor's read of it answered. */
  readonly initial: WeekResponseRead;
  readonly actions: ResponseActions;
  /** The institution's IANA zone, for the card's date, when the page has it. */
  readonly timeZone?: string;
  /**
   * The lead or chair responding for a section (SPEC §5.3). The same composer
   * pointed at the on-behalf doors through `actions`; this changes the words
   * that name who is writing. Whether the reader may edit what they published
   * is the server's `can_edit`, as for the instructor.
   */
  readonly onBehalf?: boolean;
}): JSX.Element {
  const [view, setView] = useState<WeekResponseRead>(initial);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const [seeded, setSeeded] = useState(false);
  const [pendingDraft, setPendingDraft] = useState<string | null>(null);
  const [check, setCheck] = useState<{
    readonly ranOn: string;
    readonly themes: readonly CheckThemeView[];
  } | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  // Counted so that the same sentence twice is a new node, which a screen
  // reader announces again.
  const [announcement, setAnnouncement] = useState<{
    readonly text: string;
    readonly n: number;
  }>({
    text: '',
    n: 0,
  });
  // A failed draft or check is advice that did not arrive; only a failed
  // publish or edit is a fault in what the instructor wrote or sent.
  const [advisory, setAdvisory] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const textRef = useRef(text);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(true);
  const fieldId = useId();
  const counterId = useId();
  const problemId = useId();
  const replaceId = useId();
  const replaceYesRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const published = view.response;
  const composing = published === null || editing;

  useEffect(() => {
    if (pendingDraft !== null) replaceYesRef.current?.focus();
  }, [pendingDraft]);

  function announce(text: string): void {
    setAnnouncement((last) => ({ text, n: last.n + 1 }));
  }

  function changeText(next: string): void {
    textRef.current = next;
    setText(next);
    setProblem(null);
    setAdvisory(null);
    if (next === '') {
      setSeeded(false);
      setPendingDraft(null);
    }
  }

  function failure(
    outcome: {
      readonly kind: 'refused' | 'session-ended' | 'unavailable';
      readonly detail?: string | null;
    },
    unavailable: Parameters<typeof copy>[0],
  ): string {
    if (outcome.kind === 'session-ended')
      return copy('instructor_report_page.response_session_ended');
    return outcome.detail ?? copy(unavailable);
  }

  async function fetchDraft(): Promise<void> {
    if (busy !== null) return;
    setBusy('draft');
    setProblem(null);
    setAdvisory(null);
    const outcome = await actions.draft();
    if (!mounted.current) return;
    setBusy(null);
    if (outcome.kind !== 'draft') {
      setAdvisory(failure(outcome, 'instructor_report_page.response_draft_unavailable'));
      return;
    }
    // Decided when the draft arrives, not when the button was pressed: text
    // typed while the draft was being written is text to ask about.
    if (textRef.current.trim() === '') {
      applyDraft(outcome.text);
    } else {
      setPendingDraft(outcome.text);
    }
  }

  function applyDraft(draft: string): void {
    changeText(draft);
    setSeeded(true);
    setPendingDraft(null);
    announce(copy('instructor_report_page.response_draft_ready'));
    fieldRef.current?.focus();
  }

  async function runCheck(): Promise<void> {
    if (busy !== null || textRef.current.trim() === '') return;
    const ranOn = textRef.current;
    setBusy('check');
    setProblem(null);
    setAdvisory(null);
    const outcome = await actions.check(ranOn);
    if (!mounted.current) return;
    setBusy(null);
    if (outcome.kind !== 'checked') {
      setAdvisory(failure(outcome, 'instructor_report_page.response_check_unavailable'));
      return;
    }
    setCheck({ ranOn, themes: outcome.unaddressed });
  }

  async function send(): Promise<void> {
    if (busy !== null || textRef.current.trim() === '') return;
    setBusy('write');
    setAdvisory(null);
    setProblem(null);
    const write = { text, ai_seeded: seeded };
    const outcome = await (published === null ? actions.publish(write) : actions.edit(write));
    if (!mounted.current) return;
    setBusy(null);
    if (outcome.kind !== 'saved') {
      setProblem(failure(outcome, 'instructor_report_page.response_write_unavailable'));
      return;
    }
    const wasEdit = published !== null;
    setView(outcome.view);
    setEditing(false);
    changeText('');
    setCheck(null);
    announce(
      copy(
        wasEdit
          ? 'instructor_report_page.response_edited_announce'
          : 'instructor_report_page.response_published_announce',
      ),
    );
    // The editor is gone, so focus would fall to the page; the heading names
    // what changed.
    requestAnimationFrame(() => headingRef.current?.focus());
  }

  function startEdit(): void {
    if (published === null) return;
    changeText(published.text);
    setSeeded(false);
    setCheck(null);
    setEditing(true);
    requestAnimationFrame(() => fieldRef.current?.focus());
  }

  function cancelEdit(): void {
    changeText('');
    setCheck(null);
    setEditing(false);
    requestAnimationFrame(() => headingRef.current?.focus());
  }

  const blank = text.trim() === '';
  const checkShown = check !== null && check.ranOn === text ? check : null;

  return (
    <section className="pulse-instructor-response" aria-labelledby={`${fieldId}-heading`}>
      <h2 className="pulse-report-heading" id={`${fieldId}-heading`} ref={headingRef} tabIndex={-1}>
        {onBehalf
          ? leadershipCopy('leadership_response.composer.heading')
          : copy('instructor_report_page.response_heading')}
      </h2>
      {/* Always in the tree: a live region added together with its text is not
          reliably announced. Hidden by position, never by display. */}
      <p className="pulse-instructor-response__live sr-only" role="status">
        <span key={announcement.n}>{announcement.text}</span>
      </p>

      {published === null && view.state === 'awaiting' ? (
        <StateNotice
          variant="flat"
          title={copy('instructor_report_page.response_hold_title')}
          body={copy('instructor_report_page.response_hold_body')}
        />
      ) : null}

      {published !== null && !editing ? (
        <div className="pulse-instructor-response__published">
          <p className="pulse-instructor-response__card-label">
            {copy('instructor_report_page.response_card_heading')}
          </p>
          <ResponseCard
            text={published.text}
            authorName={published.author_name}
            authorRole={published.author_role}
            publishedAt={published.published_at}
            timeZone={timeZone}
          />
          {view.can_edit ? (
            <div className="pulse-instructor-response__actions">
              <button
                type="button"
                className="pulse-instructor-response__button"
                onClick={startEdit}
              >
                {copy('instructor_report_page.response_edit')}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {composing ? (
        <form
          className="pulse-instructor-response__composer"
          onSubmit={(event) => {
            event.preventDefault();
          }}
        >
          <p className="pulse-instructor-response__intro">
            {onBehalf
              ? leadershipCopy('leadership_response.composer.intro')
              : copy('instructor_report_page.response_intro')}
          </p>
          <label className="pulse-instructor-response__label" htmlFor={fieldId}>
            {copy('instructor_report_page.response_field_label')}
          </label>
          <textarea
            id={fieldId}
            ref={fieldRef}
            className="pulse-instructor-response__field"
            maxLength={RESPONSE_MAX_LENGTH}
            aria-invalid={problem !== null}
            aria-describedby={problem === null ? counterId : `${counterId} ${problemId}`}
            value={text}
            onChange={(event) => {
              changeText(event.target.value);
            }}
          />
          <span className="pulse-instructor-response__counter" id={counterId}>
            {fillCopy('instructor_report_page.response_remaining', {
              remaining: String(RESPONSE_MAX_LENGTH - text.length),
            })}
          </span>

          {pendingDraft === null ? null : (
            <div
              className="pulse-instructor-response__confirm"
              role="group"
              aria-labelledby={replaceId}
            >
              <p id={replaceId}>{copy('instructor_report_page.response_replace_prompt')}</p>
              <div className="pulse-instructor-response__actions">
                <button
                  type="button"
                  ref={replaceYesRef}
                  className="pulse-instructor-response__button"
                  onClick={() => {
                    applyDraft(pendingDraft);
                  }}
                >
                  {copy('instructor_report_page.response_replace_yes')}
                </button>
                <button
                  type="button"
                  className="pulse-instructor-response__button"
                  onClick={() => {
                    setPendingDraft(null);
                    fieldRef.current?.focus();
                  }}
                >
                  {copy('instructor_report_page.response_replace_no')}
                </button>
              </div>
            </div>
          )}

          <div className="pulse-instructor-response__actions">
            <button
              type="button"
              className="pulse-instructor-response__button"
              aria-disabled={busy !== null}
              onClick={() => void fetchDraft()}
            >
              {copy('instructor_report_page.response_use_draft')}
            </button>
            <button
              type="button"
              className="pulse-instructor-response__button"
              aria-disabled={busy !== null || blank}
              onClick={() => void runCheck()}
            >
              {copy('instructor_report_page.response_check')}
            </button>
            <button
              type="button"
              className="pulse-instructor-response__button pulse-instructor-response__button--primary"
              aria-disabled={busy !== null || blank}
              onClick={() => void send()}
            >
              {copy(
                published === null
                  ? 'instructor_report_page.response_publish'
                  : 'instructor_report_page.response_publish_changes',
              )}
            </button>
            {published === null ? null : (
              <button
                type="button"
                className="pulse-instructor-response__button"
                onClick={cancelEdit}
              >
                {copy('instructor_report_page.response_cancel_edit')}
              </button>
            )}
          </div>

          {busy === null ? null : (
            <p className="pulse-instructor-response__busy" role="status">
              {copy(
                busy === 'draft'
                  ? 'instructor_report_page.response_drafting'
                  : busy === 'check'
                    ? 'instructor_report_page.response_checking'
                    : 'instructor_report_page.response_publishing',
              )}
            </p>
          )}
          {/* Always in the tree while the composer is, and filled when advice
              fails to arrive: a status paragraph inserted together with its
              text may not be announced at all. Empty, it takes no space. */}
          <p className="pulse-instructor-response__advisory" role="status">
            {advisory}
          </p>
          {problem === null ? null : (
            <p className="pulse-instructor-response__problem" id={problemId} role="alert">
              {problem}
            </p>
          )}

          {checkShown === null ? null : <CheckResult themes={checkShown.themes} />}
        </form>
      ) : null}
    </section>
  );
}

/** The draft check's themes, in an AI panel: quiet, and never a reason not to publish. */
function CheckResult({ themes }: { readonly themes: readonly CheckThemeView[] }): JSX.Element {
  return (
    <AiPanel
      heading={copy('instructor_report_page.response_check_heading')}
      text={copy(
        themes.length === 0
          ? 'instructor_report_page.response_check_none'
          : 'instructor_report_page.response_check_some',
      )}
    >
      {themes.length === 0 ? null : (
        <ul className="pulse-instructor-response__themes">
          {themes.map((theme, position) => (
            <li key={position}>
              {theme.comment_count === null
                ? theme.label
                : theme.comment_count === 1
                  ? fillCopy('instructor_report_page.response_check_theme_one', {
                      label: theme.label,
                    })
                  : fillCopy('instructor_report_page.response_check_theme', {
                      label: theme.label,
                      count: String(theme.comment_count),
                    })}
            </li>
          ))}
        </ul>
      )}
    </AiPanel>
  );
}
