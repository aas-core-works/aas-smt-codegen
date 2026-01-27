"""Handle implementation snippets regardless for all implementation languages."""

import csv
import io
import pathlib
import re
from typing import cast, Mapping, Tuple, Optional, List, MutableMapping

from icontract import require, ensure

from aas_smt_codegen.common import Stripped

# noinspection RegExpSimplifiable
IMPLEMENTATION_KEY_RE = re.compile("[a-zA-Z0-9._ -]+(/[a-zA-Z0-9._ -]+)*")


class ImplementationKey(str):
    """Represent a key in the map of specific implementations."""

    @require(lambda key: IMPLEMENTATION_KEY_RE.fullmatch(key))
    def __new__(cls, key: str) -> "ImplementationKey":
        return cast(ImplementationKey, key)


SpecificImplementations = Mapping[ImplementationKey, Stripped]


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def read_from_directory(
    snippets_dir: pathlib.Path,
) -> Tuple[Optional[SpecificImplementations], Optional[List[str]]]:
    """
    Read all the implementation-specific code snippets from the ``snippets_dir``.

    :return: either the map of the implementations, or the errors
    """
    mapping = dict()  # pylint: disable=use-dict-literal

    errors = []  # type: List[str]
    for pth in snippets_dir.glob("**/*"):
        # NOTE (mristin, 2022-08-25):
        # Ignore hidden or special files. In particular, we do not want Git-related
        # files such as ``.gitignore`` to be included as snippets.
        if pth.name.startswith("."):
            continue

        if pth.is_dir():
            continue

        maybe_key = (pth.relative_to(snippets_dir).parent / pth.name).as_posix()
        if IMPLEMENTATION_KEY_RE.fullmatch(maybe_key) is None:
            errors.append(
                f"The snippet key is not valid "
                f"according to {IMPLEMENTATION_KEY_RE.pattern}: {maybe_key}"
            )
            continue

        key = ImplementationKey(maybe_key)

        try:
            value = Stripped(pth.read_text(encoding="utf-8").strip())
        except UnicodeDecodeError as error:
            errors.append(
                f"The snippet file is not a valid UTF-8: {pth}. "
                f"This was the decoding error: {error}"
            )
            continue

        mapping[key] = value

    if errors:
        return None, errors

    return mapping, None


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def parse_map_from_csv(
    text: str, key_column: Stripped, value_column: Stripped
) -> Tuple[Optional[MutableMapping[Stripped, Stripped]], Optional[str]]:
    """
    Parse a map from CSV-formatted text.

    The table contains two columns -- key column and value column. There is a header
    listing these two columns.

    Return the map as a dictionary or an error, if any.
    """
    result = dict()  # type: MutableMapping[Stripped, Stripped]

    try:
        reader = csv.DictReader(io.StringIO(text))
        expected_headers = {key_column, value_column}
        actual_headers = set(reader.fieldnames or [])

        if not expected_headers.issubset(actual_headers):
            expected_headers_joined = ",".join(expected_headers)
            actual_headers_joined = (
                ",".join(actual_headers) if len(actual_headers) > 0 else "nothing"
            )

            return None, (
                f"CSV header must contain: "
                f"{expected_headers_joined}; "
                f"got: {actual_headers_joined}"
            )

        # NOTE (mristin):
        # Row index: 2 = first data row (since header is row 1)
        for row_index, row in enumerate(reader, start=2):
            key = row.get(key_column)
            value = row.get(value_column)

            if key is None or value is None:
                return None, (
                    f"Missing values at row {row_index}; "
                    f"expected 2, but got {len(row)} value(s)"
                )

            key_stripped = Stripped(key.strip())
            value_stripped = Stripped(value.strip())

            if len(key) == 0:
                return None, f"Empty {key_column!r} at row {row_index}"

            if len(value) == 0:
                return None, f"Empty {value_column!r} at row {row_index}"

            result[key_stripped] = value_stripped

        return result, None

    except Exception as exception:
        return None, str(exception)


@require(
    lambda snippet_description: snippet_description.startswith("the "),
    "The description of the snippet must be human-readable.",
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def get_str(
    spec_impls: SpecificImplementations,
    snippet_key: ImplementationKey,
    snippet_description: Stripped,
) -> Tuple[Optional[Stripped], Optional[str]]:
    """
    Try to get the snippet from the collection of implementation-specific snippets.

    The description should be human-readable. It is used to give more informative
    error messages.

    Return the snippet or an error, if any.
    """
    text: Optional[Stripped] = spec_impls.get(snippet_key, None)
    if text is None:
        return None, (
            f"The implementation snippet for {snippet_description} "
            f"is missing: {snippet_key}"
        )

    return text, None


@require(
    lambda snippet_description: snippet_description.startswith("the "),
    "The description of the snippet must be human-readable.",
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def get_and_parse_map_from_csv(
    spec_impls: SpecificImplementations,
    snippet_key: ImplementationKey,
    snippet_description: Stripped,
    key_column: Stripped,
    value_column: Stripped,
) -> Tuple[Optional[MutableMapping[Stripped, Stripped]], Optional[str]]:
    """
    Parse a mapping from a CSV snippet at ``snippet_key``.

    ``snippet_description`` describes the snippet so that we can return meaningful
    error message.
    """
    text, error = get_str(
        spec_impls=spec_impls,
        snippet_key=snippet_key,
        snippet_description=snippet_description,
    )
    if error is not None:
        return None, error

    assert text is not None

    mapping, error = parse_map_from_csv(
        text=text, key_column=key_column, value_column=value_column
    )

    if error is not None:
        return None, (
            f"Failed to parse {snippet_description} "
            f"sourced from {snippet_key}: {error}"
        )

    assert mapping is not None
    return mapping, None
