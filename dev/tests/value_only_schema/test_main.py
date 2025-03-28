# pylint: disable=missing-docstring
# pylint: disable=protected-access

import unittest
from typing import Mapping, List

import aas_smt_codegen.value_only_schema.main as value_only_schema_main
from aas_smt_codegen.common import NonNegativeInt, NonEmptySequence


# noinspection PyPep8Naming
class Test_either_or_map_to_exclusivity_map(unittest.TestCase):
    def test_empty(self) -> None:
        result = value_only_schema_main._either_or_map_to_exclusivity_map(
            either_or_by_field_index=dict()
        )
        self.assertEqual({}, result)

    def test_simple_example(self) -> None:
        either_or_by_field_index = {
            NonNegativeInt(0): "a",
            NonNegativeInt(1): "a",
            NonNegativeInt(2): "b",
            NonNegativeInt(3): "b",
        }

        result = value_only_schema_main._either_or_map_to_exclusivity_map(
            either_or_by_field_index
        )

        expected = {
            NonNegativeInt(0): [NonNegativeInt(1)],
            NonNegativeInt(1): [NonNegativeInt(0)],
            NonNegativeInt(2): [NonNegativeInt(3)],
            NonNegativeInt(3): [NonNegativeInt(2)],
        }

        self.assertEqual(expected, result)

    def test_single_field_in_group(self) -> None:
        """Test with a single field in an either_or group."""
        either_or_by_field_index = {
            NonNegativeInt(0): "a",
        }

        result = value_only_schema_main._either_or_map_to_exclusivity_map(
            either_or_by_field_index
        )

        expected = {
            NonNegativeInt(0): [],  # No other fields to exclude
        }  # type: Mapping[NonNegativeInt, List[NonNegativeInt]]

        self.assertEqual(expected, result)

    def test_three_fields_in_same_group(self) -> None:
        """Test with three fields in the same either_or group."""
        either_or_by_field_index = {
            NonNegativeInt(0): "group1",
            NonNegativeInt(1): "group1",
            NonNegativeInt(2): "group1",
        }

        result = value_only_schema_main._either_or_map_to_exclusivity_map(
            either_or_by_field_index
        )

        expected = {
            NonNegativeInt(0): [NonNegativeInt(1), NonNegativeInt(2)],
            NonNegativeInt(1): [NonNegativeInt(0), NonNegativeInt(2)],
            NonNegativeInt(2): [NonNegativeInt(0), NonNegativeInt(1)],
        }

        self.assertEqual(expected, result)

    def test_multiple_groups_with_different_sizes(self) -> None:
        """Test with multiple groups of different sizes."""
        either_or_by_field_index = {
            NonNegativeInt(0): "group1",  # Single field in group1
            NonNegativeInt(1): "group2",  # group2 has 3 fields
            NonNegativeInt(2): "group2",
            NonNegativeInt(3): "group2",
            NonNegativeInt(5): "group3",  # group3 has 2 fields
            NonNegativeInt(7): "group3",
            # Fields 4 and 6 are not in any either_or group
        }

        result = value_only_schema_main._either_or_map_to_exclusivity_map(
            either_or_by_field_index
        )

        expected = {
            NonNegativeInt(0): [],  # Single field in group1
            NonNegativeInt(1): [NonNegativeInt(2), NonNegativeInt(3)],
            NonNegativeInt(2): [NonNegativeInt(1), NonNegativeInt(3)],
            NonNegativeInt(3): [NonNegativeInt(1), NonNegativeInt(2)],
            NonNegativeInt(5): [NonNegativeInt(7)],
            NonNegativeInt(7): [NonNegativeInt(5)],
        }

        self.assertEqual(expected, result)


# noinspection PyPep8Naming
class Test_exclusivity_if_then(unittest.TestCase):
    def test_single_excluded_field(self) -> None:
        result = value_only_schema_main._exclusivity_if_then(
            field_name="a", excluded_field_names=NonEmptySequence(["b"])
        )

        expected_json = {
            "if": {"required": ["a"]},
            "then": {"not": {"anyOf": [{"required": ["b"]}]}},
        }

        self.assertEqual(expected_json, result)

    def test_multiple_excluded_fields(self) -> None:
        result = value_only_schema_main._exclusivity_if_then(
            field_name="a", excluded_field_names=NonEmptySequence(["b", "c", "d"])
        )

        expected_json = {
            "if": {"required": ["a"]},
            "then": {
                "not": {
                    "anyOf": [
                        {"required": ["b"]},
                        {"required": ["c"]},
                        {"required": ["d"]},
                    ]
                }
            },
        }

        self.assertEqual(expected_json, result)


if __name__ == "__main__":
    unittest.main()
