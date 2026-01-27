# pylint: disable=missing-docstring

import unittest

from aas_smt_codegen import specific_implementations
from aas_smt_codegen.common import Stripped
from aas_smt_codegen.opcua import parse as opcua_parse


class TestParse(unittest.TestCase):
    # pylint: disable=protected-access

    def test_with_only_opc_ua_base_model(self) -> None:
        spec_impls = {
            # pylint: disable=line-too-long
            opcua_parse._BASE_NODESET_KEY: Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
        </Model>
    </Models>
</UANodeSet>"""
            )
        }

        parsing, error = opcua_parse.parse(spec_impls=spec_impls)

        assert error is None, f"Expected no error, but got: {error}"
        assert parsing is not None

        self.assertEqual(
            """\
[
  Nodeset(
    implementation_key=base_nodeset.xml,
    namespaces=["https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation"],
    models=[
      Model(
        uri="https://admin-shell.io/zvei/nameplate/1/0/ContactInformations/AddressInformation",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          )
        ]
      )
    ],
    object_types=[]
  )
]""",
            opcua_parse.dump_nodesets(parsing.nodesets),
        )

    def test_one_self_contained_required_model(self) -> None:
        spec_impls = {
            opcua_parse._BASE_NODESET_KEY: Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelA</Uri>
        <Uri>ModelB</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelA" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
            <RequiredModel
                    ModelUri="ModelB"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.0.0"
            />
        </Model>
    </Models>
</UANodeSet>"""
            ),
            specific_implementations.ImplementationKey(
                "external_models/ModelB"
            ): Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelB</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelB" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
        </Model>
    </Models>
</UANodeSet>"""
            ),
        }

        parsing, error = opcua_parse.parse(spec_impls=spec_impls)

        assert error is None, f"Expected no error, but got: {error}"
        assert parsing is not None

        self.assertEqual(
            """\
[
  Nodeset(
    implementation_key=base_nodeset.xml,
    namespaces=["ModelA", "ModelB"],
    models=[
      Model(
        uri="ModelA",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          ),
          RequiredModel(
            uri="ModelB",
            version="1.0.0"
          )
        ]
      )
    ],
    object_types=[]
  ),
  Nodeset(
    implementation_key=external_models/ModelB,
    namespaces=["ModelB"],
    models=[
      Model(
        uri="ModelB",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          )
        ]
      )
    ],
    object_types=[]
  )
]""",
            opcua_parse.dump_nodesets(parsing.nodesets),
        )

    def test_one_self_contained_required_model_with_object_types(self) -> None:
        spec_impls = {
            opcua_parse._BASE_NODESET_KEY: Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelA</Uri>
        <Uri>ModelB</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelA" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
            <RequiredModel
                    ModelUri="ModelB"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.0.0"
            />
        </Model>
    </Models>
</UANodeSet>"""
            ),
            specific_implementations.ImplementationKey(
                "external_models/ModelB"
            ): Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelB</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelB" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
        </Model>
    </Models>
    <UAObjectType
        NodeId="ns=1;i=1001"
        BrowseName="1:B"
    >
        <References>
          <Reference
            ReferenceType="HasComponent"
          >ns=1;i=1002</Reference>
        </References>
    </UAObjectType>
    <UAVariable
        DataType="LocalizedText"
        NodeId="ns=1;i=1002"
        BrowseName="1:CityTown"
        ParentNodeId="ns=1;i=1001"
      >
        <References>
          <Reference
            ReferenceType="HasModellingRule"
          >i=80</Reference>
          <Reference
            ReferenceType="HasTypeDefinition"
          >i=68</Reference>
        </References>
    </UAVariable>
</UANodeSet>"""
            ),
        }

        parsing, error = opcua_parse.parse(spec_impls=spec_impls)

        assert error is None, f"Expected no error, but got: {error}"
        assert parsing is not None

        self.assertEqual(
            """\
[
  Nodeset(
    implementation_key=base_nodeset.xml,
    namespaces=["ModelA", "ModelB"],
    models=[
      Model(
        uri="ModelA",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          ),
          RequiredModel(
            uri="ModelB",
            version="1.0.0"
          )
        ]
      )
    ],
    object_types=[]
  ),
  Nodeset(
    implementation_key=external_models/ModelB,
    namespaces=["ModelB"],
    models=[
      Model(
        uri="ModelB",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          )
        ]
      )
    ],
    object_types=[
      ObjectType(
        identifier=1001,
        browse_name="B",
        namespace="ModelB",
        components=[
          Component(
            identifier=1002,
            namespace="ModelB"
          )
        ],
        properties=[]
      )
    ]
  )
]""",
            opcua_parse.dump_nodesets(parsing.nodesets),
        )

    def test_transitive_object_types(self) -> None:
        spec_impls = {
            opcua_parse._BASE_NODESET_KEY: Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelA</Uri>
        <Uri>ModelB</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelA" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
            <RequiredModel
                    ModelUri="ModelB"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.0.0"
            />
        </Model>
    </Models>
</UANodeSet>"""
            ),
            specific_implementations.ImplementationKey(
                "external_models/ModelB"
            ): Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelB</Uri>
        <Uri>ModelC</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelB" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
            <RequiredModel
                    ModelUri="ModelC"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.0.0"
            />
        </Model>
    </Models>
    <UAObjectType
        NodeId="ns=1;i=2001"
        BrowseName="1:B"
    >
        <References>
          <Reference
            ReferenceType="HasComponent"
          >ns=1;i=2002</Reference>
        </References>
    </UAObjectType>
    
    <UAObject
        NodeId="ns=1;i=2002"
        BrowseName="1:Something"
        ParentNodeId="ns=1;i=1709618493"
    >
        <References>
          <Reference
            ReferenceType="HasTypeDefinition"
          >ns=2;i=3001</Reference>
          <Reference
            ReferenceType="HasComponent"
          >ns=2;i=3002</Reference>
        </References>
    </UAObject>
</UANodeSet>"""
            ),
            specific_implementations.ImplementationKey(
                "external_models/ModelC"
            ): Stripped(
                """\
<?xml version="1.0" encoding="utf-8" ?>
<UANodeSet
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
        xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    >
    <NamespaceUris>
        <Uri>ModelC</Uri>
    </NamespaceUris>
    <Models>
        <Model ModelUri="ModelC" Version="1.0.0"
               PublicationDate="2025-05-21T00:00:00Z">
            <RequiredModel
                    ModelUri="http://opcfoundation.org/UA/"
                    PublicationDate="2021-09-15T00:00:00Z" Version="1.04.10"
            />
        </Model>
    </Models>
    <UAObjectType
        NodeId="ns=1;i=3001"
        BrowseName="1:C"
    >
        <References>
          <Reference
            ReferenceType="HasComponent"
          >ns=1;i=3002</Reference>
        </References>
    </UAObjectType>
    <UAVariable
        DataType="LocalizedText"
        NodeId="ns=1;i=3002"
        BrowseName="1:CityTown"
        ParentNodeId="ns=1;i=3001"
      >
        <References>
          <Reference
            ReferenceType="HasModellingRule"
          >i=80</Reference>
          <Reference
            ReferenceType="HasTypeDefinition"
          >i=68</Reference>
        </References>
    </UAVariable>
</UANodeSet>"""
            ),
        }

        parsing, error = opcua_parse.parse(spec_impls=spec_impls)

        assert error is None, f"Expected no error, but got: {error}"
        assert parsing is not None

        self.assertEqual(
            """\
[
  Nodeset(
    implementation_key=base_nodeset.xml,
    namespaces=["ModelA", "ModelB"],
    models=[
      Model(
        uri="ModelA",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          ),
          RequiredModel(
            uri="ModelB",
            version="1.0.0"
          )
        ]
      )
    ],
    object_types=[]
  ),
  Nodeset(
    implementation_key=external_models/ModelB,
    namespaces=["ModelB", "ModelC"],
    models=[
      Model(
        uri="ModelB",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          ),
          RequiredModel(
            uri="ModelC",
            version="1.0.0"
          )
        ]
      )
    ],
    object_types=[
      ObjectType(
        identifier=2001,
        browse_name="B",
        namespace="ModelB",
        components=[
          Component(
            identifier=2002,
            namespace="ModelB"
          )
        ],
        properties=[]
      )
    ]
  ),
  Nodeset(
    implementation_key=external_models/ModelC,
    namespaces=["ModelC"],
    models=[
      Model(
        uri="ModelC",
        version="1.0.0",
        required_models=[
          RequiredModel(
            uri="http://opcfoundation.org/UA/",
            version="1.04.10"
          )
        ]
      )
    ],
    object_types=[
      ObjectType(
        identifier=3001,
        browse_name="C",
        namespace="ModelC",
        components=[
          Component(
            identifier=3002,
            namespace="ModelC"
          )
        ],
        properties=[]
      )
    ]
  )
]""",
            opcua_parse.dump_nodesets(parsing.nodesets),
        )


if __name__ == "__main__":
    unittest.main()
