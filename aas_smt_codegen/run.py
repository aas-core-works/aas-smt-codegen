"""Encapsulate the entry point to different generators."""

import pathlib
import textwrap
from typing import Sequence, TextIO

from icontract import require

from aas_smt_codegen import ir, specific_implementations, frontend


class Context:
    """Represent the context of a code generation."""

    # fmt: off
    @require(
        lambda submodel_template_path:
        submodel_template_path.exists() and submodel_template_path.is_file()
    )
    @require(lambda output_dir: output_dir.exists() and output_dir.is_dir())
    # fmt: on
    def __init__(
        self,
        submodel_template_path: pathlib.Path,
        spec_impls: specific_implementations.SpecificImplementations,
        aggregational_view: ir.AggregationalView,
        output_dir: pathlib.Path,
    ) -> None:
        """Initialize with the given values."""
        self.submodel_template_path = submodel_template_path
        self.spec_impls = spec_impls
        self.aggregational_view = aggregational_view
        self.output_dir = output_dir

        self._structural_view = frontend.aggregational_to_structural_view(
            aggregational_view=aggregational_view
        )

    @property
    def structural_view(self) -> ir.StructuralView:
        """Provide the structural view based on the aggregational view."""
        return self._structural_view


@require(
    lambda errors: all(
        len(error) > 0 and not error.startswith("\n")
        # This is necessary so that we do not have double bullet point.
        and not error.startswith("*") and not error.endswith("\n")
        for error in errors
    )
)
@require(lambda message: not message.endswith(":"))
@require(lambda message: not message.endswith("\n"))
@require(lambda message: not message.startswith("\n") and not message.startswith("*"))
# fmt: on
def write_error_report(message: str, errors: Sequence[str], stderr: TextIO) -> None:
    """
    Write the report (main ``message`` and details as ``errors``) to ``stderr``.

    This method helps us to have a unified way of showing errors.
    """
    stderr.write(f"{message}:\n")
    for error in errors:
        indented = textwrap.indent(error, "  ")
        indented = "* " + indented[2:]
        stderr.write(f"{indented}\n")
