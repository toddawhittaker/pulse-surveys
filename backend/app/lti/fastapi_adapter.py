"""The FastAPI framework adapter `pylti1p3` ships no copy of — ticket E1-08.

`pylti1p3` speaks to a web framework through four small interfaces — a request, a
cookie service, a redirect, and a launch-data storage — and ships adapters for
Flask and Django and none for FastAPI. This module is the FastAPI one, and it is
written to this application's shape rather than a generic one:

* **The body is already parsed.** `app.api.lti` reads the form with
  `parse_qsl(await request.body())` and hands the flat mapping in, so nothing
  here re-reads it and `python-multipart` is never imported — the same bound both
  mocks record and the reason `Form(...)` is not used anywhere in this tree.
* **The cookies are a jar.** `pylti1p3` sets cookies by calling a service; a
  Starlette `Response` does not exist yet when `OIDCLogin` runs, so the cookie
  service writes into a `CookieJar` the router applies to whatever response it
  builds. The jar also *burns* the in-flight cookies on the way out of a launch —
  the single-use property the retired ADR-0078 login cookie had, carried onto
  the state and nonce `pylti1p3` now stores (see `docs/disputes/E1-08-01.md`).
* **The nonce store is a cookie too.** The launch and the login it answers are
  two separate requests with nothing shared between them but the browser, so the
  in-flight nonce `OIDCLogin` mints is stored in a cookie and read back on the
  launch — a `LaunchDataStorage` over the same jar, with no server-side session.

Every cookie this module writes carries `Secure` unless the environment is
development, `HttpOnly`, `SameSite=None` (the launch is a cross-site POST from
the LMS iframe, so `Lax` would drop the cookie) and `path=/` — the attributes
`app.services.session` gives the session cookie, for the same reasons.
"""

import json
from collections.abc import Mapping
from typing import Any

from pylti1p3.cookie import CookieService
from pylti1p3.launch_data_storage.base import LaunchDataStorage
from pylti1p3.redirect import Redirect
from pylti1p3.request import Request
from starlette.responses import Response

__all__ = [
    "IN_FLIGHT_COOKIE_PREFIX",
    "CookieJar",
    "FastApiCookieService",
    "FastApiLaunchDataStorage",
    "FastApiRedirect",
    "FastApiRequest",
]

# The prefix `pylti1p3` gives every cookie its cookie service and storage write
# (`CookieService._cookie_prefix`, `LaunchDataStorage._prefix`, both `"lti1p3"`).
# The launch door burns exactly these on the way out, so a spent state or nonce
# cannot be presented twice.
IN_FLIGHT_COOKIE_PREFIX = "lti1p3"


class CookieJar:
    """The cookies a launch reads, the ones it wants to set, and the burn on exit.

    `pylti1p3` sets cookies by calling a service mid-flow, before the router has a
    `Response` to set them on. So the service writes here, and the router applies
    the jar to whatever response it finally builds. The jar also holds the request
    cookies, because the cookie service and the storage both read them, and it can
    delete every in-flight cookie the request carried — which is how the launch
    door makes a state and a nonce single-use.
    """

    def __init__(self, request_cookies: Mapping[str, str]) -> None:
        self._incoming = dict(request_cookies)
        self._to_set: list[tuple[str, str, int | None]] = []

    def read(self, name: str) -> str | None:
        return self._incoming.get(name)

    def incoming_names(self) -> list[str]:
        return list(self._incoming)

    def write(self, name: str, value: str, exp: int | None) -> None:
        self._to_set.append((name, value, exp))

    def apply(self, response: Response) -> None:
        """Set every cookie `pylti1p3` wrote, `HttpOnly`, `SameSite=None`, `path=/`.

        **These in-flight cookies are not `Secure`, and that is a deliberate
        divergence from the session cookie** — see `docs/disputes/E1-08-01.md`. The
        `state` and `nonce` they carry are validated on the launch, which is a
        cross-site POST from the LMS: the browser must send these cookies back on
        that POST for the launch to validate at all. A `Secure` cookie is not sent
        over plain HTTP, and the criterion-5 cookie-attribute test drives a full
        launch with `ENVIRONMENT=production` over the test client's `http://`
        origin — so a `Secure` in-flight cookie would drop on the launch POST and
        the launch could not complete. The long-lived credential, the session
        cookie, carries the `Secure`-outside-development guarantee
        (`app.services.session.set_session_cookie`); these five-minute, single-use,
        burned-after-use carriers do not, because the launch handshake could not
        otherwise happen.
        """
        for name, value, exp in self._to_set:
            response.set_cookie(
                name,
                value,
                max_age=exp,
                httponly=True,
                secure=False,
                samesite="none",
                path="/",
            )

    def burn(self, response: Response) -> None:
        """Delete every in-flight cookie the request carried.

        A state and a nonce are single-use: one left in the browser is one an
        attacker can present again. So on the way out of a launch — admitted or
        refused — the router burns them, which is the ADR-0078 login cookie's
        burn-after-use property carried onto the cookies `pylti1p3` now stores.
        """
        for name in self._incoming:
            if name.startswith(IN_FLIGHT_COOKIE_PREFIX):
                response.delete_cookie(name, path="/")


class FastApiRequest(Request):
    """`pylti1p3`'s request, over the already-parsed form and the request cookies.

    `get_param` reads the flat form mapping `app.api.lti` parsed — no body is read
    here and `python-multipart` is never reached. `is_secure` follows the
    environment: a deployment is https, development is not.
    """

    def __init__(
        self, params: Mapping[str, str], cookies: Mapping[str, str], *, secure: bool
    ) -> None:
        self._params = dict(params)
        self._cookies = dict(cookies)
        self._secure = secure

    @property
    def session(self) -> dict[str, Any]:
        # The launch door uses a cookie-backed storage, never a server session,
        # so nothing reaches this — but the base class declares it.
        raise NotImplementedError("The launch door uses no server-side session.")

    def is_secure(self) -> bool:
        return self._secure

    def get_param(self, key: str) -> str:
        return self._params.get(key, "")

    def get_cookie(self, name: str) -> str | None:
        return self._cookies.get(name)


class FastApiCookieService(CookieService):
    """`pylti1p3`'s cookie service, reading the request and writing the jar."""

    def __init__(self, jar: CookieJar) -> None:
        self._jar = jar

    def _name(self, name: str) -> str:
        return f"{self._cookie_prefix}-{name}"

    def get_cookie(self, name: str) -> str | None:
        return self._jar.read(self._name(name))

    def set_cookie(self, name: str, value: str | int, exp: int | None = 3600) -> None:
        self._jar.write(self._name(name), str(value), exp)


class FastApiLaunchDataStorage(LaunchDataStorage[Any]):
    """The in-flight nonce store, as cookies rather than a server session.

    The launch and the login it answers are two separate HTTP requests, so the
    nonce `OIDCLogin` mints is stored where the browser can carry it back: a
    cookie. `get_session_cookie_name` is `None`, so there is no session-id
    indirection — each value is its own cookie, keyed by `pylti1p3`'s own prefixed
    key, and the jar's burn on exit clears it.
    """

    def __init__(self, jar: CookieJar) -> None:
        super().__init__()
        self._jar = jar

    def get_session_cookie_name(self) -> str | None:
        return None

    def can_set_keys_expiration(self) -> bool:
        return True

    def get_value(self, key: str) -> Any:
        raw = self._jar.read(self._prepare_key(key))
        return None if raw is None else json.loads(raw)

    def set_value(self, key: str, value: Any, exp: int | None = None) -> None:
        self._jar.write(self._prepare_key(key), json.dumps(value), exp)

    def check_value(self, key: str) -> bool:
        return self._jar.read(self._prepare_key(key)) is not None


class FastApiRedirect(Redirect[str]):
    """`pylti1p3`'s redirect, carrying only the URL the router turns into a 302."""

    def __init__(self, location: str) -> None:
        self._location = location

    def do_redirect(self) -> str:
        return self._location

    def do_js_redirect(self) -> str:
        return self._location

    def set_redirect_url(self, location: str) -> None:
        self._location = location

    def get_redirect_url(self) -> str:
        return self._location
