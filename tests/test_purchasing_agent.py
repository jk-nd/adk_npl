"""
Test Purchasing Agent with NPL Integration

Tests the purchasing agent's ability to:
1. Authenticate with Keycloak (purchasing realm)
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
    print("Testing Purchasing Agent (Acme Corp)")
    print("Realm: purchasing | Organization: Acme Corp | Department: Procurement")
    print("=" * 80)
    
    config = NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="purchasing",
        keycloak_client_id="purchasing",
        credentials={
            "username": "purchasing_agent",
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
    
    print("\n1. Authenticating with Keycloak (purchasing realm)...")
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
    print("\n3. Creating FundCompany (as Purchasing Agent)...")
    
    try:
        client = NPLClient(config.engine_url, token)
        
        result = client.create_protocol(
            package="fund_management",
            protocol_name="FundCompany",
            parties={},
            data={
                "data": {
                    "broker": "ACME_BROKER",
                    "handlGr": "GR001",
                    "zrnr": "ZR001",
                    "ktart": "ART001",
                    "ktwrg": "WRG001",
                    "ktlfnr": "LF001",
                    "dpid": "DP001",
                    "boepla": "BOEPLA001",
                    "name": "Acme Corp Fund Management",
                    "tel": "+1-555-0100",
                    "fax": "+1-555-0101",
                    "uemRef": "UEM001",
                    "xml": "Y",
                    "accNr": "ACC001",
                    "inveRef": "INV001",
                    "inveSave": "SAVE001",
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


async def test_purchasing_agent_creation(config: NPLConfig):
    """Test creating the full purchasing agent with NPL tools."""
    print("\n4. Creating Purchasing Agent with NPL tools...")
    
    try:
        from purchasing_agent import create_purchasing_agent
        
        agent = await create_purchasing_agent(
            config=config,
            agent_id="test_001",
            budget=50000.0,
            requirements="Procurement of fund management services",
            constraints={"max_delivery_days": 30},
            strategy="Negotiate for best value while maintaining quality"
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
    agent = await test_purchasing_agent_creation(config)
    
    print("\n" + "=" * 80)
    print("✅ Purchasing Agent test complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
