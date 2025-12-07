import os
import asyncio
import nest_asyncio
from dotenv import load_dotenv

from adk_npl import NPLConfig
from purchasing_agent import create_purchasing_agent

# Apply nest_asyncio to allow nested event loops
# This fixes "asyncio.run() cannot be called from a running event loop"
nest_asyncio.apply()

load_dotenv()


# Configuration from environment
config = NPLConfig(
    engine_url=os.getenv("NPL_ENGINE_URL", "http://localhost:12000"),
    keycloak_url=os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000"),
    keycloak_realm="purchasing",
    keycloak_client_id="purchasing",
    credentials={
        "username": "purchasing_agent",
        "password": os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")
    }
)


def _create_agent_sync():
    """Create the purchasing agent synchronously using nested loop support"""
    print("🔄 Initializing Purchasing Agent (synchronously)...")
    try:
        # We can now safely use asyncio.run or loop.run_until_complete
        # even if called from within another loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we are in a running loop, use run_until_complete on it (allowed by nest_asyncio)
            agent = loop.run_until_complete(create_purchasing_agent(
                config=config,
                agent_id="purchasing_001",
                budget=50000.0,
                requirements="Procurement of services and supplies",
                constraints={
                    "max_delivery_days": 30,
                    "quality": "Enterprise grade",
                },
                strategy="Negotiate for best value while maintaining quality",
                include_npl_tools=True,
            ))
        else:
            # Fallback for fresh threads
            agent = asyncio.run(create_purchasing_agent(
                config=config,
                agent_id="purchasing_001",
                budget=50000.0,
                requirements="Procurement of services and supplies",
                constraints={
                    "max_delivery_days": 30,
                    "quality": "Enterprise grade",
                },
                strategy="Negotiate for best value while maintaining quality",
                include_npl_tools=True,
            ))
            
        print(f"✅ Purchasing Agent ready with {len(agent.tools)} tools")
        return agent
    except Exception as e:
        print(f"❌ Error initializing Purchasing Agent: {e}")
        # Fallback to simple agent if NPL fails
        from google.adk.agents import LlmAgent
    return LlmAgent(
        model="gemini-2.0-flash",
            name="PurchasingAgent_purchasing_001",
            instructions=f"I am a purchasing agent. Initialization failed: {e}",
            tools=[]
        )


# Initialize immediately
root_agent = _create_agent_sync()