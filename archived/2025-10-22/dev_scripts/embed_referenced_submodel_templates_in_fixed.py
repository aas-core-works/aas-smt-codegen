"""
Embed (or overwrite) the referenced submodel templates into the submodel templates.

This is necessary so that we create a self-contained environments where all
the necessary submodels reside.
"""
import json
import os.path
import pathlib
import sys
from textwrap import indent

from aas_core3 import (
    types as aas_types,
    jsonization as aas_jsonization
)
from icontract import ensure

import aas_smt_codegen.frontend


def must_select_submodel(
        environment: aas_types.Environment,
        identifier: str
) -> aas_types.Submodel:
    """
    Get the submodel with the given ``identifier`` from the ``environment``.

    If the submodel could not be found, raise a ``ValueError`.
    """
    for submodel in environment.over_submodels_or_empty():
        if submodel.id == identifier:
            return submodel

    raise ValueError(
        f"The submodel with identifier {identifier!r} "
        f"could not be found in the environment"
    )


@ensure(
    lambda submodel, mutable_environment:
    any(
        env_submodel.id == submodel.id
        for env_submodel in mutable_environment.over_submodels_or_empty()
    ),
    "The submodel must have been added."
)
def insert_or_overwrite_submodel(
        mutable_environment: aas_types.Environment,
        submodel: aas_types.Submodel
) -> None:
    """
    Insert the ``submodel`` into the ``mutable_environment``.

    If the submodel with the same identifier already exists in the environment,
    overwrite it.
    """
    submodels = []
    overwritten = False

    for env_submodel in mutable_environment.over_submodels_or_empty():
        if env_submodel.id == submodel.id:
            overwritten = True
            submodels.append(submodel)
            continue

        submodels.append(env_submodel)

    if not overwritten:
        submodels.append(submodel)

    assert len(mutable_environment.submodels) >= 1
    mutable_environment.submodels = submodels


def main() -> int:
    """Execute the main routine."""
    repo_dir = pathlib.Path(os.path.realpath(__file__)).parent.parent
    our_address_information_path = (
            repo_dir / "test_data" / "idta_submodel_templates_enriched_with_qualifiers" / "fixed"
            / "Our AddressInformation.json"
    )
    our_address_information_text = our_address_information_path.read_text(
        encoding='utf-8'
    )

    our_address_information_environment, error = (
        aas_smt_codegen.frontend.deserialize_environment(
            our_address_information_text
        )
    )
    assert error is None, (
        f"Failed deserializing {our_address_information_path}: {error}"
    )
    assert our_address_information_environment is not None

    our_address_information = must_select_submodel(
        our_address_information_environment,
        "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/"
        "AddressInformation"
    )

    fixed_dir = repo_dir / "test_data" / "idta_submodel_templates_enriched_with_qualifiers" / "fixed"

    # NOTE (mristin):
    # We embed now address information in all the templates which need it.
    for path in [
        fixed_dir / "IDTA 02023 _Template_CarbonFootprint.json"
    ]:
        environment, error = aas_smt_codegen.frontend.deserialize_environment(
            path.read_text(encoding='utf-8')
        )
        assert error is None, f"Failed deserializing {path}: {error}"
        assert environment is not None

        insert_or_overwrite_submodel(environment, our_address_information)

        jsonable = aas_jsonization.to_jsonable(environment)
        path.write_text(json.dumps(jsonable, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
