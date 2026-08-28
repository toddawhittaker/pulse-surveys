"""How this platform divides a collection into pages, for both services that do.

E0-15 pages the NRPS roster; its review round found the AGS line-item container
unpaged and ruled that it pages "exactly as `nrps.py` does". Two callers asking
one question is what `docs/MISTAKES.md` entry 13 is about, so the question is
answered once, here, and each service keeps only what a page of *its* collection
carries.

**The `Link` header is the contract, and the body says nothing about paging.**
RFC 8288 is how a platform tells a client where the next page is, and it is what
a conformant client reads. A next URL carried in a response body reads perfectly
to a person and leaves a tool syncing page one and calling it the collection.

Four rules are worth stating because each is a defect somebody ships:

  - **`next` appears only where a next page exists.** Advertising one whenever
    the page just served was full sends a client for a page with nothing on it.
  - **Every other relation appears always, one-page collections included.** A
    collection that answered with no header at all is telling a client nothing
    about its own extent, and a tool sizing a sync before it starts has to guess.
  - **Page one is the collection's own URL**, with no page parameter added. A
    tool following a service claim and a tool following a `first` relation then
    arrive at the same string rather than at two spellings of one page.
  - **A page URL keeps the query it was asked with.** A filtered or limited
    container whose `next` drops the filter hands back page two of something
    else, which is the paging defect that looks most like working.
"""

from collections.abc import Sequence
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# The query parameter a page is addressed by, 1-based. A client is not expected
# to build it — the `Link` header is what a tool follows — but a URL a developer
# can type is worth more than an opaque cursor on a service whose whole audience
# is people debugging a sync.
PAGE_PARAMETER = "page"

# The page a request that names none is asking for, and the lowest one any
# collection has. One rather than zero because `page_url` and the `Link`
# relations are 1-based, and a cursor whose first value is not the one a client
# reads back out of `first` is two cursors.
FIRST_PAGE = 1

# How many digits a page number may be written with. **Nine, and both halves of
# that are the point.** Generous: 999,999,999 pages of this container's five
# members is five billion people in one section, and a page number that will not
# fit in a signed 32-bit integer is one no platform on the other end could hold
# anyway. Small: CPython refuses to convert a decimal string longer than
# `sys.get_int_max_str_digits()` and raises `ValueError` instead, and the
# smallest limit that interpreter will accept is
# `sys.int_info.str_digits_check_threshold`, 640 — so nine digits cannot reach
# that conversion under any configuration a deployment could be running, and
# `int()` below cannot raise.
MAX_PAGE_DIGITS = 9

T = TypeVar("T")


def page_number(requested: str | None) -> int | None:
    """The page a request asks for, or `None` where it asked for something that is not one.

    **Read here rather than declared as a bound on a route parameter**, which is
    where this rule used to live. A constraint in a route signature is enforced
    by the framework *before the handler runs at all*, so a service that checks a
    credential first cannot have one: `?page=0` was answered `422`, naming the
    parameter and the bound it broke, to a caller who had presented nothing. The
    leak is small — that this container pages, what its cursor is called, where
    it starts — and the ordering claim it broke is not, because a claim with one
    exception is a claim nobody can rely on. `app.main::memberships` states the
    ordering and `docs/adr/0099` records it.

    The string is taken as it arrived and judged whole. Nothing is stripped or
    coerced: `int` accepts leading whitespace, a sign, and the underscores a
    Python literal may carry, so `int(" 1_0")` is 10 and a request asking for
    page `1_0` would be served page ten of a collection it never named. A value
    that is not a run of ASCII digits is not a page number, and repairing one
    before judging it is `docs/MISTAKES.md` entry 29.

    **The length is judged before the conversion, and that order is the fix
    rather than a tidy-up.** Digits alone are not enough to make `int()` safe:
    CPython refuses to convert a decimal string past
    `sys.get_int_max_str_digits()` and raises `ValueError`, so a several-thousand
    digit run of nines satisfied the character check and came back out of this
    function as an exception — a `500` where this docstring promises `None` and
    the route promises a refusal. `MAX_PAGE_DIGITS` says why nine is both
    generous for any page and far below the smallest conversion limit an
    interpreter will accept.

    The guard belongs here rather than as a `max_length` on the route parameter,
    for the reason the paragraph above gives about the bound itself: a constraint
    in a signature is checked before the credential is, and an overlong `page`
    would then be answered by the framework to a caller who presented nothing.

    Absent is `FIRST_PAGE`, because a client that names no cursor is asking for
    the start; that is the same default the route parameter carried, moved here
    with the bound so both halves of "what page is this" are answered in one
    place (entry 13).
    """
    if requested is None:
        return FIRST_PAGE
    if not requested.isascii() or not requested.isdigit():
        return None
    if len(requested) > MAX_PAGE_DIGITS:
        return None
    number = int(requested)
    return number if number >= FIRST_PAGE else None


class PageOutOfRangeError(LookupError):
    """A page was asked for that this collection does not have."""


def page_count(items: int, size: int) -> int:
    """How many pages `items` divides into at `size` each. One, for an empty collection.

    An empty collection is one empty page rather than zero pages, because empty
    is a legitimate answer — an unenrolled section, a gradebook nobody has
    written to — and a service that answered `404` for it would make "there is
    nothing here" and "there is no such thing" the same response.
    """
    return max(1, -(-items // size))


def page_url(base: str, page: int) -> str:
    """The URL of one page of the collection at `base`, keeping `base`'s own query.

    Any page parameter already on `base` is replaced rather than appended, so a
    header built while serving `?page=2` cannot advertise `?page=2&page=3` — a
    URL whose meaning then depends on which one the reader takes first.
    """
    split = urlsplit(base)
    # `keep_blank_values=True`, and it is load-bearing rather than tidy.
    # `parse_qsl` drops a blank value by default, so a container filtered by
    # `?tag=` would rebuild its own `Link` URLs without the filter — answering a
    # correctly filtered first page and an unfiltered second one, and handing a
    # tool line items it did not ask for. The empty string is a value; a request
    # round-tripped through a parser that normalises is a class of defect, and
    # this is the one place in this platform that does it.
    query = [
        (name, value)
        for name, value in parse_qsl(split.query, keep_blank_values=True)
        if name != PAGE_PARAMETER
    ]
    if page > 1:
        query.append((PAGE_PARAMETER, str(page)))
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def link_header(base: str, page: int, pages: int) -> str:
    """The RFC 8288 header for one page. Always a header, never `None`.

    Five relations, and which of them apply is the whole of the rule.
    `first`, `last` and `current` are on every page including the only page of a
    one-page collection; `prev` appears from page two; `next` appears only where
    a next page exists. That is the set Canvas sends, and a client written
    against a header that only ever holds one relation passes here and breaks on
    the first platform that sends five.

    **A single page used to answer with no header at all** — right about `next`
    and under-realistic about the rest, since real platforms still say `first`,
    `last` and `current` for a collection that fits on one page. A client written
    against "read `last` to learn the extent", which is how a tool sizes a sync
    before it starts, found nothing here and had to guess. E0-28 item 5 closed
    that; the `next` half of the old rule is unchanged, and the seeded five-member
    section is still the fixture that catches a header advertising a next page
    whenever the page it is on is full.

    `current` is the page's own URL. A resumable sync records it and starts again
    there, so a `current` pointing at the first page from every page — or at the
    next one — resumes somewhere plausible and wrong.
    """
    entries = [f'<{page_url(base, 1)}>; rel="first"']
    if page > 1:
        entries.append(f'<{page_url(base, page - 1)}>; rel="prev"')
    if page < pages:
        entries.append(f'<{page_url(base, page + 1)}>; rel="next"')
    entries.append(f'<{page_url(base, pages)}>; rel="last"')
    entries.append(f'<{page_url(base, page)}>; rel="current"')
    return ", ".join(entries)


def page_size(limit: int | None, default: int, cap: int) -> int:
    """How many items a page carries: what the tool asked for, bounded by `cap`.

    **An over-large `limit` is clamped, not refused.** A tool has no way to
    discover the cap, so the only thing it can do with "your page size is too
    large" is guess a smaller one — and a platform that clamps has already
    answered the question. Canvas clamps.

    One function rather than the same `min(...)` at each container
    (`docs/MISTAKES.md` entry 13). Both AGS containers page, both have a cap, and
    two copies of this rule would be two places for one of them to drift — which
    is how a container ends up serving an institution's whole gradebook in one
    response because nobody noticed its clamp was missing.
    """
    return min(limit, cap) if limit else default


def window(items: Sequence[T], page: int, size: int) -> Sequence[T]:
    """The slice of `items` that page `page` carries, or a refusal naming the range.

    Raising for a page the collection does not have, rather than answering an
    empty one, is what turns a client following a header into nowhere into a
    `404` that says so — an empty container reads as a section nobody is in.
    """
    pages = page_count(len(items), size)
    if page < 1 or page > pages:
        raise PageOutOfRangeError(
            f"This collection has {pages} page(s) of at most {size}, and page {page} is not one "
            "of them."
        )
    return items[(page - 1) * size : page * size]
