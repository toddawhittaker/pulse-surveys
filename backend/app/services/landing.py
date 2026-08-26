"""Which empty view a verified token lands on, and the page it lands on — E0-18.

This is the seam E0-18's boundary section asks for by name: "the seam to leave
is one function that maps a verified token to a landing role, called from both
doors, so E1 edits one place". `landing_role_for` is that function, and the four
routes in `app/api/lti.py` and `app/api/auth.py` reach it and nothing else.

**The seam is one function taking which door called it**, rather than one
function that works the same for both — the third review round moved it there and
the paragraph below on vocabularies says why. E1 still edits one place; what it
edits now has two branches, one per door.

**The role comes from the verified token and never from the database.** E0 has no
identity resolution on either door — no `user` row is written for a mock subject,
no purview is computed, and `app.services.authz.transitive_purview` raises by
design (ADR 0003). A view labelled by a signature-verified claim is an honest
statement about what the issuer said; a view labelled by a claim nobody checked
would not be. E1 replaces this with the app-owned assignment model, which is the
whole reason the mapping is one function rather than a branch in each router.

**Each door reads exactly one vocabulary, and never the other one.** A launch
carries the LIS v2 membership URIs LTI 1.3 draws roles from; a web login carries
SPEC §2's own role names under the claim `mock-idp/app/flow.py` publishes and ADR
0058 documents. `landing_role_for` takes a `Door` and reads that door's claim
alone: a foreign claim beside a valid one is ignored, and a token carrying only
the foreign one is refused exactly as a token carrying no roles at all is.

**Why it is not "whichever claim the token carries", which is what this was.**
The security review of E0-18 named the consequence: the person who administers an
LMS writes what its `id_token` says, so a launch door that fell through to the
web door's claim would let that administrator put themselves on the Care screen by
adding one claim to a launch. SPEC §2 gives Care, leadership and admin the web
door *precisely so* the LMS cannot name those roles, and a dispatch that read
whichever vocabulary turned up handed the LMS both. The mirror image is just as
wrong: a web door reading the LTI claim would take role names from the vocabulary
the LMS controls. So the caller says which door it is, and that is one branch in
each router rather than a second place the vocabularies are known.

**Every page is empty, and that is the design rather than a stub.** SPEC §4.1's
visibility invariants and §6.2's Care surface both say what these screens may
show; E0 computes none of it. So each page carries a heading naming the view, one
line saying nothing is here yet, and no identifier of any kind — not even the
signed-in person's own, which would be legitimate and which nothing needs.

`@pytest.mark.invariant` tests hold four of the five pages to that, each asserted
against the rendered body rather than a returned value, and each naming its own
door's module:

  - the **leadership** and **Care** pages, in
    `tests/integration/test_web_login_door.py`: neither page names anybody but
    the person signed in;
  - the **student** and **instructor** pages, in
    `tests/integration/test_the_launch_views_name_nobody.py`: neither page names
    anybody but the person who launched, and neither carries a section code, a
    course number or a roster count. E0-41 added that module because the launch
    door — the only door a student enters through — had carried no
    `invariant`-marked test at all, so the isolated §4.1 pass walked past the
    student page entirely.

The **admin** page has no `invariant`-marked test of its own; what covers it is
the web door's ordinary dispatch tests.

**This module is a named exception to E0-09's Care tripwire, and it was
arbitrated rather than assumed.** E0-09 criterion 10 says no LTI claim and no
OIDC claim may ever produce a Care assignment, and
`tests/unit/test_care_is_not_reachable_from_a_claim.py` enforces it by failing any
module under `app/` that both reads a claim and names the role in code.
`landing_role_for` does both, because E0-18 specifies the web door as landing a
verified `CARE` roles claim on the Care empty view. The collision was ruled on
2026-08-21 in favour of E0-18, and the reasoning lives in that file's
`EXCEPTIONS` entry for this path rather than here, so there is one copy of it.

The property the ruling rests on is behavioural, not argued: nothing here writes
a `role_assignment`, the Care queue does not exist, and the reveal is gated twice
on a live assignment in the database — `app.services.safety` before it calls, and
`reveal_student_identity` again inside its own body. A `CARE` claim buys an empty
page in E0, and after the third review round it buys even that only at the web
door. E1 replaces claim-derived landing roles with the assignment model, and the
exception goes with them.

The markup follows `docs/DESIGN_BRIEF.md` and `design/tokens.css`: chalk ground,
spruce ink, Literata for the heading and Schibsted Grotesk for the body, the flat
mist pulse line the brief gives to empty states, and nothing else. The webfonts
are **not** linked: an LMS iframe fetching Google Fonts is a third-party request
from inside somebody's LMS, the stacks fall back to a serif and a grotesque that
are already there, and E1's frontend is where the real loading strategy belongs.
"""

from collections.abc import Mapping, Sequence
from enum import Enum, StrEnum, auto
from html import escape
from typing import Any

__all__ = [
    "Door",
    "LandingRole",
    "cancelled_page",
    "landing_page",
    "landing_role_for",
    "refusal_page",
]

# What a refused entry says. Deliberately one sentence and a reason, with no
# retry link: there is nowhere for a browser to go from here that is not the
# platform or the provider it came from, and a link built out of a request that
# just failed validation is the open redirect both doors exist to refuse.
REFUSAL_HEADING = "This did not open"

# What a cancelled web login says (E1-09). Calm and non-blaming, per
# `docs/DESIGN_BRIEF.md`'s tone: the person declined to sign in, or the provider
# declined for them, and neither is a fault to report back. It says what is true —
# nothing was changed, nobody is signed in — and stops there. No retry link, for
# the reason above, and not a syllable of what the provider sent: `error_description`
# and `error_uri` are text an attacker chooses, and a page that repeated them would
# be a page whose words they wrote, under this tool's own name and styling.
CANCELLED_TESTID = "web-login-cancelled"
CANCELLED_HEADING = "Sign-in did not finish"
CANCELLED_MESSAGE = "Nothing was changed and nobody is signed in. You can start again when ready."

# The claim each door states its roles in. Neither is this project's to choose:
# the first is spelled by LTI 1.3, and the second is what E0-16's provider issues
# (ADR 0058) and what its `/mock/registration` document declares under
# `roles_claim`.
LTI_ROLES_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/roles"
WEB_ROLES_CLAIM = "https://pulse.example/claims/roles"

# The LIS v2 membership URIs a launch dispatches on, spelled as the vocabulary
# spells them. SPEC §7.3 asks for strict LTI 1.3 core, and a role compared under
# any other name is a role no conformant platform sends.
MEMBERSHIP_VOCABULARY = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URI = f"{MEMBERSHIP_VOCABULARY}Instructor"
LEARNER_ROLE_URI = f"{MEMBERSHIP_VOCABULARY}Learner"

# SPEC §2's reporting chain, which is one view in E0 because it is one shape of
# screen: a roll-up over whatever the holder supervises. The scope differs per
# role and E9 is where that becomes visible; nothing here computes it.
LEADERSHIP_ROLES = ("VP_ACADEMICS", "DEAN", "ASSISTANT_DEAN", "CHAIR", "LEAD_FACULTY")


class Door(Enum):
    """Which entry door a verified token arrived at, and so which claim it may state.

    A two-member enum rather than a boolean or a claim name, so that a router
    cannot ask for a vocabulary that does not exist and cannot pass the other
    door's claim by getting an argument the wrong way round. `app/api/lti.py`
    passes `LAUNCH` and `app/api/auth.py` passes `WEB`, and those two lines are
    the whole of what either router knows about roles.
    """

    LAUNCH = auto()
    WEB = auto()


class LandingRole(StrEnum):
    """The five empty views E0 can land somebody on, by the testid each carries.

    The value *is* the `data-testid`, so the contract a Playwright spec addresses
    and the contract this module implements are the same string rather than two
    strings that have to agree. `mock-idp/app/pages.py` names its own controls
    the same way and for the same reason.
    """

    STUDENT = "pulse-landing-student"
    INSTRUCTOR = "pulse-landing-instructor"
    LEADERSHIP = "pulse-landing-leadership"
    CARE = "pulse-landing-care"
    ADMIN = "pulse-landing-admin"


# What each view is called and what it says while it is empty. One tuple per
# role, so adding a view is one entry rather than a template plus a branch.
VIEW_HEADINGS: dict[LandingRole, tuple[str, str]] = {
    LandingRole.STUDENT: (
        "Your weekly check-in",
        "There is no survey open for you yet. When one opens, it appears here.",
    ),
    LandingRole.INSTRUCTOR: (
        "Your section report",
        "There are no responses to report yet. Reports appear here once a week has closed.",
    ),
    LandingRole.LEADERSHIP: (
        "Your roll-up",
        "There is nothing to roll up yet. Sections you oversee appear here once they report.",
    ),
    # §6.2 keeps the Care surface to the threat queue and nothing else, and E0
    # builds no queue. One heading's worth of content, and the design brief gives
    # this screen no motion at all.
    LandingRole.CARE: (
        "Community standards queue",
        "Nothing needs attention.",
    ),
    LandingRole.ADMIN: (
        "Pulse console",
        "There is nothing to administer yet.",
    ),
}


def stated_roles(claim: Any) -> tuple[str, ...]:
    """The role strings in a roles claim, whatever shape the issuer sent it in.

    LTI 1.3 and OIDC both make this an array, and both mocks send one. A single
    string is accepted because some platforms send one, and a claim of any other
    shape yields nothing rather than raising — an unusable claim and an absent
    claim lead to the same refusal, and the refusal is the caller's to make.
    """
    if isinstance(claim, str):
        return (claim,)
    if isinstance(claim, Sequence):
        return tuple(role for role in claim if isinstance(role, str))
    return ()


def launch_landing(roles: Sequence[str]) -> LandingRole | None:
    """Instructor beats Learner, per E0-18: "Learner → student, Instructor → instructor".

    Ordered rather than exclusive because one enrollment can carry both — a
    teaching assistant enrolled as a learner in the course she grades is the
    ordinary case — and the higher-standing role is the one whose screen is
    useful. Comparison is exact against the LIS URI: `pylti1p3` and every
    conformant tool read these as URIs, and a substring match on "Instructor"
    would also match a claim that merely mentioned one.
    """
    if INSTRUCTOR_ROLE_URI in roles:
        return LandingRole.INSTRUCTOR
    if LEARNER_ROLE_URI in roles:
        return LandingRole.STUDENT
    return None


def web_login_landing(roles: Sequence[str]) -> LandingRole | None:
    """Leadership, then CARE, then ADMIN — E0-18's "highest-standing role in it".

    The order is a precedence and not a list of cases: a person can hold more
    than one of these, and the two-hat person E0-16 seeds is the case the ticket
    is built around. Falling through to `None` rather than to a default view is
    the point of the third branch — a dispatch with a default lands every role it
    does not recognise, including one a future provider invents, on somebody's
    screen.
    """
    if any(role in LEADERSHIP_ROLES for role in roles):
        return LandingRole.LEADERSHIP
    if "CARE" in roles:
        return LandingRole.CARE
    if "ADMIN" in roles:
        return LandingRole.ADMIN
    return None


def landing_role_for(claims: Mapping[str, Any], *, door: Door) -> LandingRole | None:
    """The view `door`'s roles claim names in a verified token, or `None` if none does.

    **The one seam E1 edits.** Both doors call this and neither has a role rule
    of its own, so replacing "the token says so" with "the assignment model says
    so" is a change in this function.

    **One claim is read and the other is not looked at**, which is the rule the
    module docstring argues for: a launch is judged on its LIS roles alone and a
    web login on SPEC §2's roles alone. `claims.get` rather than `in`, so a claim
    that is absent, empty, or full of roles this door serves no view for all reach
    the same answer — there is no third case for a fall-through to hide in.

    `None` is a refusal, not a default: a verified token stating a role this
    system has no screen for is a real state — an LMS sends `Mentor`, a provider
    sends a role a later spec adds — and the honest answer is to refuse rather
    than to pick the least-privileged view and look like it worked.
    """
    if door is Door.LAUNCH:
        return launch_landing(stated_roles(claims.get(LTI_ROLES_CLAIM)))
    return web_login_landing(stated_roles(claims.get(WEB_ROLES_CLAIM)))


# The page, as one f-string rather than a template engine: there is one layout,
# it has two variables, and nothing in the locked closure renders templates. The
# style block is inline for the same reason — E0 serves no static assets, and a
# stylesheet route would be a second thing to keep in step with `tokens.css`
# until E1's frontend replaces both.
#
# The pulse line is the brief's empty-state variant: flat, in mist, with the
# rounded caps the motif is drawn with. Flat is what it means here — nothing has
# arrived yet.
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading} · Pulse Surveys</title>
<style>
  :root {{
    --chalk: #F6F8F4;
    --spruce: #1E3932;
    --spruce-60: #5B7269;
    --mist: #93A5A0;
    --marigold: #DFA320;
    --font-display: 'Literata', Georgia, serif;
    --font-body: 'Schibsted Grotesk', 'Helvetica Neue', sans-serif;
    --space-4: 16px;
    --space-5: 24px;
    --space-7: 48px;
  }}
  :focus-visible {{ outline: 2px solid var(--marigold); outline-offset: 2px; }}
  body {{
    margin: 0;
    background: var(--chalk);
    color: var(--spruce);
    font-family: var(--font-body);
    font-size: 16px;
    line-height: 1.5;
  }}
  main {{ max-width: 720px; margin: 0 auto; padding: var(--space-7) var(--space-5); }}
  h1 {{ font-family: var(--font-display); font-size: 25px; font-weight: 600; margin: 0; }}
  .pulse {{ display: block; margin: var(--space-4) 0; }}
  p {{ color: var(--spruce-60); margin: 0; }}
</style>
</head>
<body>
<main data-testid="{testid}">
<h1>{heading}</h1>
<svg class="pulse" width="120" height="8" viewBox="0 0 120 8" aria-hidden="true"
     fill="none" stroke="var(--mist)" stroke-width="2.5" stroke-linecap="round">
  <path d="M2 4 H118"/>
</svg>
<p>{empty_state}</p>
</main>
</body>
</html>
"""


def landing_page(role: LandingRole) -> str:
    """The empty view for `role`, as a whole HTML document.

    Everything interpolated is a constant from this module, so the escaping below
    changes nothing today. It is written anyway: the day somebody puts a section
    title or a person's name in a heading, the escaping is already where it has
    to be rather than something a reviewer has to notice is missing.
    """
    heading, empty_state = VIEW_HEADINGS[role]
    return PAGE.format(
        testid=escape(role.value, quote=True),
        heading=escape(heading),
        empty_state=escape(empty_state),
    )


def refusal_page(reason: str) -> str:
    """The page a refused launch or a refused web login gets, in the same layout.

    **It carries no landing testid**, and that is a property both door suites
    assert rather than a detail: a refusal that served a landing page has
    admitted the caller and merely said so in the status line. The testid slot is
    filled with a name of its own so the markup stays one template.

    `reason` is written by `app.lti.launch` or by `app.api.auth` and is never
    assembled from the request. It is escaped anyway, for the reason
    `landing_page` gives about its own constants.
    """
    return PAGE.format(
        testid="pulse-entry-refused",
        heading=escape(REFUSAL_HEADING),
        empty_state=escape(reason),
    )


def cancelled_page() -> str:
    """The page a cancelled web login gets, in the same layout (E1-09).

    **It takes no argument at all**, and that is the security property rather than
    a convenience: the only thing this door knows about a cancel is what the
    provider's redirect said, every parameter in that redirect is attacker-chosen
    text, and a function with nowhere to put such text cannot be talked into
    rendering it. What the page says is three constants from this module.

    It carries no landing testid, like `refusal_page`, so a cancel serves nobody's
    view; and its own testid is not the refusal's, because a suite — and a person —
    has to be able to tell "you cancelled" from "this tool was handed something it
    could not account for".
    """
    return PAGE.format(
        testid=escape(CANCELLED_TESTID, quote=True),
        heading=escape(CANCELLED_HEADING),
        empty_state=escape(CANCELLED_MESSAGE),
    )
