"""The admin's people editor as it goes over the wire (SPEC §6.3).

`app.api.admin` serves the People & reporting table, the Lead Faculty mapping
table, their writes, and each table's CSV import with its dry run. The shapes
are here; every decision about them is in `app.services.people`.

**No request body carries the acting admin.** The person making a change is
the session's own (ADR 0200), so no model below has a field for it. A body that
names one anyway has that member ignored, as every unknown member is: Pydantic's
default, kept on purpose so such a request is applied as the session's person
rather than refused in a way that hints the field mattered.

**A name or category with spaces at either end is refused, never trimmed**
(`docs/MISTAKES.md` entry 29): the editor stores what the admin typed or
nothing. The limit on `category` is the column's own `varchar(50)`.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.identity import AssignmentRole

__all__ = [
    "AssignmentLine",
    "Category",
    "GrantWrite",
    "Granted",
    "ImportApply",
    "ImportFile",
    "MappingChange",
    "MappingDiff",
    "MappingLine",
    "MappingPage",
    "MappingWrite",
    "PeopleDiff",
    "PeoplePage",
    "PersonChange",
    "PersonCreated",
    "PersonLine",
    "PersonName",
    "PersonValues",
    "PersonWrite",
    "ReportsToOption",
    "ReportsToOptions",
    "ReportsToWrite",
    "UnmappedCourse",
    "WebLoginWrite",
]

# One visible character at each end, and no line break anywhere.
_TRIMMED = r"^\S(?:.*\S)?$"

PersonName = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=_TRIMMED)]
Category = Annotated[str, StringConstraints(min_length=1, max_length=50, pattern=_TRIMMED)]

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100


class PersonWrite(BaseModel):
    """A person's name and category, on a create and on an edit."""

    model_config = ConfigDict(frozen=True)

    name: PersonName
    category: Category


class PersonCreated(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_id: UUID


class AssignmentLine(BaseModel):
    """One role assignment, and the assignment it reports to, if any.

    `reports_to_name` is the parent holder's name, so two lead assignments held
    by one person show both of their chairs (SPEC §2.1).
    """

    model_config = ConfigDict(frozen=True)

    assignment_id: UUID
    role: AssignmentRole
    scope_node_id: UUID
    reports_to: UUID | None
    reports_to_name: str | None
    reports_to_role: AssignmentRole | None


class PersonLine(BaseModel):
    """One row of the People & reporting table."""

    model_config = ConfigDict(frozen=True)

    person_id: UUID
    name: str
    category: str
    web_login_linked: bool
    assignments: list[AssignmentLine]


class PeoplePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    page: int
    page_size: int
    people: list[PersonLine]


class GrantWrite(BaseModel):
    """A role to grant, and the one org node it is granted at (ADR 0200)."""

    model_config = ConfigDict(frozen=True)

    role: AssignmentRole
    scope_node_id: UUID


class Granted(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: UUID


class ReportsToWrite(BaseModel):
    """The parent assignment, or `null` to clear the edge."""

    model_config = ConfigDict(frozen=True)

    reports_to: UUID | None


class ReportsToOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: UUID
    person_id: UUID
    name: str
    role: AssignmentRole


class ReportsToOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    options: list[ReportsToOption]


class WebLoginWrite(BaseModel):
    """The verified web-login subject to link to a person (ADR 0097)."""

    model_config = ConfigDict(frozen=True)

    idp_issuer: Annotated[str, StringConstraints(min_length=1, max_length=2048, pattern=_TRIMMED)]
    idp_subject: Annotated[str, StringConstraints(min_length=1, max_length=2048, pattern=_TRIMMED)]


class MappingLine(BaseModel):
    """One row of the Lead Faculty mapping table: a course and its lead."""

    model_config = ConfigDict(frozen=True)

    course_id: UUID
    course: str
    person_id: UUID
    name: str


class MappingPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    page: int
    page_size: int
    mappings: list[MappingLine]


class MappingWrite(BaseModel):
    """The lead to map a course to."""

    model_config = ConfigDict(frozen=True)

    person_id: UUID


class ImportFile(BaseModel):
    """An import file, as the text of a CSV, for its dry run."""

    model_config = ConfigDict(frozen=True)

    csv: str = Field(max_length=2_000_000)


class ImportApply(ImportFile):
    """The same file again, and the digest its dry run answered (ADR 0204)."""

    digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class PersonValues(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    category: str


class PersonChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_id: UUID
    before: PersonValues
    after: PersonValues


class PeopleDiff(BaseModel):
    """What a people import adds and changes. People are never removed by an import."""

    model_config = ConfigDict(frozen=True)

    digest: str
    added: list[PersonValues]
    changed: list[PersonChange]


class MappingChange(BaseModel):
    """A course whose lead the import replaces."""

    model_config = ConfigDict(frozen=True)

    before: MappingLine
    after: MappingLine


class UnmappedCourse(BaseModel):
    """A course the import leaves without a lead, and the sentence saying where it falls."""

    model_config = ConfigDict(frozen=True)

    course_id: UUID
    course: str
    note: str


class MappingDiff(BaseModel):
    """What a mapping import adds, changes and removes, and the courses left unmapped."""

    model_config = ConfigDict(frozen=True)

    digest: str
    added: list[MappingLine]
    changed: list[MappingChange]
    removed: list[MappingLine]
    unmapped: list[UnmappedCourse]
