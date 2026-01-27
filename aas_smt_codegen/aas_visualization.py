"""
Visualize AAS structures so that their overall structure is easier to inspect.

This visualization is mostly used for development, to spot how submodel templates in
the wild "work".
"""

import argparse
import collections.abc
import dataclasses
import io
import pathlib
import sys
from typing import Union, TextIO, List, Sequence

import aas_core3.jsonization as aas_jsonization
import aas_core3.types as aas_types
from typing_extensions import assert_never

from aas_smt_codegen import run, frontend
from aas_smt_codegen.common import indent_but_first_line


@dataclasses.dataclass
class _Node:
    """Represent a node in a visualization tree."""

    content: str
    children: List["_Node"]


def _visualize_qualifier(qualifier: aas_types.Qualifier) -> str:
    """Represent the qualifier as a readable string."""
    if (
        qualifier.value is not None
        and qualifier.kind is aas_types.QualifierKind.CONCEPT_QUALIFIER
        and qualifier.type == "Cardinality"
        and qualifier.value_type is aas_types.DataTypeDefXSD.STRING
    ):
        return qualifier.value

    return repr(aas_jsonization.to_jsonable(qualifier))


def _visualize_submodel_element(submodel_element: aas_types.SubmodelElement) -> _Node:
    type_name = type(submodel_element).__name__

    parts = [
        (
            f"{type_name} {submodel_element.id_short!r}"
            if submodel_element.id_short is not None
            else type_name
        )
    ]  # type: List[str]

    if submodel_element.semantic_id is not None:
        semantic_id_json = aas_jsonization.to_jsonable(submodel_element.semantic_id)

        if (
            submodel_element.semantic_id.type
            is aas_types.ReferenceTypes.EXTERNAL_REFERENCE
        ):
            assert len(submodel_element.semantic_id.keys) == 1, (
                "Only one key expected in a global reference as a semantic ID: "
                f"{semantic_id_json}"
            )
            semantic_id = submodel_element.semantic_id.keys[0].value
        else:
            semantic_id = repr(semantic_id_json)

        parts.append(f"Semantic ID: {semantic_id}")

    if submodel_element.qualifiers is not None and len(submodel_element.qualifiers) > 0:
        qualifiers = [
            _visualize_qualifier(qualifier) for qualifier in submodel_element.qualifiers
        ]

        parts.append(f"Qualifiers: {qualifiers}")

    content = "\n".join(parts)

    children = []

    if isinstance(
        submodel_element,
        (aas_types.SubmodelElementCollection, aas_types.SubmodelElementList),
    ):
        if submodel_element.value is not None:
            for child in submodel_element.value:
                children.append(_visualize_submodel_element(child))

    return _Node(content=content, children=children)


def _visualize_submodel(submodel: aas_types.Submodel) -> _Node:
    return _Node(
        (
            f"Submodel - ID-short: {submodel.id_short!r} ID: {submodel.id!r}"
            if submodel.id_short is not None
            else f"Submodel - ID: {submodel.id!r}"
        ),
        children=(
            [
                _visualize_submodel_element(element)
                for element in submodel.submodel_elements
            ]
            if submodel.submodel_elements is not None
            else []
        ),
    )


def _dump_recursively(node: _Node, depth: int, stream: TextIO) -> None:
    """Visualize recursively the tree."""
    indent = depth * "   "
    stream.write(indent_but_first_line(node.content, indent))
    if len(node.children) == 0:
        return

    for i, child in enumerate(node.children):
        stream.write("\n")

        stream.write(indent)

        if i < len(node.children) - 1:
            stream.write("├─ ")
        else:
            stream.write("└─ ")

        _dump_recursively(child, depth=depth + 1, stream=stream)


def dump(
    that: Union[
        aas_types.Submodel, aas_types.SubmodelElement, Sequence[aas_types.Submodel]
    ],
) -> str:
    """Visualize ``that`` for inspection or debugging."""
    stream = io.StringIO()
    if isinstance(that, aas_types.Submodel):
        _dump_recursively(node=_visualize_submodel(that), depth=0, stream=stream)

    elif isinstance(that, aas_types.SubmodelElement):
        _dump_recursively(
            node=_visualize_submodel_element(that), depth=0, stream=stream
        )

    elif isinstance(that, collections.abc.Sequence):
        for i, item in enumerate(that):
            assert isinstance(item, aas_types.Submodel)

            _dump_recursively(node=_visualize_submodel(item), depth=0, stream=stream)

            if i < len(that) - 1:
                stream.write("\n\n")
    else:
        # noinspection PyTypeChecker
        assert_never(that)

    return stream.getvalue()


def main(prog: str) -> int:
    """
    Visualize the given submodel templates.

    Return the error code, or 0 if no errors.
    """
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument(
        "--smt", help="Path to the AAS submodel template", required=True
    )
    args = parser.parse_args()

    submodel_template_path = pathlib.Path(args.smt)

    stderr = sys.stderr

    if not submodel_template_path.exists():
        stderr.write(f"The --smt does not exist: {submodel_template_path}\n")
        return 1

    if not submodel_template_path.is_file():
        stderr.write(f"The --smt does not point to a file: {submodel_template_path}\n")
        return 1

    try:
        text = submodel_template_path.read_text(encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to read --smt {submodel_template_path}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    environment, deserialize_error = frontend.deserialize_environment(text)
    if deserialize_error is not None:
        run.write_error_report(
            message=f"Failed to de-serialize --smt {submodel_template_path}",
            errors=[deserialize_error],
            stderr=stderr,
        )
        return 1

    assert environment is not None

    sys.stdout.write(dump(that=list(environment.over_submodels_or_empty())))

    return 0


def entry_point() -> int:
    """Provide an entry point for a console script."""
    return main(prog="aas-smt-codegen-visualize")


if __name__ == "__main__":
    sys.exit(main(prog="aas-smt-codegen-visualize"))
