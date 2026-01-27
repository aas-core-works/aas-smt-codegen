"""Generate names from ``Our_identifier_snake_case`` to other cases."""

from typing import List

from aas_smt_codegen.common import Identifier


def lower_snake_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``lower_snake_case``."""
    parts = identifier.split("_")

    assert len(parts) > 0, "Expected at least one part in the identifier"

    return Identifier("_".join(part.lower() for part in parts))


def upper_snake_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``UPPER_SNAKE_CASE``."""
    parts = identifier.split("_")

    assert len(parts) > 0, "Expected at least one part in the identifier"

    return Identifier("_".join(part.upper() for part in parts))


def lower_camel_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``camelCase``."""
    parts = identifier.split("_")

    assert len(parts) > 0, "Expected at least one part in the identifier"

    if len(parts) == 1:
        return Identifier(parts[0].lower())

    cased_parts = []  # type: List[str]

    iterator = iter(parts)
    first_part = next(iterator)
    cased_parts.append(first_part.lower())

    for part in iterator:
        cased_parts.append(part.capitalize())

    return Identifier("".join(cased_parts))


def capitalized_camel_case(identifier: Identifier) -> Identifier:
    """Convert the identifier to a ``CamelCase``."""
    parts = identifier.split("_")
    return Identifier("".join(part.capitalize() for part in parts))
