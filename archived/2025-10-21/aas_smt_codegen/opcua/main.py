"""Generate the OPC-UA nodeset based on the template."""

import collections
import copy
import csv
import enum
import inspect
import io
import itertools
import re
import xml.dom.minidom

# noinspection PyPep8Naming
import xml.etree.ElementTree as ET
import xml.sax.saxutils
from typing import (
    Mapping,
    OrderedDict,
    Sequence,
    TextIO,
    Tuple,
    Optional,
    List,
    MutableMapping,
    Union,
    Final,
    Set,
    FrozenSet,
)

import aas_core3.jsonization as aas_jsonization
import aas_core3.types as aas_types
from icontract import ensure, require
from typing_extensions import assert_never

from aas_smt_codegen import ir, specific_implementations, run
from aas_smt_codegen.common import (
    try_in_english,
    Identifier,
    IDENTIFIER_RE,
    bullet_points,
)
from aas_smt_codegen.opcua import parse as opcua_parse


class _XmlNamespaceDeclarations:
    #: URL of the main namespace
    main: str

    #: URL to namespace alias
    url_to_alias: Mapping[str, str]

    #: Namespace alias to URL
    alias_to_url: OrderedDict[str, str]

    # fmt: off
    @require(
        lambda url_to_alias, alias_to_url:
        all(
            alias_to_url[alias] == url
            for url, alias in url_to_alias.items()
        )
    )
    @require(
        lambda url_to_alias, alias_to_url:
        all(
            url_to_alias[url] == alias
            for alias, url in alias_to_url.items()
        )
    )
    # fmt: on
    def __init__(
        self,
        main: str,
        url_to_alias: Mapping[str, str],
        alias_to_url: OrderedDict[str, str],
    ) -> None:
        """Initialize with the given values."""
        self.main = main
        self.url_to_alias = url_to_alias
        self.alias_to_url = alias_to_url


def _extract_xml_namespace_declarations_from_xml(
    text: str,
) -> Tuple[Optional[_XmlNamespaceDeclarations], Optional[str]]:
    """
    Extract the XML namespace declarations from the given XML document.

    These XML namespace declarations are not to be confused with OPC UA namespaces!

    Return the parsed declarations, or error, if any.
    """
    minidom_doc = xml.dom.minidom.parseString(text)

    main = None  # type: Optional[str]
    url_to_alias = dict()  # type: MutableMapping[str, str]
    alias_to_url = collections.OrderedDict()  # type: OrderedDict[str, str]

    for attribute, value in minidom_doc.documentElement.attributes.items():
        if attribute == "xmlns":
            main = value
        elif attribute.startswith("xmlns:"):
            alias = attribute[len("xmlns:") :]
            url_to_alias[value] = alias
            alias_to_url[alias] = value
        else:
            # NOTE (mristin):
            # This attribute is otherwise irrelevant.
            pass

    if main is None:
        return None, "The main namespace is missing"

    return (
        _XmlNamespaceDeclarations(
            main=main, url_to_alias=url_to_alias, alias_to_url=alias_to_url
        ),
        None,
    )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_browse_name_map(
    naming_text: str,
) -> Tuple[Optional[MutableMapping[str, Identifier]], Optional[str]]:
    """
    Parse a naming map from CSV-formatted text.

    The CSV must contain the headers:
    - "Original name"
    - "OPC UA Browse Name"

    Return a dictionary mapping original names to underscored names, and
    an error (if any).
    """
    result = dict()  # type: MutableMapping[str, Identifier]

    try:
        reader = csv.DictReader(io.StringIO(naming_text))
        expected_headers = {"Original name", "OPC UA Browse Name"}
        actual_headers = set(reader.fieldnames or [])

        if not expected_headers.issubset(actual_headers):
            expected_headers_joined = ",".join(expected_headers)
            actual_headers_joined = ",".join(actual_headers)

            return None, (
                f"CSV header must contain: "
                f"{expected_headers_joined}; "
                f"got: {actual_headers_joined}"
            )

        # NOTE (mristin):
        # Row index: 2 = first data row (since header is row 1)
        for row_index, row in enumerate(reader, start=2):
            original = row.get("Original name")
            browse_name = row.get("OPC UA Browse Name")

            if original is None or browse_name is None:
                return None, (
                    f"Missing values at row {row_index}; "
                    f"expected 2, but got {len(row)} value(s)"
                )

            original = original.strip()
            browse_name = browse_name.strip()

            if len(original) == 0:
                return None, f"Empty 'Original name' at row {row_index}"

            if len(browse_name) == 0:
                return None, f"Empty 'OPC UA Browse Name' at row {row_index}"

            if IDENTIFIER_RE.match(browse_name) is None:
                return None, (
                    f"'OPC UA Browse Name' at row {row_index} "
                    f"is not a valid variable identifier "
                    f"(expected to match {IDENTIFIER_RE.pattern}, but it does not)."
                )

            result[original] = Identifier(browse_name)

        return result, None

    except Exception as exception:
        return None, str(exception)


class _Model:
    """Represent an OPC UA model."""

    uri: Final[str]
    version: Final[str]

    def __init__(self, uri: str, version: str) -> None:
        self.uri = uri
        self.version = version


class _Registry:
    """Register entities with their browse names and OPC UA namespaces."""

    namespace_by_global_id: Final[Mapping[str, str]]
    browse_name_by_global_id: Final[Mapping[str, Identifier]]
    global_id_set: Final[FrozenSet[str]]

    # fmt: off
    @require(
        lambda browse_names: all(
            IDENTIFIER_RE.match(browse_name) is not None for browse_name in browse_names
        )
    )
    @require(
        lambda global_ids, browse_names, namespaces:
        len(global_ids)
        == len(browse_names)
        == len(namespaces)
    )
    @ensure(
        lambda self:
        sorted(self.namespace_by_global_id.keys())
        == sorted(self.browse_name_by_global_id.keys()),
    )
    @ensure(
        lambda self:
        all(
            global_id in self.namespace_by_global_id
            and global_id in self.browse_name_by_global_id
            for global_id in self.global_id_set
        ),
        "All global IDs mapped"
    )
    # fmt: on
    def __init__(
        self,
        global_ids: Sequence[str],
        browse_names: Sequence[Identifier],
        namespaces: Sequence[str],
    ) -> None:
        self.namespace_by_global_id = {
            global_id: namespace for global_id, namespace in zip(global_ids, namespaces)
        }

        self.browse_name_by_global_id = {
            global_id: browse_name
            for global_id, browse_name in zip(global_ids, browse_names)
        }

        self.global_id_set = frozenset(global_ids)


_REGISTRY_KEY = specific_implementations.ImplementationKey("registry.csv")


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _parse_entity_registry(
    registry_text: str, base_nodeset: opcua_parse.Nodeset
) -> Tuple[Optional[_Registry], Optional[str]]:
    """
    Parse the entity registry from the given CSV table.

    Return the registry, or an error, if any.
    """
    semantic_ids = []  # type: List[str]
    browse_names = []  # type: List[str]
    namespaces = []  # type: List[str]

    stream = io.StringIO(registry_text)
    reader = csv.DictReader(stream)

    expected_columns = ["Semantic ID", "Browse Name", "Namespace"]

    if reader.fieldnames != expected_columns:
        expected_columns_joined = ",".join(expected_columns)

        if reader.fieldnames is None:
            return None, f"Expected columns {expected_columns_joined}, but got none"

        fieldnames_joined = ",".join(reader.fieldnames)
        return None, (
            f"Expected columns {expected_columns_joined}, but got: {fieldnames_joined}"
        )

    errors = []  # type: List[str]

    for row_num, row in enumerate(reader, start=2):
        semantic_id = row.get("Semantic ID", "").strip()
        browse_name = row.get("Browse Name", "").strip()
        namespace = row.get("Namespace", "").strip()

        has_error = False
        if not semantic_id:
            errors.append(f"Row {row_num}: missing Semantic ID")
            has_error = True

        if not browse_name:
            errors.append(f"Row {row_num}: missing Browse Name")
            has_error = True

        if not namespace:
            errors.append(f"Row {row_num}: missing Namespace")
            has_error = True

        if has_error:
            continue

        semantic_ids.append(semantic_id)
        browse_names.append(browse_name)
        namespaces.append(namespace)

    @require(lambda: len(errors) > 0)
    def generate_error_message() -> str:
        """Generate the error message based on the ``errors``."""
        return f"One or more invalid rows:\n" f"{bullet_points(errors)}"

    if len(errors) > 0:
        return None, generate_error_message()

    assert len(semantic_ids) == len(browse_names) == len(namespaces)

    namespace_browse_name_set = set()  # type: Set[Tuple[str, str]]

    for row_num, (semantic_id, browse_name, namespace) in enumerate(
        zip(semantic_ids, browse_names, namespaces), start=2
    ):
        if IDENTIFIER_RE.match(browse_name) is None:
            errors.append(
                f"Row {row_num}: "
                f"Browse Name {browse_name!r} does not match {IDENTIFIER_RE.pattern}"
            )

        if namespace not in base_nodeset.namespace_to_index:
            errors.append(
                f"Row {row_num}: "
                f"Namespace {namespace!r} not in "
                f"the <NamespaceUris> of the base nodeset as given in "
                f"the implementation-specific snippet {base_nodeset.implementation_key}"
            )
            continue

        namespace_browse_name = (namespace, browse_name)
        if namespace_browse_name in namespace_browse_name_set:
            errors.append(
                f"Row {row_num}: "
                f"This is a duplicate for Namespace {namespace!r} and "
                f"Browse Name {browse_name!r} in "
                f"the implementation-specific snippet {base_nodeset.implementation_key}"
            )
            continue

        namespace_browse_name_set.add(namespace_browse_name)

    if len(errors) > 0:
        return None, generate_error_message()

    return (
        _Registry(
            global_ids=semantic_ids,
            browse_names=[Identifier(browse_name) for browse_name in browse_names],
            namespaces=namespaces,
        ),
        None,
    )


def _check_all_entities_covered_in_registry(
    registry: _Registry, entities: Sequence[ir.Entity]
) -> Optional[str]:
    """
    Check that the registry covers all the entities w.r.t. browse name and namespace.

    Return an error, if any.
    """
    missing_global_ids = []  # type: List[str]
    for entity in entities:
        if entity.global_id not in registry.namespace_by_global_id:
            if (
                isinstance(entity.source, aas_types.Submodel)
                and entity.source.id_short is not None
            ):
                missing_global_ids.append(
                    f"{entity.global_id}: "
                    f"Submodel with ID-short {entity.source.id_short}"
                )
            elif (
                isinstance(entity.source, aas_types.SubmodelElementCollection)
                and entity.source.id_short is not None
            ):
                missing_global_ids.append(
                    f"{entity.global_id}: "
                    f"Submodel Element Collection "
                    f"with ID-short {entity.source.id_short}"
                )
            else:
                missing_global_ids.append(entity.global_id)

    if len(missing_global_ids) == 0:
        return None

    return (
        f"One or more global IDs have not been covered "
        f"in the registry:\n"
        f"{bullet_points(missing_global_ids)}"
    )


# region OPC-UA representation


class _ObjectType:
    """Represent a UA Object Type at an abstract level."""

    namespace: str
    browse_name: Identifier

    display_name: Optional[str]
    description: Optional[str]

    components: List[Union["_Variable", "_Object"]]
    subtype: Optional["_ObjectType"]

    def __init__(
        self,
        namespace: str,
        browse_name: Identifier,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        components: Optional[List[Union["_Variable", "_Object"]]] = None,
        subtype: Optional["_ObjectType"] = None,
    ) -> None:
        self.namespace = namespace
        self.display_name = display_name
        self.browse_name = browse_name
        self.description = description
        self.components = components if components is not None else []
        self.subtype = subtype


class _ModellingRule(enum.Enum):
    """Capture the possible modelling rules for variables and objects."""

    Optional = 80
    Mandatory = 78
    OptionalPlaceholder = 11508
    MandatoryPlaceholder = 11510


_MULTIPLICITY_TO_MODELLING_RULE = {
    ir.Multiplicity.ZERO_TO_ONE: _ModellingRule.Optional,
    ir.Multiplicity.ONE: _ModellingRule.Mandatory,
    ir.Multiplicity.ZERO_TO_MANY: _ModellingRule.OptionalPlaceholder,
    ir.Multiplicity.ONE_TO_MANY: _ModellingRule.MandatoryPlaceholder,
}

assert all(
    multiplicity in _MULTIPLICITY_TO_MODELLING_RULE for multiplicity in ir.Multiplicity
), "All multiplicities mapped"


class _DataType(enum.Enum):
    """
    List data types with their aliases.

    We explicitly do not list identifiers since we want the nodeset to be readable.
    """

    BOOLEAN = "Boolean"
    INT16 = "Int16"
    INT32 = "Int32"
    INT64 = "Int64"
    DOUBLE = "Double"
    FLOAT = "Float"
    STRING = "String"
    LOCALIZED_TEXT = "LocalizedText"
    DATE_TIME = "DateTime"
    RANGE = "Range"


_XSD_DATA_TYPE_TO_DATA_TYPE = {
    aas_types.DataTypeDefXSD.BOOLEAN: _DataType.BOOLEAN,
    aas_types.DataTypeDefXSD.SHORT: _DataType.INT16,
    aas_types.DataTypeDefXSD.INT: _DataType.INT32,
    aas_types.DataTypeDefXSD.LONG: _DataType.INT64,
    aas_types.DataTypeDefXSD.INTEGER: _DataType.STRING,
    aas_types.DataTypeDefXSD.FLOAT: _DataType.FLOAT,
    aas_types.DataTypeDefXSD.DOUBLE: _DataType.DOUBLE,
    aas_types.DataTypeDefXSD.STRING: _DataType.STRING,
    aas_types.DataTypeDefXSD.DECIMAL: _DataType.STRING,
    aas_types.DataTypeDefXSD.DATE: _DataType.DATE_TIME,
    aas_types.DataTypeDefXSD.DATE_TIME: _DataType.DATE_TIME,
    aas_types.DataTypeDefXSD.ANY_URI: _DataType.STRING,
}  # type: Final[Mapping[aas_types.DataTypeDefXSD, _DataType]]


class _Variable:
    """Represent an UA Variable at an abstract level."""

    namespace: str
    browse_name: Identifier
    data_type: _DataType
    parent_node: _ObjectType
    modelling_rule: _ModellingRule

    display_name: Optional[str]
    description: Optional[str]
    value_rank: Optional[int]

    def __init__(
        self,
        namespace: str,
        browse_name: Identifier,
        data_type: _DataType,
        parent_node: _ObjectType,
        modelling_rule: _ModellingRule,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        value_rank: Optional[int] = None,
    ) -> None:
        self.namespace = namespace
        self.browse_name = browse_name
        self.data_type = data_type
        self.parent_node = parent_node
        self.modelling_rule = modelling_rule
        self.display_name = display_name
        self.description = description
        self.value_rank = value_rank


class _BuiltInTypeDefinition(enum.Enum):
    """
    List the type definitions which we handle here as well.

    See: https://www.open62541.org/doc/0.3/constants.html for a list of identifiers.
    """

    FileType = 11575


class _ImportedObjectType:
    """Represent an object type which is imported from a Required Model."""

    # NOTE (mristin):
    # We wrap an object from opcua.parse module to signal its purpose through its
    # type information.

    parsed: opcua_parse.ObjectType

    def __init__(self, parsed: opcua_parse.ObjectType):
        self.parsed = parsed


class _Object:
    """Represent a UA Object at an abstract level."""

    namespace: str
    browse_name: Identifier

    #: This is type definition which points either to our object types or
    #: OPC UA built-in object types.
    type_definition: Union[_ObjectType, _BuiltInTypeDefinition, _ImportedObjectType]

    parent_node: _ObjectType
    modelling_rule: _ModellingRule

    display_name: Optional[str]
    description: Optional[str]

    def __init__(
        self,
        namespace: str,
        browse_name: Identifier,
        type_definition: Union[
            _ObjectType, _BuiltInTypeDefinition, _ImportedObjectType
        ],
        parent_node: _ObjectType,
        modelling_rule: _ModellingRule,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        self.namespace = namespace
        self.browse_name = browse_name
        self.type_definition = type_definition
        self.parent_node = parent_node
        self.modelling_rule = modelling_rule
        self.display_name = display_name
        self.description = description


_Node = Union[_ObjectType, _Variable, _Object]

# endregion OPC-UA representation

# region Translation Intermediate Representation 🠒 OPC UA Representation

_BROWSE_NAME_MAP_KEY = specific_implementations.ImplementationKey("browse_name_map.csv")


def _get_browse_name_from_map(
    name: Identifier, browse_name_map: Mapping[str, Identifier]
) -> Tuple[Identifier, Optional[str]]:
    """
    Map the name to the snake case from the ``naming_map``.

    If the name is not properly mapped, return a dummy placeholder and the error.
    The dummy name is necessary so that we can continue the processing and report
    any potential other errors.

    Otherwise, if there is no error, return the mapped name and None.
    """
    browse_name = browse_name_map.get(name, None)
    if browse_name is None:
        # NOTE (mristin):
        # We set a dummy browse name just to be able to continue the processing
        # and return all the possible errors.
        caller = inspect.stack()[1]
        module = inspect.getmodule(caller.frame)
        module_name = module.__name__.replace(".", "_") if module else "unknown_module"
        line_number = caller.lineno + 1

        dummy_name = Identifier(
            f"Dummy_since_{name}_not_mapped_in_naming_map_{module_name}_at_{line_number}"
        )

        return dummy_name, (
            f"The name is not mapped in "
            f"the naming map snippet {_BROWSE_NAME_MAP_KEY}: {name!r}"
        )

    return browse_name, None


# fmt: off
@ensure(
    lambda result:
    not (result[0] is not None)
    or (
        len({id(object_type) for object_type in result[0]}) == len(result[0])
        and len(
            {
                (object_type.namespace, object_type.browse_name)
                for object_type in result[0]
            }
        ) == len(result[0])
    ),
    "No duplicate resulting object types"
)
@ensure(
    lambda result: not (result[1] is not None) or len(result[1]) >= 1,
    "At least one error if errors are not None"
)
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@require(
    lambda entities:
    len({id(entity) for entity in entities}) == len(entities),
    "No duplicate entities"
)
# fmt: on
def _entities_to_object_types(
    entities: Sequence[ir.Entity],
    registry: _Registry,
    browse_name_map: Mapping[str, Identifier],
    parsing: opcua_parse.Parsing,
) -> Tuple[Optional[List[_ObjectType]], Optional[List[str]]]:
    """
    Translate all the entities to OPC UA nodes.

    The naming map is used to translate the names to snake case. This is necessary
    as submodel templates usually contain names in camelCase which can not easily
    be split into parts (*e.g.*, ``PCFCO2eq`` 🠒 ``PCF_CO2_eq``).

    Return the translated object types, or errors, if any.
    """
    entity_to_object_type = (
        dict()
    )  # type: MutableMapping[ir.Entity, Union[_ObjectType, _ImportedObjectType]]

    result = []  # type: List[_ObjectType]
    errors = []  # type: List[str]

    # NOTE (mristin):
    # First, we map all the imported object types so that we can reference them
    # if they are used for definitions of our internal object types.
    assert parsing.base_nodeset is parsing.nodesets[0]

    imported_object_type_by_namespace_and_browse_name = (
        dict()
    )  # type: MutableMapping[Tuple[str, str], _ImportedObjectType]

    for nodeset in itertools.islice(parsing.nodesets, 1, None):
        for parsed_object_type in nodeset.object_types:
            imported_object_type_by_namespace_and_browse_name[
                (parsed_object_type.namespace, parsed_object_type.browse_name)
            ] = _ImportedObjectType(parsed=parsed_object_type)

    # NOTE (mristin):
    # We have to map all entities to work-in-progress object types so that we
    # can look them up when translating the aggregations.

    for entity in entities:
        browse_name = registry.browse_name_by_global_id.get(entity.global_id, None)
        if browse_name is None:
            id_short_part = (
                f" and ID-short {entity.source.id_short}"
                if entity.source.id_short is not None
                else ""
            )
            errors.append(
                f"The entity with "
                f"the semantic ID {entity.global_id}{id_short_part} "
                f"is missing the entry in the registry coming "
                f"from the implementation-specific snippet {_REGISTRY_KEY}"
            )
            continue

        namespace = registry.namespace_by_global_id[entity.global_id]

        imported_object_type = imported_object_type_by_namespace_and_browse_name.get(
            (namespace, browse_name), None
        )

        if imported_object_type is not None:
            entity_to_object_type[entity] = imported_object_type
        else:
            entity_to_object_type[entity] = _ObjectType(
                namespace=registry.namespace_by_global_id[entity.global_id],
                browse_name=browse_name,
                display_name=try_in_english(entity.source.display_name),
                description=try_in_english(entity.source.description),
            )

    namespace_set_for_imported_object_types = {
        object_type.parsed.namespace
        for entity, object_type in entity_to_object_type.items()
        if isinstance(object_type, _ImportedObjectType)
    }  # type: Set[str]

    missing_namespaces = sorted(
        namespace_set_for_imported_object_types.difference(
            set(parsing.base_nodeset.namespaces)
        )
    )

    if len(missing_namespaces):
        errors.append(
            "The following one or more namespaces are required "
            "by the imported object types, "
            "but they are missing from <NamespaceUris> "
            "in the base nodeset as provided by "
            f"the implementation-specific snippet {parsing.base_nodeset_key}:\n"
            f"{bullet_points(missing_namespaces)}"
        )

    if len(errors) > 0:
        return None, errors

    # NOTE (mristin):
    # Once all the entities are mapped to object types, we can translate
    # the aggregations.

    for entity in entities:
        object_type = entity_to_object_type[entity]

        # NOTE (mristin):
        # We do not re-define the object types from the external models imported
        # through ``<RequiredModel>``.
        if isinstance(object_type, _ImportedObjectType):
            continue

        result.append(object_type)

        for aggregation in entity.aggregations:
            component: _Variable | _Object

            modelling_rule = _MULTIPLICITY_TO_MODELLING_RULE[aggregation.multiplicity]

            browse_name, error = _get_browse_name_from_map(
                name=aggregation.name, browse_name_map=browse_name_map
            )
            if error is not None:
                # NOTE (mristin):
                # The browse_name is now a dummy browse name. We use it just to be able
                # to continue the processing and return all the possible errors.
                errors.append(error)

            if isinstance(aggregation.aggregatee, ir.PathedElement):
                element = aggregation.aggregatee.element

                display_name = try_in_english(element.display_name)
                description = try_in_english(element.description)

                if isinstance(element, aas_types.Property):
                    data_type = _XSD_DATA_TYPE_TO_DATA_TYPE.get(
                        element.value_type, None
                    )

                    if data_type is None:
                        raise NotImplementedError(
                            f"We have not implemented the translation of XSD data type "
                            f"{element.value_type.value}. Please contact "
                            f"the developers if you need this feature."
                        )

                    component = _Variable(
                        namespace=object_type.namespace,
                        browse_name=browse_name,
                        data_type=data_type,
                        parent_node=object_type,
                        modelling_rule=modelling_rule,
                        display_name=display_name,
                        description=description,
                    )

                    if aggregation.multiplicity in (
                        ir.Multiplicity.ZERO_TO_MANY,
                        ir.Multiplicity.ONE_TO_MANY,
                    ):
                        component.value_rank = 1

                elif isinstance(element, aas_types.File):
                    component = _Object(
                        namespace=object_type.namespace,
                        browse_name=browse_name,
                        type_definition=_BuiltInTypeDefinition.FileType,
                        parent_node=object_type,
                        modelling_rule=modelling_rule,
                        display_name=display_name,
                        description=description,
                    )
                elif isinstance(element, aas_types.MultiLanguageProperty):
                    component = _Variable(
                        namespace=object_type.namespace,
                        browse_name=browse_name,
                        data_type=_DataType.LOCALIZED_TEXT,
                        parent_node=object_type,
                        modelling_rule=modelling_rule,
                        display_name=display_name,
                        description=description,
                    )
                elif isinstance(element, aas_types.Range):
                    if element.value_type not in (
                        aas_types.DataTypeDefXSD.FLOAT,
                        aas_types.DataTypeDefXSD.DOUBLE,
                    ):
                        raise NotImplementedError(
                            f"We have not implemented the translation of "
                            f"{element.__class__.__name__} "
                            f"with value type {element.value_type} to OPC UA:\n"
                            f"{aas_jsonization.to_jsonable(element)}\n"
                            f"Please contact the developers if you need this feature."
                        )

                    component = _Variable(
                        namespace=object_type.namespace,
                        browse_name=browse_name,
                        data_type=_DataType.RANGE,
                        parent_node=object_type,
                        modelling_rule=modelling_rule,
                        display_name=display_name,
                        description=description,
                    )

                else:
                    raise NotImplementedError(
                        f"We have not implemented the translation of "
                        f"{element.__class__.__name__} to OPC UA:\n"
                        f"{aas_jsonization.to_jsonable(element)}\n"
                        f"Please contact the developers if you need this feature."
                    )

            elif isinstance(aggregation.aggregatee, ir.Entity):
                entity = aggregation.aggregatee

                display_name = try_in_english(entity.source.display_name)
                description = try_in_english(entity.source.description)

                component = _Object(
                    namespace=object_type.namespace,
                    browse_name=browse_name,
                    type_definition=entity_to_object_type[aggregation.aggregatee],
                    parent_node=object_type,
                    modelling_rule=modelling_rule,
                    display_name=display_name,
                    description=description,
                )

            else:
                assert_never(aggregation.aggregatee)
                raise AssertionError("Unexpected execution path")

            object_type.components.append(component)

    if len(errors) > 0:
        return None, errors

    return result, None


# endregion Translation Intermediate Representation 🠒 OPC UA Representation

# region Translate OPC UA Representation to ElementTree


class _IdentifierMachine:
    """
    Produce stable identifiers for different nodes.

    The Identifier Machine knows nothing about your scheme, so you have to come up
    with your own.

    It will try to be as stable as possible, *i.e.*, the identifiers for the names
    should not change even if the order of :py:func:`obtain` is changed.

    >>> machine = _IdentifierMachine()
    >>> machine.obtain("something")
    207137056

    Obtaining an identifier is idem-potent:

    >>> machine.obtain("something")
    207137056

    Another text gives you another identifier:

    >>> machine.obtain("something_else")
    165180381
    """

    def __init__(self) -> None:
        self._identifier_map = dict()  # type: MutableMapping[str, int]
        self._taken_identifiers = set()  # type: Set[int]

    @staticmethod
    def _hash(text: str) -> int:
        """
        Compute the non-cryptographic hash of the given string.

        We implement our own hash so that the implementation need not change across
        different Python versions, in case they change the hash function.

        >>> _IdentifierMachine._hash("something")
        207137056

        >>> _IdentifierMachine._hash("something_else")
        165180381

        >>> _IdentifierMachine._hash("")
        7
        """
        result = 7
        for character in text:
            result = (result * 31 + ord(character)) % 0x7FFFFFFF

        return result

    def obtain(self, text: str) -> int:
        """
        Assign a slot for the text using hashing.

        In most cases, we do not expect the resulting ID to change.
        """
        identifier = self._identifier_map.get(text, None)
        if identifier is not None:
            return identifier

        identifier = _IdentifierMachine._hash(text)

        while identifier in self._taken_identifiers:
            identifier += 1

        self._taken_identifiers.add(identifier)
        self._identifier_map[text] = identifier

        return identifier


def _reference_element(
    reference_type: str, target: str, is_forward: Optional[bool] = None
) -> ET.Element:
    """Create a ``<Reference>`` element."""
    attrib = collections.OrderedDict([("ReferenceType", reference_type)])
    if is_forward is not None:
        attrib["IsForward"] = "true" if is_forward else "false"

    reference_el = ET.Element("Reference", attrib)
    reference_el.text = target

    return reference_el


def _object_type_to_element(
    object_type: _ObjectType,
    id_map: Mapping[_Node, int],
    base_nodeset: opcua_parse.Nodeset,
) -> ET.Element:
    """Translate the OPC UA object type to a nodeset XML element."""
    ns_id = base_nodeset.namespace_to_index[object_type.namespace]

    object_type_el = ET.Element(
        "UAObjectType",
        collections.OrderedDict(
            [
                ("NodeId", f"ns={ns_id};i={id_map[object_type]}"),
                ("BrowseName", f"{ns_id}:{object_type.browse_name}"),
            ]
        ),
    )

    if object_type.display_name is not None:
        display_name_el = ET.Element("DisplayName")
        display_name_el.text = object_type.display_name
        object_type_el.append(display_name_el)

    if object_type.description is not None:
        description_el = ET.Element("Description")
        description_el.text = object_type.description
        object_type_el.append(description_el)

    references_el = ET.Element("References")

    # Taken from: https://www.open62541.org/doc/0.3/constants.html
    # i=58 is BaseObjectType.
    references_el.append(
        _reference_element(reference_type="HasSubtype", target="i=58", is_forward=False)
    )

    for component in object_type.components:
        references_el.append(
            _reference_element(
                reference_type="HasComponent",
                target=f"ns={ns_id};i={id_map[component]}",
            )
        )

    object_type_el.append(references_el)

    return object_type_el


def _variable_to_element(
    variable: _Variable, id_map: Mapping[_Node, int], base_nodeset: opcua_parse.Nodeset
) -> ET.Element:
    """Translate the OPC UA Variable to a nodeset XML element."""
    ns_id = base_nodeset.namespace_to_index[variable.namespace]

    variable_el = ET.Element(
        "UAVariable",
        collections.OrderedDict(
            [
                ("DataType", variable.data_type.value),
                ("NodeId", f"ns={ns_id};i={id_map[variable]}"),
                ("BrowseName", f"{ns_id}:{variable.browse_name}"),
                ("ParentNodeId", f"ns={ns_id};i={id_map[variable.parent_node]}"),
            ]
        ),
    )

    if variable.value_rank is not None:
        variable_el.attrib["ValueRank"] = str(variable.value_rank)

    if variable.display_name is not None:
        display_name_el = ET.Element("DisplayName")
        display_name_el.text = variable.display_name
        variable_el.append(display_name_el)

    if variable.description is not None:
        description_el = ET.Element("Description")
        description_el.text = variable.description
        variable_el.append(description_el)

    references_el = ET.Element("References")
    references_el.append(
        _reference_element(
            reference_type="HasModellingRule",
            target=f"i={variable.modelling_rule.value}",
        )
    )
    references_el.append(
        # Taken from: https://www.open62541.org/doc/0.3/constants.html
        # i=68 is PropertyType.
        # See also: https://reference.opcfoundation.org/Core/Part5/v104/docs/7.3
        _reference_element(reference_type="HasTypeDefinition", target="i=68")
    )
    variable_el.append(references_el)

    return variable_el


def _object_to_element(
    obj: _Object, id_map: Mapping[_Node, int], base_nodeset: opcua_parse.Nodeset
) -> ET.Element:
    """Translate the OPC UA Object to a nodeset XML element."""
    ns_id = base_nodeset.namespace_to_index[obj.namespace]

    object_el = ET.Element(
        "UAObject",
        collections.OrderedDict(
            [
                ("NodeId", f"ns={ns_id};i={id_map[obj]}"),
                ("BrowseName", f"1:{obj.browse_name}"),
                ("ParentNodeId", f"ns={ns_id};i={id_map[obj.parent_node]}"),
            ]
        ),
    )

    if obj.display_name is not None:
        display_name_el = ET.Element("DisplayName")
        display_name_el.text = obj.display_name
        object_el.append(display_name_el)

    if obj.description is not None:
        description_el = ET.Element("Description")
        description_el.text = obj.description
        object_el.append(description_el)

    references_el = ET.Element("References")

    if isinstance(obj.type_definition, _ObjectType):
        object_type = obj.type_definition

        target_ns_id = base_nodeset.namespace_to_index[object_type.namespace]

        references_el.append(
            _reference_element(
                reference_type="HasTypeDefinition",
                target=f"ns={target_ns_id};i={id_map[object_type]}",
            )
        )

        for component in object_type.components:
            references_el.append(
                _reference_element(
                    reference_type="HasComponent",
                    target=f"ns={target_ns_id};i={id_map[component]}",
                )
            )

    elif isinstance(obj.type_definition, _ImportedObjectType):
        parsed = obj.type_definition.parsed

        target_ns_id = base_nodeset.namespace_to_index[parsed.namespace]

        references_el.append(
            _reference_element(
                reference_type="HasTypeDefinition",
                target=f"ns={target_ns_id};i={parsed.identifier}",
            )
        )

        for parsed_component in parsed.components:
            target_comp_ns_id = base_nodeset.namespace_to_index[
                parsed_component.namespace
            ]

            references_el.append(
                _reference_element(
                    reference_type="HasComponent",
                    target=f"ns={target_comp_ns_id};i={parsed_component.identifier}",
                )
            )

    elif isinstance(obj.type_definition, _BuiltInTypeDefinition):
        references_el.append(
            _reference_element(
                reference_type="HasTypeDefinition",
                target=f"i={obj.type_definition.value}",
            )
        )

        if obj.type_definition is _BuiltInTypeDefinition.FileType:
            # NOTE (mristin):
            # We figured this out using https://www.open62541.org/doc/0.3/constants.html,
            # https://reference.opcfoundation.org/nodesets/144/40085, and
            # validating with SiOME - OPC UA Modeling Editor 2.8.7.

            references_el.append(
                _reference_element(reference_type="HasComponent", target="i=11583")
            )
            references_el.append(
                _reference_element(reference_type="HasComponent", target="i=11590")
            )
            references_el.append(
                _reference_element(reference_type="HasComponent", target="i=11580")
            )
            references_el.append(
                _reference_element(reference_type="HasProperty", target="i=11579")
            )
            references_el.append(
                _reference_element(reference_type="HasComponent", target="i=11585")
            )
            references_el.append(
                _reference_element(reference_type="HasComponent", target="i=11593")
            )
            references_el.append(
                _reference_element(reference_type="HasProperty", target="i=11576")
            )
            references_el.append(
                _reference_element(reference_type="HasProperty", target="i=12687")
            )
            references_el.append(
                _reference_element(reference_type="HasProperty", target="i=12686")
            )
            references_el.append(
                _reference_element(reference_type="HasComponent", target="i=11588")
            )

        else:
            assert_never(obj.type_definition)

    else:
        assert_never(obj.type_definition)
        raise AssertionError("Unexpected execution path")

    references_el.append(
        _reference_element(
            reference_type="HasModellingRule", target=f"i={obj.modelling_rule.value}"
        )
    )

    object_el.append(references_el)

    return object_el


# fmt: off
@ensure(
    lambda result: not (len(result) >= 1) or result[-1].tail is None,
    "No newline at the end"
)
# fmt: on
def _object_types_to_elements(
    object_types: Sequence[_ObjectType], base_nodeset: opcua_parse.Nodeset
) -> List[ET.Element]:
    """Translate the definitions of object types to XML elements."""
    identifier_machine = _IdentifierMachine()

    id_map = dict()  # type: MutableMapping[_Node, int]

    for object_type in object_types:
        id_map[object_type] = identifier_machine.obtain(text=object_type.browse_name)

        for component in object_type.components:
            id_map[component] = identifier_machine.obtain(
                text=f"{object_type.browse_name}.{component.browse_name}"
            )

    result = []  # type: List[ET.Element]

    for i, object_type in enumerate(object_types):
        comment_starts = ET.Comment(f"{object_type.browse_name} starts.")
        comment_starts.tail = "\n"
        result.append(comment_starts)

        result.append(
            _object_type_to_element(
                object_type=object_type, id_map=id_map, base_nodeset=base_nodeset
            )
        )

        for component in object_type.components:
            if isinstance(component, _Variable):
                result.append(
                    _variable_to_element(
                        variable=component, id_map=id_map, base_nodeset=base_nodeset
                    )
                )

            elif isinstance(component, _Object):
                result.append(
                    _object_to_element(
                        obj=component, id_map=id_map, base_nodeset=base_nodeset
                    )
                )
            else:
                assert_never(component)

        comment_ends = ET.Comment(f"{object_type.browse_name} ends.")
        if i < len(object_types) - 1:
            comment_ends.tail = "\n"

        result.append(comment_ends)

    return result


# endregion Translate OPC UA Representation to ElementTree

INDENT = "  "

# NOTE (mristin):
# The ElementTree library is very peculiar when it comes to namespaces. The namespace
# URLs are directly inserted as prefixes to tag names, even when the user specifies
# an alias.
_ET_NAMESPACE_PREFIX_RE = re.compile(r"^\{(?P<namespace>[^}]*)}")


def _render(
    element: ET.Element,
    writer: TextIO,
    namespace_declarations: _XmlNamespaceDeclarations,
    level: int = 0,
) -> None:
    """
    Render the given XML tree starting with the ``element`` at the root.

    We designed the rendering such that the XMLs are easy to read and diff.
    """
    indention = INDENT * level

    if element.tag is ET.Comment:  # type: ignore
        writer.write(f"{indention}<!-- {element.text} -->\n")
    else:
        if len(element) > 0:
            if element.text is not None and not element.text.isspace():
                raise ValueError(
                    f"Unexpected element with children "
                    f"and non-whitespace text: {element}; "
                    f"the text was: {element.text!r}"
                )

            if element.tail is not None and not element.tail.isspace():
                raise ValueError(
                    f"Unexpected element with children "
                    f"and non-whitespace tail: {element}; "
                    f"the tail was: {element.tail!r}"
                )

        ns_match = _ET_NAMESPACE_PREFIX_RE.match(element.tag)
        if ns_match is not None:
            ns_url = ns_match.group("namespace")

            if ns_url == namespace_declarations.main:
                # NOTE (mristin):
                # We add 2 for the enclosing ``{`` and ``}``.
                name = element.tag[len(ns_url) + 2 :]
            else:
                ns_alias = namespace_declarations.url_to_alias.get(ns_url, None)
                if ns_alias is None:
                    raise ValueError(
                        f"Unexpected namespace URL in the ET element {element}. "
                        f"The declared namespaces aliases "
                        f"were: {namespace_declarations.url_to_alias}"
                    )

                # NOTE (mristin):
                # We add 2 for the enclosing ``{`` and ``}``.
                local_name = element.tag[len(ns_url) + 2 :]
                name = f"{ns_alias}:{local_name}"
        else:
            name = element.tag

        text = None  # type: Optional[str]
        if element.text is not None and not element.text.isspace():
            text = element.text

        if text is None and len(element) == 0:
            if len(element.attrib) == 0:
                writer.write(f"{indention}<{name} />\n")
            else:
                writer.write(f"{indention}<{name}\n")
                for attrib, value in element.attrib.items():
                    quoted_value = xml.sax.saxutils.quoteattr(value)
                    writer.write(f"{indention}{INDENT}{attrib}={quoted_value}\n")

                writer.write(f"{indention}/>\n")

        elif text is not None and len(element) == 0:
            escaped_text = xml.sax.saxutils.escape(text)

            if len(element.attrib) == 0:
                writer.write(f"{indention}<{name}>{escaped_text}</{name}>\n")
            else:
                writer.write(f"{indention}<{name}\n")

                for attrib, value in element.attrib.items():
                    quoted_value = xml.sax.saxutils.quoteattr(value)
                    writer.write(f"{indention}{INDENT}{attrib}={quoted_value}\n")

                writer.write(f"{indention}>{escaped_text}</{name}>\n")

        elif text is None and len(element) > 0:
            if len(element.attrib) == 0:
                writer.write(f"{indention}<{name}>\n")

                for child in element:
                    _render(
                        element=child,
                        writer=writer,
                        namespace_declarations=namespace_declarations,
                        level=level + 1,
                    )

                writer.write(f"{indention}</{name}>\n")
            else:
                writer.write(f"{indention}<{name}\n")

                for attrib, value in element.attrib.items():
                    quoted_value = xml.sax.saxutils.quoteattr(value)
                    writer.write(f"{indention}{INDENT}{attrib}={quoted_value}\n")

                writer.write(f"{indention}>\n")

                for child in element:
                    _render(
                        element=child,
                        writer=writer,
                        namespace_declarations=namespace_declarations,
                        level=level + 1,
                    )

                writer.write(f"{indention}</{name}>\n")

        else:
            raise AssertionError("Unexpected execution path")


def _generate_aliases() -> ET.Element:
    """Generate the aliases including the primitive values."""
    aliases = ET.Element("Aliases")

    for name, i in (
        ("Boolean", 1),
        ("Int16", 4),
        ("Int32", 6),
        ("Int64", 8),
        ("Float", 10),
        ("Double", 11),
        ("String", 12),
        ("DateTime", 13),
        ("ByteString", 15),
        ("LocalizedText", 21),
        ("Range", 884),
        ("HasModellingRule", 37),
        ("HasTypeDefinition", 40),
        ("HasSubtype", 45),
        ("HasProperty", 46),
        ("HasComponent", 47),
        ("HasInterface", 17603),
    ):
        alias = ET.Element("Alias", {"Alias": name})
        alias.text = f"i={i}"
        aliases.append(alias)

    return aliases


@ensure(lambda result: not (result[1] is not None) or (len(result[1]) >= 1))
@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
@ensure(lambda result: not (result[0] is not None) or (result[0].endswith("\n")))
def _generate(
    entities: Sequence[ir.Entity],
    spec_impls: specific_implementations.SpecificImplementations,
) -> Tuple[Optional[str], Optional[str]]:
    """Generate tne node set according to the symbol table."""
    naming_text = spec_impls.get(_BROWSE_NAME_MAP_KEY, None)
    if naming_text is None:
        return None, (
            f"The implementation snippet for the table defining how "
            f"to map aggregation names to OPC UA Browse Names "
            f"(*e.g.*, 'PCFCO2eq' 🠒 'PCFCO2Eq') is missing: {_BROWSE_NAME_MAP_KEY}"
        )

    browse_name_map, error = _parse_browse_name_map(naming_text)
    if error is not None:
        return None, (
            f"The mapping between the aggregation names and OPC UA Browse Names "
            f"could not be extracted from the CSV table "
            f"given in implementation-specific snippet {_BROWSE_NAME_MAP_KEY}: {error}"
        )

    assert browse_name_map is not None

    nodeset_parsing, parse_error = opcua_parse.parse(spec_impls=spec_impls)
    if parse_error is not None:
        return None, parse_error

    assert nodeset_parsing is not None

    registry_text = spec_impls.get(_REGISTRY_KEY, None)
    if registry_text is None:
        return None, (
            f"The implementation snippet for the entity registry "
            f"is missing: {_REGISTRY_KEY}"
        )

    registry, error = _parse_entity_registry(
        registry_text=registry_text, base_nodeset=nodeset_parsing.base_nodeset
    )

    if error is not None:
        return None, (
            f"Failed to parse the entity registry "
            f"from the implementation-specific snippet {_REGISTRY_KEY}: {error}"
        )

    assert registry is not None

    error = _check_all_entities_covered_in_registry(
        registry=registry, entities=entities
    )
    if error is not None:
        return None, (
            f"The entity registry specified as "
            f"an implementation-specific snippet in {_REGISTRY_KEY} "
            f"is incomplete: {error}"
        )

    object_types, errors = _entities_to_object_types(
        entities=entities,
        registry=registry,
        browse_name_map=browse_name_map,
        parsing=nodeset_parsing,
    )

    if errors is not None:
        return None, (
            f"Failed to translate entities to OPC UA ObjectTypes:\n"
            f"{bullet_points(errors)}"
        )

    assert object_types is not None

    xml_namespace_declarations, error = _extract_xml_namespace_declarations_from_xml(
        text=nodeset_parsing.base_nodeset_text
    )
    if error is not None:
        return None, (
            f"The namespaces could not be extracted from the implementation snippet "
            f"for the base OPC UA nodeset {nodeset_parsing.base_nodeset_key}: {error}"
        )

    assert xml_namespace_declarations is not None

    if "uax" not in xml_namespace_declarations.alias_to_url:
        return None, (
            f"The namespace alias for 'uax' is missing in "
            f"the implementation snippet for the base OPC UA "
            f"nodeset: {nodeset_parsing.base_nodeset_key}"
        )

    # NOTE (mristin):
    # We have finished all the parsing, and from now on we extend the OPC UA
    # base nodeset.

    root = copy.deepcopy(nodeset_parsing.base_nodeset_el)
    root.append(_generate_aliases())

    root.extend(
        _object_types_to_elements(
            object_types=object_types, base_nodeset=nodeset_parsing.base_nodeset
        )
    )

    writer = io.StringIO()

    # NOTE (mristin):
    # ElementTree removes the namespaces in the root, so we have to add them back
    # manually.
    root.attrib["xmlns"] = xml_namespace_declarations.main
    for alias, url in xml_namespace_declarations.alias_to_url.items():
        root.attrib[f"xmlns:{alias}"] = url

    _render(
        element=root, writer=writer, namespace_declarations=xml_namespace_declarations
    )

    return writer.getvalue(), None


def execute(
    context: run.Context,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """
    Execute the generation with the given parameters.

    Return the error code, or 0 if no errors.
    """
    code, generate_error = _generate(
        entities=context.entities, spec_impls=context.spec_impls
    )

    if generate_error is not None:
        run.write_error_report(
            message=f"Failed to generate the OPC UA node set "
            f"based on {context.submodel_template_path}",
            errors=[generate_error],
            stderr=stderr,
        )
        return 1

    assert code is not None

    # noinspection SpellCheckingInspection
    pth = context.output_dir / "nodeset.xml"
    try:
        pth.write_text(code, encoding="utf-8")
    except Exception as exception:
        run.write_error_report(
            message=f"Failed to write the OPC UA node set to {pth}",
            errors=[str(exception)],
            stderr=stderr,
        )
        return 1

    stdout.write(f"Code generated to: {context.output_dir}\n")

    return 0
