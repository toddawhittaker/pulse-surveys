"""The FastAPI framework adapter `pylti1p3` ships no copy of — ticket E1-08.

`pylti1p3` speaks to a web framework through four small interfaces — a request, a
cookie service, a redirect, and a launch-data storage — and ships adapters for
Flask and Django and none for FastAPI. This module is the FastAPI one, and it is
written to this application's shape rather than a generic one:

* **The body is already parsed.** `app.api.lti` reads the form with
  `parse_qsl(await request.body())` and hands the flat mapping in, so nothing
  here re-reads it and `python-multipart` is never imported — the same bound both
  mocks record and the reason `Form(...)` is not used anywhere in this tree.
* **The handshake is server-side, so the cookie service and the storage do
  nothing.** E1-08's first cut carried the launch `state`/`nonce` in `pylti1p3`'s
  own cookies; those are third-party cookies inside the LMS iframe and a browser
  blocks them whatever their attributes say, so the launch could not validate
  (ADR 0089). The handshake now lives in `app.lti.in_flight` (a server-side
  table), and `app.lti.launch` validates `state`/`nonce` against it directly
  rather than through `pylti1p3.validate_state`/`validate_nonce`. So the cookie
  service and the launch-data storage here are inert: they exist only because
  `OIDCLogin` and `MessageLaunch` require one of each, and every value they carry
  is read back from the store, not from them. The only cookie the launch sets is
  the long-lived session cookie (`app.services.session`).
"""

from collections.abc import Mapping
from typing import Any

from pylti1p3.cookie import CookieService
from pylti1p3.launch_data_storage.base import LaunchDataStorage
from pylti1p3.redirect import Redirect
from pylti1p3.request import Request

__all__ = [
    "NoOpCookieService",
    "NoOpLaunchDataStorage",
    "FastApiRedirect",
    "FastApiRequest",
]


class FastApiRequest(Request):
    """`pylti1p3`'s request, over the already-parsed form.

    `get_param` reads the flat form mapping `app.api.lti` parsed — no body is read
    here and `python-multipart` is never reached. `is_secure` follows the
    environment: a deployment is https, development is not.
    """

    def __init__(self, params: Mapping[str, str], *, secure: bool) -> None:
        self._params = dict(params)
        self._secure = secure

    @property
    def session(self) -> dict[str, Any]:
        # The launch door uses a server-side handshake store, never a server
        # session, so nothing reaches this — but the base class declares it.
        raise NotImplementedError("The launch door uses no server-side session.")

    def is_secure(self) -> bool:
        return self._secure

    def get_param(self, key: str) -> str:
        return self._params.get(key, "")


class NoOpCookieService(CookieService):
    """`pylti1p3`'s cookie service, inert.

    `OIDCLogin` sets a `state` cookie and `MessageLaunch.validate_state` reads it;
    E1-08 does neither through `pylti1p3` — the handshake is validated against
    `app.lti.in_flight` — so reads answer `None` and writes are dropped. The only
    cookie the launch door sets is the session cookie, and that is not `pylti1p3`'s.
    """

    def get_cookie(self, name: str) -> str | None:
        return None

    def set_cookie(self, name: str, value: str | int, exp: int | None = 3600) -> None:
        return None


class NoOpLaunchDataStorage(LaunchDataStorage[Any]):
    """`pylti1p3`'s launch-data storage, inert, for the same reason.

    `OIDCLogin.save_nonce` writes here and `MessageLaunch.validate_nonce` reads it;
    E1-08 validates the nonce against `app.lti.in_flight` instead, so this stores
    nothing. `get_session_cookie_name` is `None` so `pylti1p3` sets up no session
    cookie around it.
    """

    def get_session_cookie_name(self) -> str | None:
        return None

    def can_set_keys_expiration(self) -> bool:
        return True

    def get_value(self, key: str) -> Any:
        return None

    def set_value(self, key: str, value: Any, exp: int | None = None) -> None:
        return None

    def check_value(self, key: str) -> bool:
        return False


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
