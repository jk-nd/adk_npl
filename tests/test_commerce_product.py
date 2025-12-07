import os
import pytest

from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth


@pytest.mark.integration
def test_create_product_via_api():
    """
    Validate that the commerce Product protocol can be instantiated via NPL API.
    Uses supplier_agent credentials (supplier realm) and relies on rules.yml
    to extract party claims for the seller role.
    """
    engine_url = os.getenv("NPL_ENGINE_URL", "http://localhost:12000")
    keycloak_url = os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000")
    password = os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")

    config = NPLConfig(
        engine_url=engine_url,
        keycloak_url=keycloak_url,
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={"username": "supplier_agent", "password": password},
    )

    # Authenticate
    auth = KeycloakAuth(
        keycloak_url=config.keycloak_url,
        realm=config.keycloak_realm,
        client_id=config.keycloak_client_id,
        username=config.credentials["username"],
        password=config.credentials["password"],
    )
    import asyncio
    token = asyncio.run(auth.authenticate())

    client = NPLClient(config.engine_url, token)

    # Create Product (explicit @parties, no rules)
    payload = {
        "name": "Widget Batch",
        "description": "100 standard widgets",
        "sku": "WGT-100",
        "gtin": None,
        "brand": None,
        "category": "Widgets",
        "itemCondition": "NewCondition",
    }

    resp = client.create_protocol(
        package="commerce",
        protocol_name="Product",
        parties={
            "seller": {
                "claims": {
                    "organization": ["Supplier Inc"],
                    "department": ["Sales"]
                }
            }
        },
        data=payload,
    )

    assert resp, "No response from Product create"
    proto_id = resp.get("@id") or resp.get("id") or resp.get("instance") or resp.get("uuid")
    assert proto_id, f"Unexpected response: {resp}"


