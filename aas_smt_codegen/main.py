"""Transpile AAS Submodel Templates."""

import argparse
import enum
import pathlib
import sys
from typing import TextIO

from typing_extensions import assert_never

import aas_smt_codegen
from aas_smt_codegen import (
    frontend,
    run,
    specific_implementations,
)
from aas_smt_codegen.value_only_schema import main as value_only_schema_main

assert aas_smt_codegen.__doc__ == __doc__


class Target(enum.Enum):
    """List available target implementations."""

    VALUE_ONLY_SCHEMA = "value-only-schema"


class Parameters:
    """Represent the program parameters."""

    def __init__(
        self,
        smt: pathlib.Path,
        target: Target,
        snippets_dir: pathlib.Path,
        output_dir: pathlib.Path,
    ) -> None:
        """Initialize with the given values."""
        self.submodel_template_path = smt
        self.target = target
        self.snippets_dir = snippets_dir
        self.output_dir = output_dir


# noinspection SpellCheckingInspection
def execute(params: Parameters, stdout: TextIO, stderr: TextIO) -> int:
    """Run the program."""
    # region Basic checks
    if not params.submodel_template_path.exists():
        stderr.write(f"The --smt does not exist: {params.submodel_template_path}\n")
        return 1

    if not params.submodel_template_path.is_file():
        stderr.write(
            f"The --smt does not point to a file: {params.submodel_template_path}\n"
        )
        return 1

    if not params.snippets_dir.exists():
        stderr.write(f"The --snippets_dir does not exist: {params.snippets_dir}\n")
        return 1

    if not params.snippets_dir.is_dir():
        stderr.write(
            f"The --snippets_dir does not point to a directory: "
            f"{params.snippets_dir}\n"
        )
        return 1

    if not params.output_dir.exists():
        params.output_dir.mkdir(parents=True, exist_ok=True)
    else:
        if not params.output_dir.is_dir():
            stderr.write(
                f"The --output_dir does not point to a directory: "
                f"{params.output_dir}\n"
            )
            return 1

    # endregion

    # region Front end

    spec_impls, spec_impls_errors = specific_implementations.read_from_directory(
        snippets_dir=params.snippets_dir
    )

    if spec_impls_errors:
        run.write_error_report(
            message="Failed to resolve the implementation-specific snippets",
            errors=spec_impls_errors,
            stderr=stderr,
        )
        return 1

    assert spec_impls is not None

    try:
        text = params.submodel_template_path.read_text(encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to read --smt {params.submodel_template_path}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    environment, deserialize_error = frontend.deserialize_environment(text)
    if deserialize_error is not None:
        run.write_error_report(
            message=f"Failed to de-serialize --smt {params.submodel_template_path}",
            errors=[deserialize_error],
            stderr=stderr,
        )
        return 1

    assert environment is not None

    aggregational_view, parse_errors = frontend.parse_aggregational_view(
        submodels=list(environment.over_submodels_or_empty())
    )

    if parse_errors is not None:
        run.write_error_report(
            message=(
                f"Failed to parse aggregational view "
                f"from --smt {params.submodel_template_path}"
            ),
            errors=[str(error) for error in parse_errors],
            stderr=stderr,
        )
        return 1

    assert aggregational_view is not None

    # endregion

    # region Dispatch

    run_context = run.Context(
        submodel_template_path=params.submodel_template_path,
        spec_impls=spec_impls,
        aggregational_view=aggregational_view,
        output_dir=params.output_dir,
    )

    if params.target is Target.VALUE_ONLY_SCHEMA:
        return value_only_schema_main.execute(
            context=run_context, stdout=stdout, stderr=stderr
        )

    else:
        assert_never(params.target)

    # endregion


def main(prog: str) -> int:
    """
    Execute the main routine.

    :param prog: name of the program to be displayed in the help
    :return: exit code
    """
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument(
        "--smt", help="Path to the AAS submodel template", required=True
    )
    parser.add_argument(
        "--snippets_dir",
        help="path to the directory containing implementation-specific code snippets",
        required=True,
    )
    parser.add_argument(
        "--output_dir", help="path to the generated code", required=True
    )
    parser.add_argument(
        "--target",
        help="target language or schema",
        required=True,
        choices=[literal.value for literal in Target],
    )
    parser.add_argument(
        "--version", help="show the current version and exit", action="store_true"
    )

    # NOTE (mristin):
    # The module ``argparse`` is not flexible enough to understand special options such
    # as ``--version`` so we manually hard-wire.
    if "--version" in sys.argv and "--help" not in sys.argv:
        print(aas_smt_codegen.__version__)
        return 0

    args = parser.parse_args()

    target_to_str = {literal.value: literal for literal in Target}

    params = Parameters(
        smt=pathlib.Path(args.smt),
        target=target_to_str[args.target],
        snippets_dir=pathlib.Path(args.snippets_dir),
        output_dir=pathlib.Path(args.output_dir),
    )

    return execute(params=params, stdout=sys.stdout, stderr=sys.stderr)


def entry_point() -> int:
    """Provide an entry point for a console script."""
    return main(prog="aas-smt-codegen")


if __name__ == "__main__":
    sys.exit(main(prog="aas-smt-codegen"))
