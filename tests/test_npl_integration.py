"""
NPL Engine Integration Tests

Tests for actual NPL Engine interactions:
- Authentication with Keycloak
- OpenAPI spec fetching
- Tool generation from specs
- Protocol creation
- Error handling

Run with: pytest tests/test_npl_integration.py -v
"""
import pytest
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from adk_npl.config import NPLConfig
from adk_npl.auth import KeycloakAuth
from adk_npl.client import NPLClient
from adk_npl.tools import NPLToolGenerator


# ============================================================================
# Configuration
# ============================================================================

BUYER_CONFIG = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="purchasing",
    keycloak_client_id="purchasing",
    credentials={"username": "purchasing_agent", "password": "Welcome123"}
)

SUPPLIER_CONFIG = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="supplier",
    keycloak_client_id="supplier",
    credentials={"username": "supplier_agent", "password": "Welcome123"}
)


async def get_supplier_client():
    """Helper to get authenticated supplier client."""
    auth = KeycloakAuth(
        keycloak_url=SUPPLIER_CONFIG.keycloak_url,
        realm=SUPPLIER_CONFIG.keycloak_realm,
        client_id=SUPPLIER_CONFIG.keycloak_client_id,
        username=SUPPLIER_CONFIG.credentials["username"],
        password=SUPPLIER_CONFIG.credentials["password"]
    )
    token = await auth.authenticate()
    return NPLClient(base_url=SUPPLIER_CONFIG.engine_url, auth_token=token)


# ============================================================================
# Authentication Tests
# ============================================================================

@pytest.mark.asyncio
async def test_buyer_authentication():
    """Test: Buyer agent can authenticate."""
    auth = KeycloakAuth(
        keycloak_url=BUYER_CONFIG.keycloak_url,
        realm=BUYER_CONFIG.keycloak_realm,
        client_id=BUYER_CONFIG.keycloak_client_id,
        username=BUYER_CONFIG.credentials["username"],
        password=BUYER_CONFIG.credentials["password"]
    )
    token = await auth.authenticate()
    
    assert token is not None
    assert len(token) > 100, "Token should be a valid JWT"


@pytest.mark.asyncio
async def test_supplier_authentication():
    """Test: Supplier agent can authenticate."""
    auth = KeycloakAuth(
        keycloak_url=SUPPLIER_CONFIG.keycloak_url,
        realm=SUPPLIER_CONFIG.keycloak_realm,
        client_id=SUPPLIER_CONFIG.keycloak_client_id,
        username=SUPPLIER_CONFIG.credentials["username"],
        password=SUPPLIER_CONFIG.credentials["password"]
    )
    token = await auth.authenticate()
    
    assert token is not None
    assert len(token) > 100, "Token should be a valid JWT"


# ============================================================================
# OpenAPI Spec Tests
# ============================================================================

@pytest.mark.asyncio
async def test_fetch_commerce_spec():
    """Test: Can fetch commerce package OpenAPI spec."""
    client = await get_supplier_client()
    spec = client.get_openapi_spec("commerce")
    
    assert "paths" in spec, "Spec should have paths"
    assert "components" in spec, "Spec should have components"
    assert len(spec["paths"]) > 5, "Commerce package should have multiple endpoints"


@pytest.mark.asyncio
async def test_spec_contains_schemas():
    """Test: Spec contains protocol schemas."""
    client = await get_supplier_client()
    spec = client.get_openapi_spec("commerce")
    
    schemas = spec.get("components", {}).get("schemas", {})
    assert len(schemas) > 0, "Should have schemas"
    
    schema_names = list(schemas.keys())
    has_product = any("Product" in n for n in schema_names)
    has_offer = any("Offer" in n for n in schema_names)
    
    assert has_product, f"Should have Product schema. Found: {schema_names[:10]}"
    assert has_offer, f"Should have Offer schema. Found: {schema_names[:10]}"


# ============================================================================
# Tool Generation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_generate_commerce_tools():
    """Test: Can generate tools from commerce package."""
    client = await get_supplier_client()
    generator = NPLToolGenerator(npl_client=client, protocol_memory=None)
    tools = await generator.generate_tools(packages=["commerce"])
    
    assert len(tools) > 10, f"Should generate multiple tools. Got: {len(tools)}"
    
    tool_names = [t.name for t in tools]
    has_product_create = any("Product_create" in n for n in tool_names)
    has_offer_create = any("Offer_create" in n for n in tool_names)
    
    assert has_product_create, f"Should have Product_create. Tools: {tool_names[:5]}"
    assert has_offer_create, f"Should have Offer_create. Tools: {tool_names[:5]}"


@pytest.mark.asyncio
async def test_tool_descriptions_have_enum_values():
    """Test: Tool descriptions include enum values."""
    client = await get_supplier_client()
    generator = NPLToolGenerator(npl_client=client, protocol_memory=None)
    tools = await generator.generate_tools(packages=["commerce"])
    
    # Find Product_create tool
    product_tool = None
    for t in tools:
        if "Product_create" in t.name:
            product_tool = t
            break
    
    assert product_tool is not None, "Should have Product_create tool"
    
    desc = product_tool.description
    assert "NewCondition" in desc, "Should include enum value NewCondition"
    assert "UsedCondition" in desc, "Should include enum value UsedCondition"


@pytest.mark.asyncio
async def test_tool_descriptions_have_party_info():
    """Test: Tool descriptions include party information."""
    client = await get_supplier_client()
    generator = NPLToolGenerator(npl_client=client, protocol_memory=None)
    tools = await generator.generate_tools(packages=["commerce"])
    
    # Find Product_create tool
    product_tool = None
    for t in tools:
        if "Product_create" in t.name:
            product_tool = t
            break
    
    assert product_tool is not None
    
    desc = product_tool.description.lower()
    assert "seller" in desc, "Should mention seller party"


# ============================================================================
# Protocol Creation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_product():
    """Test: Can create a Product protocol instance."""
    client = await get_supplier_client()
    unique_sku = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    
    parties = {
        "seller": {
            "claims": {
                "email": ["supplier_agent@supplier.com"]
            }
        }
    }
    
    data = {
        "name": "Test Product",
        "description": "Automated test product",
        "sku": unique_sku,
        "gtin": None,  # Required field, can be null
        "brand": "TestBrand",
        "category": "Testing",
        "itemCondition": "NewCondition"
    }
    
    result = client.create_protocol("commerce", "Product", parties, data)
    
    assert "@id" in result, "Should return protocol ID"
    assert result["sku"] == unique_sku, "SKU should match"


@pytest.mark.asyncio
async def test_invalid_creation_returns_error():
    """Test: Invalid creation returns informative error."""
    client = await get_supplier_client()
    
    parties = {
        "seller": {
            "claims": {
                "email": ["supplier_agent@supplier.com"]
            }
        }
    }
    
    # Missing required 'name' field
    invalid_data = {
        "description": "Test",
        "sku": "INVALID-001",
        "itemCondition": "NewCondition"
    }
    
    with pytest.raises(Exception) as exc_info:
        client.create_protocol("commerce", "Product", parties, invalid_data)
    
    error_msg = str(exc_info.value)
    assert "400" in error_msg or "name" in error_msg.lower() or "required" in error_msg.lower(), \
        f"Error should be informative. Got: {error_msg[:200]}"


@pytest.mark.asyncio
async def test_wrong_party_format_returns_error():
    """Test: Wrong party format returns clear error."""
    client = await get_supplier_client()
    
    # Using 'entity' instead of 'claims' - common mistake
    wrong_parties = {
        "seller": {
            "entity": {  # Wrong! Should be "claims"
                "email": ["supplier_agent@supplier.com"]
            }
        }
    }
    
    data = {
        "name": "Test",
        "sku": "TEST-001",
        "itemCondition": "NewCondition"
    }
    
    with pytest.raises(Exception) as exc_info:
        client.create_protocol("commerce", "Product", wrong_parties, data)
    
    error_msg = str(exc_info.value)
    assert "400" in error_msg or "claim" in error_msg.lower(), \
        f"Error should mention claims. Got: {error_msg[:200]}"


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_invalid_package_error():
    """Test: Invalid package returns informative error."""
    client = await get_supplier_client()
    
    with pytest.raises(Exception) as exc_info:
        client.get_openapi_spec("nonexistent_package")
    
    error_msg = str(exc_info.value)
    assert "404" in error_msg or "not found" in error_msg.lower(), \
        f"Should indicate package not found. Got: {error_msg[:100]}"


@pytest.mark.asyncio
async def test_invalid_protocol_error():
    """Test: Invalid protocol returns error."""
    client = await get_supplier_client()
    
    parties = {"seller": {"claims": {"email": ["test@test.com"]}}}
    data = {"name": "Test"}
    
    with pytest.raises(Exception):
        client.create_protocol("commerce", "NonExistentProtocol", parties, data)


# ============================================================================
# Run tests directly
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
