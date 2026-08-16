"""One typed output contract per SPEC §7.4 task — ticket E0-12.

§7.4 lists five model tasks and, for each, what it outputs. This module declares
those five outputs as Pydantic models, before any of them has a caller, so the
shape is decided deliberately rather than falling out of whichever
implementation happens to arrive first.

**One model, three jobs.** §7.4: "The same models serve three purposes without
duplication: the runtime contract, the API response schema, and the eval
fixtures in §9.3 — so an eval case is a typed object, not a string comparison."
That is why nothing here may be forked for API or eval use. A second shape for
the same task is free to drift from the first, and the moment it does, an eval
case stops proving anything about what the gateway actually validates. Where an
API response needs something these do not carry, it composes one of these rather
than restating it.

**What a contract carries.** Each one carries the task's output and the two
values that make a stored result reproducible: the prompt version and the model
ID (`AiTaskOutput` below, and
`docs/adr/0031-every-task-contract-carries-the-prompt-version-and-model-id.md`
for why all five rather than the two classifiers §7.4's sentence names).

**What a contract does not carry: identity.** These models are the API response
schema and the eval fixture as well as the runtime contract, and an eval set is
a file committed to the repository. A field naming a student would therefore be
confidential text in git *and* in an HTTP response. §4 permits re-identification
only through the audited Care reveal (§6.2), so nothing here is keyed to a
student, and the comment being classified is not echoed back either — the
gateway knows which comment it sent.

**Single-shot.** §7.4: every task in the table is one call in, one validated
object out. There is no field here for a reasoning trace, a tool call or an
intermediate step, because there is no loop to record. "The agent decided to
check three things and concluded" is not a defensible record when a participation
grade or a safety flag is questioned.

Related decisions:
`docs/adr/0030-a-verdict-is-an-enum-whose-value-is-the-stored-token.md`,
`docs/adr/0031-every-task-contract-carries-the-prompt-version-and-model-id.md`,
`docs/adr/0032-a-prompt-file-is-immutable-once-a-classification-cites-it.md`.
"""

import enum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Closed sets
# ---------------------------------------------------------------------------


class ValidityVerdict(enum.Enum):
    """§7.4's output for the comment-validity task, and §3.3's gate.

    "Each submitted comment is classified by the AI provider as **substantive /
    insufficient / nonsense**" — three answers, no more and no fewer. A fourth
    is a value §3.3's participation gating has no branch for; a missing one is an
    answer the provider is asked for and cannot give.

    The value is the token that gets stored and compared, never the member name:
    ADR 0030.
    """

    SUBSTANTIVE = "substantive"
    INSUFFICIENT = "insufficient"
    NONSENSE = "nonsense"


class ModerationVerdict(enum.Enum):
    """§7.4's output for the moderation task: clear / harmful / privacy /
    nonsense / threat / self-harm.

    Six members, and the last two are why the count is exact. §5.2 routes abuse
    aimed at the instructor to the Lead Faculty queue and self-harm to Care
    immediately; §6.2 gives threat-of-harm and self-harm risk their own queue,
    suppressed from every instructor and leadership view; §9.3 makes the threat
    and self-harm recall floor the strictest gate in the suite.

    **`THREAT` and `SELF_HARM` are two members and may never become one.**
    Folding them — or making one an alias of the other, which reads as six names
    over five verdicts — leaves §6.2's queue unable to tell a threat to another
    person from a student at risk, and makes §9.3's recall floor a measurement of
    something other than what it names.
    """

    CLEAR = "clear"
    HARMFUL = "harmful"
    PRIVACY = "privacy"
    NONSENSE = "nonsense"
    THREAT = "threat"
    SELF_HARM = "self_harm"


class CommentStream(enum.Enum):
    """The two streams every comment surface in the product is grouped by.

    §5.1: comments are grouped under "About the instructor" / "About the course,"
    each group led by its own AI summary, and the trend charts are a stacked pair
    over the same two streams. A summary is produced per stream, so it says which
    one it is about.
    """

    INSTRUCTOR = "instructor"
    COURSE = "course"


# ---------------------------------------------------------------------------
# What every task output carries
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    """How everything in this module validates. No fields — the posture only.

    Stated once rather than on each model, so a part added later cannot quietly
    arrive without it. Three choices, each load-bearing:

    - `extra="forbid"` — a provider is an untrusted dependency (`CLAUDE.md`), and
      §7.4 has the gateway "retry on shape violations" rather than store
      whatever came back. A field nobody declared is a shape violation, including
      one the provider volunteered that happens to share a name with something
      real.
    - `frozen=True` — a validated output is a record of what a model returned. It
      is written once, stored, and read by the drift panel (§6.1) and by eval
      cases (§9.3); mutating one after validation would make those two disagree
      about the same run.
    - `protected_namespaces=()` — pydantic reserves the `model_` prefix for its
      own methods and warns on any field using it. `model_id` is the spec's
      word (§7.4) and there is no `model_id` method to shadow, so the reservation
      is lifted here rather than the spec's vocabulary being renamed around it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class AiTaskOutput(ContractModel):
    """The audit pair every §7.4 task output carries.

    §7.4: "Prompts are versioned in-repo; every classification stores prompt
    version and model ID for reproducibility", and the single-shot boundary rests
    on exactly this — "the threat/self-harm classifier must be auditable, meaning
    a specific prompt version and model ID produced a specific classification for
    a specific comment." Both fields are required. An optional one gives every
    reader of the model an auditability field and every record written through it
    permission to carry nothing, which is the shape that reads as a guarantee and
    is not one.

    ADR 0031 records why all five contracts inherit this rather than the two
    classifiers alone, and why the gateway rather than the model supplies the
    values.

    Every task contract below inherits this. Nothing else should: a model that is
    a *part* of a contract inherits `ContractModel` instead, because the audit
    pair belongs to a call and a call produces one object.
    """

    prompt_version: str = Field(
        min_length=1,
        description=(
            "The prompt file this output was produced by, named as its path stem under "
            "`app/ai/prompts/` — for example `validity.v1`. That directory's README states "
            "the scheme, and a file it names is never edited in place (ADR 0032), so the "
            "value identifies exactly one text."
        ),
    )
    model_id: str = Field(
        min_length=1,
        description=(
            "The provider's identifier for the model that produced this output, as the "
            "provider spells it. §9.3's eval floors compare runs of different models, so a "
            "stored verdict that does not name one cannot be placed in that comparison."
        ),
    )


class CommentTheme(ContractModel):
    """A theme drawn from one week's comments, with how many comments carry it.

    Shared by the weekly summary and the draft check because both name themes
    and both count the comments behind them — §7.4 gives the draft check the
    output "Names themes the draft hasn't addressed, **with comment counts**",
    and §5.1 requires a summary to "state the response count they draw from".
    Composing one part into two contracts is what E0-12 means by "compose rather
    than copy"; two near-identical theme models would be the copy.

    This is not a confidentiality-critical read path, so the carve-out in
    `CLAUDE.md` for deliberate duplication does not apply — nothing here is an
    identity-separated query.

    It carries no prompt version or model ID of its own: it is part of an object
    that carries them, and repeating the pair on every theme would put four
    copies of one fact in a summary with four themes.
    """

    label: str = Field(
        min_length=1,
        description="A short phrase naming the theme, in the words of the comments it covers.",
    )
    comment_count: int = Field(
        ge=1,
        description=(
            "How many of the week's comments carry this theme. At least one: a theme drawn "
            "from no comment is a theme the model invented, and §5.1 has summaries preserve "
            "what students actually said rather than sand it into something smoother."
        ),
    )


# ---------------------------------------------------------------------------
# The five task contracts, in §7.4's table order
# ---------------------------------------------------------------------------


class CommentValidityOutput(AiTaskOutput):
    """§7.4, "Comment validity" — substantive / insufficient / nonsense.

    §3.3 makes this the participation gate: a comment classified `nonsense`
    reduces the section's validity rate, and an `insufficient` one is refused at
    submit time with coaching copy before the student is committed to it.

    One field, deliberately. §7.4's Output column for this task is the three
    verdicts and nothing else, and §3.3 asks the classifier for a call rather
    than for an explanation. The coaching copy a student sees is the product's
    words, not the model's, so there is nothing here for a provider to fill with
    prose that would then be shown to a student unreviewed.

    The fail-open in §3.3 — on provider timeout the character heuristic applies
    and the submission is accepted — is the gateway's behaviour when no output
    arrives, not a state this contract can represent. There is no "unknown"
    verdict, because a stored `unknown` would be a classification that never
    happened.
    """

    verdict: ValidityVerdict = Field(
        description="Which of §3.3's three classes the comment falls in.",
    )


class ModerationOutput(AiTaskOutput):
    """§7.4, "Moderation" — clear / harmful / privacy / nonsense / threat / self-harm.

    The verdict is what §5.2 routes on: `harmful` reaches the Lead Faculty review
    queue alongside the instructor's own moderation view, `privacy` marks a
    comment naming a third party, and `threat` or `self_harm` bypasses that flow
    entirely and goes straight to the Care queue in §6.2, suppressed from every
    instructor and leadership view regardless of small-N.

    One field, for the same reason as the validity contract, and one more: this
    output crosses into a surface only the Care role may read. A free-text field
    beside the verdict would be model-written prose about a student in crisis,
    stored in a queue whose whole design is that the fewest possible people see
    the fewest possible words.
    """

    verdict: ModerationVerdict = Field(
        description="Which of §5.2's classes the comment falls in; the value §5.2's routing reads.",
    )


class WeeklySummaryOutput(AiTaskOutput):
    """§7.4, "Weekly summary" — per-stream, per-node themed summaries under §5.1.

    §5.1's requirements on a summary, and where each lands here: it belongs to
    one of the two comment streams (`stream`); it states the response count it
    draws from (`comment_count`); and it preserves clearly critical themes rather
    than sanding them off, which is what `themes` makes checkable — a summary
    whose prose drops a theme still lists it.

    "Per-node" is the caller's context rather than a field. The same contract
    serves a section summary and a leadership roll-up node (§5.5); which node was
    summarised is known to whoever asked, and putting it in the output would
    invite a model to answer for a scope it was not given.

    Small-N is not represented here either. §5.1 generates a summary "even in
    small-N weeks — there, the summary is the only comment signal", so
    suppression is a decision the reporting layer makes about a summary that
    exists, not a state the model reports.
    """

    stream: CommentStream = Field(
        description=(
            "Which of §5.1's two comment groups this summary covers. Returned rather than "
            "assumed, so a summary that answered for the wrong stream is refused by the "
            "gateway instead of being filed under the stream that was asked for."
        ),
    )
    summary: str = Field(
        min_length=1,
        description=(
            "The summary itself, as it appears above its comment group. §5.1: clearly "
            "critical themes are preserved, never sanded off."
        ),
    )
    themes: tuple[CommentTheme, ...] = Field(
        description=(
            "The themes the summary is built from. May be empty in a week whose comments "
            "share nothing; the summary is still written, per §5.1."
        ),
    )
    comment_count: int = Field(
        ge=0,
        description=(
            "How many comments this summary draws from — §5.1 requires a summary to state "
            "it. Zero is legitimate: a week with ratings and no comments still gets a "
            "summary, and its comment group shows a one-line notice rather than a hidden "
            "heading. Flagged-held content is excluded upstream and is not counted here."
        ),
    )


class ResponseDraftOutput(AiTaskOutput):
    """§7.4, "Response draft" — a draft class response from the week's themes and ratings.

    §5.3: the model may draft the instructor's "You said / we heard / here's what
    changes" response, "addressing criticism concretely rather than deflecting".
    The draft is advisory and editable, and nothing is ever published without a
    human pressing publish — so this contract carries the text and no signal that
    could be read as approval to post it.

    The draft is prose because the thing being produced is prose. There is no
    per-theme breakdown here: naming which themes a draft covers is the *draft
    check's* job (`DraftCheckOutput`), it is instructor-initiated and
    re-runnable, and a self-report from the drafting call would be the model
    marking its own work.
    """

    draft: str = Field(
        min_length=1,
        description="The draft response, ready for the instructor to edit and publish or discard.",
    )


class DraftCheckOutput(AiTaskOutput):
    """§7.4, "Draft check" — names themes the draft hasn't addressed, with comment counts.

    §5.3: instructor-initiated, never forced and never blocking, re-runnable, and
    the result clears when the draft changes. It "quietly names any theme not yet
    addressed (with its comment count)" — so the output is that list and nothing
    else. There is no score, no verdict and no pass/fail: §5.3 makes this
    advisory, and a grade on a draft would turn a check the instructor chose to
    run into something that judges them.

    An empty tuple is the good case and the common one — every theme addressed —
    which is why the field is required rather than defaulted. A default empty
    list would turn a response the provider never sent into "nothing left to
    address", and the instructor would publish on the strength of a check that
    did not happen.
    """

    unaddressed_themes: tuple[CommentTheme, ...] = Field(
        description=(
            "The week's themes the draft does not yet address, each with the number of "
            "comments behind it. Empty when the draft addresses all of them."
        ),
    )
