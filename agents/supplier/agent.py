"""
Supplier Agent configuration for ADK

This creates the agent instance that ADK web/run commands will use.
"""

import os
import asyncio
import nest_asyncio
from dotenv import load_dotenv

from adk_npl import NPLConfig
from supplier_agent import create_supplier_agent

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

load_dotenv()


# Configuration from environment
config = NPLConfig(
    engine_url=os.getenv("NPL_ENGINE_URL", "http://localhost:12000"),
    keycloak_url=os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000"),
    keycloak_realm="supplier",
    keycloak_client_id="supplier",
    credentials={
        "username": "supplier_agent",
        "password": os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")
    }
)


def _create_agent_sync():
    """Create the supplier agent synchronously using nested loop support"""
    print("🔄 Initializing Supplier Agent (synchronously)...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            agent = loop.run_until_complete(create_supplier_agent(
                config=config,
                agent_id="supplier_001",
                min_price=15.0,
                inventory={"widgets": 5000, "gadgets": 2000},
                capacity={"max_quantity": 10000, "min_lead_time": 14},
                strategy="Maximize margin while staying competitive",
                include_npl_tools=True,
            ))
        else:
            agent = asyncio.run(create_supplier_agent(
                config=config,
                agent_id="supplier_001",
                min_price=15.0,
                inventory={"widgets": 5000, "gadgets": 2000},
                capacity={"max_quantity": 10000, "min_lead_time": 14},
                strategy="Maximize margin while staying competitive",
                include_npl_tools=True,
            ))
            
        print(f"✅ Supplier Agent ready with {len(agent.tools)} tools")
        return agent
    except Exception as e:
        print(f"❌ Error initializing Supplier Agent: {e}")
        from google.adk.agents import LlmAgent
    return LlmAgent(
        model="gemini-2.0-flash",
            name="SupplierAgent_supplier_001",
            instructions=f"I am a supplier agent. Initialization failed: {e}",
            tools=[]
        )


# Initialize immediately
root_agent = _create_agent_sync()

