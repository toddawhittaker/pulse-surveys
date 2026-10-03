"""The words on the four pages a door answers with when it answers no landing — E5.1-03.

Either door — the LTI launch and the web login — ends in one of five ways: a
landing, or one of four pages `app.api.deps` renders. This tool refuses what it
was handed (`entry.refused.*`); the person cancelled, or their provider declined
for them (`entry.cancelled.*`); Pulse holds no record of the person
(`entry.no_account.*`); or Pulse holds their record and nothing in it gives them a
view at this door (`entry.no_access.*`). The sentences were literals in
`app.api.deps` until E5.1-03, so the inventory `app.copy.copy_modules()` publishes
could not see them, and SPEC §4.1 items 4 and 5 were asserted over none of them.

**Moved word for word.** Every text below is the sentence the page served
before, byte for byte. `tests/e2e/exit-refused-launches.spec.ts` matches two of
them as its copy canary — the refusal heading, and the replayed-nonce sentence,
which is `app.lti.replay_guard`'s own words copied whole.

**What stays in `app.api.deps`.** The mapping from a refusing guard's class name
to its entry, the testids and the page template. The guard names are a routing
vocabulary (ADR 0103 puts them in `data-reason`), not words a person reads, and
the page derives its sentence from that closed vocabulary so that no caller's
string can reach it.

**None of them is a confidentiality line, and none is owed.** The pages render
before a session exists and show nobody's data, so SPEC §4.1 item 5's sentence
would have no subject on them — the reason the unknown-address screen owes none.

**`COPY` beside the entries, because that is the shape the package settles.**
Each copy module publishes `COPY: Mapping[str, CopyEntry]` keyed by dotted keys,
which is what `app.copy.copy_modules()`'s readers walk.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "CANCELLED_HEADING",
    "CANCELLED_MESSAGE",
    "COPY",
    "NO_ACCESS_HEADING",
    "NO_ACCESS_MESSAGE",
    "NO_ACCOUNT_HEADING",
    "NO_ACCOUNT_MESSAGE",
    "REFUSED_ANONYMOUS_LAUNCH",
    "REFUSED_AUDIENCE",
    "REFUSED_CLOCK_SKEW",
    "REFUSED_DEFAULT",
    "REFUSED_DEPLOYMENT",
    "REFUSED_HEADING",
    "REFUSED_ISSUER",
    "REFUSED_MESSAGE_TYPE",
    "REFUSED_NONCE",
    "REFUSED_NONCE_REPLAYED",
    "REFUSED_SESSION",
    "REFUSED_SIGNATURE",
    "REFUSED_STATE",
    "REFUSED_VERSION",
]

# ---------------------------------------------------------------------------
# The refusal page: one heading, and one sentence per refusing guard.
# ---------------------------------------------------------------------------

# Deliberately one sentence and a reason, with no retry link: there is nowhere for
# a browser to go from a refusal that is not the platform or the provider it came
# from.
REFUSED_HEADING = CopyEntry(key="entry.refused.heading", text="This did not open")

REFUSED_SIGNATURE = CopyEntry(
    key="entry.refused.signature",
    text=(
        "This launch could not be verified. Its signature, the algorithm it names, or the key it "
        "was signed with did not hold."
    ),
)
REFUSED_AUDIENCE = CopyEntry(
    key="entry.refused.audience",
    text="This launch was issued for a different tool than this one.",
)
REFUSED_ISSUER = CopyEntry(
    key="entry.refused.issuer",
    text="No registration here exists for the platform that began this launch.",
)
REFUSED_NONCE = CopyEntry(
    key="entry.refused.nonce",
    text="This launch carries no `nonce`, or one this tool did not send.",
)
# `app.lti.replay_guard`'s own two sentences, copied whole; the browser spec
# matches this string.
REFUSED_NONCE_REPLAYED = CopyEntry(
    key="entry.refused.nonce_replayed",
    text=(
        "This launch has already been delivered once. A launch nonce is single-use, and "
        "presenting the same signed launch a second time is refused."
    ),
)
REFUSED_DEPLOYMENT = CopyEntry(
    key="entry.refused.deployment",
    text="This launch names a deployment this tool was never installed into.",
)
REFUSED_MESSAGE_TYPE = CopyEntry(
    key="entry.refused.message_type",
    text="This launch is a message type this tool does not serve.",
)
REFUSED_VERSION = CopyEntry(
    key="entry.refused.version",
    text="This launch states an LTI version this tool does not speak.",
)
REFUSED_STATE = CopyEntry(
    key="entry.refused.state",
    text="This launch returns a `state` this tool did not issue, or none at all.",
)
REFUSED_CLOCK_SKEW = CopyEntry(
    key="entry.refused.clock_skew",
    text="This launch was minted too far in the future, or expired too long ago.",
)
REFUSED_ANONYMOUS_LAUNCH = CopyEntry(
    key="entry.refused.anonymous_launch",
    text=(
        "This launch names nobody. Pulse Surveys shows each person their own work, so a launch "
        "carrying no subject is one it cannot open."
    ),
)
REFUSED_SESSION = CopyEntry(
    key="entry.refused.session",
    text=(
        "That sign-in could not be verified, and nobody has been signed in. Start again from "
        "where you opened Pulse Surveys."
    ),
)

# What a guard nothing maps is answered with. Every word of it is true of any
# refusal, and it reports nothing about what was handed in.
REFUSED_DEFAULT = CopyEntry(
    key="entry.refused.default",
    text=(
        "This tool could not account for what it was handed, and nobody has been signed in. Start "
        "again from where you opened Pulse Surveys."
    ),
)

# ---------------------------------------------------------------------------
# The three pages that take no argument.
# ---------------------------------------------------------------------------

# A cancelled web login (E1-09). Calm and non-blaming, per `docs/DESIGN_BRIEF.md`'s
# tone: it says what is true — nothing was changed, nobody is signed in — and
# stops there.
CANCELLED_HEADING = CopyEntry(key="entry.cancelled.heading", text="Sign-in did not finish")
CANCELLED_MESSAGE = CopyEntry(
    key="entry.cancelled.message",
    text="Nothing was changed and nobody is signed in. You can start again when ready.",
)

# A verified web login by somebody Pulse holds no record of (E1-12). It says who to
# ask, and names nobody.
NO_ACCOUNT_HEADING = CopyEntry(
    key="entry.no_account.heading", text="Pulse Surveys has no account for you yet"
)
NO_ACCOUNT_MESSAGE = CopyEntry(
    key="entry.no_account.message",
    text=(
        "You signed in correctly and nothing went wrong. Pulse Surveys keeps its own record of who "
        "works here, and there is no record for you yet, so there is nothing to show. Ask whoever "
        "administers Pulse Surveys at your institution to add you."
    ),
)

# Somebody Pulse holds a record of, with nothing in it that gives them a view at
# the door they came in by (E1-13). What is true, the LMS-launch hint for somebody
# who teaches, and who to ask.
NO_ACCESS_HEADING = CopyEntry(
    key="entry.no_access.heading", text="There is nothing in Pulse Surveys for you yet"
)
NO_ACCESS_MESSAGE = CopyEntry(
    key="entry.no_access.message",
    text=(
        "Nothing went wrong and nobody is at fault. Pulse Surveys keeps its own record of who works "
        "here and who is enrolled, and nothing in yours gives you a view at this door yet. If you "
        "teach, open Pulse Surveys from inside one of your courses in the LMS rather than from "
        "here. Otherwise, ask whoever administers Pulse Surveys at your institution."
    ),
)

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        REFUSED_HEADING,
        REFUSED_SIGNATURE,
        REFUSED_AUDIENCE,
        REFUSED_ISSUER,
        REFUSED_NONCE,
        REFUSED_NONCE_REPLAYED,
        REFUSED_DEPLOYMENT,
        REFUSED_MESSAGE_TYPE,
        REFUSED_VERSION,
        REFUSED_STATE,
        REFUSED_CLOCK_SKEW,
        REFUSED_ANONYMOUS_LAUNCH,
        REFUSED_SESSION,
        REFUSED_DEFAULT,
        CANCELLED_HEADING,
        CANCELLED_MESSAGE,
        NO_ACCOUNT_HEADING,
        NO_ACCOUNT_MESSAGE,
        NO_ACCESS_HEADING,
        NO_ACCESS_MESSAGE,
    )
}
