"""
Make collections empty if they share a semantic ID with another collection.

The empty collections serve as references, while non-empty collections serve as
definitions.

This also affects the qualifiers, so we remove them in references as well.
"""

import os
import pathlib
import sys
from typing import Set

from aas_core3 import xmlization as aas_xmlization, types as aas_types

from aas_smt_codegen import frontend, aasing


def _deduplicate_in_situ(environment: aas_types.Environment) -> None:
    """
    Replace structure re-definitions with structure references.

    That is, each collection with a semantic ID already defined before will have its
    elements and qualifiers removed.

    Return error, if any.
    """
    observed_definitions = set()  # type: Set[str]
    for element, _ in aasing.over_elements(environment):
        if not isinstance(element, aas_types.SubmodelElementCollection):
            continue

        if element.semantic_id is None:
            continue

        global_identifier = aasing.reference_as_text(element.semantic_id)

        if global_identifier not in observed_definitions:
            observed_definitions.add(global_identifier)
        else:
            element.value = None
            element.qualifiers = None


def main() -> int:
    """Execute the main routine."""
    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent

    originals_dir = (
        repo_root
        / "test_data"
        / "idta_submodel_templates_enriched_with_qualifiers"
        / "originals_with_duplicated_definitions"
    )

    deduplicated_dir = (
        repo_root
        / "test_data"
        / "idta_submodel_templates_enriched_with_qualifiers"
        / "deduplicated_with_structure_references"
    )

    assert originals_dir.exists() and originals_dir.is_dir(), f"{originals_dir=}"

    for path in sorted(originals_dir.glob("*.xml")):
        environment, error = frontend.deserialize_environment(
            path.read_text(encoding="utf-8")
        )
        if error is not None:
            print(f"Failed to de-serialize {path}: {error}", file=sys.stderr)
            return 1

        assert environment is not None

        _deduplicate_in_situ(environment)

        target_path = deduplicated_dir / f"{path.stem}.xml"

        target_path.write_text(aas_xmlization.to_str(environment), encoding="utf-8")
        print(f"Deduplicated from {path} and saved to: {target_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
