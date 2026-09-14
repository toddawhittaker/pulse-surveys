"""Leadership's named comparison sets: the seven routes the definition surface is (SPEC §5.1).

§13's tree gives the leadership-facing API this module, and §13's closing rule
keeps it thin: a handler here resolves the session, hands the work to
`app.services.comparison_sets`, and turns what comes back into an HTTP answer.
Every decision — who may change which set, what a set may be, how wide one is —
is in that service, and the payload's shape is `app.schemas.comparison_sets`.

**Seven routes and no others.** The institution's sets, one set, the choices a
set is defined out of, and the three writes; plus the preview, which is how a
definer sees what a set reaches before anything renders a figure over it. E5-09
consumes all seven.

**`/leadership/comparison-sets/options` is declared before
`/leadership/comparison-sets/{set_id}`, and that is load-bearing.** FastAPI
matches in declaration order, so with the keyed route first this path is read as
a set id that is not a uuid and the whole definition form answers a validation
error. The two are written in that order here and
`tests/integration/test_the_named_set_options_offer_only_the_valid_choices.py`
holds them in it.

**Every route carries one of `app.api.deps`' two leadership dependencies rather
than a check of its own.** That is what makes them findable: a sweep asking the
running application which routes carry `require_leadership` gets this module's
whole surface, and a route that resolved a session for itself would be a
leadership route outside every such walk — the shape `app.api.student` and
`app.api.instructor` already hold. The reads carry `require_leadership` and the
three writes carry `csrf_verified_leadership`, which is the same gate plus ADR
0089's double-submit check.

**Scope is asymmetric, and the asymmetry is the decision** (ADR 0173). Every
leadership session reads every set in the institution — §5.1's set-definition
surface is one list, and two leaders looking at different halves of it would
define the same cohort twice. Only the leader whose `person` row defined a set
may edit or delete it, which is what `editable` on the list says and what the
403 below answers. Purview over the supervision graph is E9's.

**Three refusals and three layers, which is why they are three sentences.** A
session that is not a leadership session is refused by the dependency with a 401
and a `Bearer` challenge; a set id nothing defined is a 404; another leader's set
on a write is a 403. The 404 comes before the 403 on a write, deliberately: a set
that is not there is not there for anybody, and answering 403 for an unknown id
would tell a caller that a set exists and belongs to somebody else — the
enumeration `app.api.instructor`'s own refusal pair exists to prevent, in the one
place here where it has a foothold.

**The five write refusals are translations rather than checks.** SPEC §2.2's
lengths, §8's levels and §5.1's exact level match are all held by Postgres
(E5-01, ADR 0164); the service attempts the write and maps the constraint that
fired to one sentence. So a 422 from here carries a sentence out of
`app.copy.leadership_sets` rather than a list of field errors, and a body that
carried field errors would mean the wire model had refused the value before the
database saw it.

**The preview answers two counts and nothing else.** SPEC §4.1 item 7 suppresses
statistics computed over a comparison set below the configured minimums; a count
of member courses and a count of resolved sections say how wide a cohort is and
nothing about what anybody in it answered, which is what makes them safe at
definition time. A name, a section code or a mean here would be a figure reaching
a reader outside E4-07's suppression chokepoint.

**Every answer carries `Cache-Control: no-store`.** A leadership answer sitting
in a shared cache is a set definition, and the list of every cohort in the
institution, served to whoever asks next on the same machine. The student and
instructor read paths set the same header for the same reason.

**No `audit_log` row is written by any of this** (ADR 0174). What is recorded is
on the set's own row — the creator and `created_at` on a create, `updated_at` on
an edit — and `docs/tickets/e5/deferred.md` carries what a delete leaves behind,
which is nothing.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import csrf_verified_leadership, require_leadership
from app.config import Settings
from app.copy.leadership_sets import NOT_THE_SETS_DEFINER, SET_UNAVAILABLE
from app.db import get_session
from app.schemas.comparison_sets import (
    SetDetail,
    SetList,
    SetOptions,
    SetPreview,
    SetWrite,
)
from app.services.comparison_sets import (
    NotTheSetsDefinerError,
    SetUnavailableError,
    WriteRefusedError,
    create_set,
    definition_options,
    delete_set,
    edit_set,
    listed_sets,
    preview_of,
    read_set,
)
from app.services.session import SessionClaims

router = APIRouter(tags=["leadership"])

# Where the institution's sets are listed and where one is defined. Written out
# in full rather than carried on a router prefix, so that what a route is
# registered at is what this file says it is — the convention `app.api.student`
# settled and `app.api.instructor` follows.
SETS_PATH = "/leadership/comparison-sets"

# The choices a set is defined out of. **Declared before the keyed paths below**
# — see the module docstring — and written out in full like its siblings.
OPTIONS_PATH = f"{SETS_PATH}/options"

# One set, and what it reaches.
SET_PATH = f"{SETS_PATH}/{{set_id}}"
PREVIEW_PATH = f"{SET_PATH}/preview"

# The statuses the three keyed refusals answer with. 404 for an id nothing
# defined and 403 for another leader's set: the two are different facts and a
# leader may read every set, so saying "this one is not yours" discloses nothing
# the list does not already show.
SET_UNAVAILABLE_STATUS = 404
NOT_THE_SETS_DEFINER_STATUS = 403

CREATED = 201
NO_CONTENT = 204

NO_STORE = "no-store"


@router.get(SETS_PATH, summary="Every comparison set this institution has defined")
def read_sets(
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetList:
    """The institution's sets, in name order, each marked editable or not.

    **Institution-wide rather than this session's own** (ADR 0173). The reader
    still comes from the session and from nowhere else: `editable` is decided
    against the `person` row this session was resolved to at the door, so no part
    of this request's own text decides which sets it may change.

    **Synchronous, and FastAPI runs it in a threadpool**, for the reason
    `app.api.instructor` gives: the session is synchronous (ADR 0013) and every
    statement behind this blocks, so an `async` handler would take them on the
    event loop.
    """
    response.headers["Cache-Control"] = NO_STORE
    return SetList(sets=listed_sets(session, person_id=_person_of(claims)))


@router.post(SETS_PATH, status_code=CREATED, summary="Define a comparison set")
def define_set(
    write: SetWrite,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> SetDetail:
    """Define a set for whoever this session is, or translate what the database refused.

    **The definer comes from the session and never from the body**, and it is
    what every later edit and delete of this set is scoped by.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return create_set(session, write=write, person_id=_person_of(claims), settings=settings)
    except NotTheSetsDefinerError:
        raise _not_the_definer() from None
    except WriteRefusedError as refused:
        raise _refused(refused) from None


@router.get(OPTIONS_PATH, summary="The lengths, levels and courses a set may be defined out of")
def read_options(
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetOptions:
    """The closed choices the definition form offers. Declared before `{set_id}`.

    It takes no parameter, so there is nothing in the request to refuse and no
    refusal here beyond the role gate. The courses it lists are every course this
    institution runs, because the form is where a new cohort is built.
    """
    response.headers["Cache-Control"] = NO_STORE
    return definition_options(session)


@router.get(SET_PATH, summary="One comparison set, whoever defined it")
def read_one_set(
    set_id: UUID,
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetDetail:
    """One set and its membership.

    **A set id that is not a uuid is refused before this runs**, by FastAPI's own
    parsing of the path parameter — which is an answer about the shape of a
    request rather than about a set. ADR 0016 makes every key a uuid, so a
    malformed value is not a set id at all and never reaches the lookup.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        return read_set(session, set_id=set_id, person_id=_person_of(claims))
    except SetUnavailableError:
        raise _unavailable() from None


@router.put(SET_PATH, summary="Replace the definition of a set I defined")
def replace_set(
    set_id: UUID,
    write: SetWrite,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> SetDetail:
    """Replace a set's whole definition, for the leader who defined it.

    The three refusals in order: an id nothing defined is a 404, another leader's
    set is a 403, and a definition the database will not store is one of the five
    translated sentences.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return edit_set(
            session,
            set_id=set_id,
            write=write,
            person_id=_person_of(claims),
            settings=settings,
        )
    except SetUnavailableError:
        raise _unavailable() from None
    except NotTheSetsDefinerError:
        raise _not_the_definer() from None
    except WriteRefusedError as refused:
        raise _refused(refused) from None


@router.delete(SET_PATH, status_code=NO_CONTENT, summary="Delete a set I defined")
def remove_set(
    set_id: UUID,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> None:
    """Delete a set, taking its membership rows and nothing else (ADR 0164).

    204 and no body, because there is nothing left to describe. A course named by
    the set is untouched and stays undeletable while any set names it, which is
    the opposite direction of the same rule.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        delete_set(session, set_id=set_id, person_id=_person_of(claims))
    except SetUnavailableError:
        raise _unavailable() from None
    except NotTheSetsDefinerError:
        raise _not_the_definer() from None


@router.get(PREVIEW_PATH, summary="How many courses and sections a set reaches")
def read_preview(
    set_id: UUID,
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetPreview:
    """Two counts and nothing else — see the module docstring on what that costs and why.

    Answered for every set, not only for this session's own: a count is what
    makes an institution-wide list usable, and it says nothing about anybody.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        return preview_of(session, set_id=set_id)
    except SetUnavailableError:
        raise _unavailable() from None


def _person_of(claims: SessionClaims) -> UUID | None:
    """The `person` row this session was resolved to, or `None` where it names none.

    A claim in a JWT is JSON, so `person_id` is a string here and a `uuid.UUID`
    everywhere below (ADR 0016). A value that is not one is a token this
    deployment did not issue in the shape it issues them, and it resolves to
    nobody rather than to a 500 from inside the parse — which the service answers
    as a session that may read every set and write none.

    The same reader `app.api.instructor` holds, and it is deliberately a second
    copy of four lines rather than a shared helper: promoting it is a change to a
    module this ticket was told not to touch, and the pull request proposes it
    rather than making it.
    """
    if claims.person_id is None:
        return None
    try:
        return UUID(claims.person_id)
    except ValueError:
        return None


def _unavailable() -> HTTPException:
    """The 404 for a set id nothing defined, carrying one sentence and nothing it was handed."""
    return HTTPException(status_code=SET_UNAVAILABLE_STATUS, detail=SET_UNAVAILABLE)


def _not_the_definer() -> HTTPException:
    """The 403 for another leader's set on a write."""
    return HTTPException(status_code=NOT_THE_SETS_DEFINER_STATUS, detail=NOT_THE_SETS_DEFINER)


def _refused(refused: WriteRefusedError) -> HTTPException:
    """One translated constraint refusal, with the status that rule is answered under."""
    return HTTPException(status_code=refused.status_code, detail=refused.detail)
