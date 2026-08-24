"""The LTI 1.3 registration: which platforms may launch this tool, and from where.

SPEC §7.3 and §8. A registration is what a launch is validated against — the
issuer that signed the `id_token`, the client ID it was issued for, the
deployment it came from, and the key set the signature is checked with. E0-18's
launch door reads both tables today: `app.lti.launch.registered_platform` looks
a platform up by issuer, and `registered_deployment` refuses a launch naming a
deployment nobody registered under it.

**No secret is stored, and that is the design rather than an omission.** LTI 1.3
is asymmetric: the platform signs, and the tool verifies with public keys it
fetches from the platform's JWKS URL. There is no shared secret in the protocol
to store, so E0-08 criterion 7 — "`lti_platform` stores no client secret in
plaintext, and a test asserts the column either does not exist or is encrypted at
rest" — is met by the column not existing. `jwks_url` is a public address and the
keys behind it are public keys.

The tool's *own* signing key is the one piece of key material an LTI 1.3
deployment needs, and it is deliberately not here. It is not a per-platform
value, nothing in this ticket reads it, and a key sitting in a table that no code
opens is a credential at rest with no owner. E1 introduces it with the launch
flow that uses it, and the epic README's configuration rule means it earns its
`.env.example` line at the moment an `app.config.Settings` field resolves to it —
not before. **So this ticket adds no configuration variable**, which is the
honest answer to its definition-of-done item rather than a skipped one.

**What a launch needs that is not here yet.** §7.3 leaves the platform's OIDC
authorization endpoint to the registration, but E0-23 decided that the
service-address columns for it are E1's, built with the sync that reads them;
E0-18's launch door uses `Settings.lti_platform_authorization_endpoint` as its
stand-in until then (`docs/adr/0075`). E0-08's scope names issuer, client ID,
deployment IDs, JWKS URL and last fetch, and those are what this module builds.

**Nothing here is marked LMS-owned.** An `lms_` prefix (ADR 0014) marks a column
Pulse may never edit. A registration is typed into the admin console by an
administrator (SPEC §2, Admin: "LTI registration"), so every column in this
module is Pulse's to write. `user.lms_user_id` in `app.models.identity` is the
contrasting case: the `sub` claim arrives from the platform and Pulse never
chooses it.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base


class LtiPlatform(Base):
    """One registered LTI 1.3 platform — one issuer, one client ID.

    **Identified by the pair, not by the issuer alone.** A platform issues a
    client ID per tool registration, and one LMS can register this tool twice —
    a pilot alongside production is the ordinary case. So `UNIQUE (issuer,
    client_id)` and not a unique issuer, which would make the second registration
    unwritable.

    `jwks_fetched_at` is the "last fetch" E0-08's scope names: when the key set
    behind `jwks_url` was last retrieved. Nullable, because a platform that has
    been registered and never launched from has never been fetched, and a
    zero-value timestamp would be a lie that later code has to special-case
    anyway. `AwareDateTime` refuses a naive value at the bind boundary
    (ADR 0019).
    """

    __tablename__ = "lti_platform"
    __table_args__ = (UniqueConstraint("issuer", "client_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Text and not a bounded string: an issuer is a URL the platform chooses, and
    # a length limit here would reject a registration for a reason that has
    # nothing to do with Pulse. Same for the client ID, which is opaque, and for
    # the JWKS URL.
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    jwks_url: Mapped[str] = mapped_column(Text, nullable=False)
    jwks_fetched_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class LtiDeployment(Base):
    """One deployment of this tool within a platform (the `deployment_id` claim).

    A platform can deploy the same tool registration in more than one place — a
    sub-account, a course template — and each launch carries the deployment it
    came from. Unique per platform rather than globally: two platforms may well
    hand out the same deployment string, and it means nothing across issuers.

    Deleting a platform that still has deployments is refused rather than
    cascading, for the reason `app.models.org` gives about containment: losing the
    parent silently loses the record of what was deployed under it.
    """

    __tablename__ = "lti_deployment"
    __table_args__ = (UniqueConstraint("lti_platform_id", "deployment_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No index of its own: it leads `uq_lti_deployment_lti_platform_id_deployment_id`,
    # which serves a lookup of one platform's deployments.
    lti_platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("lti_platform.id", ondelete="RESTRICT"), nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(Text, nullable=False)
