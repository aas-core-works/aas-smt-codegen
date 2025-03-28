"""Operate on the AAS submodel templates."""

import collections
import dataclasses
import json
import re
from typing import (
    Union,
    List,
    Optional,
    Iterator,
    Tuple,
    Sequence,
    TypeVar,
    overload,
    OrderedDict,
    MutableMapping,
    Mapping,
)

from aas_core3 import (
    jsonization as aas_jsonization,
    types as aas_types,
    xmlization as aas_xmlization,
    verification as aas_verification,
)
from icontract import ensure, require
from typing_extensions import assert_never

from aas_smt_codegen import ir
from aas_smt_codegen.common import (
    IDENTIFIER_RE,
    Identifier,
    Stripped,
    try_in_english,
    bullet_points,
)


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def deserialize_environment(
    text: str,
) -> Tuple[Optional[aas_types.Environment], Optional[str]]:
    """Deserialize the environment from the given text either as JSON or XML."""
    first_non_space = None  # type: Optional[str]
    for char in text:
        if char.isspace() or char == "\ufeff":
            continue

        first_non_space = char
        break

    if first_non_space is None:
        return None, "No text to be parsed"

    environment: aas_types.Environment

    if first_non_space == "{":
        try:
            jsonable = json.loads(text)
        except json.JSONDecodeError as exception:
            return None, f"Failed to parse JSON: {exception}"

        try:
            environment = aas_jsonization.environment_from_jsonable(jsonable)
        except aas_jsonization.DeserializationException as exception:
            return None, f"Failed to parse: {exception}"

    elif first_non_space == "<":
        try:
            environment = aas_xmlization.environment_from_str(text)
        except aas_xmlization.DeserializationException as exception:
            return None, f"Failed to parse: {exception}"

    else:
        return (
            None,
            f"Unrecognized first character, "
            f"so we do not know how to parse: {first_non_space!r}",
        )

    return environment, None


def select_submodel_templates(
    submodels: Optional[Sequence[aas_types.Submodel]],
) -> List[aas_types.Submodel]:
    """Select the submodels of the template kind."""
    if submodels is None:
        return []

    return [
        submodel
        for submodel in submodels
        if submodel.kind_or_default() is aas_types.ModellingKind.TEMPLATE
    ]


def _try_global_id(
    that: Union[aas_types.Submodel, aas_types.SubmodelElementCollection],
) -> Tuple[Optional[ir.GlobalIdentifier], Optional[str]]:
    if that.semantic_id is None:
        return None, "The semantic ID is missing."

    if (
        that.semantic_id.type is aas_types.ReferenceTypes.EXTERNAL_REFERENCE
        and len(that.semantic_id.keys) == 1
        and that.semantic_id.keys[0].type is aas_types.KeyTypes.GLOBAL_REFERENCE
    ):
        return ir.GlobalIdentifier(that.semantic_id.keys[0].value.strip()), None

    if isinstance(that, aas_types.SubmodelElementCollection):
        with_id_short_part = (
            f" with ID-short {that.id_short!r}" if that.id_short is not None else ""
        )

        return None, (
            f"The semantic ID of the submodel element collection{with_id_short_part} "
            f"was expected to be an external reference "
            f"with a single global reference key, "
            f"but it was not: {aas_jsonization.to_jsonable(that.semantic_id)}"
        )

    elif isinstance(that, aas_types.Submodel):
        if (
            that.semantic_id.type is aas_types.ReferenceTypes.MODEL_REFERENCE
            and len(that.semantic_id.keys) == 1
            and that.semantic_id.keys[0].type is aas_types.KeyTypes.SUBMODEL
        ):
            return ir.GlobalIdentifier(that.semantic_id.keys[0].value.strip()), None

        return None, (
            "The semantic ID of the submodel was expected to be either an external "
            "reference with a single global reference key or a model reference with "
            "a single key to a submodel, but it was neither: "
            f"{aas_jsonization.to_jsonable(that.semantic_id)}"
        )

    else:
        # noinspection PyTypeChecker
        assert_never(that)


@dataclasses.dataclass
class Error:
    """Represent an error when parsing the submodel template into IR."""

    path: ir.Path
    cause: str

    def __str__(self) -> Stripped:  # pylint: disable=invalid-str-returned
        parts = [f"Error in {self.path.submodel_id}"]  # type: List[str]

        if len(self.path.segments) >= 0:
            parts.append(f" at {self.path.segments_as_str()}")

        if len(self.cause) > 0:
            parts.append(f": {self.cause}")

        return Stripped("".join(parts))


T = TypeVar("T")


@overload
def _triplewise_with_none(
    seq: str,
) -> Iterator[Tuple[Optional[str], str, Optional[str]]]:
    raise NotImplementedError()


@overload
def _triplewise_with_none(
    seq: Sequence[T],
) -> Iterator[Tuple[Optional[T], T, Optional[T]]]:
    raise NotImplementedError()


# noinspection PyTypeChecker
def _triplewise_with_none(
    seq: Union[str, Sequence[T]],
) -> Union[
    Iterator[Tuple[Optional[str], str, Optional[str]]],
    Iterator[Tuple[Optional[T], T, Optional[T]]],
]:
    """
    Iterate over the sequence yielding (prev, current, next) triples,
    using None for out-of-bound neighbors.

    Example:
    >>> list(_triplewise_with_none(""))
    []

    >>> list(_triplewise_with_none("ABCD"))
    [(None, 'A', 'B'), ('A', 'B', 'C'), ('B', 'C', 'D'), ('C', 'D', None)]
    """
    if len(seq) == 0:
        return

    for i, current_item in enumerate(seq):
        prev_item = seq[i - 1] if i > 0 else None
        next_item = seq[i + 1] if i < len(seq) - 1 else None

        # NOTE (mristin):
        # It is too cumbersome to fix mypy here due to the overloads, so we simply
        # ignore it.
        yield prev_item, current_item, next_item  # type: ignore


class _EntityMapper(aas_types.PassThroughVisitor):
    """Map all the entities contained in a submodel."""

    errors: List[Error]
    entity_map: OrderedDict[ir.GlobalIdentifier, ir.Entity]

    def __init__(self) -> None:
        self.errors = []
        self.entity_map = collections.OrderedDict()

        # Path to the currently visited instance
        self._path = ir.Path(submodel_id="")

    @staticmethod
    @ensure(lambda result: result.startswith("a "))
    def _describe(
        that: Union[aas_types.SubmodelElementCollection, aas_types.Submodel],
    ) -> Stripped:
        """Describe ``that`` instance for a human-readable message."""
        if isinstance(that, aas_types.SubmodelElementCollection):
            if that.id_short is not None:
                return Stripped("a submodel element collection")
            else:
                return Stripped(f"a submodel element collection {that.id_short}")

        elif isinstance(that, aas_types.Submodel):
            return Stripped(f"a submodel {that.id}")

        else:
            # noinspection PyTypeChecker
            assert_never(that)

    def visit_submodel(self, that: aas_types.Submodel) -> None:
        # NOTE (mristin):
        # We reset the path on every submodel visit.
        self._path = ir.Path(submodel_id=that.id)

        global_id, global_id_error = _try_global_id(that)

        if global_id_error is not None:
            self.errors.append(
                Error(path=self._path.deep_copy(), cause=global_id_error)
            )
            return

        assert global_id is not None

        if global_id in self.entity_map:
            self.errors.append(
                Error(
                    path=self._path.deep_copy(),
                    cause=(
                        f"Duplicate entity definition for the submodel "
                        f"with ID {global_id!r}"
                    ),
                )
            )
            return

        description_not_stripped = try_in_english(that.description)
        description = (
            None
            if description_not_stripped is None
            else Stripped(description_not_stripped.strip())
        )

        self.entity_map[global_id] = ir.Entity(
            global_identifier=global_id,
            source=that,
            path=self._path.deep_copy(),
            # The aggregations will be populated at a later stage.
            aggregations=[],
            description=description,
        )

        if that.submodel_elements is not None:
            for submodel_element in that.submodel_elements:
                assert submodel_element.id_short is not None, (
                    "Expected all the ID-shorts to be set in a submodel; "
                    "if this assertion fails, check that you verify "
                    "the environment properly before."
                )

                self._path.segments.append(submodel_element.id_short)
                self.visit(submodel_element)
                self._path.segments.pop()

    def visit_submodel_element_list(self, that: aas_types.SubmodelElementList) -> None:
        if that.value is None:
            return

        for i, submodel_element in enumerate(that.value):
            self._path.segments.append(i)
            self.visit(submodel_element)
            self._path.segments.pop()

    def visit_submodel_element_collection(
        self, that: aas_types.SubmodelElementCollection
    ) -> None:
        global_id, global_id_error = _try_global_id(that)
        if global_id_error is not None:
            self.errors.append(
                Error(path=self._path.deep_copy(), cause=global_id_error)
            )
            return

        assert global_id is not None

        existing_entity = self.entity_map.get(global_id, None)

        # NOTE (mristin):
        # If set, we will set the entity with this instance, overwriting any
        # previous entity definitions.
        set_entity = False

        if existing_entity is not None:
            if isinstance(existing_entity.source, aas_types.Submodel):
                self.errors.append(
                    Error(
                        path=self._path.deep_copy(),
                        cause=(
                            "There are conflicting entity definitions for the ID "
                            f"{global_id} — one definition comes from "
                            f"a Submodel with ID {existing_entity.source.id!r} "
                            f"and the other definition comes from "
                            f"this Submodel Element Collection. "
                            f"We do not know how to resolve this conflict. "
                            f"Please fix your submodel template."
                        ),
                    )
                )
                return

            # NOTE (mristin):
            # We decide to resolve the conflict such that the collection with
            # at least one element wins over collections with zero elements.
            #
            # If both have non-zero elements then we do not know how to resolve
            # the conflict.

            existing_entity_element_count = (
                len(existing_entity.source.value)
                if existing_entity.source.value is not None
                else 0
            )

            this_element_count = len(that.value) if that.value is not None else 0

            if existing_entity_element_count > 0 and this_element_count > 0:
                self.errors.append(
                    Error(
                        path=self._path.deep_copy(),
                        cause=(
                            "There are conflicting entity definitions for the ID "
                            f"{global_id} — both definitions contain "
                            f"more than one element. We do not know how to "
                            f"resolve this conflict. Please fix your submodel "
                            f"template."
                        ),
                    )
                )
                return
            elif existing_entity_element_count >= 0 and this_element_count == 0:
                # NOTE (mristin):
                # We keep the existing entity and simply ignore this submodel
                # element collection.
                return

            elif existing_entity_element_count == 0 and this_element_count > 0:
                # NOTE (mristin):
                # We overwrite the existing entity definition as our definition
                # is richer.
                set_entity = True
        else:
            set_entity = True

        if set_entity:
            description_not_stripped = try_in_english(that.description)
            description = (
                None
                if description_not_stripped is None
                else Stripped(description_not_stripped.strip())
            )

            self.entity_map[global_id] = ir.Entity(
                global_identifier=global_id,
                source=that,
                path=self._path.deep_copy(),
                # The aggregations will be populated at a later stage.
                aggregations=[],
                description=description,
            )

        if that.value is not None:
            for submodel_element in that.value:
                assert submodel_element.id_short is not None, (
                    "Expected all submodel elements of a submodel element collection "
                    "to have their ID-shorts set; if this assertion fails, check that "
                    "the AAS model has been properly verified in the code before."
                )

                self._path.segments.append(submodel_element.id_short)
                self.visit(submodel_element)
                self._path.segments.pop()


@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None",
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _map_entities_recursively_by_semantic_ids(
    submodels: Sequence[aas_types.Submodel],
) -> Tuple[
    Optional[OrderedDict[ir.GlobalIdentifier, ir.Entity]], Optional[List[Error]]
]:
    """Iterate over all the AAS instances and map the respective data entities."""
    visitor = _EntityMapper()

    for submodel in submodels:
        visitor.visit(submodel)

    if len(visitor.errors) > 0:
        return None, visitor.errors

    return visitor.entity_map, None


_QUALIFIER_VALUE_TO_MULTIPLICITY = {
    "One": ir.Multiplicity.ONE,
    "ZeroToOne": ir.Multiplicity.ZERO_TO_ONE,
    "ZeroToMany": ir.Multiplicity.ZERO_TO_MANY,
    "OneToMany": ir.Multiplicity.ONE_TO_MANY,
}


def _determine_multiplicity(
    qualifiers: Optional[Sequence[aas_types.Qualifier]],
) -> Tuple[Optional[ir.Multiplicity], Optional[str]]:
    """
    Determine the multiplicity from the given qualifiers.

    Return the multiplicity, or error, if any.
    """
    if qualifiers is None:
        return None, None

    multiplicity = None  # type: Optional[ir.Multiplicity]

    for qualifier in qualifiers:
        if qualifier.type in ("Cardinality", "SMT/Cardinality", "Multiplicity"):
            if qualifier.value_type is not aas_types.DataTypeDefXSD.STRING:
                return None, (
                    f"The qualifier type was {qualifier.type}; "
                    f"expected the value type to be xs:string, "
                    f"but got: {qualifier.value_type}"
                )

            if qualifier.value is None:
                return None, (
                    f"The qualifier type was {qualifier.type}, "
                    f"but the value was not set."
                )

            if qualifier.value not in _QUALIFIER_VALUE_TO_MULTIPLICITY:
                return None, (
                    f"The qualifier type was {qualifier.type}, "
                    f"but the value was invalid: {qualifier.value!r}"
                )

            if multiplicity is not None:
                return None, (
                    f"Duplicate multiplicity qualifiers; "
                    f"got {multiplicity} and "
                    f"{_QUALIFIER_VALUE_TO_MULTIPLICITY[qualifier.value]}"
                )

            multiplicity = _QUALIFIER_VALUE_TO_MULTIPLICITY[qualifier.value]

    return multiplicity, None


def _get_qualifier_value(
    element: aas_types.SubmodelElement, tajp: str
) -> Optional[str]:
    """
    Extract the qualifier value for the given qualifier ``tajp``.

    If the qualifier is not available, return None.
    """
    for qualifier in element.over_qualifiers_or_empty():
        if qualifier.type == tajp:
            return qualifier.value

    return None


# noinspection RegExpRedundantEscape
_RANGE_RE = re.compile(r"^\s*([\[(])([^,]+),([^,]+)([\])])\s*$")


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _get_allowed_ranges(
    element: aas_types.SubmodelElement,
) -> Tuple[Optional[List[ir.Range]], Optional[str]]:
    """
    Parse the allowed range qualifier of the element.

    If there is no such qualifier, return an empty list.

    Return parsed ranges, or an error, if any.
    """
    allowed_range_str = _get_qualifier_value(element, tajp="SMT/AllowedRange")
    if allowed_range_str is None:
        return [], None

    default_value = _get_qualifier_value(element, tajp="SMT/DefaultValue")

    ranges = []  # type: List[ir.Range]

    # Split on | to handle multiple ranges
    range_parts = allowed_range_str.split("|")

    for part in range_parts:
        part = part.strip()

        # NOTE (mristin):
        # ``*`` denotes a default value.
        if part.strip() == "*":
            assert default_value is not None
            ranges.append(
                ir.Range(
                    minimum=default_value,
                    inclusive_minimum=True,
                    maximum=default_value,
                    inclusive_maximum=True,
                )
            )
            continue

        match = _RANGE_RE.match(part)

        if match:
            open_bracket, min_str, max_str, close_bracket = match.groups()

            inclusive_minimum = open_bracket == "["
            inclusive_maximum = close_bracket == "]"

            ranges.append(
                ir.Range(
                    minimum=min_str,
                    inclusive_minimum=inclusive_minimum,
                    maximum=max_str,
                    inclusive_maximum=inclusive_maximum,
                )
            )
        else:
            return None, (
                f"Range from SMT/AllowedRange, {part!r}, could not be parsed as "
                f"it does not match the expected pattern {_RANGE_RE.pattern!r}."
            )

    return ranges, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _get_required_lang(
    element: aas_types.SubmodelElement,
) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Parse the required language qualifier of the element.

    If there is no such qualifier, return an empty list.

    Return parsed required languages, or an error, if any.
    """
    required_lang_str = _get_qualifier_value(element, tajp="SMT/RequiredLang")
    if required_lang_str is None:
        return [], None

    languages = []  # type: List[str]

    for part in required_lang_str.split("|"):
        part = part.strip()

        if not aas_verification.matches_bcp_47(part):
            return None, (
                f"The language {part!r} from SMT/RequiredLang is not "
                f"a valid BCP 47 language tag."
            )

        languages.append(part)

    return languages, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _get_relevant_qualifiers(
    element: aas_types.SubmodelElement,
) -> Tuple[Optional[ir.Qualifiers], Optional[List[str]]]:
    """
    Parse the relevant qualifiers from the element.

    Return the parsed qualifiers, or errors, if any.
    """
    errors = []

    allowed_value = _get_qualifier_value(element, "SMT/AllowedValue")

    allowed_ranges: List[ir.Range] = []
    maybe_ranges, ranges_error = _get_allowed_ranges(element)
    if ranges_error is not None:
        errors.append(f"Failed to parse SMT/AllowedRange: {ranges_error}")
    else:
        assert maybe_ranges is not None
        allowed_ranges = maybe_ranges

    required_lang: List[str] = []
    maybe_required_lang, required_lang_error = _get_required_lang(element)
    if required_lang_error is not None:
        errors.append(f"Failed to parse the required language: {required_lang_error}")
    else:
        assert maybe_required_lang is not None
        required_lang = maybe_required_lang

    allowed_id_short = _get_qualifier_value(element, "SMT/AllowedIdShort")

    either_or = _get_qualifier_value(element, "SMT/EitherOr")

    example_values = []  # type: List[str]
    example_value_str = _get_qualifier_value(element, "SMT/ExampleValue")
    if example_value_str is not None:
        example_values = example_value_str.split("|")

    if len(errors) > 0:
        return None, errors

    return (
        ir.Qualifiers(
            allowed_value=allowed_value,
            allowed_ranges=allowed_ranges,
            required_lang=required_lang,
            allowed_id_short=allowed_id_short,
            either_or=either_or,
            example_values=example_values,
        ),
        None,
    )


class _AggregationInferencerInPlace(aas_types.PassThroughVisitor):
    """Recursively set the aggregation relationships for the entities in-place."""

    errors: List[Error]

    def __init__(self, entity_map: Mapping[ir.GlobalIdentifier, ir.Entity]) -> None:
        self.errors = []

        # Path to the currently visited instance
        self._path = ir.Path(submodel_id="DUMMY")

        self._entity_map = entity_map

    def _retrieve_entity(
        self,
        that: Union[aas_types.SubmodelElementCollection, aas_types.Submodel],
        path: ir.Path,
    ) -> ir.Entity:
        """
        Retrieve the entity corresponding to the given instance.

        All instances are expected to be mapped in a previous stage, so an exception
        is raised if the entity could not be retrieved.
        """

        @ensure(lambda result: result.startswith("a "))
        def describe_that() -> Stripped:
            """Describe ``that`` instance for a human-readable message."""
            if isinstance(that, aas_types.SubmodelElementCollection):
                if that.id_short is not None:
                    return Stripped("a submodel element collection")
                else:
                    return Stripped(
                        f"a submodel element collection with ID-short {that.id_short!r}"
                    )

            elif isinstance(that, aas_types.Submodel):
                return Stripped("a submodel")

            else:
                # noinspection PyTypeChecker
                assert_never(that)

        global_id, global_id_error = _try_global_id(that)
        assert global_id_error is None, (
            f"Failed to get the global ID of {describe_that()} at {path}: "
            f"{global_id_error}; this was expected to be caught at the previous "
            f"stage when we mapped the entities to their global IDs."
        )

        assert global_id is not None

        entity = self._entity_map.get(global_id, None)

        semantic_id_jsonable = (
            aas_jsonization.to_jsonable(that.semantic_id)
            if that.semantic_id is not None
            else None
        )

        assert entity is not None, (
            f"The global identifier {global_id!r}, "
            f"extracted from a semantic ID of {describe_that()} at {path} "
            f"could not be found in the entity map, but the mapping was "
            f"expected to be correct from the previous stage when "
            f"we mapped the entities: "
            f"{semantic_id_jsonable}\n\n"
            f"The keys available in the entity map were:\n"
            f"{sorted(self._entity_map.keys())}"
        )

        return entity

    def _determine_aggregations_in_place(
        self,
        entity: ir.Entity,
        submodel_elements: Optional[Sequence[aas_types.SubmodelElement]],
    ) -> None:
        """Determine the aggregations of the given entity based on its elements."""
        if submodel_elements is None:
            return

        for i, submodel_element in enumerate(submodel_elements):
            description_not_stripped = try_in_english(submodel_element.description)
            description = (
                None
                if description_not_stripped is None
                else Stripped(description_not_stripped.strip())
            )

            def current_path_segments(
                an_i: int = i,
                a_submodel_element: aas_types.SubmodelElement = submodel_element,
            ) -> List[Union[str, int]]:
                """Create segments for the current submodel element."""
                return self._path.segments + [
                    (
                        a_submodel_element.id_short
                        if a_submodel_element.id_short is not None
                        else an_i
                    )
                ]

            name = None  # type: Optional[Identifier]
            aggregatee = None  # type: Optional[Union[ir.Entity, ir.PathedElement]]

            multiplicity, multiplicity_error = _determine_multiplicity(
                submodel_element.qualifiers
            )

            if multiplicity_error is not None:
                self.errors.append(
                    Error(
                        path=ir.Path(
                            submodel_id=self._path.submodel_id,
                            segments=current_path_segments(),
                        ),
                        cause=(
                            "The multiplicity based on qualifiers could not "
                            f"be determined: {multiplicity_error}"
                        ),
                    )
                )
            else:
                if multiplicity is None:
                    multiplicity = ir.Multiplicity.ONE

            if submodel_element.id_short is None:
                self.errors.append(
                    Error(
                        path=ir.Path(
                            submodel_id=self._path.submodel_id,
                            segments=current_path_segments(),
                        ),
                        cause="No ID-short set",
                    )
                )

            elif IDENTIFIER_RE.match(submodel_element.id_short) is None:
                self.errors.append(
                    Error(
                        path=ir.Path(
                            submodel_id=self._path.submodel_id,
                            segments=current_path_segments(),
                        ),
                        cause=f"Invalid ID-short: {submodel_element.id_short!r}",
                    )
                )
            else:
                name = Identifier(submodel_element.id_short)

            if isinstance(submodel_element, aas_types.SubmodelElementCollection):
                aggregatee = self._retrieve_entity(
                    that=submodel_element,
                    path=ir.Path(self._path.submodel_id, current_path_segments()),
                )

            elif isinstance(submodel_element, aas_types.SubmodelElementList):
                if submodel_element.value is None:
                    self.errors.append(
                        Error(
                            path=ir.Path(
                                submodel_id=self._path.submodel_id,
                                segments=current_path_segments(),
                            ),
                            cause=(
                                "We expect the submodel element list in a template "
                                "to have exactly one element which defines its element "
                                "type, but got value none"
                            ),
                        )
                    )
                elif len(submodel_element.value) != 1:
                    self.errors.append(
                        Error(
                            path=ir.Path(
                                submodel_id=self._path.submodel_id,
                                segments=current_path_segments(),
                            ),
                            cause=(
                                "We expect the submodel element list in a template "
                                "to have exactly one element which defines its element "
                                f"type, but got {len(submodel_element.value)} elements"
                            ),
                        )
                    )
                else:
                    assert len(submodel_element.value) == 1, "Expected else branch case"

                    # NOTE (mristin):
                    # The multiplicity refers here to the list element, not the value
                    # element. We infer the multiplicity of the aggregee combining
                    # the fact that there is a list *and* that the list is either
                    # optional or mandatory. Furthermore, we know that AAS does not
                    # allow empty lists (see the invariant of Submodel Element List).
                    if multiplicity is None:
                        # NOTE (mristin):
                        # There was an error parsing the multiplicity, so we do not
                        # set it here either.
                        pass
                    elif multiplicity is ir.Multiplicity.ONE:
                        multiplicity = ir.Multiplicity.ONE_TO_MANY
                    elif multiplicity is ir.Multiplicity.ZERO_TO_ONE:
                        multiplicity = ir.Multiplicity.ZERO_TO_MANY

                    elif (
                        multiplicity is ir.Multiplicity.ZERO_TO_MANY
                        or multiplicity is ir.Multiplicity.ONE_TO_MANY
                    ):
                        # NOTE (mristin):
                        # We assume that the author of the submodel template did not
                        # have *multiple lists* in mind, but rather the multiplicity
                        # of the items.
                        pass
                    else:
                        # noinspection PyTypeChecker
                        assert_never(multiplicity)

                    assert isinstance(
                        submodel_element.value[0],
                        ir.ElementTypesAsTuple
                        + (
                            aas_types.SubmodelElementList,
                            aas_types.SubmodelElementCollection,
                        ),
                    )

                    if isinstance(submodel_element.value[0], ir.ElementTypesAsTuple):
                        path = ir.Path(
                            submodel_id=self._path.submodel_id,
                            segments=current_path_segments() + [0],
                        )

                        qualifiers, qualifiers_errors = _get_relevant_qualifiers(
                            submodel_element.value[0]
                        )

                        if qualifiers_errors is not None:
                            self.errors.append(
                                Error(
                                    path=path,
                                    cause=(
                                        f"One or more relevant qualifiers "
                                        f"could not be parsed:\n"
                                        f"{bullet_points(qualifiers_errors)}"
                                    ),
                                )
                            )
                        else:
                            assert qualifiers is not None

                            # noinspection PyTypeChecker
                            aggregatee = ir.PathedElement(
                                element=submodel_element.value[0],
                                path=path,
                                qualifiers=qualifiers,
                            )

                    elif isinstance(
                        submodel_element.value[0], aas_types.SubmodelElementCollection
                    ):
                        first_element_of_value = submodel_element.value[0]
                        assert isinstance(
                            first_element_of_value, aas_types.SubmodelElementCollection
                        )

                        aggregatee = self._retrieve_entity(
                            that=first_element_of_value,
                            path=ir.Path(
                                self._path.submodel_id, current_path_segments() + [0]
                            ),
                        )

                    elif isinstance(
                        submodel_element.value[0], aas_types.SubmodelElementList
                    ):
                        self.errors.append(
                            Error(
                                path=ir.Path(
                                    submodel_id=self._path.submodel_id,
                                    segments=current_path_segments(),
                                ),
                                cause=(
                                    "We have not implemented handling of lists of "
                                    "lists as it is not clear how this should fit "
                                    "aggregation relationship model. Please contact "
                                    "the developers if you need this feature."
                                ),
                            )
                        )

                    else:
                        # noinspection PyTypeChecker
                        assert_never(submodel_element.value[0])
            else:
                assert isinstance(submodel_element, ir.ElementTypesAsTuple)

                path = ir.Path(
                    submodel_id=self._path.submodel_id,
                    segments=current_path_segments(),
                )

                qualifiers, qualifiers_errors = _get_relevant_qualifiers(
                    submodel_element
                )

                if qualifiers_errors is not None:
                    self.errors.append(
                        Error(
                            path=path,
                            cause=(
                                f"One or more relevant qualifiers "
                                f"could not be parsed:\n"
                                f"{bullet_points(qualifiers_errors)}"
                            ),
                        )
                    )
                else:
                    assert qualifiers is not None

                    # noinspection PyTypeChecker
                    aggregatee = ir.PathedElement(
                        element=submodel_element,
                        path=ir.Path(
                            submodel_id=self._path.submodel_id,
                            segments=current_path_segments(),
                        ),
                        qualifiers=qualifiers,
                    )

            if name is not None and aggregatee is not None and multiplicity is not None:
                entity.aggregations.append(
                    ir.Aggregation(
                        name=name,
                        aggregatee=aggregatee,
                        multiplicity=multiplicity,
                        description=description,
                    )
                )

    def visit_submodel(self, that: aas_types.Submodel) -> None:
        self._path = ir.Path(submodel_id=that.id)

        entity = self._retrieve_entity(that=that, path=self._path)

        self._determine_aggregations_in_place(
            entity=entity, submodel_elements=that.submodel_elements
        )

        if that.submodel_elements is not None:
            for i, submodel_element in enumerate(that.submodel_elements):
                self._path.segments.append(
                    submodel_element.id_short
                    if submodel_element.id_short is not None
                    else i
                )
                self.visit(submodel_element)
                self._path.segments.pop()

    def visit_submodel_element_collection(
        self, that: aas_types.SubmodelElementCollection
    ) -> None:
        entity = self._retrieve_entity(that=that, path=self._path)

        self._determine_aggregations_in_place(
            entity=entity, submodel_elements=that.value
        )

        if that.value is not None:
            for i, submodel_element in enumerate(that.value):
                self._path.segments.append(
                    submodel_element.id_short
                    if submodel_element.id_short is not None
                    else i
                )
                self.visit(submodel_element)
                self._path.segments.pop()


@ensure(
    lambda result: not (result is not None) or len(result) >= 1,
    "At least one error if errors are not None",
)
def _determine_aggregations_in_place(
    submodels: Sequence[aas_types.Submodel],
    entity_map: MutableMapping[ir.GlobalIdentifier, ir.Entity],
) -> Optional[List[Error]]:
    """Recurse over the submodels and figure out the aggregation relationships."""
    visitor = _AggregationInferencerInPlace(entity_map=entity_map)

    for submodel in submodels:
        visitor.visit(submodel)

    if len(visitor.errors) > 0:
        return visitor.errors

    return None


@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None",
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def parse_aggregational_view(
    submodels: Sequence[aas_types.Submodel],
) -> Tuple[Optional[ir.AggregationalView], Optional[List[Error]]]:
    """Interpret the submodel templates as aggregation relationships."""
    entity_map, mapping_errors = _map_entities_recursively_by_semantic_ids(
        submodels=submodels
    )

    if mapping_errors is not None:
        return None, mapping_errors

    assert entity_map is not None

    aggregation_errors = _determine_aggregations_in_place(
        submodels=submodels, entity_map=entity_map
    )

    if aggregation_errors is not None:
        return None, aggregation_errors

    # noinspection PyTypeChecker
    return (
        ir.AggregationalView(entities=list(entity_map.values())),
        None,
    )


@require(lambda aggregation: not is_arbitrary(aggregation.aggregatee))
def _aggregation_to_field(
    aggregation: ir.Aggregation,
    structures_by_global_id: Mapping[ir.GlobalIdentifier, ir.Structure],
) -> ir.Field:
    """Translate the aggregation to the corresponding field with a type annotation."""
    required: bool
    if (
        aggregation.multiplicity is ir.Multiplicity.ZERO_TO_ONE
        or aggregation.multiplicity is ir.Multiplicity.ZERO_TO_MANY
    ):
        required = False
    elif (
        aggregation.multiplicity is ir.Multiplicity.ONE
        or aggregation.multiplicity is ir.Multiplicity.ONE_TO_MANY
    ):
        required = True
    else:
        # noinspection PyTypeChecker
        assert_never(aggregation.multiplicity)

    type_annotation: ir.TypeAnnotation
    if (
        aggregation.multiplicity is ir.Multiplicity.ZERO_TO_ONE
        or aggregation.multiplicity is ir.Multiplicity.ONE
    ):
        if isinstance(aggregation.aggregatee, ir.Entity):
            type_annotation = structures_by_global_id[aggregation.aggregatee.global_id]
        elif isinstance(aggregation.aggregatee, ir.PathedElement):
            type_annotation = aggregation.aggregatee
        else:
            # noinspection PyTypeChecker
            assert_never(aggregation.aggregatee)

    elif (
        aggregation.multiplicity is ir.Multiplicity.ZERO_TO_MANY
        or aggregation.multiplicity is ir.Multiplicity.ONE_TO_MANY
    ):
        min_length: int
        if aggregation.multiplicity is ir.Multiplicity.ZERO_TO_MANY:
            min_length = 0
        elif aggregation.multiplicity is ir.Multiplicity.ONE_TO_MANY:
            min_length = 1
        else:
            # noinspection PyTypeChecker
            assert_never(aggregation.multiplicity)

        items_type_annotation: Union[ir.Structure, ir.PathedElement]

        if isinstance(aggregation.aggregatee, ir.Entity):
            items_type_annotation = structures_by_global_id[
                aggregation.aggregatee.global_id
            ]
        elif isinstance(aggregation.aggregatee, ir.PathedElement):
            items_type_annotation = aggregation.aggregatee
        else:
            # noinspection PyTypeChecker
            assert_never(aggregation.aggregatee)

        type_annotation = ir.Array(items=items_type_annotation, min_length=min_length)

    else:
        # noinspection PyTypeChecker
        assert_never(aggregation.multiplicity)

    return ir.Field(
        name=aggregation.name,
        type_annotation=type_annotation,
        required=required,
        description=aggregation.description,
    )


@require(lambda aggregation: is_arbitrary(aggregation.aggregatee))
def _aggregation_to_arbitrary_field(
    aggregation: ir.Aggregation,
    structures_by_global_id: Mapping[ir.GlobalIdentifier, ir.Structure],
) -> ir.Field:
    # NOTE (mristin):
    # We ignore the multiplicity for arbitrary fields -- they are additional elements
    # which are only constrained in type, but not in cardinality.

    type_annotation: Union[ir.Structure, ir.PathedElement]

    if isinstance(aggregation.aggregatee, ir.Entity):
        type_annotation = structures_by_global_id[aggregation.aggregatee.global_id]
    elif isinstance(aggregation.aggregatee, ir.PathedElement):
        type_annotation = aggregation.aggregatee
    else:
        # noinspection PyTypeChecker
        assert_never(aggregation.aggregatee)

    return ir.Field(
        # NOTE (mristin):
        # We include the name of the element for debugging. The name of an arbitrary
        # field is irrelevant, and will be ignored downstream.
        name=aggregation.name,
        type_annotation=type_annotation,
        required=False,
        description=aggregation.description,
    )


_SEMANTIC_ID_SET_OF_ARBITRARIES = {
    "https://admin-shell.io/SMT/General/ArbitraryMLP",
    "https://admin-shell.io/SMT/General/ArbitraryFile",
    "https://admin-shell.io/SMT/General/ArbitraryProp",
}


def is_arbitrary(that: Union[ir.Entity, ir.PathedElement]) -> bool:
    """Determine whether ``that`` is an arbitrary element."""
    if isinstance(that, ir.Entity):
        return False

    assert isinstance(that, ir.PathedElement)
    semantic_id = that.element.semantic_id

    if semantic_id is None:
        return False

    global_id = None  # type: Optional[str]
    if (
        semantic_id.type is aas_types.ReferenceTypes.EXTERNAL_REFERENCE
        and len(semantic_id.keys) == 1
        and semantic_id.keys[0].type is aas_types.KeyTypes.GLOBAL_REFERENCE
    ):
        global_id = semantic_id.keys[0].value.strip()

    if global_id is None:
        raise NotImplementedError(
            f"We expect all semantic IDs to be external references, "
            f"but we got:\n{json.dumps(aas_jsonization.to_jsonable(semantic_id))}\n\n"
            f"Please contact the developers if you need this feature."
        )

    return global_id in _SEMANTIC_ID_SET_OF_ARBITRARIES


def aggregational_to_structural_view(
    aggregational_view: ir.AggregationalView,
) -> ir.StructuralView:
    """Translate the aggregational view of a submodel template into a structural one."""
    # NOTE (mristin):
    # We first create empty structures, without fields, so that we can reference them
    # as placeholders.
    structures_by_global_id: MutableMapping[ir.GlobalIdentifier, ir.Structure] = (
        collections.OrderedDict(
            [
                (
                    entity.global_id,
                    ir.Structure(
                        global_id=entity.global_id,
                        fields=[],
                        arbitraries=[],
                        source=entity.source,
                        path=entity.path,
                        description=entity.description,
                    ),
                )
                for entity in aggregational_view.entities
            ]
        )
    )

    # NOTE (mristin):
    # We update now the structures in-place.
    for structure in structures_by_global_id.values():
        entity = aggregational_view.entities_by_global_id[structure.global_id]

        structure.fields = [
            _aggregation_to_field(
                aggregation=aggregation, structures_by_global_id=structures_by_global_id
            )
            for aggregation in entity.aggregations
            if not is_arbitrary(aggregation.aggregatee)
        ]

        structure.arbitraries = [
            _aggregation_to_arbitrary_field(
                aggregation=aggregation, structures_by_global_id=structures_by_global_id
            )
            for aggregation in entity.aggregations
            if is_arbitrary(aggregation.aggregatee)
        ]

    return ir.StructuralView(structures=list(structures_by_global_id.values()))
