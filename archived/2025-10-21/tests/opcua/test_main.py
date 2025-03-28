# pylint: disable=missing-docstring

import contextlib
import io
import pathlib
import tempfile
import unittest

import aas_smt_codegen.ir
import aas_smt_codegen.main

import tests.common


class TestAgainstRecorded(unittest.TestCase):
    def test_cases(self) -> None:
        for test_case in tests.common.over_test_cases():
            case_dir = tests.common.TEST_DATA_DIR / "opcua" / test_case.relative_dir

            snippets_dir = case_dir / "snippets"
            assert snippets_dir.exists() and snippets_dir.is_dir(), snippets_dir

            expected_output_dir = case_dir / "expected_output"

            with contextlib.ExitStack() as exit_stack:
                if tests.common.RERECORD:
                    output_dir = expected_output_dir
                    expected_output_dir.mkdir(exist_ok=True, parents=True)
                else:
                    assert (
                        expected_output_dir.exists() and expected_output_dir.is_dir()
                    ), expected_output_dir

                    # pylint: disable=consider-using-with
                    tmp_dir = tempfile.TemporaryDirectory()
                    exit_stack.push(tmp_dir)
                    output_dir = pathlib.Path(tmp_dir.name)

                params = aas_smt_codegen.main.Parameters(
                    smt=test_case.submodel_template_path,
                    target=aas_smt_codegen.main.Target.OPCUA,
                    snippets_dir=snippets_dir,
                    output_dir=output_dir,
                )

                stdout = io.StringIO()
                stderr = io.StringIO()

                return_code = aas_smt_codegen.main.execute(
                    params=params, stdout=stdout, stderr=stderr
                )

                if test_case.expected:
                    if stderr.getvalue() != "":
                        raise AssertionError(
                            f"Expected no stderr on valid models, but got:\n"
                            f"{stderr.getvalue()}\n"
                            f"for: {test_case.submodel_template_path}"
                        )

                    self.assertEqual(
                        0,
                        return_code,
                        (
                            f"Expected 0 return code on a valid submodel template "
                            f"{test_case.submodel_template_path}"
                        ),
                    )

                    stdout_pth = expected_output_dir / "stdout.txt"
                    normalized_stdout = stdout.getvalue().replace(
                        str(output_dir), "<output dir>"
                    )

                    if tests.common.RERECORD:
                        stdout_pth.write_text(normalized_stdout, encoding="utf-8")
                    else:
                        self.assertEqual(
                            normalized_stdout,
                            stdout_pth.read_text(encoding="utf-8"),
                            stdout_pth,
                        )

                    for relevant_rel_pth in [
                        pathlib.Path("nodeset.xml"),
                    ]:
                        expected_pth = expected_output_dir / relevant_rel_pth
                        output_pth = output_dir / relevant_rel_pth

                        if not output_pth.exists():
                            raise FileNotFoundError(
                                f"The output file is missing: {output_pth}"
                            )

                        if tests.common.RERECORD:
                            expected_pth.write_text(
                                output_pth.read_text(encoding="utf-8"), encoding="utf-8"
                            )
                        else:
                            self.assertEqual(
                                expected_pth.read_text(encoding="utf-8"),
                                output_pth.read_text(encoding="utf-8"),
                                f"The files {expected_pth} and {output_pth} do not match.",
                            )

                else:
                    if stderr.getvalue() == "":
                        raise AssertionError(
                            f"Expected stderr on invalid models, but got empty stderr "
                            f"for: {test_case.submodel_template_path}"
                        )

                    self.assertNotEqual(
                        0,
                        return_code,
                        (
                            f"Expected non-zero return code on "
                            f"an invalid submodel template "
                            f"{test_case.submodel_template_path}"
                        ),
                    )

                    stderr_pth = expected_output_dir / "stderr.txt"
                    normalized_stderr = stderr.getvalue().replace(
                        str(output_dir), "<output dir>"
                    )

                    if tests.common.RERECORD:
                        stderr_pth.write_text(normalized_stderr, encoding="utf-8")
                    else:
                        self.assertEqual(
                            normalized_stderr,
                            stderr_pth.read_text(encoding="utf-8"),
                            stderr_pth,
                        )


if __name__ == "__main__":
    unittest.main()
