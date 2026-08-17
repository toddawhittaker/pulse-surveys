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

Three rules are worth stating because each is a defect somebody ships:

  - **`next` appears only where a next page exists.** Advertising one whenever
    the page just served was full sends a client for a page with nothing on it.
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

T = TypeVar("T")


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


def link_header(base: str, page: int, pages: int) -> str | None:
    """The RFC 8288 header for one page, or `None` for a collection that fits on one.

    `first`, `prev` and `last` ride along with `next` because a real header
    carries several relations, and a client written against a header that only
    ever holds one passes here and breaks on the first platform that sends two.

    `None` for a single page is deliberate about `next` and under-realistic about
    the rest — real platforms still send `first` and `last` on a one-page
    container. That is [E0-28](../../docs/tickets/e0/E0-28-review-debt-from-e0-15.md)
    item 5 rather than an oversight here.
    """
    if pages <= 1:
        return None
    entries = [f'<{page_url(base, 1)}>; rel="first"']
    if page > 1:
        entries.append(f'<{page_url(base, page - 1)}>; rel="prev"')
    if page < pages:
        entries.append(f'<{page_url(base, page + 1)}>; rel="next"')
    entries.append(f'<{page_url(base, pages)}>; rel="last"')
    return ", ".join(entries)


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
