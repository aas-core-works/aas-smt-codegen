"""Generate the JSON schema for value-only representation based on the template."""

import collections
import decimal
import json
from typing import (
    TextIO,
    Tuple,
    Optional,
    Set,
    List,
    TypedDict,
    Literal,
    Mapping,
    Any,
    OrderedDict,
    cast,
    MutableMapping,
    Union,
)

from aas_core3 import types as aas_types
from icontract import ensure
from typing_extensions import assert_never

from aas_smt_codegen import ir, specific_implementations, run
from aas_smt_codegen.common import (
    bullet_points,
    Stripped,
    NonNegativeInt,
    NonEmptySequence,
)


class _DefDict(TypedDict):
    """Represent a definition of a JSON object."""

    type: Literal["object"]
    properties: List[OrderedDict[str, Any]]
    required: List[str]


_DATA_TYPE_XSD_TO_NAME = {
    aas_types.DataTypeDefXSD.ANY_URI: "XsAnyUri",
    aas_types.DataTypeDefXSD.BASE_64_BINARY: "XsBase64Binary",
    aas_types.DataTypeDefXSD.BOOLEAN: "XsBoolean",
    aas_types.DataTypeDefXSD.BYTE: "XsByte",
    aas_types.DataTypeDefXSD.DATE: "XsDate",
    aas_types.DataTypeDefXSD.DATE_TIME: "XsDateTime",
    aas_types.DataTypeDefXSD.DECIMAL: "XsDecimal",
    aas_types.DataTypeDefXSD.DOUBLE: "XsDouble",
    aas_types.DataTypeDefXSD.DURATION: "XsDuration",
    aas_types.DataTypeDefXSD.FLOAT: "XsFloat",
    aas_types.DataTypeDefXSD.G_DAY: "XsGDay",
    aas_types.DataTypeDefXSD.G_MONTH: "XsGMonth",
    aas_types.DataTypeDefXSD.G_MONTH_DAY: "XsGMonthDay",
    aas_types.DataTypeDefXSD.G_YEAR: "XsGYear",
    aas_types.DataTypeDefXSD.G_YEAR_MONTH: "XsGYearMonth",
    aas_types.DataTypeDefXSD.HEX_BINARY: "XsHexBinary",
    aas_types.DataTypeDefXSD.INT: "XsInt",
    aas_types.DataTypeDefXSD.INTEGER: "XsInteger",
    aas_types.DataTypeDefXSD.LONG: "XsLong",
    aas_types.DataTypeDefXSD.NEGATIVE_INTEGER: "XsNegativeInteger",
    aas_types.DataTypeDefXSD.NON_NEGATIVE_INTEGER: "XsNonNegativeInteger",
    aas_types.DataTypeDefXSD.NON_POSITIVE_INTEGER: "XsNonPositiveInteger",
    aas_types.DataTypeDefXSD.POSITIVE_INTEGER: "XsPositiveInteger",
    aas_types.DataTypeDefXSD.SHORT: "XsShort",
    aas_types.DataTypeDefXSD.STRING: "XsString",
    aas_types.DataTypeDefXSD.TIME: "XsTime",
    aas_types.DataTypeDefXSD.UNSIGNED_BYTE: "XsUnsignedByte",
    aas_types.DataTypeDefXSD.UNSIGNED_INT: "XsUnsignedInt",
    aas_types.DataTypeDefXSD.UNSIGNED_LONG: "XsUnsignedLong",
    aas_types.DataTypeDefXSD.UNSIGNED_SHORT: "XsUnsignedShort",
}
assert all(
    data_type in _DATA_TYPE_XSD_TO_NAME for data_type in aas_types.DataTypeDefXSD
)


def _range_to_subschema(
    a_range: ir.Range, value_type: aas_types.DataTypeDefXSD
) -> collections.OrderedDict[str, Any]:
    """Convert a range to a JSON range subschema."""
    subschema = collections.OrderedDict()  # type: collections.OrderedDict[str, Any]

    if a_range.inclusive_minimum:
        subschema["minimum"] = _to_json_value(a_range.minimum, value_type)
    else:
        subschema["exclusiveMinimum"] = a_range.minimum

    if a_range.inclusive_maximum:
        subschema["maximum"] = _to_json_value(a_range.maximum, value_type)
    else:
        subschema["exclusiveMaximum"] = a_range.maximum

    return subschema


def _to_json_value(
    text: str, value_type: aas_types.DataTypeDefXSD
) -> Union[bool, decimal.Decimal, str]:
    """Convert a text value to appropriate JSON type based on XSD data type."""
    if value_type == aas_types.DataTypeDefXSD.BOOLEAN:
        return text.lower() in ("true", "1")
    elif value_type in (
        aas_types.DataTypeDefXSD.BYTE,
        aas_types.DataTypeDefXSD.DECIMAL,
        aas_types.DataTypeDefXSD.DOUBLE,
        aas_types.DataTypeDefXSD.FLOAT,
        aas_types.DataTypeDefXSD.INT,
        aas_types.DataTypeDefXSD.INTEGER,
        aas_types.DataTypeDefXSD.LONG,
        aas_types.DataTypeDefXSD.NEGATIVE_INTEGER,
        aas_types.DataTypeDefXSD.NON_NEGATIVE_INTEGER,
        aas_types.DataTypeDefXSD.NON_POSITIVE_INTEGER,
        aas_types.DataTypeDefXSD.POSITIVE_INTEGER,
        aas_types.DataTypeDefXSD.SHORT,
        aas_types.DataTypeDefXSD.UNSIGNED_BYTE,
        aas_types.DataTypeDefXSD.UNSIGNED_INT,
        aas_types.DataTypeDefXSD.UNSIGNED_LONG,
        aas_types.DataTypeDefXSD.UNSIGNED_SHORT,
    ):
        return decimal.Decimal(text)
    else:
        return text


@ensure(lambda result: "description" not in result)
def _type_annotation_to_json_subschema(
    type_annotation: ir.TypeAnnotation,
    external_reference_map: Mapping[Stripped, Stripped],
    name_map: Mapping[Stripped, Stripped],
    url_of_schema_for_aas_elements: str,
) -> OrderedDict[str, Any]:
    """Translate a field of a structure to a JSON schema property."""
    if isinstance(type_annotation, ir.Structure):
        ref = external_reference_map.get(type_annotation.global_id, None)

        if ref is None:
            name = name_map.get(type_annotation.global_id, None)

            if name is None:
                raise AssertionError(
                    f"Unexpected dangling reference for structure "
                    f"with global ID {type_annotation.global_id!r} -- "
                    f"the dangling references were expected to be verified before"
                )

            ref = Stripped(f"#/$defs/{name}")

        assert ref is not None

        # noinspection PyTypeChecker
        return collections.OrderedDict([("$ref", ref)])

    elif isinstance(type_annotation, ir.Array):
        definition: OrderedDict[str, Any] = collections.OrderedDict(
            [
                ("type", "array"),
                (
                    "items",
                    _type_annotation_to_json_subschema(
                        type_annotation=type_annotation.items,
                        external_reference_map=external_reference_map,
                        name_map=name_map,
                        url_of_schema_for_aas_elements=url_of_schema_for_aas_elements,
                    ),
                ),
            ]
        )

        if type_annotation.min_length is not None and type_annotation.min_length != 0:
            definition["minItems"] = type_annotation.min_length

        return definition

    elif isinstance(type_annotation, ir.PathedElement):
        if isinstance(type_annotation.element, aas_types.Property):
            value_type = _DATA_TYPE_XSD_TO_NAME[type_annotation.element.value_type]

            subschema = collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/{value_type}")]
            )  # type: OrderedDict[str, Any]

            if type_annotation.qualifiers.allowed_value is not None:
                subschema["pattern"] = type_annotation.qualifiers.allowed_value

            if len(type_annotation.qualifiers.allowed_ranges) > 0:
                subschema["anyOf"] = [
                    _range_to_subschema(
                        a_range=allowed_range,
                        value_type=type_annotation.element.value_type,
                    )
                    for allowed_range in type_annotation.qualifiers.allowed_ranges
                ]

            if (
                type_annotation.qualifiers.example_values is not None
                and len(type_annotation.qualifiers.example_values) > 0
            ):
                example_values = type_annotation.qualifiers.example_values

                if len(example_values) == 1:
                    subschema["example"] = _to_json_value(
                        example_values[0],
                        value_type=type_annotation.element.value_type,
                    )
                else:
                    subschema["examples"] = [
                        _to_json_value(
                            text=example_value,
                            value_type=type_annotation.element.value_type,
                        )
                        for example_value in example_values
                    ]

            return subschema

        elif isinstance(type_annotation.element, aas_types.Range):
            value_type = _DATA_TYPE_XSD_TO_NAME[type_annotation.element.value_type]

            ref_value_type = collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/{value_type}")]
            )

            # NOTE (mristin):
            # JSON schema does not support generics, so we have to instantiate
            # the concrete subschema for the Range.

            # noinspection PyTypeChecker
            return collections.OrderedDict(
                [
                    ("type", "object"),
                    (
                        "properties",
                        collections.OrderedDict(
                            [("min", ref_value_type), ("max", ref_value_type)]
                        ),
                    ),
                ]
            )
        elif isinstance(
            type_annotation.element, aas_types.AnnotatedRelationshipElement
        ):
            return collections.OrderedDict(
                [
                    (
                        "$ref",
                        f"{url_of_schema_for_aas_elements}#/$defs/"
                        f"AnnotatedRelationshipElement",
                    )
                ]
            )
        elif isinstance(type_annotation.element, aas_types.BasicEventElement):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/BasicEventElement")]
            )
        elif isinstance(type_annotation.element, aas_types.Blob):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/Blob")]
            )
        elif isinstance(type_annotation.element, aas_types.Capability):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/Capability")]
            )
        elif isinstance(type_annotation.element, aas_types.Entity):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/Entity")]
            )
        elif isinstance(type_annotation.element, aas_types.File):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/File")]
            )
        elif isinstance(type_annotation.element, aas_types.MultiLanguageProperty):
            subschema = collections.OrderedDict(
                [
                    (
                        "$ref",
                        f"{url_of_schema_for_aas_elements}#/$defs/MultiLanguageProperty",
                    )
                ]
            )

            if (
                type_annotation.qualifiers.required_lang is not None
                and len(type_annotation.qualifiers.required_lang) > 0
            ):
                languages = type_annotation.qualifiers.required_lang

                # NOTE (mristin):
                # We have to inline the subschema in allOf and define the required
                # languages on top of it. This has to be thus the last transformative
                # command in the chain for multi-language properties.
                #
                # Here is an example:
                # "allOf": [
                #   {
                #     "$ref": ".../value-only-schema.json#/$defs/MultiLanguageProperty"
                #   },
                #   { "minItems": 2 },
                #   { "contains": { "required": ["en"] } },
                #   { "contains": { "required": ["de"] } }
                # ]

                subschema = collections.OrderedDict(
                    [
                        (
                            "allOf",
                            [
                                subschema,
                                collections.OrderedDict([("minItems", len(languages))]),
                            ],
                        )
                    ]
                )

                for language in languages:
                    subschema["allOf"].append(
                        collections.OrderedDict(
                            [
                                (
                                    "contains",
                                    collections.OrderedDict([("required", [language])]),
                                )
                            ]
                        )
                    )

            return subschema

        elif isinstance(type_annotation.element, aas_types.Operation):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/Operation")]
            )
        elif isinstance(type_annotation.element, aas_types.ReferenceElement):
            return collections.OrderedDict(
                [("$ref", f"{url_of_schema_for_aas_elements}#/$defs/ReferenceElement")]
            )
        elif isinstance(type_annotation.element, aas_types.RelationshipElement):
            return collections.OrderedDict(
                [
                    (
                        "$ref",
                        f"{url_of_schema_for_aas_elements}#/$defs/RelationshipElement",
                    )
                ]
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_annotation.element)
    else:
        # noinspection PyTypeChecker
        assert_never(type_annotation)


# fmt: off
@ensure(
    lambda result:
    all(
        value == sorted(value)
        for value in result.values()
    )
)
@ensure(
    lambda result:
    all(
        key not in value
        for key, value in result.items()
    )
)
@ensure(
    lambda either_or_by_field_index, result:
    set(either_or_by_field_index.keys()) == set(result.keys())
)
# fmt: on
def _either_or_map_to_exclusivity_map(
    either_or_by_field_index: Mapping[NonNegativeInt, str],
) -> MutableMapping[NonNegativeInt, List[NonNegativeInt]]:
    """
    Compute the exclusivity list for each field.

    The ``either_or_by_field_index`` indicates the either-or group of the structure's
    field. If the field is not assigned to an either-or group, it is omitted.

    The exclusivity map indicates which other fields should be excluded in
    the structure if the key field is present.
    """
    group_map = dict()  # type: MutableMapping[str, Set[NonNegativeInt]]

    for field_i, either_or_group in either_or_by_field_index.items():
        group_map.setdefault(either_or_group, set()).add(field_i)

    exclusivity_map = (
        dict()
    )  # type: MutableMapping[NonNegativeInt, List[NonNegativeInt]]

    for field_i in either_or_by_field_index.keys():
        either_or_group = either_or_by_field_index[field_i]

        exclusivity_map[field_i] = sorted(
            group_map[either_or_group].difference([field_i])
        )

    return exclusivity_map


def _exclusivity_if_then(
    field_name: str, excluded_field_names: NonEmptySequence[str]
) -> OrderedDict[str, Any]:
    """
    Create an if-then constraint for field exclusivity.

    If field_name is present, then none of the excluded_field_names should be present.
    """
    any_of_clauses = [
        collections.OrderedDict([("required", [excluded_field_name])])
        for excluded_field_name in excluded_field_names
    ]

    return collections.OrderedDict(
        [
            ("if", collections.OrderedDict([("required", [field_name])])),
            (
                "then",
                collections.OrderedDict(
                    [("not", collections.OrderedDict([("anyOf", any_of_clauses)]))]
                ),
            ),
        ]
    )


def _structure_to_json_definition(
    structure: ir.Structure,
    external_reference_map: Mapping[Stripped, Stripped],
    name_map: Mapping[Stripped, Stripped],
    url_of_schema_for_aas_elements: str,
) -> _DefDict:
    """Translate the structure to a JSON schema definition."""
    properties: OrderedDict[str, Any] = collections.OrderedDict()

    # NOTE (mristin):
    # The qualifier ``SMT/AllowedIdShort`` allow us to represent union types. All fields
    # which share the same ID-short should be joined in a single oneOf.
    field_group_map = (
        collections.OrderedDict()
    )  # type: OrderedDict[str, List[ir.Field]]

    for field in structure.fields:
        field_group_map.setdefault(field.name, []).append(field)

    for property_name, field_group in field_group_map.items():
        assert len(field_group) > 0

        if len(field_group) == 1:
            subschema = _type_annotation_to_json_subschema(
                type_annotation=field_group[0].type_annotation,
                external_reference_map=external_reference_map,
                name_map=name_map,
                url_of_schema_for_aas_elements=url_of_schema_for_aas_elements,
            )
        else:
            subschema = collections.OrderedDict()
            subschema["one_of"] = [
                _type_annotation_to_json_subschema(
                    type_annotation=field.type_annotation,
                    external_reference_map=external_reference_map,
                    name_map=name_map,
                    url_of_schema_for_aas_elements=url_of_schema_for_aas_elements,
                )
                for field in field_group
            ]

        for field in field_group:
            if field.description is not None:
                assert "description" not in subschema, (
                    'Expected no "description" to be set ' "before in subschema"
                )
                subschema["description"] = field.description
                break

        properties[property_name] = subschema

    def_dict = collections.OrderedDict(
        [
            ("type", "object"),
            ("properties", properties),
            ("required", [field.name for field in structure.fields if field.required]),
        ]
    )  # type: MutableMapping[str, Any]

    if len(structure.arbitraries) == 0:
        def_dict["additionalProperties"] = False
    else:
        pattern_properties_map = (
            collections.OrderedDict()
        )  # type: MutableMapping[str, Any]

        additional_properties = []  # type: List[Any]

        for arbitrary in structure.arbitraries:
            subschema = _type_annotation_to_json_subschema(
                type_annotation=arbitrary.type_annotation,
                external_reference_map=external_reference_map,
                name_map=name_map,
                url_of_schema_for_aas_elements=url_of_schema_for_aas_elements,
            )

            is_additional_property = True

            if isinstance(arbitrary.type_annotation, ir.PathedElement):
                allowed_id_short = arbitrary.type_annotation.qualifiers.allowed_id_short

                if allowed_id_short is not None:
                    is_additional_property = False

                    if allowed_id_short not in pattern_properties_map:
                        pattern_properties_map[allowed_id_short] = [subschema]
                    else:
                        pattern_properties_map[allowed_id_short].append(subschema)

            if is_additional_property:
                additional_properties.append(subschema)

        if len(pattern_properties_map) > 0:
            def_dict["patternProperties"] = collections.OrderedDict()

            for pattern in sorted(pattern_properties_map.keys()):
                pattern_subschemas = pattern_properties_map[pattern]

                assert len(pattern_subschemas) > 0

                if len(pattern_subschemas) == 1:
                    def_dict["patternProperties"][pattern] = pattern_subschemas[0]
                else:
                    def_dict["patternProperties"][pattern] = collections.OrderedDict(
                        [("oneOf", pattern_subschemas)]
                    )

        if len(additional_properties) == 1:
            def_dict["additionalProperties"] = additional_properties[0]
        else:
            def_dict["additionalProperties"] = collections.OrderedDict(
                [("oneOf", additional_properties)]
            )

    if structure.description is not None:
        def_dict["description"] = structure.description

    # NOTE (mristin):
    # We handle here "SMT/EitherOr" groups, if there are any.
    #
    # We enforce that only one element from an equivalence class can be present.
    #
    # Example:
    # {
    #   "allOf": [
    #     { "if": { "required": ["a"] }, "then": { "not": { "required": ["b"] } } },
    #     { "if": { "required": ["b"] }, "then": { "not": { "required": ["a"] } } }
    #   ]
    # }

    exclusivity_map = _either_or_map_to_exclusivity_map(
        either_or_by_field_index={
            NonNegativeInt(i): field.type_annotation.qualifiers.either_or
            for i, field in enumerate(structure.fields)
            if (
                isinstance(field.type_annotation, ir.PathedElement)
                and field.type_annotation.qualifiers.either_or is not None
            )
        }
    )

    if len(exclusivity_map) > 0:
        all_of = []  # type: List[Any]

        for field_i in sorted(exclusivity_map.keys()):
            excluded_field_indices = exclusivity_map[field_i]

            if len(excluded_field_indices) == 0:
                # NOTE (mristin):
                # This is an either-or group with a single element, so there is no
                # need to impose a constraint.
                continue

            all_of.append(
                _exclusivity_if_then(
                    field_name=structure.fields[field_i].name,
                    excluded_field_names=NonEmptySequence(
                        [
                            structure.fields[excluded_field_i].name
                            for excluded_field_i in excluded_field_indices
                        ]
                    ),
                )
            )

        if len(all_of) > 0:
            assert "allOf" not in def_dict
            def_dict["allOf"] = all_of

    # noinspection PyTypeChecker,PyInvalidCast
    return cast(_DefDict, def_dict)


class _EncoderPlusDecimal(json.JSONEncoder):
    """Encode ``decimal.Decimal`` in addition to other types."""

    def default(self, o: Any) -> str:
        if isinstance(o, decimal.Decimal):
            return str(o)

        result = super().default(o)
        assert isinstance(result, str)
        return result


@ensure(lambda result: not (result[1] is not None) or (len(result[1]) >= 1))
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(lambda result: not (result[0] is not None) or (result[0].endswith("\n")))
def _generate(
    structural_view: ir.StructuralView,
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[str]]:
    """Generate tne JSON schema according to the structural view of the template."""
    # region Get snippets
    schema_base_key = specific_implementations.ImplementationKey("schema_base.json")

    schema_base_text, error = specific_implementations.get_str(
        spec_impls=spec_impls,
        snippet_key=schema_base_key,
        snippet_description=Stripped("the root JSON schema object"),
    )
    if error is not None:
        return None, error

    assert schema_base_text is not None

    try:
        # noinspection PyTypeChecker
        schema = json.loads(schema_base_text, object_pairs_hook=collections.OrderedDict)
    except json.JSONDecodeError as exception:
        return None, (
            f"Failed to parse the implementation snippet for "
            f"the root JSON schema object from {schema_base_key}: {exception}"
        )

    if not isinstance(schema, collections.OrderedDict):
        return None, (
            f"Expected the root JSON schema to be an object, "
            f"but got {type(schema)} from {schema_base_key}"
        )

    if "$ref" not in schema:
        return None, (
            f"Expected the root JSON schema from {schema_base_key} "
            f'to reference the relevant structure with "$ref" property, '
            f"but it does not."
        )

    external_reference_map_key = specific_implementations.ImplementationKey(
        "external_reference_map.csv"
    )

    external_reference_map, error = specific_implementations.get_and_parse_map_from_csv(
        spec_impls=spec_impls,
        snippet_key=external_reference_map_key,
        snippet_description=Stripped("the map from AAS identifiers to JSON references"),
        key_column=Stripped("AAS ID"),
        value_column=Stripped("JSON Reference"),
    )
    if error is not None:
        return None, error

    assert external_reference_map is not None

    name_map_key = specific_implementations.ImplementationKey("name_map.csv")

    name_map, error = specific_implementations.get_and_parse_map_from_csv(
        spec_impls=spec_impls,
        snippet_key=name_map_key,
        snippet_description=Stripped(
            "the map from AAS identifiers to definition names"
        ),
        key_column=Stripped("AAS ID"),
        value_column=Stripped("Definition Name"),
    )
    if error is not None:
        return None, error

    assert name_map is not None

    url_of_schema_for_aas_elements, error = specific_implementations.get_str(
        spec_impls=spec_impls,
        snippet_key=specific_implementations.ImplementationKey(
            "url_of_schema_for_aas_elements.txt"
        ),
        snippet_description=Stripped(
            "the URL of the schema defining value-only serialization of AAS elements"
        ),
    )
    if error is not None:
        return None, error

    assert url_of_schema_for_aas_elements is not None

    # endregion

    # region Verify

    missing_in_maps_set: Set[str] = {
        structure.global_id
        for structure in structural_view.structures
        if (
            structure.global_id not in external_reference_map
            and structure.global_id not in name_map
        )
    }

    if len(missing_in_maps_set) > 0:
        return None, (
            f"One or more structures lacked entry either "
            f"in {external_reference_map_key} "
            f"or in {name_map_key}:\n"
            f"{bullet_points(sorted(missing_in_maps_set))}"
        )

    defined_in_both_maps_set: Set[str] = {
        structure.global_id
        for structure in structural_view.structures
        if (
            structure.global_id in external_reference_map
            and structure.global_id in name_map
        )
    }

    if len(defined_in_both_maps_set) > 0:
        return None, (
            f"One or more structures are specified both "
            f"in {external_reference_map_key} "
            f"and in {name_map_key}:\n"
            f"{bullet_points(sorted(defined_in_both_maps_set))}"
        )

    # endregion

    # region Translate

    errors: List[str] = []

    for structure in structural_view.structures:
        if structure.global_id in external_reference_map:
            continue

        identifier = name_map.get(structure.global_id, None)
        if identifier is None:
            errors.append(
                f"The mapping "
                f"from global AAS identifier {structure.global_id!r} "
                f"to a definition name "
                f"in implementation-specific snippet {name_map_key} is missing."
            )
            continue

        definition = _structure_to_json_definition(
            structure=structure,
            external_reference_map=external_reference_map,
            name_map=name_map,
            url_of_schema_for_aas_elements=url_of_schema_for_aas_elements,
        )

        if "$defs" not in schema:
            schema["$defs"] = collections.OrderedDict()

        if identifier in schema["$defs"]:
            return None, (
                f"The structure with identifier {identifier!r} has a duplicate "
                f'in "$defs" in the JSON schema. Was it already in {schema_base_key} '
                f"or is it maybe a bug?"
            )

        schema["$defs"][identifier] = definition

    # endregion

    if len(errors) > 0:
        return None, (
            f"One or more errors occurred while translating "
            f"to JSON schema for value-only representation:\n"
            f"{bullet_points(errors)}"
        )

    return json.dumps(schema, indent=2, cls=_EncoderPlusDecimal) + "\n", None


def execute(
    context: run.Context,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """
    Execute the generation with the given parameters.

    Return the error code, or 0 if no errors.
    """
    code, generate_error = _generate(
        structural_view=context.structural_view, spec_impls=context.spec_impls
    )

    if generate_error is not None:
        run.write_error_report(
            message=f"Failed to generate the JSON schema for value-only representation "
            f"based on {context.submodel_template_path}",
            errors=[generate_error],
            stderr=stderr,
        )
        return 1

    assert code is not None

    # noinspection SpellCheckingInspection
    pth = context.output_dir / "value-only-schema.json"
    try:
        pth.write_text(code, encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to write to {pth}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")

    return 0
