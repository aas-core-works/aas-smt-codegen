"""
Parse existing OPC UA nodesets.

This is necessary so that we can import models and use them in our generated nodeset.
"""

import contextlib
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from typing import (
    Sequence,
    Final,
    Mapping,
    Optional,
    Tuple,
    List,
    Iterator,
    FrozenSet,
)

from icontract import require, ensure, snapshot

from aas_smt_codegen import specific_implementations
from aas_smt_codegen.common import (
    bullet_points,
    indent_but_first_line,
    Identifier,
    IDENTIFIER_RE,
)

I = "  "
II = I * 2


class RequiredModel:
    """Represent a model import in an OPC UA model."""

    uri: Final[str]
    version: Final[str]

    def __init__(self, uri: str, version: str) -> None:
        self.uri = uri
        self.version = version

    def __str__(self) -> str:
        return f"""\
{self.__class__.__name__}(
{I}uri={json.dumps(self.uri)},
{I}version={json.dumps(self.version)}
)"""


class Model:
    """Represent an OPC UA model."""

    uri: Final[str]
    version: Final[str]

    required_models: Final[Sequence[RequiredModel]]

    def __init__(
        self, uri: str, version: str, required_models: Sequence[RequiredModel]
    ) -> None:
        self.uri = uri
        self.version = version
        self.required_models = required_models

    def __str__(self) -> str:
        if len(self.required_models) == 0:
            required_models_str = "[]"
        else:
            required_joined = ",\n".join(
                str(required_model) for required_model in self.required_models
            )
            required_models_str = f"""\
[
{I}{indent_but_first_line(required_joined)}
]"""

        return f"""\
{self.__class__.__name__}(
{I}uri={json.dumps(self.uri)},
{I}version={json.dumps(self.version)},
{I}required_models={indent_but_first_line(required_models_str)}
)"""


class Component:
    """Represent a component of an OPC UA object type."""

    identifier: int

    #: Referenced namespace; empty means default (built-in) namespace.
    namespace: str

    def __init__(self, identifier: int, namespace: str) -> None:
        self.identifier = identifier
        self.namespace = namespace

    def __str__(self) -> str:
        return f"""\
{self.__class__.__name__}(
{I}identifier={self.identifier},
{I}namespace={json.dumps(self.namespace)}
)"""


class Property:
    """Represent a property of an OPC UA object type."""

    identifier: int

    #: Referenced namespace; empty means default (built-in) namespace.
    namespace: str

    def __init__(self, identifier: int, namespace: str) -> None:
        self.identifier = identifier
        self.namespace = namespace

    def __str__(self) -> str:
        return f"""\
{self.__class__.__name__}(
{I}identifier={self.identifier},
{I}namespace={json.dumps(self.namespace)}
)"""


class ObjectType:
    """Represent a definition of an object type in an OPC UA nodeset."""

    identifier: int
    browse_name: Final[Identifier]
    namespace: Final[str]
    components: Final[Sequence[Component]]
    properties: Final[Sequence[Property]]

    def __init__(
        self,
        identifier: int,
        browse_name: Identifier,
        namespace: str,
        components: Sequence[Component],
        properties: Sequence[Property],
    ) -> None:
        self.identifier = identifier
        self.browse_name = browse_name
        self.namespace = namespace
        self.components = components
        self.properties = properties

    def __str__(self) -> str:
        if len(self.components) == 0:
            components_str = "[]"
        else:
            components_joined = ",\n".join(
                str(component) for component in self.components
            )
            components_str = f"""\
[
{I}{indent_but_first_line(components_joined)}
]"""

        if len(self.properties) == 0:
            properties_str = "[]"
        else:
            properties_joined = ",\n".join(str(prop) for prop in self.properties)
            properties_str = f"""\
[
{I}{indent_but_first_line(properties_joined)}
]"""

        return f"""\
{self.__class__.__name__}(
{I}identifier={self.identifier},
{I}browse_name={json.dumps(self.browse_name)},
{I}namespace={json.dumps(self.namespace)},
{I}components={indent_but_first_line(components_str)},
{I}properties={indent_but_first_line(properties_str)}
)"""


class Nodeset:
    """Represent an OPC UA nodeset."""

    #: Key in the implementation-specific snippets
    implementation_key: Final[specific_implementations.ImplementationKey]

    namespaces: Final[Sequence[str]]
    namespace_to_index: Final[Mapping[str, int]]

    models: Final[Sequence[Model]]
    model_by_uri: Final[Mapping[str, Model]]

    object_types: Final[Sequence[ObjectType]]
    object_type_by_browse_name: Final[Mapping[str, ObjectType]]

    #: Set of all URIs over all the required models of all the models
    all_required_model_uri_set: Final[FrozenSet[str]]

    @require(
        lambda namespaces: len(set(namespaces)) == len(namespaces),
        "No duplicates in the namespaces",
    )
    @ensure(
        lambda self: all(an_index > 0 for an_index in self.namespace_to_index.values()),
        "Namespace indices start with 1",
    )
    def __init__(
        self,
        implementation_key: specific_implementations.ImplementationKey,
        namespaces: Sequence[str],
        models: Sequence[Model],
        object_types: Sequence[ObjectType],
    ) -> None:
        self.implementation_key = implementation_key

        self.namespaces = namespaces
        self.namespace_to_index = {
            namespace: i + 1 for i, namespace in enumerate(namespaces)
        }

        self.models = models
        self.model_by_uri = {model.uri: model for model in models}

        self.object_types = object_types
        self.object_type_by_browse_name = {
            object_type.browse_name: object_type for object_type in object_types
        }

        self.all_required_model_uri_set = frozenset(
            required_model.uri
            for model in self.models
            for required_model in model.required_models
        )

    def __str__(self) -> str:
        if len(self.models) == 0:
            models_str = "[]"
        else:
            models_joined = ",\n".join(str(model) for model in self.models)
            models_str = f"""\
[
{I}{indent_but_first_line(models_joined)}
]"""

        if len(self.object_types) == 0:
            object_types_str = "[]"
        else:
            object_types_joined = ",\n".join(
                str(object_type) for object_type in self.object_types
            )
            object_types_str = f"""\
[
{I}{indent_but_first_line(object_types_joined)}
]"""

        return f"""\
{self.__class__.__name__}(
{I}implementation_key={indent_but_first_line(self.implementation_key, I)},
{I}namespaces={json.dumps(self.namespaces)},
{I}models={indent_but_first_line(models_str)},
{I}object_types={indent_but_first_line(object_types_str, I)}
)"""


def _ordinal(number: int) -> str:
    """Generate the readable ordinal for the given integer."""
    if (number % 10) == 1:
        return "1st"
    elif (number % 10) == 2:
        return "2nd"
    elif (number % 10) == 3:
        return "3rd"
    else:
        return f"{number}th"


@require(lambda tag: "}" not in tag)
def _over_all_regardless_of_namespace(
    node: ET.Element, tag: str
) -> Iterator[ET.Element]:
    suffix = f"}}{tag}"
    for child in node:
        if not (child.tag == tag or child.tag.endswith(suffix)):
            continue

        yield child


# fmt: off
@require(
    lambda element:
    element.tag == "RequiredModel" or element.tag.endswith("}RequiredModel")
)
@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _required_model_from_element(
    element: ET.Element,
) -> Tuple[Optional[RequiredModel], Optional[List[str]]]:
    """
    Parse the ``<RequiredModel>.

    Return the parsed required model, or an error, if any.
    """
    errors = []  # type: List[str]

    uri = element.attrib.get("ModelUri", "").strip()

    if len(uri) == 0:
        errors.append("The ModelUri is not specified.")

    version = element.attrib.get("Version", "").strip()

    if len(version) == 0:
        errors.append("The Version is not specified")

    if len(errors) > 0:
        return None, errors

    return RequiredModel(uri=uri, version=version), None


# fmt: off
@require(
    lambda element:
    element.tag == "Model" or element.tag.endswith("}Model")
)
@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _model_from_element(
    element: ET.Element,
) -> Tuple[Optional[Model], Optional[List[str]]]:
    """
    Parse the ``<Model>``.

    Return the parsed model, or an error, if any.
    """
    errors = []  # type: List[str]

    uri = element.attrib.get("ModelUri", "").strip()
    if len(uri) == 0:
        errors.append("The ModelUri is not specified.")

    version = element.attrib.get("Version", "").strip()
    if len(version) == 0:
        errors.append("The Version is not specified")

    required_models = []  # type: List[RequiredModel]

    for required_model_el_i, required_model_el in enumerate(
        _over_all_regardless_of_namespace(element, "RequiredModel")
    ):
        required_model, required_model_errors = _required_model_from_element(
            required_model_el
        )

        if required_model_errors is not None:
            required_model_uri = required_model_el.attrib.get("ModelUri", "").strip()

            required_model_el_designation = (
                f"{_ordinal(required_model_el_i)}th <RequiredModel>"
                if len(required_model_uri) == 0
                else f"<RequiredModel> with ModelUri {required_model_uri}"
            )

            errors.append(
                f"Failed to parse {required_model_el_designation}:\n"
                f"{bullet_points(errors)}"
            )
            continue

        assert required_model is not None

        required_models.append(required_model)

    if len(errors) > 0:
        return None, errors

    return Model(uri=uri, version=version, required_models=required_models), None


class _Reference:
    """Represent a reference in an OPC UA model."""

    reference_type: Final[str]
    is_forward: Final[bool]
    target: Final[str]

    def __init__(self, reference_type: str, is_forward: bool, target: str) -> None:
        self.reference_type = reference_type
        self.is_forward = is_forward
        self.target = target


# fmt: off
@require(
    lambda element:
    element.tag == "Reference"
    or element.tag.endswith("}Reference")
)
@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _reference_from_element(
    element: ET.Element,
) -> Tuple[Optional[_Reference], Optional[List[str]]]:
    """
    Parse a reference from the nodeset element.

    Return the parsed reference, or an error, if any.
    """
    errors = []  # type: List[str]

    reference_type = element.attrib.get("ReferenceType", "").strip()
    if len(reference_type) == 0:
        errors.append("The ReferenceType is not specified.")

    is_forward = None  # type: Optional[bool]

    is_forward_str = element.attrib.get("IsForward", "").strip().lower()
    if is_forward_str in ("true", "1"):
        is_forward = True
    elif is_forward_str in ("false", "0", ""):
        is_forward = False
    else:
        errors.append(
            f"The IsForward attribute can not be parsed as a boolean: {is_forward_str!r}"
        )

    target = element.text.strip() if element.text is not None else ""
    if len(target) == 0:
        errors.append("The target (element text) is not specified.")

    if len(errors) > 0:
        return None, errors

    assert is_forward is not None

    return (
        _Reference(reference_type=reference_type, is_forward=is_forward, target=target),
        None,
    )


# fmt: off
@require(
    lambda element:
    element.tag == "UAObjectType" or element.tag.endswith("}UAObjectType")
)
@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
# fmt: on
def _object_type_from_element(
    element: ET.Element, namespaces: Sequence[str]
) -> Tuple[Optional[ObjectType], Optional[List[str]]]:
    """
    Parse the ``<UAObjectType>``.

    Return the parsed object type, or an error, if any.
    """
    errors = []  # type: List[str]

    ns_i = None  # type: Optional[int]
    namespace = None  # type: Optional[str]
    identifier = None  # type: Optional[int]

    node_id = element.attrib.get("NodeId", "").strip()
    if len(node_id) == 0:
        errors.append("The NodeId is not specified.")
    else:
        match = re.match(r"^ns=(?P<ns_i>[0-9]+);i=(?P<identifier>[0-9]+)$", node_id)
        if match is None:
            errors.append(f"The NodeId could not be parsed: {node_id}")
        else:
            ns_i = int(match.group("ns_i"))

            if ns_i > len(namespaces) or ns_i < 1:
                errors.append(
                    f"The namespace index of the node ID points "
                    f"to an unknown namespace: {node_id}"
                )
            else:
                namespace = namespaces[ns_i - 1]
                identifier = int(match.group("identifier"))

    browse_name = element.attrib.get("BrowseName", None)
    if browse_name is not None:
        browse_name = browse_name.strip()

        if len(browse_name) == 0:
            browse_name = None

    if browse_name is None:
        errors.append("The BrowseName is not specified.")
    else:
        if ":" in browse_name:
            match = re.match(r"^(?P<ns_i>[0-9]+):(?P<browse_name>.+)$", browse_name)

            if match is None:
                errors.append(f"The BrowseName could not be parse: {browse_name!r}")
            else:
                got_ns_i = int(match.group("ns_i"))
                browse_name = match.group("browse_name")

                # NOTE (mristin):
                # We check here that ns_i could be properly parsed before since
                # we can not report the error otherwise.
                if ns_i is not None and got_ns_i != ns_i:
                    errors.append(
                        f"The namespace index of BrowseName does not match "
                        f"the expected namespace index {ns_i} "
                        f"as extracted from NodeId {node_id!r}: {browse_name!r}"
                    )
                    browse_name = None

    if browse_name is not None and IDENTIFIER_RE.match(browse_name) is None:
        errors.append(
            f"The BrowseName is expected to be a variable identifier "
            f"matching {IDENTIFIER_RE.pattern}, but it was not: {browse_name!r}"
        )
        browse_name = None

    components = []  # type: List[Component]
    properties = []  # type: List[Property]

    for references_el in _over_all_regardless_of_namespace(element, "References"):
        for reference_el in _over_all_regardless_of_namespace(
            references_el, "Reference"
        ):
            reference, reference_errors = _reference_from_element(reference_el)

            if reference_errors is not None:
                errors.append(
                    f"Failed to parse a reference:\n"
                    f"{bullet_points(reference_errors)}"
                )
                continue

            assert reference is not None

            if reference.reference_type in ("HasComponent", "HasProperty"):
                match = re.match(r"^i=(?P<identifier>[0-9]+)$", reference.target)
                if match is not None:
                    components.append(
                        Component(
                            identifier=int(match.group("identifier")), namespace=""
                        )
                    )

                match = re.match(
                    r"^ns=(?P<ns_i>[0-9]+);i=(?P<identifier>[0-9]+)$", reference.target
                )
                if match is not None:
                    target_ns_i = int(match.group("ns_i"))
                    target_identifier = int(match.group("identifier"))

                    if target_ns_i < 1 or target_ns_i > len(namespaces):
                        errors.append(
                            f"The target of a Has-Component reference points to "
                            f"an invalid namespace index: {target_ns_i!r}"
                        )
                    else:
                        if reference.reference_type == "HasComponent":
                            components.append(
                                Component(
                                    identifier=target_identifier,
                                    namespace=namespaces[target_ns_i - 1],
                                )
                            )
                        elif reference.reference_type == "HasProperty":
                            properties.append(
                                Property(
                                    identifier=target_identifier,
                                    namespace=namespaces[target_ns_i - 1],
                                )
                            )
                        else:
                            raise NotImplementedError(
                                f"Unhandled reference type: "
                                f"{reference.reference_type!r}"
                            )

                else:
                    errors.append(
                        f"We do not know how to parse the target of "
                        f"a Has-Component reference: {reference.target!r}"
                    )

    if len(errors) > 0:
        return None, errors

    assert identifier is not None
    assert namespace is not None
    assert browse_name is not None

    return (
        ObjectType(
            identifier=identifier,
            namespace=namespace,
            browse_name=Identifier(browse_name),
            components=components,
            properties=properties,
        ),
        None,
    )


def _parse_nodeset(
    root: ET.Element,
    implementation_key: specific_implementations.ImplementationKey,
) -> Tuple[Optional[Nodeset], Optional[List[str]]]:
    """
    Parse the given nodeset from XML.

    Return the parsed nodeset, or error if any.
    """
    namespaces = []  # type: List[str]

    for namespace_uris_el in _over_all_regardless_of_namespace(root, "NamespaceUris"):
        for uri_el in _over_all_regardless_of_namespace(namespace_uris_el, "Uri"):
            uri = uri_el.text.strip() if uri_el.text is not None else ""

            if len(uri) == 0:
                # NOTE (mristin):
                # Namespaces are critical, so we have to abort if one or more namespace
                # definitions are invalid.
                return None, [
                    "There is one or more empty <Uri> elements in an <NamespaceUris>."
                ]

            namespaces.append(uri)

    errors = []  # type: List[str]

    models = []  # type: List[Model]

    for models_el in _over_all_regardless_of_namespace(root, "Models"):
        for model_el_i, model_el in enumerate(
            _over_all_regardless_of_namespace(models_el, "Model")
        ):
            model, model_errors = _model_from_element(model_el)

            if model_errors is not None:
                model_uri = model_el.attrib.get("ModelUri", "").strip()
                model_el_designation = (
                    f"{_ordinal(model_el_i)}th <Model>"
                    if len(model_uri) == 0
                    else f"<Model> with ModelUri {model_uri}"
                )

                errors.append(
                    f"Failed to parse {model_el_designation}:\n"
                    f"{bullet_points(model_errors)}"
                )
                continue

            assert model is not None

            models.append(model)

    object_types = []  # type: List[ObjectType]

    for object_type_el_i, object_type_el in enumerate(
        _over_all_regardless_of_namespace(root, "UAObjectType")
    ):
        object_type, object_type_errors = _object_type_from_element(
            object_type_el, namespaces=namespaces
        )

        if object_type_errors is not None:
            node_id = object_type_el.attrib.get("NodeId", "").strip()
            object_type_el_designation = (
                f"{_ordinal(object_type_el_i)}th <UAObjectType>"
                if len(node_id) == 0
                else f"<UAObjectType> with NodeId {node_id}"
            )

            errors.append(
                f"Failed to parse {object_type_el_designation}:\n"
                f"{bullet_points(object_type_errors)}"
            )
            continue

        assert object_type is not None

        object_types.append(object_type)

    if len(errors) > 0:
        return None, errors

    return (
        Nodeset(
            implementation_key=implementation_key,
            namespaces=namespaces,
            models=models,
            object_types=object_types,
        ),
        None,
    )


_BASE_NODESET_KEY = specific_implementations.ImplementationKey(
    "base_nodeset.xml"
)  # type: Final[specific_implementations.ImplementationKey]


class _RecursiveParser:
    #: Errors which occurred during the parsing
    errors: List[str]

    #: The text of the XML document corresponding to the first parsed model
    first_nodeset_text: Optional[str]

    #: The XML document corresponding to the first parsed model
    first_nodeset_el: Optional[ET.Element]

    #: The parsed nodesets; the first element corresponds to the base OPC UA nodeset
    nodesets: List[Nodeset]

    _spec_impls: Final[specific_implementations.SpecificImplementations]

    #: Chain of model keys to the model that we are currently parsing.
    _path: List[str]

    def __init__(
        self, spec_impls: specific_implementations.SpecificImplementations
    ) -> None:
        self._spec_impls = spec_impls

        self.errors = []  # type: List[str]

        #: Chain of model keys to the model that we are currently parsing.
        self._path = []  # type: List[str]

        self.first_nodeset_text = None
        self.first_nodeset_el = None

        self.nodesets = []

    def _path_as_str(self) -> str:
        """Represent the import chain to the model which we currently parse."""
        return " 🠒 ".join(self._path)

    # fmt: off
    @require(
        lambda expected_model_uri, expected_version:
        (expected_model_uri is None) == (expected_model_uri is None),
        "Either both expected model URI and version are none, or both are set",
    )
    @ensure(
        lambda self:
        not (len(self.errors) == 0)
        or (self.first_nodeset_text is not None and self.first_nodeset_el is not None),
        "If there are no errors, the properties corresponding to the first nodeset "
        "are set after the very first parsing.",
    )
    @snapshot(lambda self: self.nodesets[:], "nodesets")
    @ensure(
        lambda self, OLD:
        not (len(self.errors) == 0)
        or (
            len(self.nodesets) > len(OLD.nodesets)
            and OLD.nodesets == self.nodesets[: len(OLD.nodesets)]
        ),
        "At least one nodeset added to the nodesets if no errors.",
    )
    # fmt: on
    def parse(
        self,
        implementation_key: specific_implementations.ImplementationKey,
        expected_model_uri: Optional[str] = None,
        expected_version: Optional[str] = None,
    ) -> None:
        """
        Retrieve the model as an implementation-specific snippet and parse it.

        We parse recursively, *i.e.*, we collect namespaces which are used for
        object types, components and properties, and parse those which correspond
        to required models.

        The implementation key defines *which* implementation-specific snippet to
        retrieve. The expected model URI and version indicate that the nodeset
        is imported due to a ``<RequiredModel>`` in the previous nodeset of
        the recursion chain. Since we can only know the exact provided model URI and
        version *after* parsing the nodeset, we have to check for them at the end
        instead of the time point of the import (*i.e.*, before the parsing).

        :py:prop:`.errors` contains any errors which occurred during the recursion.

        Return the parsed nodeset, or nothing if there were errors.
        """
        self._path.append(implementation_key)
        with contextlib.ExitStack() as exit_stack:
            exit_stack.callback(lambda: self._path.pop())

            text = self._spec_impls.get(implementation_key, None)
            if text is None:
                self.errors.append(
                    f"The implementation snippet for the nodeset "
                    f"of the OPC UA model"
                    f"is missing: {implementation_key}\n"
                    f"The chain of import was: {self._path_as_str()}"
                )
                return

            if self.first_nodeset_text is None:
                self.first_nodeset_text = text

            try:
                nodeset_el = ET.fromstring(text)
            except Exception as err:
                self.errors.append(
                    f"Failed to parse the OPC UA nodeset "
                    f"from the implementation-specific snippet {implementation_key}: {err}\n"
                    f"The chain of import was: {self._path_as_str()}"
                )
                return

            if self.first_nodeset_el is None:
                self.first_nodeset_el = nodeset_el

            nodeset, nodeset_errors = _parse_nodeset(
                root=nodeset_el, implementation_key=implementation_key
            )
            if nodeset_errors is not None:
                self.errors.append(
                    f"Failed to parse the OPC UA nodeset "
                    f"from the implementation-specific snippet {implementation_key}:\n"
                    f"{bullet_points(nodeset_errors)}\n"
                    f"The chain of import was: {self._path_as_str()}"
                )
                return

            assert nodeset is not None

            if (
                expected_model_uri is not None
                and expected_version is not None
                and not any(
                    model.uri == expected_model_uri
                    and model.version == expected_version
                    for model in nodeset.models
                )
            ):
                self.errors.append(
                    "Expected the nodeset from the implementation-specific snippet "
                    f"{implementation_key} to have a model "
                    f"with URI {expected_model_uri!r} and version {expected_version!r}, "
                    f"but none could be found in its <Models>."
                )
                return

            self.nodesets.append(nodeset)

            for required_model in [
                required_model
                for model in nodeset.models
                for required_model in model.required_models
                # NOTE (mristin):
                # We ignore the model for the default OPC UA namespace.
                if required_model.uri
                not in ("http://opcfoundation.org/UA/", "http://opcfoundation.org/UA")
            ]:
                model_uri = required_model.uri
                namespace_escaped = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", model_uri)

                if namespace_escaped == model_uri:
                    implementation_key = specific_implementations.ImplementationKey(
                        f"external_models/{namespace_escaped}"
                    )
                else:
                    namespace_hash = hashlib.sha1(model_uri.encode()).hexdigest()[:8]

                    implementation_key = specific_implementations.ImplementationKey(
                        f"external_models/{namespace_escaped}_{namespace_hash}"
                    )

                self.parse(
                    implementation_key=implementation_key,
                    expected_model_uri=required_model.uri,
                    expected_version=required_model.version,
                )


class Parsing:
    """Represent the final result of a parsing of OPC UA models."""

    base_nodeset: Final[Nodeset]
    nodesets: Sequence[Nodeset]
    base_nodeset_el: Final[ET.Element]
    base_nodeset_text: Final[str]
    base_nodeset_key: Final[str]

    # fmt: off
    @require(
        lambda base_nodeset, nodesets:
        len(nodesets) >= 1 and base_nodeset is nodesets[0]
    )
    # fmt: on
    def __init__(
        self,
        base_nodeset: Nodeset,
        nodesets: Sequence[Nodeset],
        base_nodeset_el: ET.Element,
        base_nodeset_text: str,
        base_nodeset_key: str,
    ) -> None:
        self.base_nodeset = base_nodeset
        self.nodesets = nodesets
        self.base_nodeset_el = base_nodeset_el
        self.base_nodeset_text = base_nodeset_text
        self.base_nodeset_key = base_nodeset_key


def parse(
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[Parsing], Optional[str]]:
    """
    Parse all the OPC UA nodesets given in the implementation-specific snippets.

    We start from the base nodeset indicated by the :py:data:`BASE_NODESET_KEY`, and
    proceed recursively. Only the models which are used by the object types, their
    components and properties are considered.
    """
    parser = _RecursiveParser(spec_impls=spec_impls)
    parser.parse(implementation_key=_BASE_NODESET_KEY)

    if len(parser.errors) > 0:
        return None, (
            "Failed to parse the OPC UA nodesets "
            "from the implementation-specific snippets:\n"
            f"{bullet_points(parser.errors)}"
        )

    assert parser.first_nodeset_el is not None
    assert parser.first_nodeset_text is not None

    return (
        Parsing(
            base_nodeset=parser.nodesets[0],
            nodesets=parser.nodesets,
            base_nodeset_el=parser.first_nodeset_el,
            base_nodeset_text=parser.first_nodeset_text,
            base_nodeset_key=_BASE_NODESET_KEY,
        ),
        None,
    )


def dump_nodesets(nodesets: Sequence[Nodeset]) -> str:
    """Produce a string representation of a list of nodesets."""
    nodesets_joined = ",\n".join(str(nodeset) for nodeset in nodesets)

    return f"""\
[
{I}{indent_but_first_line(nodesets_joined, I)}
]"""
