"""No roll-up payload carries a comment, a summary, a theme or a comment count — E9-07 done-when 9.

> 9. **No comment on any roll-up payload.** The roll-up schemas carry no
>    comment, summary, theme or comment count; a schema sweep over
>    `schemas/rollup.py` asserts it, with a canary member planted to show the
>    sweep can see one.

README ruling 2: "No comments on roll-up pages." Pooled comments at a node can be
re-attributed by subtracting one node or week from another (`docs/MISTAKES.md`
entry 51), so the refusal is structural: a member that is not declared cannot be
filled.

**What the sweep reads.** Every `pydantic.BaseModel` declared in
`app.schemas.rollup`, and every model reachable from their fields, however
nested (`list[...]`, `dict[..., ...]`, `X | None`). A model imported from another
schema module and used inside a roll-up payload (the report's comment model, for
instance) is one level out of the module and is read all the same
(`docs/MISTAKES.md` entry 53). Each model's field names, their aliases and its
computed fields are matched against the stems below as substrings, so
`comment_count`, `commentCount`, `top_themes` and `ai_summary` are all caught.

**Which failure a red is:** a member found FAILS the criterion test, naming the
model and the member. A missing `app.schemas.rollup` FAILS on a `pytest.fail`.
The schemas exist at dac77db5, so the criterion test is expected to pass there
unless the light builder declared such a member; the canaries are the evidence
that a pass means something.
"""

import importlib
import typing
from typing import Any

import pytest
from pydantic import BaseModel, Field, computed_field, create_model

ROLLUP_SCHEMA_MODULE = "app.schemas.rollup"

# The stems ruling 2 and done-when 9 name: a comment (and so a comment count), a
# summary, a theme. `summar` so `summaries` is caught as well as `summary`.
FORBIDDEN_STEMS = ("comment", "summar", "theme")


def rollup_models() -> list[type[BaseModel]]:
    """Every model declared in the roll-up schema module, by name; a FAILED if the module is absent."""
    try:
        module = importlib.import_module(ROLLUP_SCHEMA_MODULE)
    except ModuleNotFoundError as missing:
        if missing.name and ROLLUP_SCHEMA_MODULE.startswith(missing.name):
            pytest.fail(
                f"`{ROLLUP_SCHEMA_MODULE}` does not exist. E9-07 owns `backend/app/schemas/rollup.py`."
            )
        raise
    found = {
        value.__name__: value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value is not BaseModel
        and value.__module__ == module.__name__
    }
    return [found[name] for name in sorted(found)]


def models_inside(annotation: Any) -> list[type[BaseModel]]:
    """Every model an annotation names, unwrapping containers and unions."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in typing.get_args(annotation):
        found.extend(models_inside(argument))
    return found


def reachable(roots: list[type[BaseModel]]) -> list[type[BaseModel]]:
    """The roots and every model reachable from their fields and computed fields."""
    seen: dict[type[BaseModel], None] = {}
    pending = list(roots)
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen[model] = None
        for field in model.model_fields.values():
            pending.extend(models_inside(field.annotation))
        for computed in model.model_computed_fields.values():
            pending.extend(models_inside(computed.return_type))
    return list(seen)


def names_of(model: type[BaseModel]) -> list[str]:
    """Every name a member of `model` can appear under on the wire."""
    names: list[str] = []
    for name, field in model.model_fields.items():
        names.append(name)
        for alias in (field.alias, field.serialization_alias, field.validation_alias):
            if isinstance(alias, str):
                names.append(alias)
    for name, computed in model.model_computed_fields.items():
        names.append(name)
        if isinstance(computed.alias, str):
            names.append(computed.alias)
    return names


def forbidden_members(roots: list[type[BaseModel]]) -> list[tuple[str, str]]:
    """`(model, member)` for every member of a reachable model that names a forbidden stem."""
    return sorted(
        {
            (model.__name__, name)
            for model in reachable(roots)
            for name in names_of(model)
            if any(stem in name.lower() for stem in FORBIDDEN_STEMS)
        }
    )


# ---------------------------------------------------------------------------
# The instrument's own controls.
# ---------------------------------------------------------------------------


class PlantedCommentCard(BaseModel):
    rule: str
    comment_count: int


class PlantedAliasedTheme(BaseModel):
    figure: float = Field(alias="topThemes")


class PlantedComputedSummary(BaseModel):
    label: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_summary(self) -> str:
        return self.label


class PlantedNode(BaseModel):
    label: str
    cards: list[PlantedCommentCard]
    children: dict[str, PlantedAliasedTheme | None]
    digest: PlantedComputedSummary


class CleanNode(BaseModel):
    label: str
    section_count: int
    response_rate: float | None
    children: list["CleanNode"]


def test_the_sweep_finds_a_comment_count_an_alias_and_a_computed_summary_nested_in_a_payload() -> (
    None
):
    """The canary: three planted members, each one level or more below the root it is handed.

    **The mutations it kills (in the sweep):** reading only the root model's own
    fields; reading names and not aliases; skipping computed fields; matching
    whole names rather than stems. **A red here means the sweep is broken, not
    the code.**
    """
    found = forbidden_members([PlantedNode])
    assert found == [
        ("PlantedAliasedTheme", "topThemes"),
        ("PlantedCommentCard", "comment_count"),
        ("PlantedComputedSummary", "ai_summary"),
    ], f"The sweep found {found} in the planted payload."


def test_the_sweep_spares_a_payload_of_labels_counts_and_rates() -> None:
    """The near miss: section counts, rates, labels and a self-referencing tree are not comments.

    **A red here means the sweep is broken, not the code.**
    """
    found = forbidden_members([CleanNode])
    assert found == [], f"The sweep reported {found} on a payload with no comment in it."


def test_the_sweep_sees_a_member_planted_on_a_real_rollup_model() -> None:
    """The canary on the module itself: a real roll-up model, extended by one `comments` member.

    Shows the sweep reads the module's own models (the discovery found them and
    they are models the walker can open), so the criterion's pass below is a
    statement about `app.schemas.rollup`.
    """
    models = rollup_models()
    assert models, (
        f"`{ROLLUP_SCHEMA_MODULE}` declares no `pydantic.BaseModel`, so a sweep over it is over "
        "nothing and would pass any payload."
    )
    planted = create_model(
        f"Planted{models[0].__name__}", __base__=models[0], comments=(list[str], [])
    )
    found = forbidden_members([planted])
    assert (planted.__name__, "comments") in found, (
        f"A `comments` member planted on `{models[0].__name__}` was not found; the sweep found "
        f"{found}."
    )


def test_no_rollup_schema_declares_a_comment_summary_theme_or_comment_count() -> None:
    """The criterion: no model in, or reachable from, `app.schemas.rollup` names a forbidden stem.

    **The mutation it kills:** a `comment_count`, `comments`, `summary` or
    `themes` member added to any roll-up model, or a roll-up model holding a
    model from another schema module that carries one. **The near miss it
    spares:** counts of sections, rates and labels.
    """
    models = rollup_models()
    assert models, f"`{ROLLUP_SCHEMA_MODULE}` declares no model to sweep."
    swept = reachable(models)
    assert (
        sum(len(names_of(model)) for model in swept) > 0
    ), f"The models of `{ROLLUP_SCHEMA_MODULE}` declare no member at all, so this sweep read nothing."
    found = forbidden_members(models)
    assert not found, (
        f"These roll-up payload members carry a comment, summary or theme: {found}. README ruling "
        "2: no comments on roll-up pages; done-when 9: no comment, summary, theme or comment count."
    )
