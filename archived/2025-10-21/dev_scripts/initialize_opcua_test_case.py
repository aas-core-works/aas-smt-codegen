"""Prepare test case directory structure for an OPC UA test case."""

import argparse
import os
import pathlib
import sys
from typing import List, Iterable
import xml.etree.ElementTree as ET

from aas_core3 import types as aas_types

from aas_smt_codegen import frontend
from aas_smt_codegen.common import bullet_points


def _generate_base_nodeset(namespaces: Iterable[str]) -> ET.Element:
    """Generate the base OPC UA nodeset as an XML document."""
    root = ET.Element(
        "UANodeSet",
        attrib={
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns": "http://opcfoundation.org/UA/2011/03/UANodeSet.xsd",
            "xmlns:uax": "http://opcfoundation.org/UA/2008/02/Types.xsd",
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
        }
    )

    # Add <NamespaceUris>
    namespace_uris = ET.SubElement(root, "NamespaceUris")
    for namespace in namespaces:
        uri_elem = ET.SubElement(namespace_uris, "Uri")
        uri_elem.text = namespace

    # Add <Models>
    models = ET.SubElement(root, "Models")
    for namespace in namespaces:
        model = ET.SubElement(
            models,
            "Model",
            attrib={
                "ModelUri": namespace,
                "Version": "1.0.0",
                "PublicationDate": "2025-05-21T00:00:00Z"
            }
        )
        ET.SubElement(
            model,
            "RequiredModel",
            attrib={
                "ModelUri": "http://opcfoundation.org/UA/",
                "Version": "1.04.10",
                "PublicationDate": "2021-09-15T00:00:00Z"
            }
        )

    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smt",
        type=str,
        required=True,
        help="Path to the Submodel Template file"
    )
    args = parser.parse_args()

    smt_path = pathlib.Path(args.smt)

    script_path = pathlib.Path(os.path.realpath(__file__))
    repo_dir = script_path.parent.parent

    test_case_dir = (
            repo_dir / "test_data" / "opcua" / "expected" / smt_path.stem
    )

    snippets_dir = test_case_dir / "snippets"
    snippets_dir.mkdir(parents=True, exist_ok=True)

    try:
        text = smt_path.read_text(encoding="utf-8")
    except Exception as exception:
        print(f"Failed to read --smt {smt_path}: {exception}", file=sys.stderr)
        return 1

    environment, deserialize_error = frontend.deserialize_environment(text)
    if deserialize_error is not None:
        print(
            f"Failed to de-serialize --smt {smt_path}: {deserialize_error}",
            file=sys.stderr
        )
        return 1

    assert environment is not None

    aggregational_view, parse_errors = frontend.parse_aggregational_view(
        submodels=list(environment.over_submodels_or_empty())
    )

    if parse_errors is not None:
        print(
            f"Failed to parse --smt {smt_path}:\n"
            f"{bullet_points(str(error) for error in parse_errors)}",
            file=sys.stderr
        )
        return 1

    # NOTE (mristin):
    # We assume here that the namespaces in OPC UA correspond to the global IDs
    # of the submodels.
    #
    # The operator must add additional namespaces themselves later.

    namespaces = []  # type: List[str]

    for entity in aggregational_view.entities:
        if not isinstance(entity.source, aas_types.Submodel):
            continue

        namespaces.append(entity.global_id)

    base_nodeset_root = _generate_base_nodeset(namespaces=namespaces)

    tree = ET.ElementTree(base_nodeset_root)
    tree.write(
        snippets_dir / "base_nodeset.xml",
        encoding="utf-8",
        xml_declaration=True
    )

    (snippets_dir / "browse_name_map.csv").write_text(
        """\
Original name,OPC UA Browse Name
""",
        encoding='utf-8'
    )

    (snippets_dir / "registry.csv").write_text(
        """\
Semantic ID,Browse Name,Namespace
""",
        encoding='utf-8'
    )


if __name__ == "__main__":
    sys.exit(main())
