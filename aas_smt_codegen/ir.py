"""Provide the intermediate representation for AAS Submodel Templates."""

import collections.abc
import dataclasses
import enum
import json
from typing import (
    Final,
    Union,
    List,
    get_args,
    Sequence,
    Mapping,
    Iterable,
    cast,
    Optional,
)

import aas_core3.jsonization as aas_jsonization
import aas_core3.types as aas_types
from icontract import require
from typing_extensions import assert_never

from aas_smt_codegen.common import (
    Identifier,
    assert_union_of_descendants_exhaustive,
    assert_union_without_excluded,
    Stripped,
    indent_but_first_line,
    assert_two_tuples_of_types_equal,
    is_stripped,
)


class GlobalIdentifier(Stripped):
    """Represent a non-empty string with no leading or trailing whitespace."""

    @require(lambda value: len(value) > 0)
    @require(lambda value: is_stripped(value))
    def __new__(cls, value: str) -> "GlobalIdentifier":
        return cast(GlobalIdentifier, value)


class Path:
    """Represent a path to an element in a submodel."""

    submodel_id: str
    segments: List[Union[str, int]]

    def segments_as_str(self) -> str:
        """Represent the path as the model reference path."""
        if len(self.segments) == 0:
            return ""

        parts = []  # type: List[str]
        for i, segment in enumerate(self.segments):
            if isinstance(segment, str):
                if i == 0:
                    parts.append(segment)
                else:
                    parts.append(f".{segment}")
            elif isinstance(segment, int):
                parts.append(f"[{segment}]")
            else:
                # noinspection PyTypeChecker
                assert_never(segment)

        return "".join(parts)

    def __init__(
        self, submodel_id: str, segments: Optional[List[Union[str, int]]] = None
    ) -> None:
        self.submodel_id = submodel_id
        self.segments = segments if segments is not None else []

    def deep_copy(self) -> "Path":
        """Make a deep copy of the instance."""
        return Path(submodel_id=self.submodel_id, segments=self.segments[:])

    def __str__(self) -> str:
        return f"{self.submodel_id} at {self.segments_as_str()}"


# region Primitive elements


SubmodelElementUnion = Union[
    aas_types.AnnotatedRelationshipElement,
    aas_types.BasicEventElement,
    aas_types.Blob,
    aas_types.Capability,
    aas_types.Entity,
    aas_types.File,
    aas_types.MultiLanguageProperty,
    aas_types.Operation,
    aas_types.Property,
    aas_types.Range,
    aas_types.ReferenceElement,
    aas_types.RelationshipElement,
    aas_types.SubmodelElementCollection,
    aas_types.SubmodelElementList,
]

#: Represent all the primitive elements
Element = Union[
    aas_types.AnnotatedRelationshipElement,
    aas_types.BasicEventElement,
    aas_types.Blob,
    aas_types.Capability,
    aas_types.Entity,
    aas_types.File,
    aas_types.MultiLanguageProperty,
    aas_types.Operation,
    aas_types.Property,
    aas_types.Range,
    aas_types.ReferenceElement,
    aas_types.RelationshipElement,
]

assert aas_types.SubmodelElementList not in get_args(Element), (
    "Submodel element lists are not primitives -- "
    "they are aggregations -- "
    "so they are handled differently from other elements."
)

assert aas_types.SubmodelElementCollection not in get_args(Element), (
    "Submodel element collections are not primitives -- "
    "they are aggregations -- "
    "so they are handled differently from other elements."
)

ElementTypesAsTuple = (
    aas_types.AnnotatedRelationshipElement,
    aas_types.BasicEventElement,
    aas_types.Blob,
    aas_types.Capability,
    aas_types.Entity,
    aas_types.File,
    aas_types.MultiLanguageProperty,
    aas_types.Operation,
    aas_types.Property,
    aas_types.Range,
    aas_types.ReferenceElement,
    aas_types.RelationshipElement,
)

assert_two_tuples_of_types_equal(get_args(Element), ElementTypesAsTuple)


@dataclasses.dataclass
class Range:
    """
    Represent an allowed range for a value.

    The bounds (``minimum``, ``maximum``) are stored in string representation, as
    obtained from the qualifier. Make sure that you convert them to the actual value
    corresponding to your artifact (*e.g.*, number if you are generating a JSON schema).
    """

    minimum: str
    inclusive_minimum: bool

    maximum: str
    inclusive_maximum: bool


@dataclasses.dataclass
class Qualifiers:
    """Represent relevant qualifiers parsed from an element."""

    allowed_value: Optional[str]
    allowed_ranges: List[Range]
    required_lang: List[str]
    allowed_id_short: Optional[str]
    either_or: Optional[str]

    #: The raw example value in the qualifier.
    #:
    #: When you translate this into an artifact, make sure you convert it to
    #: the appropriate type that your artifact expects. For example, if you are
    #: converting to JSON, convert this to a value corresponding to the value type
    #: of a property.
    example_values: List[str]


@dataclasses.dataclass
class PathedElement:
    """Represent an element in a submodel template with the related model path."""

    element: Element
    path: Path
    qualifiers: Qualifiers


# endregion Primitive elements

# region Aggregational view


class Multiplicity(enum.Enum):
    """List possible multiplicities in an aggregation."""

    ZERO_TO_ONE = "ZeroToOne"
    ONE = "One"
    ZERO_TO_MANY = "ZeroToMany"
    ONE_TO_MANY = "OneToMany"


@dataclasses.dataclass
class Aggregation:
    """Represent an aggregation relationship."""

    name: Identifier
    aggregatee: Union["Entity", PathedElement]
    multiplicity: Multiplicity
    description: Optional[Stripped]


class Entity:
    """Represent an entity of the data model."""

    #: Unique global identifier; this can be a URI, an IRDI *etc.*
    global_id: GlobalIdentifier

    aggregations: List[Aggregation]

    description: Optional[Stripped]

    source: Union[aas_types.Submodel, aas_types.SubmodelElementCollection]
    path: Path

    def __init__(
        self,
        global_identifier: GlobalIdentifier,
        source: Union[aas_types.Submodel, aas_types.SubmodelElementCollection],
        path: Path,
        aggregations: Optional[List[Aggregation]],
        description: Optional[Stripped],
    ) -> None:
        self.global_id = global_identifier
        self.source = source
        self.path = path
        self.aggregations = aggregations if aggregations is not None else []
        self.description = description


class AggregationalView:
    """Provide a view of the submodel template as aggregational relationships."""

    entities: Final[Sequence[Entity]]  # pylint: disable=invalid-name

    entities_by_global_id: Final[Mapping[str, Entity]]  # pylint: disable=invalid-name

    # fmt: off
    @require(
        lambda entities:
        len(set(entity.global_id for entity in entities)) == len(entities),
        "No duplicate global identifiers across entities.",
    )
    # fmt: on
    def __init__(self, entities: Sequence[Entity]) -> None:
        self.entities = entities

        self.entities_by_global_id = {
            entity.global_id: entity for entity in self.entities
        }


# endregion Aggregational view

# region Structural view


@dataclasses.dataclass
class Field:
    """Represent a field of a data structure."""

    name: Identifier
    type_annotation: "TypeAnnotation"
    required: bool
    description: Optional[Stripped]


@dataclasses.dataclass
class Structure:
    """Represent a potentially nested data structure."""

    #: Unique global identifier; this can be a URI, an IRDI *etc.*
    global_id: GlobalIdentifier

    fields: List[Field]

    #: Arbitrary fields which are restricted to one or more types. The name
    #: of the fields is not known ahead of the runtime.
    arbitraries: List[Field]

    description: Optional[Stripped]

    source: Union[aas_types.Submodel, aas_types.SubmodelElementCollection]
    path: Path


class Array:
    """Represent an array of items."""

    items: "TypeAnnotation"
    min_length: Optional[int]

    @require(lambda min_length: not (min_length is not None) or min_length >= 0)
    def __init__(
        self, items: "TypeAnnotation", min_length: Optional[int] = None
    ) -> None:
        self.items = items
        self.min_length = min_length


TypeAnnotation = Union[Structure, Array, PathedElement]  # pylint: disable=invalid-name


class StructuralView:
    """Provide a view of the submodel template as structures of fields."""

    structures: Final[Sequence[Structure]]  # pylint: disable=invalid-name

    structures_by_global_id: Final[  # pylint: disable=invalid-name
        Mapping[str, Structure]
    ]

    @require(
        lambda structures: len(set(structure.global_id for structure in structures))
        == len(structures),
        "No duplicate global identifiers across structures.",
    )
    def __init__(self, structures: Sequence[Structure]) -> None:
        self.structures = structures

        self.structures_by_global_id = {
            structure.global_id: structure for structure in self.structures
        }


# endregion Structural view

# region Testing and debugging


def _dump_entity(that: Entity) -> Stripped:
    """Represent the entity as human-readable string for debugging or testing."""
    description_part = f" {that.description}" if that.description is not None else ""

    parts = [f"Entity {that.global_id!r}{description_part}"]  # type: List[str]

    indent = "  "

    for aggregation in that.aggregations:
        if isinstance(aggregation.aggregatee, Entity):
            parts.append(
                f"{indent}{aggregation.name} "
                f"{aggregation.multiplicity.value} "
                f"{aggregation.aggregatee.global_id}"
            )
        elif isinstance(aggregation.aggregatee, PathedElement):
            jsonable = aas_jsonization.to_jsonable(aggregation.aggregatee.element)

            text = json.dumps(jsonable, sort_keys=True)

            parts.append(
                f"""\
{indent}{aggregation.name!r} {aggregation.multiplicity.value}
{indent}{indent_but_first_line(text, indent)}"""
            )
        else:
            # noinspection PyTypeChecker
            assert_never(aggregation.aggregatee)

    return Stripped("\n".join(parts))


def _dump_type_annotation(type_annotation: TypeAnnotation) -> Stripped:
    """Recursively represent the given type annotation as string."""
    if isinstance(type_annotation, Structure):
        return Stripped(repr(type_annotation.global_id))

    elif isinstance(type_annotation, Array):
        min_length = (
            f" with {type_annotation.min_length} or more items"
            if type_annotation.min_length is not None
            else ""
        )

        indent = "  "

        items = _dump_type_annotation(type_annotation.items)

        return Stripped(f"Array{min_length} of {indent_but_first_line(items, indent)}")

    elif isinstance(type_annotation, PathedElement):
        jsonable = aas_jsonization.to_jsonable(type_annotation.element)

        text = json.dumps(jsonable, sort_keys=True)

        return Stripped(text)

    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


def _dump_structure(that: Structure) -> Stripped:
    """Represent the structure as human-readable string for debugging or testing."""
    description_part = f" {that.description}" if that.description is not None else ""

    parts = [f"Structure {that.global_id!r}{description_part}"]  # type: List[str]

    indent = "  "

    for field in that.fields:
        required_part = "required" if field.required else "optional"

        type_annotation = _dump_type_annotation(field.type_annotation)

        description_part = (
            f" {field.description}" if field.description is not None else ""
        )

        parts.append(
            f"""\
{indent}{field.name!r} {required_part} {type_annotation}{description_part}"""
        )

    return Stripped("\n".join(parts))


def dump(
    that: Union[Entity, Structure, Iterable[Entity], Iterable[Structure]],
) -> Stripped:
    """Represent that instance as a string for easier debugging or testing."""
    if isinstance(that, Entity):
        return _dump_entity(that)
    elif isinstance(that, Structure):
        return _dump_structure(that)
    elif isinstance(that, collections.abc.Iterable):
        return Stripped("\n---\n".join(map(dump, that)))
    else:
        # noinspection PyTypeChecker
        assert_never(that)


# endregion Testing and debugging

# region Assertions
assert_union_of_descendants_exhaustive(
    union=SubmodelElementUnion, base_class=aas_types.SubmodelElement
)

assert_union_without_excluded(
    original_union=SubmodelElementUnion,
    subset_union=Element,
    excluded=[aas_types.SubmodelElementCollection, aas_types.SubmodelElementList],
)

# endregion Assertions
