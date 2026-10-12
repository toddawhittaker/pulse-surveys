"""The people editor's ordering and paging, over rows the definers would answer (SPEC §6.3).

Name columns sort by last name with titles stripped; category sorts by
hierarchy rank. The definers are replaced by fixed rows here, because the
shared test database holds other tests' people and a whole-table order is only
stable over rows a test owns. The same order over HTTP is asserted by
`tests/integration/test_the_people_editor_sorts_and_pages_over_http.py`.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.services import people

ZELLER, ADAMS, ZIMMER, NAVARRO = (uuid4() for _ in range(4))
ROWS = {
    ZELLER: {"identity_name": "Dr. Ana Zeller", "category": "Lead Faculty", "idp_issuer": None},
    ADAMS: {"identity_name": "Bo Adams", "category": "Department Chair", "idp_issuer": "x"},
    ZIMMER: {"identity_name": "Prof. Cy Zimmer", "category": "Dean", "idp_issuer": None},
    NAVARRO: {"identity_name": "Eve Navarro", "category": "VP of Academics", "idp_issuer": None},
}


class _Session:
    def rollback(self) -> None:
        pass


@pytest.fixture
def fixed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(people, "_people", lambda session, actor: dict(ROWS))
    monkeypatch.setattr(people, "_assignments", lambda session, actor: [])


def _page(sort: Any, order: Any = "asc", page: int = 1, size: int = 10) -> list[UUID]:
    answer = people.people_page(
        _Session(),  # type: ignore[arg-type]
        actor=uuid4(),
        sort=sort,
        order=order,
        page=page,
        page_size=size,
    )
    assert answer.total == len(ROWS)
    return [line.person_id for line in answer.people]


def test_titled_and_untitled_names_sort_by_last_name(fixed_rows: None) -> None:
    assert _page("name") == [ADAMS, NAVARRO, ZELLER, ZIMMER]
    assert _page("name", "desc") == [ZIMMER, ZELLER, NAVARRO, ADAMS]


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Dr. Ana Zeller", ("zeller", "ana zeller")),
        ("Prof. Cy Zimmer", ("zimmer", "cy zimmer")),
        ("Bo Adams", ("adams", "bo adams")),
        ("Dr Prof. Dee Ray", ("ray", "dee ray")),
        ("Dr.", ("dr.", "dr.")),
    ],
)
def test_the_name_key_strips_leading_titles_only(name: str, key: tuple[str, str]) -> None:
    assert people.name_sort_key(name) == key


def test_category_sorts_by_hierarchy_rank_and_unknown_categories_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = dict(ROWS)
    stranger = uuid4()
    rows[stranger] = {"identity_name": "Al Stranger", "category": "Adjunct", "idp_issuer": None}
    monkeypatch.setattr(people, "_people", lambda session, actor: rows)
    monkeypatch.setattr(people, "_assignments", lambda session, actor: [])
    answer = people.people_page(
        _Session(),  # type: ignore[arg-type]
        actor=uuid4(),
        sort="category",
        order="asc",
        page=1,
        page_size=10,
    )
    assert [line.person_id for line in answer.people] == [NAVARRO, ZIMMER, ADAMS, ZELLER, stranger]


def test_pages_are_stable_slices_with_a_total_and_past_the_end_is_empty(fixed_rows: None) -> None:
    whole = _page("name")
    assert _page("name", page=1, size=3) + _page("name", page=2, size=3) == whole
    assert _page("name", page=1, size=3) == _page("name", page=1, size=3)
    assert _page("name", page=3, size=3) == []
