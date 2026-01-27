# pylint: disable=missing-docstring
import io
import pathlib
import tempfile
import unittest

import aas_smt_codegen.aas_visualization
import aas_smt_codegen.frontend
import aas_smt_codegen.ir
import aas_smt_codegen.main
import tests.common


class TestAgainstRecorded(unittest.TestCase):
    def test_cases(self) -> None:
        for test_case in tests.common.over_test_cases():
            if not test_case.expected:
                continue

            case_dir = (
                tests.common.TEST_DATA_DIR / "value_only_schema" / test_case.identifier
            )

            snippets_dir = case_dir / "snippets"
            output_dir = case_dir / "expected_output"

            if tests.common.RERECORD:
                output_dir.mkdir(exist_ok=True, parents=True)

                stdout = io.StringIO()
                stderr = io.StringIO()

                params = aas_smt_codegen.main.Parameters(
                    smt=test_case.submodel_template_path,
                    target=aas_smt_codegen.main.Target.VALUE_ONLY_SCHEMA,
                    snippets_dir=snippets_dir,
                    output_dir=output_dir,
                )

                return_code = aas_smt_codegen.main.execute(
                    params=params, stdout=stdout, stderr=stderr
                )

                assert return_code == 0, (
                    f"Expected the return code 0 "
                    f"on translating {params.submodel_template_path} "
                    f"to {params.target.value} with {snippets_dir=}, "
                    f"but got: {return_code=}\n\n"
                    f"STDOUT:\n{stdout.getvalue()}\n\n"
                    f"STDERR:\n{stderr.getvalue()}"
                )

            else:
                expected_path = case_dir / "expected_output" / "value-only-schema.json"

                if not expected_path.exists() or not expected_path.is_file():
                    raise RuntimeError(
                        f"The golden file for the test case is either missing or "
                        f"is not a file: {expected_path}"
                    )

                expected_text = expected_path.read_text(encoding="utf-8")

                with tempfile.TemporaryDirectory() as tmp_dir:
                    stdout = io.StringIO()
                    stderr = io.StringIO()

                    params = aas_smt_codegen.main.Parameters(
                        smt=test_case.submodel_template_path,
                        target=aas_smt_codegen.main.Target.VALUE_ONLY_SCHEMA,
                        snippets_dir=snippets_dir,
                        output_dir=pathlib.Path(tmp_dir),
                    )

                    return_code = aas_smt_codegen.main.execute(
                        params=params, stdout=stdout, stderr=stderr
                    )

                    assert return_code == 0, (
                        f"Expected the return code 0 "
                        f"on translating {params.submodel_template_path} "
                        f"to {params.target.value} with {snippets_dir=}, "
                        f"but got: {return_code=}\n\n"
                        f"STDOUT:\n{stdout.getvalue()}\n\n"
                        f"STDERR:\n{stderr.getvalue()}"
                    )

                    output_path = output_dir / "value-only-schema.json"

                    if not output_path.exists() or not output_path.is_file():
                        raise AssertionError(
                            f"The output file is either missing "
                            f"or is not a file: {output_path}"
                        )

                    output_text = output_path.read_text(encoding="utf-8")

                    self.assertEqual(
                        expected_text.strip(),
                        output_text.strip(),
                        f"Failed the comparison against the golden file "
                        f"for: {case_dir}",
                    )


if __name__ == "__main__":
    unittest.main()
