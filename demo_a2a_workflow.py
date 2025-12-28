#!/usr/bin/env python3
"""
A2A (Agent-to-Agent) Demo using Google ADK's A2A Protocol

This demo shows true agent-to-agent communication where:
- Buyer and Supplier agents run as separate A2A servers
- Agents communicate directly with each other via A2A protocol
- NPL governance still applies to all business actions

Architecture:
  ┌─────────────────┐    A2A Protocol    ┌─────────────────┐
  │  Buyer Agent    │◄──────────────────►│ Supplier Agent  │
  │  (Port 8010)    │                    │  (Port 8011)    │
  └────────┬────────┘                    └────────┬────────┘
           │                                      │
           └──────────────┬───────────────────────┘
                          ▼
                 ┌─────────────────┐
                 │   NPL Engine    │
                 │  (Port 12000)   │
                 └─────────────────┘
"""

import asyncio
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# A2A imports
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import FunctionTool

import uvicorn

# Local imports
from adk_npl import NPLConfig, get_activity_logger
from purchasing_agent import create_purchasing_agent
from supplier_agent import create_supplier_agent

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ENGINE_URL = os.getenv("ENGINE_URL", "http://localhost:12000")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:11000")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "Welcome123")

BUYER_PORT = 8010
SUPPLIER_PORT = 8011

activity_logger = get_activity_logger()


def create_buyer_agent_card() -> AgentCard:
    """Create AgentCard for the Buyer agent."""
    return AgentCard(
        name="BuyerAgent",
        description="Purchasing agent for Acme Corp. Evaluates offers and places orders.",
        url=f"http://localhost:{BUYER_PORT}",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="procurement",
                name="Procurement",
                description="Evaluate supplier offers, negotiate terms, and place purchase orders",
                tags=["purchasing", "procurement", "orders"]
            )
        ]
    )


def create_supplier_agent_card() -> AgentCard:
    """Create AgentCard for the Supplier agent."""
    return AgentCard(
        name="SupplierAgent",
        description="Sales agent for Supplier Inc. Creates offers and fulfills orders.",
        url=f"http://localhost:{SUPPLIER_PORT}",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="sales",
                name="Sales",
                description="Create product offers, negotiate pricing, and ship orders",
                tags=["sales", "offers", "shipping"]
            )
        ]
    )


async def create_a2a_buyer_agent(supplier_card: AgentCard) -> LlmAgent:
    """Create buyer agent with A2A capability to call supplier."""
    config = NPLConfig(
        engine_url=ENGINE_URL,
        keycloak_url=KEYCLOAK_URL,
        keycloak_realm="purchasing",
        keycloak_client_id="purchasing",
        credentials={"username": "purchasing_agent", "password": DEFAULT_PASSWORD}
    )
    
    # Create base agent with NPL tools
    base_agent = await create_purchasing_agent(
        config=config,
        agent_id="buyer_a2a",
        budget=20000.0,
        requirements="Industrial equipment",
        strategy="Negotiate best price while maintaining quality"
    )
    
    # Add RemoteA2aAgent as a sub-agent to call supplier
    supplier_remote = RemoteA2aAgent(
        name="SupplierAgent",
        agent_card=supplier_card,
        description="Remote supplier agent - delegate tasks to negotiate and request offers"
    )
    
    # Create enhanced agent with A2A capability via sub_agents
    enhanced_agent = LlmAgent(
        model="gemini-2.0-flash",
        name="BuyerAgent_A2A",
        description="Buyer agent with A2A capability to communicate with supplier",
        instruction=base_agent.instruction + """

## A2A Communication
You can delegate tasks to the SupplierAgent sub-agent to:
- Request product information
- Negotiate pricing
- Confirm order terms

The SupplierAgent is a remote agent you can transfer control to for supplier-related tasks.
After agreeing on terms, use the NPL tools to finalize the transaction.
""",
        tools=list(base_agent.tools),
        sub_agents=[supplier_remote]
    )
    
    return enhanced_agent


async def create_a2a_supplier_agent(buyer_card: AgentCard) -> LlmAgent:
    """Create supplier agent with A2A capability to call buyer."""
    config = NPLConfig(
        engine_url=ENGINE_URL,
        keycloak_url=KEYCLOAK_URL,
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={"username": "supplier_agent", "password": DEFAULT_PASSWORD}
    )
    
    # Create base agent with NPL tools
    base_agent = await create_supplier_agent(
        config=config,
        agent_id="supplier_a2a",
        min_price=900.0,
        inventory={"Industrial Pump X": 200},
        strategy="Maximize revenue while building long-term relationships"
    )
    
    # Add RemoteA2aAgent as a sub-agent to call buyer
    buyer_remote = RemoteA2aAgent(
        name="BuyerAgent",
        agent_card=buyer_card,
        description="Remote buyer agent - delegate tasks to send offers and confirm order details"
    )
    
    # Create enhanced agent with A2A capability via sub_agents
    enhanced_agent = LlmAgent(
        model="gemini-2.0-flash",
        name="SupplierAgent_A2A",
        description="Supplier agent with A2A capability to communicate with buyer",
        instruction=base_agent.instruction + """

## A2A Communication
You can delegate tasks to the BuyerAgent sub-agent to:
- Present product offers
- Respond to price negotiations
- Confirm shipment details

The BuyerAgent is a remote agent you can transfer control to for buyer-related tasks.
After agreeing on terms, use the NPL tools to finalize the transaction.
""",
        tools=list(base_agent.tools),
        sub_agents=[buyer_remote]
    )
    
    return enhanced_agent


def run_a2a_server(app, port: int, name: str):
    """Run an A2A server in a thread."""
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    logger.info(f"Starting {name} A2A server on port {port}")
    server.run()


async def main():
    print("=" * 80)
    print("◇ A2A (Agent-to-Agent) Communication Demo")
    print("=" * 80)
    print()
    print("This demo shows true agent-to-agent communication using Google ADK's A2A protocol.")
    print()
    
    # Create agent cards
    buyer_card = create_buyer_agent_card()
    supplier_card = create_supplier_agent_card()
    
    print(f"📋 Buyer AgentCard: {buyer_card.url}")
    print(f"📋 Supplier AgentCard: {supplier_card.url}")
    print()
    
    # Create agents with A2A capabilities
    print("🔧 Creating agents with A2A capabilities...")
    
    session_service = InMemorySessionService()
    
    # Create agents
    buyer_agent = await create_a2a_buyer_agent(supplier_card)
    supplier_agent = await create_a2a_supplier_agent(buyer_card)
    
    # Create runners
    buyer_runner = Runner(
        agent=buyer_agent,
        session_service=session_service,
        app_name="buyer_a2a"
    )
    supplier_runner = Runner(
        agent=supplier_agent,
        session_service=session_service,
        app_name="supplier_a2a"
    )
    
    # Create A2A executors and request handlers
    buyer_executor = A2aAgentExecutor(runner=buyer_runner)
    supplier_executor = A2aAgentExecutor(runner=supplier_runner)
    
    buyer_task_store = InMemoryTaskStore()
    supplier_task_store = InMemoryTaskStore()
    
    buyer_handler = DefaultRequestHandler(
        agent_executor=buyer_executor,
        task_store=buyer_task_store
    )
    supplier_handler = DefaultRequestHandler(
        agent_executor=supplier_executor,
        task_store=supplier_task_store
    )
    
    # Create A2A Starlette apps
    buyer_app = A2AStarletteApplication(
        agent_card=buyer_card,
        http_handler=buyer_handler
    )
    supplier_app = A2AStarletteApplication(
        agent_card=supplier_card,
        http_handler=supplier_handler
    )
    
    print("   ✅ Buyer and Supplier A2A agents ready")
    print()
    
    # Start servers in background threads
    print("🚀 Starting A2A servers...")
    buyer_thread = threading.Thread(
        target=run_a2a_server,
        args=(buyer_app.build(), BUYER_PORT, "Buyer"),
        daemon=True
    )
    supplier_thread = threading.Thread(
        target=run_a2a_server,
        args=(supplier_app.build(), SUPPLIER_PORT, "Supplier"),
        daemon=True
    )
    
    buyer_thread.start()
    supplier_thread.start()
    
    # Wait for servers to start
    await asyncio.sleep(2)
    print(f"   ✅ Buyer A2A server running at http://localhost:{BUYER_PORT}")
    print(f"   ✅ Supplier A2A server running at http://localhost:{SUPPLIER_PORT}")
    print()
    
    # Now run a negotiation via A2A
    print("=" * 80)
    print("📣 Starting A2A Negotiation")
    print("=" * 80)
    print()
    
    # Log A2A demo start
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="system",
        action="a2a_negotiation_start",
        details={
            "buyer_url": f"http://localhost:{BUYER_PORT}",
            "supplier_url": f"http://localhost:{SUPPLIER_PORT}"
        },
        level="info"
    )
    
    # Create a session for the buyer to start the conversation
    await session_service.create_session(
        app_name="buyer_a2a",
        user_id="buyer_user",
        session_id="negotiation_session"
    )
    
    from google.genai import types
    
    # Buyer initiates conversation with supplier
    print("🛒 Buyer agent initiating contact with Supplier...")
    
    initial_prompt = """
I need to procure Industrial Pump X units. Please:
1. Contact the SupplierAgent to request a quote for 10 units
2. Negotiate for the best price you can get
3. Once terms are agreed, use NPL tools to create the order

Start by sending a message to SupplierAgent asking about Industrial Pump X availability and pricing.
"""
    
    content = types.Content(role="user", parts=[types.Part(text=initial_prompt)])
    
    print("   Sending initial prompt to Buyer agent...")
    print()
    
    # Log initial prompt
    activity_logger.log_agent_message(
        from_agent="user",
        to_agent="buyer_agent",
        message=initial_prompt.strip(),
        message_type="a2a_initiation"
    )
    
    async for event in buyer_runner.run_async(
        new_message=content,
        user_id="buyer_user",
        session_id="negotiation_session"
    ):
        event_type = event.__class__.__name__
        
        if hasattr(event, "content") and hasattr(event.content, "parts"):
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    print(f"   💬 Buyer: {part.text}")
                    # Log buyer's text response
                    activity_logger.log_agent_reasoning(
                        actor="buyer_agent",
                        reasoning=part.text,
                        context={"step": "a2a_negotiation"}
                    )
                if hasattr(part, "function_call") and part.function_call:
                    func = part.function_call
                    print(f"   🔧 Tool call: {func.name}")
                    # Log tool call - especially A2A transfers
                    if "transfer" in func.name.lower():
                        activity_logger.log_event(
                            event_type="a2a_transfer",
                            actor="buyer_agent",
                            action=f"transfer_to_supplier",
                            details={"tool": func.name},
                            level="info"
                        )
                    else:
                        activity_logger.log_agent_action(
                            agent="buyer_agent",
                            action=func.name,
                            protocol="a2a",
                            protocol_id=None,
                            outcome="called"
                        )
                if hasattr(part, "function_response") and part.function_response:
                    resp = part.function_response
                    print(f"   📨 Response from: {resp.name}")
                    # Log A2A response
                    if "transfer" in resp.name.lower() or "agent" in resp.name.lower():
                        activity_logger.log_event(
                            event_type="a2a_response",
                            actor="supplier_agent",
                            action="a2a_message_received",
                            details={"from_tool": resp.name},
                            level="info"
                        )
    
    # Log demo complete
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="system",
        action="a2a_negotiation_complete",
        details={"status": "success"},
        level="info"
    )
    
    print()
    print("=" * 80)
    print("✅ A2A Negotiation Demo Complete")
    print("=" * 80)
    print()
    print("What we demonstrated:")
    print("  1. Buyer and Supplier agents running as A2A servers")
    print("  2. Direct agent-to-agent communication via A2A protocol")
    print("  3. Transparent message exchange visible in activity log")
    print()
    print(f"📝 Activity log: logs/{activity_logger.log_file.name}")
    print()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())

