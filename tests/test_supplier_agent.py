"""
Test Supplier Agent with NPL Integration

Tests the supplier agent's ability to:
1. Authenticate with Keycloak (supplier realm)
2. Discover NPL tools dynamically
3. Create protocol instances
"""
import asyncio
import logging
from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth
from adk_npl.tools import NPLToolGenerator
from dotenv import load_dotenv
import base64
import json
import os

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_authentication():
    """Test Keycloak authentication and token claims."""
    print("=" * 80)
    print("Testing Supplier Agent (Supplier Inc)")
    print("Realm: supplier | Organization: Supplier Inc | Department: Sales")
    print("=" * 80)
    
    config = NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={
            "username": "supplier_agent",
            "password": os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")
        }
    )
    
    auth = KeycloakAuth(
        keycloak_url=config.keycloak_url,
        realm=config.keycloak_realm,
        client_id=config.keycloak_client_id,
        username=config.credentials["username"],
        password=config.credentials["password"]
    )
    
    print("\n1. Authenticating with Keycloak (supplier realm)...")
    try:
        token = await auth.authenticate()
        print(f"✅ Authenticated as {config.credentials['username']}")
        
        # Decode token to show claims
        payload = token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = json.loads(base64.b64decode(payload))
        
        print(f"\n   Token Claims:")
        print(f"   - Issuer: {decoded.get('iss')}")
        print(f"   - Organization: {decoded.get('organization')}")
        print(f"   - Department: {decoded.get('department')}")
        print(f"   - Subject: {decoded.get('sub')}")
        
        return config, token
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None, None


async def test_npl_tools(config: NPLConfig, token: str):
    """Test NPL tool discovery and generation."""
    print("\n2. Discovering NPL tools...")
    
    try:
        client = NPLClient(config.engine_url, token)
        generator = NPLToolGenerator(client)
        tools = await generator.generate_tools()
        
        print(f"✅ Discovered {len(tools)} NPL tools:")
        for tool in tools[:5]:  # Show first 5
            print(f"   - {tool.func.__name__}")
        if len(tools) > 5:
            print(f"   ... and {len(tools) - 5} more")
        
        return tools
        
    except Exception as e:
        print(f"❌ Tool discovery failed: {e}")
        return []


async def test_protocol_creation(config: NPLConfig, token: str):
    """Test creating a FundCompany protocol instance."""
    print("\n3. Creating FundCompany (as Supplier Agent)...")
    
    try:
        client = NPLClient(config.engine_url, token)
        
        result = client.create_protocol(
            package="fund_management",
            protocol_name="FundCompany",
            parties={},
            data={
                "data": {
                    "broker": "SUPPLIER_BROKER",
                    "handlGr": "GR002",
                    "zrnr": "ZR002",
                    "ktart": "ART002",
                    "ktwrg": "WRG002",
                    "ktlfnr": "LF002",
                    "dpid": "DP002",
                    "boepla": "BOEPLA002",
                    "name": "Supplier Inc Fund Services",
                    "tel": "+1-555-0200",
                    "fax": "+1-555-0201",
                    "uemRef": "UEM002",
                    "xml": "Y",
                    "accNr": "ACC002",
                    "inveRef": "INV002",
                    "inveSave": "SAVE002",
                    "gtca": "Y",
                    "wrgSenden": "N",
                    "productTypes": []
                }
            }
        )
        
        name = result.get('data', {}).get('name', 'Unknown')
        instance_id = result.get('id', 'N/A')
        print(f"✅ Created FundCompany: '{name}'")
        print(f"   Instance ID: {instance_id}")
        
        return result
        
    except Exception as e:
        print(f"❌ Failed to create FundCompany: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_supplier_agent_creation(config: NPLConfig):
    """Test creating the full supplier agent with NPL tools."""
    print("\n4. Creating Supplier Agent with NPL tools...")
    
    try:
        from supplier_agent import create_supplier_agent
        
        agent = await create_supplier_agent(
            config=config,
            agent_id="supplier_001",
            min_price=15.0,
            inventory={"widgets": 5000, "gadgets": 2000},
            capacity={"max_quantity": 10000, "min_lead_time": 14},
            strategy="Maximize margin while staying competitive"
        )
        
        print(f"✅ Created agent: {agent.name}")
        print(f"   Model: {agent.model}")
        print(f"   Tools: {len(agent.tools)}")
        
        # List tool names
        for tool in agent.tools[:8]:
            print(f"   - {tool.func.__name__}")
        if len(agent.tools) > 8:
            print(f"   ... and {len(agent.tools) - 8} more")
        
        return agent
        
    except Exception as e:
        print(f"❌ Failed to create agent: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Run all tests."""
    # Test 1: Authentication
    config, token = await test_authentication()
    if not token:
        print("\n❌ Cannot continue without authentication")
        return
    
    # Test 2: NPL Tool Discovery
    tools = await test_npl_tools(config, token)
    
    # Test 3: Protocol Creation
    result = await test_protocol_creation(config, token)
    
    # Test 4: Full Agent Creation
    agent = await test_supplier_agent_creation(config)
    
    print("\n" + "=" * 80)
    print("✅ Supplier Agent test complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
