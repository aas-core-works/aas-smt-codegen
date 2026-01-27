# pylint: disable=missing-docstring
import unittest
from typing import Optional

import aas_smt_codegen.aas_visualization
import aas_smt_codegen.frontend
import aas_smt_codegen.ir
import tests.common
from aas_smt_codegen.common import indent_but_first_line


class TestAgainstRecorded(unittest.TestCase):
    def test_cases(self) -> None:
        for test_case in tests.common.over_test_cases():
            environment = tests.common.must_read_valid_environment_with_submodels(
                path=test_case.submodel_template_path
            )

            aggregational_view, errors = (
                aas_smt_codegen.frontend.parse_aggregational_view(
                    submodels=list(environment.over_submodels_or_empty())
                )
            )

            errors_text: Optional[str] = None
            if errors is not None:
                error_indent = "  "
                errors_text = "\n".join(
                    f"* {indent_but_first_line(str(error), error_indent)}"
                    for error in errors
                )

            if test_case.expected:
                if errors is not None:
                    submodels_text = aas_smt_codegen.aas_visualization.dump(
                        list(environment.over_submodels_or_empty())
                    )

                    raise AssertionError(
                        f"Unexpected error for a valid submodel template "
                        f"{test_case.submodel_template_path}:\n{errors_text}\n\n"
                        f"The submodel template was:\n"
                        f"{submodels_text}"
                    )
            else:
                if errors is None:
                    raise AssertionError(
                        f"Expected an error for an invalid submodel template "
                        f"{test_case.submodel_template_path}, but got none"
                    )

            expected_or_unexpected = "expected" if test_case.expected else "unexpected"
            output_dir = (
                tests.common.TEST_DATA_DIR
                / "frontend"
                / expected_or_unexpected
                / test_case.identifier
            )

            aggregational_view_text = (
                aas_smt_codegen.ir.dump(aggregational_view.entities).strip()
                if aggregational_view is not None
                else None
            )

            structural_view_text: Optional[str] = None
            if aggregational_view is not None:
                structural_view = (
                    aas_smt_codegen.frontend.aggregational_to_structural_view(
                        aggregational_view=aggregational_view
                    )
                )

                structural_view_text = aas_smt_codegen.ir.dump(
                    structural_view.structures
                )

            aggregational_view_path = output_dir / "aggregational_view.txt"
            structural_view_path = output_dir / "structural_view.txt"
            error_path = output_dir / "error.txt"

            if tests.common.RERECORD:
                output_dir.mkdir(exist_ok=True, parents=True)

                assert (aggregational_view_text is not None) ^ (errors is not None)

                if aggregational_view_text is not None:
                    aggregational_view_path.write_text(
                        aggregational_view_text, encoding="utf-8"
                    )

                if structural_view_text is not None:
                    structural_view_path.write_text(
                        structural_view_text, encoding="utf-8"
                    )

                if errors is not None:
                    assert errors_text is not None
                    error_path.write_text(errors_text, encoding="utf-8")

            else:
                if test_case.expected:
                    if not aggregational_view_path.exists():
                        raise FileNotFoundError(
                            f"The test case {test_case.identifier} "
                            f"is expected to work, "
                            f"but the golden file does not "
                            f"exist: {aggregational_view_path}"
                        )

                    if not structural_view_path.exists():
                        raise FileNotFoundError(
                            f"The test case {test_case.identifier} "
                            f"is expected to work, "
                            f"but the golden file does not "
                            f"exist: {structural_view_path}"
                        )

                    expected_aggregational_view_text = (
                        aggregational_view_path.read_text(encoding="utf-8").strip()
                    )

                    expected_structural_view_text = structural_view_path.read_text(
                        encoding="utf-8"
                    ).strip()

                    if errors is not None:
                        raise AssertionError(
                            f"The test case {test_case.identifier} is expected "
                            f"to work, but got one or more errors: {errors}"
                        )

                    self.assertEqual(
                        expected_aggregational_view_text,
                        aggregational_view_text,
                        f"Expected from {aggregational_view_path}",
                    )

                    self.assertEqual(
                        expected_structural_view_text,
                        structural_view_text,
                        f"Expected from {structural_view_path}",
                    )
                else:
                    if not error_path.exists():
                        raise FileNotFoundError(
                            f"The test case {test_case.identifier} is expected not "
                            f"to work, but the expected error is missing: {error_path}"
                        )

                    expected_error = error_path.read_text(encoding="utf-8").strip()

                    assert errors_text is not None

                    self.assertEqual(
                        expected_error,
                        errors_text,
                        f"Expected error from {error_path}",
                    )


if __name__ == "__main__":
    unittest.main()
