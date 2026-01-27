"""Provide common functionality for different tests."""

import itertools
import json
import os
import pathlib
import re
from typing import Final, Optional, Iterator, cast

import aas_core3.jsonization as aas_jsonization
import aas_core3.types as aas_types
import aas_core3.xmlization as aas_xmlization
from icontract import ensure, require

#: If set, this environment variable indicates that the golden files should be
#: re-recorded instead of checked against.
RERECORD = os.environ.get("AAS_SMT_CODEGEN_RERECORD", "").lower() in (
    "1",
    "true",
    "on",
)

FILENAMEABLE_RE = re.compile("^[^;/:]+$")


class Filenameable(str):
    """Represent a string which can be used as a filename in a file system."""

    @require(lambda value: FILENAMEABLE_RE.fullmatch(value) is not None)
    def __new__(cls, value: str) -> "Filenameable":
        return cast(Filenameable, value)


class Case:
    """Represent a test case stored in the test data."""

    # pylint: disable=invalid-name

    #: If true, this is a positive case where no error is expected. Otherwise,
    #: the submodel template is invalid in some semantical way.
    expected: Final[bool]

    #: Globally-unique identifier
    identifier: Final[Filenameable]

    #: Absolute path to the submodel template
    submodel_template_path: Final[pathlib.Path]

    @require(lambda submodel_template_path: submodel_template_path.is_absolute())
    def __init__(
        self,
        expected: bool,
        identifier: Filenameable,
        submodel_template_path: pathlib.Path,
    ) -> None:
        self.expected = expected
        self.identifier = identifier
        self.submodel_template_path = submodel_template_path


@ensure(lambda result: result.submodels is not None and len(result.submodels) >= 1)
def must_read_valid_environment_with_submodels(
    path: pathlib.Path,
) -> aas_types.Environment:
    """
    Read the environment from the given ``path``.

    Raise an exception if the environment is not valid.
    """
    text = path.read_text(encoding="utf-8")

    first_non_space = None  # type: Optional[str]
    for char in text:
        if char.isspace() or char == "\ufeff":
            continue

        first_non_space = char
        break

    if first_non_space is None:
        raise RuntimeError(f"No text to be parsed from: {path}")

    environment: aas_types.Environment

    if first_non_space == "{":
        try:
            jsonable = json.loads(text)
        except json.JSONDecodeError as exception:
            raise RuntimeError(f"Failed to parse JSON from {path}") from exception

        try:
            environment = aas_jsonization.environment_from_jsonable(jsonable)
        except aas_jsonization.DeserializationException as exception:
            raise RuntimeError(f"Failed to parse {path}") from exception

    elif first_non_space == "<":
        try:
            environment = aas_xmlization.environment_from_str(text)
        except aas_xmlization.DeserializationException as exception:
            raise RuntimeError(f"Failed to parse {path}") from exception

    else:
        raise AssertionError(
            f"Unrecognized first character from {path}, "
            f"so we do not know how to parse: {first_non_space!r}",
        )

    return environment


TEST_DATA_DIR = pathlib.Path(os.path.realpath(__file__)).parent.parent / "test_data"


def over_test_cases() -> Iterator[Case]:
    """List all the submodel template cases in the test data directory."""
    templates_dir = (
        TEST_DATA_DIR
        / "idta_submodel_templates_enriched_with_qualifiers"
        / "deduplicated_with_structure_references"
    )

    for path in sorted(
        itertools.chain(templates_dir.glob("**/*.xml"), templates_dir.glob("**/*.json"))
    ):
        assert path.is_absolute()

        yield Case(
            expected=True,
            identifier=Filenameable(path.stem),
            submodel_template_path=path,
        )
