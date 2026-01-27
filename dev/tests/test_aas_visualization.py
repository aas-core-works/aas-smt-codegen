# pylint: disable=missing-docstring

import unittest

import aas_smt_codegen.aas_visualization
import aas_smt_codegen.frontend
import aas_smt_codegen.ir
import tests.common


class TestAgainstRecorded(unittest.TestCase):
    def test_cases(self) -> None:
        for test_case in tests.common.over_test_cases():
            if not test_case.expected:
                continue

            environment = tests.common.must_read_valid_environment_with_submodels(
                path=test_case.submodel_template_path
            )

            text = aas_smt_codegen.aas_visualization.dump(
                list(environment.over_submodels_or_empty())
            )

            case_dir = (
                tests.common.TEST_DATA_DIR / "aas_visualization" / test_case.identifier
            )

            expected_path = case_dir / "aas_visualization.txt"

            if tests.common.RERECORD:
                case_dir.mkdir(exist_ok=True, parents=True)

                expected_path.write_text(text, encoding="utf-8")
            else:
                if not expected_path.exists():
                    raise FileNotFoundError(
                        f"The golden file does not exist: {expected_path}"
                    )

                expected = expected_path.read_text(encoding="utf-8").strip()

                self.assertEqual(expected, text, f"Expected from {expected_path}")


if __name__ == "__main__":
    unittest.main()
