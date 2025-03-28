"""
Create the submodel template Address Information.

The submodel template Carbon Footprint [0] depends on Address Information [1]. It was
expected that the structure Address Information is defined in Contact Information [2]
submodel template — however, it is not.

We generate the submodel template Address Information so that we can properly test
Carbon Footprint, even though it has not been officially published.

[0]: https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0
[1]: https://admin-shell.io/idta/SubmodelTemplate/ContactInformation/1/0
[2]: https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation
"""

import json
import os
import pathlib
import sys

import aas_core3.jsonization as aas_jsonization
import aas_core3.types as aas_types


# pylint: disable=missing-docstring


def make_qualifier_zero_to_one() -> aas_types.Qualifier:
    return aas_types.Qualifier(
        kind=aas_types.QualifierKind.CONCEPT_QUALIFIER,
        type="SMT/Cardinality",
        value_type=aas_types.DataTypeDefXSD.STRING,
        value="ZeroToOne",
    )


def make_semantic_id(identifier: str) -> aas_types.Reference:
    return aas_types.Reference(
        type=aas_types.ReferenceTypes.EXTERNAL_REFERENCE,
        keys=[
            aas_types.Key(type=aas_types.KeyTypes.GLOBAL_REFERENCE, value=identifier)
        ],
    )


def main() -> int:
    """Execute the main routine."""
    this_path = pathlib.Path(os.path.realpath(__file__))
    repo_root = this_path.parent.parent

    environment = aas_types.Environment(
        submodels=[
            aas_types.Submodel(
                id=(
                    "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"
                    "/AddressInformation"
                ),
                semantic_id=make_semantic_id(
                    identifier=(
                        "https://admin-shell.io/zvei/nameplate/1/0/ContactInformations"
                        "/AddressInformation"
                    )
                ),
                submodel_elements=[
                    aas_types.MultiLanguageProperty(
                        id_short="Street",
                        semantic_id=make_semantic_id("0173-1#02-AAO128#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                    aas_types.MultiLanguageProperty(
                        id_short="CityTown",
                        semantic_id=make_semantic_id("0173-1#02-AAO132#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                    aas_types.MultiLanguageProperty(
                        id_short="Zipcode",
                        semantic_id=make_semantic_id("0173-1#02-AAO129#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                    aas_types.MultiLanguageProperty(
                        id_short="POBox",
                        semantic_id=make_semantic_id("0173-1#02-AAO130#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                    aas_types.MultiLanguageProperty(
                        id_short="ZipCodeOfPOBox",
                        semantic_id=make_semantic_id("0173-1#02-AAO131#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                    aas_types.MultiLanguageProperty(
                        id_short="StateCounty",
                        semantic_id=make_semantic_id("0173-1#02-AAO133#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                    aas_types.MultiLanguageProperty(
                        id_short="NationalCode",
                        semantic_id=make_semantic_id("0173-1#02-AAO134#002"),
                        qualifiers=[make_qualifier_zero_to_one()],
                    ),
                ],
            )
        ]
    )

    jsonable = aas_jsonization.to_jsonable(environment)

    path = (
        repo_root
        / "test_data"
        / "idta_submodel_templates_enriched_with_qualifiers"
        / "fixed"
        / "Our AddressInformation.json"
    )
    path.parent.mkdir(exist_ok=True)
    with path.open("wt") as fid:
        json.dump(jsonable, fid, indent=2, sort_keys=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
