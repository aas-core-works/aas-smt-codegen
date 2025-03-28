"""Provide common functions and types for the code generation."""

import collections.abc
import difflib
import enum
import inspect
import re
import textwrap
from typing import (
    cast,
    Any,
    Iterable,
    List,
    Tuple,
    Type,
    Optional,
    Sequence,
    TypeVar,
    overload,
    Union,
)

import aas_core3.types as aas_types
from icontract import require, DBC, ensure


class Rstripped(str):
    """
    Represent a block of text without trailing whitespace.

    The block can be both single-line or multi-line.
    """

    @require(
        lambda block: not block.endswith("\n")
        and not block.endswith(" ")
        and not block.endswith("\t")
    )
    def __new__(cls, block: str) -> "Rstripped":
        return cast(Rstripped, block)


def is_stripped(text: str) -> bool:
    """Check that the ``text`` does not have leading and trailing whitespace."""
    return (
        not text.startswith("\n")
        and not text.startswith(" ")
        and not text.startswith("\t")
    ) and (
        not text.endswith("\n") and not text.endswith(" ") and not text.endswith("\t")
    )


class Stripped(Rstripped):
    """
    Represent a block of text without leading and trailing whitespace.

    The block of text can be both single-line and multi-line.
    """

    @require(lambda block: is_stripped(block))
    def __new__(cls, block: str) -> "Stripped":
        return cast(Stripped, block)


# noinspection RegExpSimplifiable
IDENTIFIER_RE = re.compile(r"[a-zA-Z_][a-zA-Z_0-9]*")


class Identifier(DBC, Stripped):
    """Represent an identifier."""

    @require(lambda value: IDENTIFIER_RE.fullmatch(value))
    def __new__(cls, value: str) -> "Identifier":
        return cast(Identifier, value)


@ensure(lambda text, result: text.startswith("\n") or not result.startswith("\n"))
def indent_but_first_line(text: str, indent: str = "  ") -> str:
    """
    Indent all but the first line.

    Examples:
    >>> indent_but_first_line("Line 1\\nLine 2\\nLine 3")
    'Line 1\\n  Line 2\\n  Line 3'

    >>> indent_but_first_line("Single line only")
    'Single line only'

    >>> indent_but_first_line("First\\nSecond", indent=">> ")
    'First\\n>> Second'

    >>> indent_but_first_line("")
    ''

    >>> indent_but_first_line("Just one line\\n")
    'Just one line\\n'
    """
    split = text.split("\n", 1)
    if len(split) == 1:
        return text
    first, rest = split
    return first + "\n" + textwrap.indent(rest, indent)


def assert_union_of_descendants_exhaustive(union: Any, base_class: Any) -> None:
    """
    Check that the ``union`` covers all the concrete subclasses of ``base_class``.

    Make sure you put the assertion at the end of the module where no new classes are
    defined.

    See also for more details: https://hakibenita.com/python-mypy-exhaustive-checking
    """
    if inspect.isclass(union):
        union_map = {id(union): union}
    elif hasattr(union, "__args__"):
        union_map = {id(cls): cls for cls in union.__args__}
    else:
        raise NotImplementedError(f"We do not know how to handle the union: {union}")

    # We have to recursively figure out the subclasses.
    concrete_subclasses = []  # type: List[Any]

    stack = base_class.__subclasses__()  # type: List[Any]

    while len(stack) > 0:
        sub_cls = stack.pop()
        if not inspect.isabstract(sub_cls):
            concrete_subclasses.append(sub_cls)

        stack.extend(sub_cls.__subclasses__())

    subclass_map = {id(sub_cls): sub_cls for sub_cls in concrete_subclasses}

    union_set = set(union_map.keys())
    subclass_set = set(subclass_map.keys())

    if union_set != subclass_set:
        union_diff = union_set.difference(subclass_set)
        union_diff_names = [union_map[cls_id].__name__ for cls_id in union_diff]

        subclass_diff = subclass_set.difference(union_set)
        subclass_diff_names = [
            subclass_map[cls_id].__name__ for cls_id in subclass_diff
        ]

        if len(union_diff_names) == 0 and len(subclass_diff_names) > 0:
            raise AssertionError(
                f"The following concrete subclasses of {base_class.__name__!r} were "
                f"not listed in the union: {subclass_diff_names}"
            )

        elif len(union_diff_names) > 0 and len(subclass_diff_names) == 0:
            raise AssertionError(
                f"The following classes were listed in the union, "
                f"but they are not sub-classes "
                f"of {base_class.__name__!r}: {union_diff_names}"
            )
        else:
            raise AssertionError(
                f"The following classes were listed in the union, "
                f"but they are not sub-classes "
                f"of {base_class.__name__!r}: {union_diff_names}.\n\n"
                f"The following concrete sub-classes of {base_class.__name__!r} were "
                f"not listed in the union: {subclass_diff_names}"
            )


def assert_union_without_excluded(
    original_union: Any, subset_union: Any, excluded: Iterable[Any]
) -> None:
    """
    Check that the ``subset_union`` ∪ ``excluded`` is ``original_union``.

    Make sure you put the assertion at the end of the module where no new classes are
    defined.

    See also for more details: https://hakibenita.com/python-mypy-exhaustive-checking
    """
    # region Map the identifiers of the inputs to their objects

    if inspect.isclass(original_union):
        original_union_map = {id(original_union): original_union}
    elif hasattr(original_union, "__args__"):
        original_union_map = {id(a_type): a_type for a_type in original_union.__args__}
    else:
        raise NotImplementedError(
            f"We do not know how to handle the original_union: {original_union}"
        )

    if inspect.isclass(subset_union):
        subset_union_map = {id(subset_union): subset_union}
    elif hasattr(subset_union, "__args__"):
        subset_union_map = {id(a_type): a_type for a_type in subset_union.__args__}
    else:
        raise NotImplementedError(
            f"We do not know how to handle the subset_union: {subset_union}"
        )

    excluded_map = {id(a_type): a_type for a_type in excluded}

    name_map = {**original_union_map, **subset_union_map, **excluded_map}

    # endregion

    # region Compute the sets of the identifiers

    original_union_set = set(original_union_map.keys())
    subset_union_set = set(subset_union_map.keys())
    excluded_set = set(excluded_map.keys())

    # endregion

    # region Check that it all fits

    intersection = subset_union_set.intersection(excluded_set)
    if len(intersection) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in intersection)
        raise AssertionError(
            f"The following types were listed both "
            f"in the subset_union and the excluded: {names}"
        )

    diff = subset_union_set.difference(original_union_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the subset_union, "
            f"but not in the original_union: {names}"
        )

    diff = excluded_set.difference(original_union_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the excluded, "
            f"but not in the original_union: {names}"
        )

    reconstructed_set = subset_union_set.union(excluded_set)

    diff = original_union_set.difference(reconstructed_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the original_union, "
            f"but not in the subset_union ∪ excluded: {names}"
        )

    diff = reconstructed_set.difference(original_union_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the subset_union ∪ excluded, "
            f"but not in the original_union: {names}"
        )

    # endregion


def assert_consistency_of_names_and_values_of_an_enum(
    enumeration: Type[enum.Enum],
) -> None:
    """Assert that all the enumeration literals have the equal name and value."""
    for member in enumeration:
        if member.name != member.value:
            raise AssertionError(
                f"Enum member {member} has name '{member.name}' "
                f"but value '{member.value}', expected them to be equal."
            )


def assert_two_tuples_of_types_equal(
    that: Tuple[Type[Any], ...], other: Tuple[Type[Any], ...]
) -> None:
    """Check that the two tuples of types are equal, considering the order."""
    if that != other:
        actual_lines = [repr(t) for t in that]
        expected_lines = [repr(t) for t in other]
        diff = "\n".join(difflib.ndiff(actual_lines, expected_lines))

        raise AssertionError(f"Mismatch between that and other tuple of types:\n{diff}")


def try_in_english(
    language_strings: Optional[Sequence[aas_types.AbstractLangString]],
) -> Optional[str]:
    """Try to retrieve the text in English."""
    if language_strings is None:
        return None

    for lang_string in language_strings:
        language_lowercase = lang_string.language.lower()
        if language_lowercase == "en" or language_lowercase.startswith("en-"):
            return lang_string.text

    return None


def bullet_points(points: Iterable[str]) -> str:
    """Make a bullet point list out of the given points."""
    indent = "  "
    return "\n".join(f"* {indent_but_first_line(point, indent)}" for point in points)


class NonNegativeInt(int):
    """Represent a non-negative integer."""

    @require(lambda value: value >= 0)
    def __new__(cls, value: int) -> "NonNegativeInt":
        return cast(NonNegativeInt, value)


T_co = TypeVar("T_co", covariant=True)


class NonEmptySequence(collections.abc.Sequence[T_co]):
    """Represent a non-emtpy generic sequence."""

    @overload
    def __getitem__(self, index: int) -> T_co: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T_co]: ...

    def __getitem__(self, index: Union[int, slice]) -> Union[T_co, Sequence[T_co]]:
        raise AssertionError(
            "The concrete instance of this class is never expected as we use __new__"
        )

    def __len__(self) -> int:
        raise AssertionError(
            "The concrete instance of this class is never expected as we use __new__"
        )

    @require(lambda value: len(value) > 0)
    def __new__(cls, value: Sequence[T_co]) -> "NonEmptySequence[T_co]":
        return cast(NonEmptySequence[T_co], value)
