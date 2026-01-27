"""Iterate over AAS elements."""

import json
from typing import (
    Sequence,
    Union,
    Final,
    Iterator,
    Tuple,
    get_args,
    List,
    Optional,
)

from aas_core3 import types as aas_types, jsonization as aas_jsonization
from typing_extensions import assert_never


class Path:
    """Represent an ID-short path."""

    fragments: Final[Sequence[Union[str, int]]]

    def __init__(self, fragments: Sequence[Union[str, int]]) -> None:
        self.fragments = fragments

    def __str__(self) -> str:
        if len(self.fragments) == 0:
            return ""

        parts = []  # type: List[str]

        iterator = iter(self.fragments)

        first = next(iterator)
        assert first is not None

        parts.append(str(first))

        for fragment in iterator:
            if isinstance(fragment, str):
                parts.append(f".{fragment}")
            elif isinstance(fragment, int):
                parts.append(f"[{fragment}]")
            else:
                # noinspection PyTypeChecker
                assert_never(fragment)

        return "".join(parts)


_Collection = Union[
    aas_types.Submodel,
    aas_types.SubmodelElementList,
    aas_types.SubmodelElementCollection,
]

_CollectionAsTuple = (
    aas_types.Submodel,
    aas_types.SubmodelElementList,
    aas_types.SubmodelElementCollection,
)

assert _CollectionAsTuple == get_args(_Collection)


def _over_elements(
    collection: _Collection, prefix: Path
) -> Iterator[Tuple[aas_types.SubmodelElement, Path]]:
    if isinstance(collection, aas_types.Submodel):
        for element in collection.over_submodel_elements_or_empty():
            assert (
                element.id_short is not None
            ), "All elements of a Submodel must have an ID-short."
            path = Path(fragments=list(prefix.fragments) + [element.id_short])

            yield element, path

            if isinstance(element, _CollectionAsTuple):
                yield from _over_elements(collection=element, prefix=path)
    elif isinstance(collection, aas_types.SubmodelElementList):
        for i, element in enumerate(collection.over_value_or_empty()):
            path = Path(fragments=list(prefix.fragments) + [i])

            yield element, path

            if isinstance(element, _CollectionAsTuple):
                yield from _over_elements(collection=element, prefix=path)
    elif isinstance(collection, aas_types.SubmodelElementCollection):
        for element in collection.over_value_or_empty():
            assert (
                element.id_short is not None
            ), "All elements of a Submodel Element Collection must have an ID-short."
            path = Path(fragments=list(prefix.fragments) + [element.id_short])

            yield element, path

            if isinstance(element, _CollectionAsTuple):
                yield from _over_elements(collection=element, prefix=path)
    else:
        # noinspection PyTypeChecker
        assert_never(collection)


def over_elements(
    environment: aas_types.Environment,
) -> Iterator[Tuple[aas_types.SubmodelElement, Path]]:
    """Iterate over all the submodel elements contained in the environment."""
    for submodel in environment.over_submodels_or_empty():
        prefix = Path(fragments=[])

        yield from _over_elements(collection=submodel, prefix=prefix)


def reference_as_text(reference: aas_types.Reference) -> str:
    """
    Convert the AAS reference into a string identifier.

    This is necessary since the reference is given as a list of keys.
    """
    assert len(reference.keys) > 0

    if reference.type is aas_types.ReferenceTypes.EXTERNAL_REFERENCE:
        assert len(reference.keys) == 1, "Expected only one key for external references"
        return reference.keys[0].value

    elif reference.type is aas_types.ReferenceTypes.MODEL_REFERENCE:
        jsonable = aas_jsonization.to_jsonable(reference)
        jsonable_str = json.dumps(jsonable, indent=2)

        raise NotImplementedError(
            f"We have not implemented the stringification of model references. "
            f"If you need this feature, please contact the developers. "
            f"The model reference was: {jsonable_str}"
        )

    else:
        # noinspection PyTypeChecker
        assert_never(reference.type)


def text_in_english(
    lang_strings: Optional[Sequence[aas_types.AbstractLangString]],
) -> Optional[str]:
    """
    Try to extract the contained text in English.

    If there is no language string at all or no text in English, return None.
    """
    if lang_strings is None:
        return None

    for lang_string in lang_strings:
        lang = lang_string.language.lower()
        if lang == "en" or lang.startswith("en-"):
            return lang_string.text

    return None


def relevant_details(environment: aas_types.Environment) -> Optional[str]:
    """
    Translate the elements and the concept descriptions into succinct text.

    Return None if there is nothing relevant.
    """
    # fmt: off
    elements_paths: Sequence[
        Tuple[
            Union[
                aas_types.Property,
                aas_types.Range
            ],
            Path
        ]
    ] = [
        (element, path)
        for element, path in over_elements(environment)
        if isinstance(element, (aas_types.Property, aas_types.Range))
    ]
    # fmt: on

    if len(elements_paths) == 0 and (
        environment.concept_descriptions is None
        or len(environment.concept_descriptions) == 0
    ):
        return None

    blocks = []  # type: List[str]

    if len(elements_paths) > 0:
        blocks.append("# Elements")

        for element, path in elements_paths:
            element_parts = [
                f"{element.__class__.__name__} at path {str(path)!r}"
            ]  # type: List[str]

            if element.id_short is not None:
                element_parts.append(f" with ID-short {element.id_short!r}")

            description_in_en = text_in_english(element.description)
            if description_in_en is not None:
                element_parts.append(f" with description {description_in_en!r}")

            display_name_in_en = text_in_english(element.display_name)
            if display_name_in_en is not None:
                element_parts.append(f" with display name {display_name_in_en!r}")

            element_parts.append(f" with value type {element.value_type.value}")

            if element.semantic_id is not None:
                semantic_id_as_text = reference_as_text(element.semantic_id)

                element_parts.append(
                    f" and with concept description {semantic_id_as_text!r}"
                )

            block = "".join(element_parts)
            blocks.append(block)

    if (
        environment.concept_descriptions is not None
        and len(environment.concept_descriptions) > 0
    ):
        blocks.append("# Concept descriptions")
        for concept_description in environment.over_concept_descriptions_or_empty():
            concept_description_parts = [
                f"Concept description {concept_description.id!r}"
            ]

            description_in_en = text_in_english(concept_description.description)
            if description_in_en is not None:
                concept_description_parts.append(f" means: {description_in_en!r}")

            unit_parts = []  # type: List[str]
            for (
                data_specification
            ) in concept_description.over_embedded_data_specifications_or_empty():
                content = data_specification.data_specification_content

                if isinstance(content, aas_types.DataSpecificationIEC61360):
                    if content.unit is not None:
                        unit_parts.append(content.unit)

            if len(unit_parts) > 0:
                units_str = ", ".join(unit_parts)

                if len(unit_parts) == 1:
                    concept_description_parts.append(f" with unit {units_str}")
                else:
                    concept_description_parts.append(f" with units {units_str}")

            block = "".join(concept_description_parts)
            blocks.append(block)

    text = "\n\n".join(blocks)
    return text
