***************
aas-smt-codegen
***************

.. image:: https://github.com/aas-core-works/aas-smt-codegen/actions/workflows/ci.yml/badge.svg
    :target: https://github.com/aas-core-works/aas-smt-codegen/actions/workflows/ci.yml
    :alt: Continuous integration

.. image:: https://coveralls.io/repos/github/aas-core-works/aas-smt-codegen/badge.svg?branch=main
    :target: https://coveralls.io/github/aas-core-works/aas-smt-codegen?branch=main
    :alt: Test coverage

aas-smt-codegen:

* ... generates code for different schemas and programming environments
* ... to handle AAS Submodel Templates
* ... based on the AAS Submodel Template definition given as AAS environment.

Motivation
==========
TODO

Therefore we can easily scale to many languages and schemas.

Here is a diagram to illustrate the whole process:

..
    digraph G {
        node [shape=rect]

        details [label="Details of Asset Administration Shell (the book)"];
        metamodel [label="Meta-model in a subset of Python\n\n* Data types\n* Constraints\n* Markers"];

        subgraph cluster_1 {
            label="aas-smt-codegen"
            color=blue
            labelloc="t"
            labeljust="r"

            parser [label="Parser"];
            intermediate [label="Intermediate representation\n(Meta-model-specific, but language agnostic)"];

            csharpgen [label="C\# generator"];
            javagen [label="Java generator"];

            dot [label="..."];
        }

        csharpcode [label="C\# code"];
        javacode [label="Java code"];

        details -> metamodel;
        metamodel -> parser;
        parser -> intermediate;
        intermediate -> csharpgen;
        intermediate -> javagen;
        intermediate -> dot;
        csharpgen -> csharpcode;
        javagen -> javacode;
    }

.. image:: https://raw.githubusercontent.com/aas-core-works/aas-smt-codegen/main/diagram.svg

Installation
============
Create a virtual environment:

.. code-block::

    python -m venv venv-aas-smt-codegen

Activate it (in Windows):

.. code-block::

    venv-venv-aas-smt-codegen\Scripts\activate

or in Linux and OS X:

.. code-block::

    source venv-aas-smt-codegen/bin/activate

Install the tool in the virtual environment from the GitHub:

.. code-block::

    pip3 install git+https://github.com/aas-core-works/aas-smt-codegen.git

The development is still very fast, so we decided to wait till it slows down for proper release cycles.

Usage
-----
Download a submodel template from https://industrialdigitaltwin.org/en/content-hub/submodels or write your own and serialize it either as a JSON or XML file.

Make sure you are within the virtual environment where you installed the generator.

Write all the necessary implementation-specific snippets to a directory.
For example, in case of JSON schema for value-only representation, this includes the base JSON schema, mapping of identifier to JSON references for external structures as well as mapping of identifiers to JSON names for local structures (see `test_data/value_only_schema/*/snippets`_ for concrete examples).

.. _test_data/value_only_schema/*/snippets: https://github.com/aas-core-works/aas-smt-codegen/blob/main/test_data/value_only_schema

Call the generator with the appropriate target:

.. code-block::

    aas-smt-codegen \
        --smt path/to/submodel-template.json \
        --snippets_dir path/to/snippets \
        --output_dir path/to/output \
        --target value_only_schema


``--help``
==========

.. Help starts: aas-smt-codegen --help
.. code-block::

    usage: aas-smt-codegen [-h] --smt SMT --snippets_dir SNIPPETS_DIR --output_dir
                           OUTPUT_DIR --target {value-only-schema} [--version]

    Transpile AAS Submodel Templates.

    options:
      -h, --help            show this help message and exit
      --smt SMT             Path to the AAS submodel template
      --snippets_dir SNIPPETS_DIR
                            path to the directory containing implementation-
                            specific code snippets
      --output_dir OUTPUT_DIR
                            path to the generated code
      --target {value-only-schema}
                            target language or schema
      --version             show the current version and exit

.. Help ends: aas-smt-codegen --help

Versioning
==========
We are still not clear about how to version the generator.
At the moment, since we are still in a fast development phase, we simply rely on Git commit revisions.


Contributing
============

Feature requests or bug reports are always very, very welcome!

Please see quickly if the issue does not already exist in the `issue section`_ and, if not, create `a new issue`_.

.. _issue section: https://github.com/aas-core-works/aas-smt-codegen/issues
.. _a new issue: https://github.com/aas-core-works/aas-smt-codegen/issues/new

Contributions in code are also welcome!
Please see `CONTRIBUTING.rst`_ for developing guidelines.

.. _CONTRIBUTING.rst: https://github.com/aas-core-works/aas-smt-codegen/blob/main/CONTRIBUTING.rst

