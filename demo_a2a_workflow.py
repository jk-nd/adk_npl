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

## CRITICAL: Do NOT create new offers during A2A negotiation!
When negotiating with the buyer:
1. Discuss pricing and terms verbally
2. DO NOT create new Product or Offer protocols during the conversation
3. The buyer will accept the existing offer after negotiation
4. Use get_protocol_id("Offer") to recall which offer you created
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
    
    # Initialize client variables for fallback scenarios
    supplier_client = None
    buyer_client = None
    
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
    import re
    import time
    from datetime import timezone, timedelta
    from adk_npl import NPLClient
    from adk_npl.auth import KeycloakAuth
    
    def _iso_now(offset_days: int = 0) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat().replace("+00:00", "Z")
    
    async def run_autonomous_agent(
        runner,
        initial_objective: str,
        user_id: str,
        session_id: str,
        agent_name: str,
        check_condition: callable,
        max_iterations: int = 10,
        poll_interval: float = 3.0
    ):
        """
        Run an agent autonomously - it monitors state and acts based on its objective.
        The agent will check state, reason, and act until the condition is met.
        
        Args:
            runner: ADK Runner for the agent
            initial_objective: The agent's goal/objective (given once, not per-turn)
            user_id: User ID for the agent
            session_id: Session ID for the agent
            agent_name: Name of the agent (for logging)
            check_condition: Async function that returns True when agent's objective is complete
            max_iterations: Maximum number of autonomous turns
            poll_interval: Seconds between state checks
        """
        activity_logger.log_agent_message(
            from_agent="system",
            to_agent=agent_name,
            message=f"Autonomous objective: {initial_objective}",
            message_type="autonomous_mode"
        )
        
        print(f"   🤖 {agent_name} running autonomously with objective...")
        
        for iteration in range(max_iterations):
            # Check if condition is already met
            if await check_condition():
                print(f"   ✅ {agent_name} objective completed")
                return True
            
            # Agent checks state and decides what to do
            prompt = f"""
{initial_objective}

Current iteration: {iteration + 1}/{max_iterations}
Continue working towards your objective. If you encounter NPL rejections, they indicate the state isn't ready yet - 
check the state and retry when appropriate.
"""
            
            response_parts = []
            tool_calls = []
            npl_errors_detected = []
            turn_start = time.time()
            
            content = types.Content(role="user", parts=[types.Part(text=prompt)])
            
            async for event in runner.run_async(
                new_message=content,
                user_id=user_id,
                session_id=session_id
            ):
                if hasattr(event, "content") and hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            response_parts.append(part.text)
                            activity_logger.log_agent_reasoning(
                                actor=agent_name,
                                reasoning=part.text,
                                context={"iteration": iteration + 1, "autonomous": True}
                            )
                        if hasattr(part, "function_call") and part.function_call:
                            func = part.function_call
                            tool_calls.append(func.name)
                            activity_logger.log_agent_action(
                                agent=agent_name,
                                action=func.name,
                                protocol="autonomous",
                                protocol_id=None,
                                outcome="called"
                            )
                        if hasattr(part, "function_response") and part.function_response:
                            resp = part.function_response
                            result = getattr(resp, "response", None)
                            # Detect NPL errors
                            if isinstance(result, dict):
                                error_msg = result.get("message") or result.get("error") or result.get("errorType")
                                if error_msg:
                                    error_lower = str(error_msg).lower()
                                    if any(keyword in error_lower for keyword in [
                                        "illegal protocol state",
                                        "current state is not",
                                        "business rule",
                                        "assertion",
                                        "runtime error",
                                        "r13", "r14", "r15"
                                    ]):
                                        npl_errors_detected.append(error_msg)
                                        print(f"   ⚠️  NPL Rejection detected: {error_msg[:100]}")
                                        activity_logger.log_event(
                                            event_type="npl_rejection",
                                            actor=agent_name,
                                            action=getattr(resp, "name", "unknown"),
                                            details={
                                                "error": error_msg,
                                                "iteration": iteration + 1
                                            },
                                            level="warning"
                                        )
            
            # Log LLM call
            total_time = (time.time() - turn_start) * 1000
            activity_logger.log_llm_call(
                model="gemini-2.0-flash",
                agent=agent_name,
                latency_ms=total_time,
                success=True,
                step="autonomous_iteration",
                tool_calls=len(tool_calls),
                iteration=iteration + 1
            )
            
            # Check if condition is now met
            if await check_condition():
                print(f"   ✅ {agent_name} objective completed after {iteration + 1} iteration(s)")
                return True
            
            # Wait before next check
            if iteration < max_iterations - 1:
                await asyncio.sleep(poll_interval)
        
        print(f"   ⚠️  {agent_name} reached max iterations without completing objective")
        return False
    
    async def run_agent_turn(runner, prompt, user_id, session_id, agent_name, step_name):
        """Run a single agent turn and log all events including LLM calls."""
        activity_logger.log_agent_message(
            from_agent="system",
            to_agent=agent_name,
            message=prompt,
            message_type=step_name
        )
        
        response_parts = []
        tool_calls = []
        tool_results = {}
        llm_call_count = 0
        
        content = types.Content(role="user", parts=[types.Part(text=prompt)])
        
        # Track LLM call timing
        turn_start = time.time()
        
        async for event in runner.run_async(
            new_message=content,
            user_id=user_id,
            session_id=session_id
        ):
            if hasattr(event, "content") and hasattr(event.content, "parts"):
                # Each content event represents an LLM response
                llm_call_count += 1
                call_time = (time.time() - turn_start) * 1000  # ms
                
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)
                        print(f"   💬 {agent_name}: {part.text[:200]}")
                        activity_logger.log_agent_reasoning(
                            actor=agent_name,
                            reasoning=part.text,
                            context={"step": step_name}
                        )
                    if hasattr(part, "function_call") and part.function_call:
                        func = part.function_call
                        tool_calls.append(func.name)
                        print(f"   🔧 Tool: {func.name}")
                        if "transfer" in func.name.lower():
                            # Log A2A transfer with timing
                            activity_logger.log_a2a_transfer(
                                from_agent=agent_name,
                                to_agent="remote_agent",
                                task=step_name,
                                success=True,
                                latency_ms=call_time
                            )
                        else:
                            activity_logger.log_agent_action(
                                agent=agent_name,
                                action=func.name,
                                protocol="npl",
                                protocol_id=None,
                                outcome="called"
                            )
                    if hasattr(part, "function_response") and part.function_response:
                        resp = part.function_response
                        name = getattr(resp, "name", "unknown")
                        result = getattr(resp, "response", None)
                        
                        # Try to parse JSON if result is a string
                        if isinstance(result, str):
                            try:
                                import json
                                parsed = json.loads(result)
                                tool_results[name] = parsed
                                result = parsed  # Use parsed for error detection
                            except:
                                tool_results[name] = result
                        else:
                            tool_results[name] = result
                        
                        # Detect NPL errors in the result
                        npl_error = None
                        if isinstance(result, dict):
                            # Check for NPL error patterns
                            error_msg = result.get("message") or result.get("error") or result.get("errorType")
                            if error_msg:
                                error_lower = str(error_msg).lower()
                                if any(keyword in error_lower for keyword in [
                                    "illegal protocol state",
                                    "current state is not",
                                    "business rule",
                                    "assertion",
                                    "runtime error",
                                    "r13", "r14", "r15"  # NPL error codes
                                ]):
                                    npl_error = error_msg
                                    print(f"   ⚠️  NPL Rejection: {name} - {error_msg[:150]}")
                                    activity_logger.log_event(
                                        event_type="npl_rejection",
                                        actor=agent_name,
                                        action=name,
                                        details={
                                            "tool": name,
                                            "error": error_msg,
                                            "step": step_name
                                        },
                                        level="warning"
                                    )
                            else:
                                # Check if result contains an ID (success case)
                                result_id = result.get("@id") or result.get("id")
                                if result_id:
                                    print(f"      → Found ID in result: {result_id}")
                        
                        if not npl_error:
                            print(f"   📨 Result: {name}")
                            if result and isinstance(result, str) and len(result) < 200:
                                print(f"      → Result preview: {result[:100]}")
                        
                        if "transfer" in name.lower() or "agent" in name.lower():
                            activity_logger.log_event(
                                event_type="a2a_response",
                                actor=f"remote_{agent_name}",
                                action="a2a_response",
                                details={"tool": name},
                                level="info"
                            )
        
        # Log LLM usage for this turn
        total_time = (time.time() - turn_start) * 1000
        activity_logger.log_llm_call(
            model="gemini-2.0-flash",
            agent=agent_name,
            latency_ms=total_time,
            success=True,
            step=step_name,
            tool_calls=len(tool_calls),
            llm_rounds=llm_call_count
        )
        
        full_text = "".join(response_parts).strip()
        
        # Extract UUID from response
        uuid_pattern = r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
        uuid_match = re.search(uuid_pattern, full_text)
        extracted_id = uuid_match.group(1) if uuid_match else None
        
        # Also check tool results for IDs
        if not extracted_id:
            for name, result in tool_results.items():
                if isinstance(result, dict):
                    for key in ["@id", "id", "protocol_id"]:
                        if key in result:
                            extracted_id = str(result[key])
                            break
                if extracted_id:
                    break
        
        return full_text, tool_calls, tool_results, extracted_id
    
    async def get_authenticated_client(realm: str, username: str) -> NPLClient:
        auth = KeycloakAuth(
            keycloak_url=KEYCLOAK_URL,
            realm=realm,
            client_id=realm,
            username=username,
            password=DEFAULT_PASSWORD
        )
        token = await auth.authenticate()
        return NPLClient(ENGINE_URL, token)
    
    # =========================================================================
    # STEP 1: Supplier creates Product (AUTONOMOUS)
    # =========================================================================
    print("📦 Step 1: Supplier creates Product...")
    
    await session_service.create_session(
        app_name="supplier_a2a",
        user_id="supplier_user",
        session_id="supplier_session"
    )
    
    product_prompt = f"""
Create a Product for "Industrial Pump X" - a high-performance industrial water pump.

Product details:
- Name: "Industrial Pump X"
- Description: "High-performance industrial water pump"
- SKU: "PUMP-X-A2A"
- GTIN: "0123456789012"
- Brand: "PumpCo"
- Category: "Industrial Equipment"
- Condition: New

Use your available NPL tools to create the product. Check the tool signatures to see what parameters are required.
Your organization is Supplier Inc, Sales department (from your base instructions).

Report the product ID after creation.
"""
    _, _, tool_results, product_id = await run_agent_turn(
        supplier_runner, product_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "product_create"
    )
    
    # Extract product ID from tool results if not in response text
    if not product_id:
        for name, result in tool_results.items():
            if isinstance(result, dict):
                product_id = result.get("@id") or result.get("id")
                if product_id:
                    break
    
    if not product_id:
        print("   ❌ Could not extract product ID - agent must report it")
        return
    
    activity_logger.log_agent_action(
        agent="supplier_agent",
        action="create_product",
        protocol="Product",
        protocol_id=product_id,
        outcome="success"
    )
    print(f"   ✅ Product created: {product_id}")
    print()
    
    # =========================================================================
    # STEP 2: Supplier creates and publishes Offer (AUTONOMOUS)
    # =========================================================================
    print("💰 Step 2: Supplier creates and publishes Offer...")
    
    offer_prompt = f"""
Create and publish an Offer for product {product_id}:

Offer terms:
- Price: $1200 per unit
- Available quantity: 100 units
- Delivery lead time: 14 days
- Valid for 30 days from now
- Buyer: Acme Corp, Procurement department

Use your NPL tools to create and publish the offer. Check tool signatures for required parameters.
Your organization is Supplier Inc, Sales department.
"""
    full_text, tool_calls, tool_results, offer_id = await run_agent_turn(
        supplier_runner, offer_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "offer_create_publish"
    )
    
    # Extract offer ID from tool results if not in response text
    if not offer_id:
        for name, result in tool_results.items():
            if isinstance(result, dict):
                # Check top level
                offer_id = result.get("@id") or result.get("id")
                if offer_id:
                    break
                # Check nested structures (e.g., if result is wrapped)
                for key, value in result.items():
                    if isinstance(value, dict):
                        offer_id = value.get("@id") or value.get("id")
                        if offer_id:
                            break
                if offer_id:
                    break
    
    # If still no ID, try to find it in the full text response with more patterns
    if not offer_id:
        # Look for UUIDs in various formats
        uuid_patterns = [
            r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
            r'offer[:\s]+([a-f0-9-]{36})',
            r'ID[:\s]+([a-f0-9-]{36})',
            r'id[:\s]+([a-f0-9-]{36})'
        ]
        for pattern in uuid_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                offer_id = match.group(1) if match.groups() else match.group(0)
                break
    
    if not offer_id:
        print("   ❌ Could not extract offer ID - agent must report it")
        print(f"   Tool results keys: {list(tool_results.keys())}")
        print(f"   Tool calls: {tool_calls}")
        if tool_results:
            print(f"   Sample result: {list(tool_results.values())[0] if tool_results.values() else 'None'}")
        print(f"   Agent response preview: {full_text[:500] if full_text else 'No response'}")
        return
    
    # Verify offer was published
    supplier_client = await get_authenticated_client("supplier", "supplier_agent")
    offer_data = supplier_client.get_instance(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id
    )
    offer_state = offer_data.get("@state") or offer_data.get("state")
    
    if offer_state == "published":
        activity_logger.log_agent_action(
            agent="supplier_agent",
            action="create_offer",
            protocol="Offer",
            protocol_id=offer_id,
            outcome="success"
        )
        activity_logger.log_state_transition(
            protocol="Offer",
            protocol_id=offer_id,
            from_state="draft",
            to_state="published",
            triggered_by="supplier_agent"
        )
        print(f"   ✅ Offer created and published: {offer_id}")
    else:
        print(f"   ⚠️  Offer state is {offer_state}, expected published")
    print()
    
    # =========================================================================
    # STEP 3: A2A Negotiation - Buyer contacts Supplier
    # =========================================================================
    print("=" * 80)
    print("🤝 Step 3: A2A Negotiation - Buyer contacts Supplier")
    print("=" * 80)
    print()
    
    a2a_prompt = f"""
I want to purchase Industrial Pump X. The offer ID is: {offer_id}

IMPORTANT: Use remember_protocol("Offer", "{offer_id}", "published", "buyer") to store this offer ID in your memory first!

Then contact the SupplierAgent to negotiate terms (volume discount, better price, etc.) using the transfer_to_agent tool.

After negotiation is complete, you MUST accept the offer to proceed:
1. Use get_protocol_id("Offer") to recall the offer ID from memory
2. Check the offer state with npl_commerce_Offer_get
3. If state is "published", accept it with npl_commerce_Offer_accept(instance_id="{offer_id}", party="buyer")

DO NOT create new offers during negotiation - just negotiate and then accept the existing offer {offer_id}.
If the supplier mentions a different offer ID, use remember_protocol to store it, then accept that one.
"""
    
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="buyer_agent",
        action="a2a_negotiation_start",
        details={"offer_id": offer_id},
        level="info"
    )
    
    full_text, a2a_tools, tool_results, _ = await run_agent_turn(
        buyer_runner, a2a_prompt, "buyer_user", "negotiation_session",
        "buyer_agent", "a2a_negotiation"
    )
    
    # Check if agent tried to accept the offer by looking at tool calls
    accepted_offer_id = offer_id
    if "accept" in str(a2a_tools).lower() or "npl_commerce_Offer_accept" in str(a2a_tools):
        print("   ℹ️  Buyer agent attempted to accept offer")
        # Check tool results for any new offer IDs if supplier created one
        for name, result in tool_results.items():
            if isinstance(result, dict):
                new_offer_id = result.get("@id") or result.get("id")
                if new_offer_id and new_offer_id != offer_id:
                    print(f"   ℹ️  Found new offer ID in results: {new_offer_id}")
                    accepted_offer_id = new_offer_id
    
    # Check if offer was accepted by the agent
    buyer_client = await get_authenticated_client("purchasing", "purchasing_agent")
    offer_state = None
    try:
        offer_data = buyer_client.get_instance(
            package="commerce",
            protocol_name="Offer",
            instance_id=accepted_offer_id
        )
        offer_state = offer_data.get("@state") or offer_data.get("state")
    except Exception as e:
        # Offer might not be accessible from buyer realm, try with supplier client
        print(f"   ℹ️  Checking offer state via supplier client...")
        supplier_client = await get_authenticated_client("supplier", "supplier_agent")
        try:
            offer_data = supplier_client.get_instance(
                package="commerce",
                protocol_name="Offer",
                instance_id=accepted_offer_id
            )
            offer_state = offer_data.get("@state") or offer_data.get("state")
        except Exception as e2:
            print(f"   ⚠️  Could not access offer: {e2}")
            offer_state = "unknown"
    
    if offer_state == "accepted":
        # Update offer_id if a new one was accepted
        if accepted_offer_id != offer_id:
            print(f"   ℹ️  Supplier created new offer during negotiation: {accepted_offer_id}")
            offer_id = accepted_offer_id
        
        activity_logger.log_event(
            event_type="a2a_demo",
            actor="buyer_agent",
            action="a2a_negotiation_complete",
            details={"tools_used": a2a_tools, "offer_id": offer_id},
            level="info"
        )
        activity_logger.log_state_transition(
            protocol="Offer",
            protocol_id=offer_id,
            from_state="published",
            to_state="accepted",
            triggered_by="buyer_agent"
        )
        print("   ✅ Offer accepted after A2A negotiation")
    elif offer_state == "withdrawn":
        print(f"   ⚠️  Offer was withdrawn - agent should have handled this or found a new offer")
        print(f"   ℹ️  If supplier created a new offer during negotiation, agent should have accepted it")
    else:
        print(f"   ⚠️  Offer state is {offer_state}, expected 'accepted'")
        print(f"   ℹ️  Agent should have accepted the offer - NPL may have rejected the action")
        print(f"   ℹ️  Tool calls made: {a2a_tools}")
    
    # If offer wasn't accepted, we can't continue
    if offer_state != "accepted":
        print("   ❌ Cannot continue without accepted offer")
        return
    
    print()
    
    # =========================================================================
    # STEP 4: Buyer creates PurchaseOrder (AUTONOMOUS)
    # =========================================================================
    print("📋 Step 4: Buyer creates PurchaseOrder...")
    
    quantity = 10
    unit_price = 1200.0
    total = quantity * unit_price
    order_number = f"PO-A2A-{datetime.now().strftime('%H%M%S')}"
    
    po_prompt = f"""
Create a PurchaseOrder for the accepted offer {offer_id}:

Order details:
- Order number: {order_number}
- Quantity: {quantity} units
- Unit price: ${unit_price}
- Total: ${total}
- Seller: Supplier Inc, Sales department
- Approver: Acme Corp, Finance department

Use your NPL tools to create the purchase order. Check tool signatures for required parameters.
Your organization is Acme Corp, Procurement department (from your base instructions).
"""
    full_text, tool_calls, tool_results, po_id = await run_agent_turn(
        buyer_runner, po_prompt, "buyer_user", "negotiation_session",
        "buyer_agent", "po_create"
    )
    
    # Extract PO ID from tool results if not in response text
    if not po_id:
        for name, result in tool_results.items():
            if isinstance(result, dict):
                # Check top level
                po_id = result.get("@id") or result.get("id")
                if po_id:
                    break
                # Check nested structures (e.g., if result is wrapped)
                for key, value in result.items():
                    if isinstance(value, dict):
                        po_id = value.get("@id") or value.get("id")
                        if po_id:
                            break
                if po_id:
                    break
    
    # If still no ID, try to find it in the full text response with more patterns
    if not po_id:
        # Look for UUIDs in various formats
        uuid_patterns = [
            r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
            r'purchase[-\s]?order[:\s]+([a-f0-9-]{36})',
            r'PO[:\s]+([a-f0-9-]{36})',
            r'ID[:\s]+([a-f0-9-]{36})',
            r'id[:\s]+([a-f0-9-]{36})'
        ]
        for pattern in uuid_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                po_id = match.group(1) if match.groups() else match.group(0)
                break
    
    if not po_id:
        print("   ❌ Could not extract PO ID - agent must report it or tool must return it")
        print(f"   Tool results keys: {list(tool_results.keys())}")
        print(f"   Tool calls: {tool_calls}")
        if tool_results:
            print(f"   Sample result: {list(tool_results.values())[0] if tool_results.values() else 'None'}")
        print(f"   Agent response preview: {full_text[:500] if full_text else 'No response'}")
        return
    
    activity_logger.log_agent_action(
        agent="buyer_agent",
        action="create_purchase_order",
        protocol="PurchaseOrder",
        protocol_id=po_id,
        outcome="success",
        order_total=total
    )
    print(f"   ✅ PurchaseOrder created: {po_id}")
    print()
    
    # =========================================================================
    # Give Buyer Agent Objective: Place Order (will fail until approved - that's fine!)
    # =========================================================================
    print("🤖 Buyer agent objective: Place order when approved (will retry until state allows)...")
    
    buyer_objective = f"""
You are responsible for PurchaseOrder {po_id}. Your objective is to place the order when it's ready.

Monitor the order state and attempt to place it. If NPL rejects your action (e.g., "illegal protocol state" or 
"current state is not one of [expected states]"), this means the order isn't ready yet. Check the state, 
understand why it was rejected, wait a bit, and retry. The state will change to "Approved" after human 
approval, at which point your action will succeed. Keep trying until the order is placed.

The order ID is: {po_id}
"""
    
    # Start buyer agent as background task - it will keep trying
    async def buyer_autonomous_task():
        async def buyer_condition_met():
            order_data = buyer_client.get_instance(
                package="commerce",
                protocol_name="PurchaseOrder",
                instance_id=po_id
            )
            state = order_data.get("@state") or order_data.get("state")
            return state == "Ordered"
        
        await run_autonomous_agent(
            runner=buyer_runner,
            initial_objective=buyer_objective,
            user_id="buyer_user",
            session_id="negotiation_session",
            agent_name="buyer_agent",
            check_condition=buyer_condition_met,
            max_iterations=20,  # More iterations since it needs to wait for approval
            poll_interval=3.0
        )
    
    buyer_task = asyncio.create_task(buyer_autonomous_task())
    print()
    
    # =========================================================================
    # STEP 5: Supplier submits quote (AUTONOMOUS)
    # =========================================================================
    print("💵 Step 5: Supplier submits quote...")
    
    submit_prompt = f"""
A buyer has created PurchaseOrder {po_id} for 10 units at $1200 per unit (total: $12,000).

Review the purchase order and submit your quote. This is a high-value order, so it will require approval.

Use your NPL tools to submit the quote. Your organization is Supplier Inc, Sales department.
"""
    await run_agent_turn(
        supplier_runner, submit_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "submit_quote"
    )
    
    # Verify state was transitioned
    order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    current_state = order_data.get("@state") or order_data.get("state")
    
    if current_state == "ApprovalRequired":
        activity_logger.log_state_transition(
            protocol="PurchaseOrder",
            protocol_id=po_id,
            from_state="Requested",
            to_state="ApprovalRequired",
            triggered_by="supplier_agent",
            reason="High-value order requires approval"
        )
        print("   ✅ Quote submitted, approval required")
    else:
        print(f"   ⚠️  State is {current_state}, expected ApprovalRequired")
    print()
    
    # =========================================================================
    # Give Supplier Agent Objective: Ship Order (will fail until ordered - that's fine!)
    # =========================================================================
    print("🤖 Supplier agent objective: Ship order when state allows (will retry until state allows)...")
    
    supplier_objective = f"""
You are responsible for fulfilling PurchaseOrder {po_id}. Your objective is to ship the order when it's ready.

Monitor the order state and attempt to ship it with a tracking number. If NPL rejects your action (e.g., 
"illegal protocol state" or "current state is not one of [expected states]"), this means the order isn't 
ready yet. Check the state, understand why it was rejected, wait a bit, and retry. The state will change 
to "Ordered" after the buyer places the order, at which point your action will succeed. Keep trying until 
the order is shipped.

The order ID is: {po_id}
"""
    
    # Start supplier agent as background task - it will keep trying
    async def supplier_autonomous_task():
        supplier_client = await get_authenticated_client("supplier", "supplier_agent")
        async def supplier_condition_met():
            order_data = buyer_client.get_instance(
                package="commerce",
                protocol_name="PurchaseOrder",
                instance_id=po_id
            )
            state = order_data.get("@state") or order_data.get("state")
            if state == "Shipped":
                tracking_used = order_data.get("trackingNumber") or order_data.get("tracking")
                if tracking_used:
                    print(f"   📦 Tracking: {tracking_used}")
                activity_logger.log_state_transition(
                    protocol="PurchaseOrder",
                    protocol_id=po_id,
                    from_state="Ordered",
                    to_state="Shipped",
                    triggered_by="supplier_agent"
                )
                return True
            return False
        
        await run_autonomous_agent(
            runner=supplier_runner,
            initial_objective=supplier_objective,
            user_id="supplier_user",
            session_id="supplier_session",
            agent_name="supplier_agent",
            check_condition=supplier_condition_met,
            max_iterations=20,  # More iterations since it needs to wait for order
            poll_interval=3.0
        )
    
    supplier_task = asyncio.create_task(supplier_autonomous_task())
    print()
    
    # =========================================================================
    # STEP 6: Human Approval (Agents are already trying in background)
    # =========================================================================
    print("=" * 80)
    print("👤 Step 6: HUMAN APPROVAL REQUIRED")
    print("=" * 80)
    print()
    print("   ╔═══════════════════════════════════════════════════════════════╗")
    print("   ║                    ACTION REQUIRED                            ║")
    print("   ╚═══════════════════════════════════════════════════════════════╝")
    print()
    print(f"   📋 Order ID: {po_id}")
    print(f"   💰 Total Value: ${total:,.2f}")
    print()
    print("   🔐 Login to approve:")
    print("      • Realm: purchasing")
    print("      • User: approver")
    print("      • Password: Welcome123")
    print()
    print("   ℹ️  Buyer agent is attempting to place order (NPL will reject until approved)")
    print("   ℹ️  Supplier agent is attempting to ship (NPL will reject until ordered)")
    print()
    print("   ⏳ Waiting for approval (up to 5 minutes)...")
    print()
    
    # Give user a moment to see the message
    await asyncio.sleep(3)
    
    max_wait = 300
    start = time.time()
    approved = False
    last_status_time = start
    status_interval = 10  # Print status every 10 seconds
    
    while not approved and (time.time() - start) < max_wait:
        order_data = buyer_client.get_instance(
            package="commerce",
            protocol_name="PurchaseOrder",
            instance_id=po_id
        )
        current_state = order_data.get("@state") or order_data.get("state")
        if current_state == "Approved":
            approved = True
            print()
            print("   ✅ Approval detected! Buyer agent should now succeed...")
            activity_logger.log_agent_action(
                agent="approver",
                action="approve_order",
                protocol="PurchaseOrder",
                protocol_id=po_id,
                outcome="success"
            )
            activity_logger.log_state_transition(
                protocol="PurchaseOrder",
                protocol_id=po_id,
                from_state="ApprovalRequired",
                to_state="Approved",
                triggered_by="approver"
            )
            break
        
        # Print status periodically instead of just dots
        elapsed = time.time() - start
        if time.time() - last_status_time >= status_interval:
            remaining = max_wait - elapsed
            print(f"   ⏳ Still waiting... ({int(remaining)}s remaining, current state: {current_state})")
            last_status_time = time.time()
        else:
            print(".", end="", flush=True)
        
        await asyncio.sleep(2)
    
    print()
    if not approved:
        print("   ❌ TIMEOUT: Order was not approved within 5 minutes")
        print(f"   Current state: {current_state}")
        buyer_task.cancel()
        supplier_task.cancel()
        return
    
    # Wait for buyer agent to complete (place order)
    print("   ⏳ Waiting for buyer agent to place order...")
    try:
        buyer_success = await asyncio.wait_for(buyer_task, timeout=60.0)
        if buyer_success:
            print("   ✅ Buyer agent successfully placed the order")
        else:
            print("   ⚠️  Buyer agent did not complete within iterations")
    except asyncio.TimeoutError:
        print("   ⚠️  Buyer agent timeout")
    
    # Check if order was placed
    order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    current_state = order_data.get("@state") or order_data.get("state")
    if current_state == "Ordered":
        print("   ✅ Order state: Ordered - Supplier agent should now succeed...")
        activity_logger.log_state_transition(
            protocol="PurchaseOrder",
            protocol_id=po_id,
            from_state="Approved",
            to_state="Ordered",
            triggered_by="buyer_agent"
        )
    else:
        print(f"   ⚠️  Order state is {current_state}, expected Ordered")
    
    # Wait for supplier agent to complete (ship order)
    print("   ⏳ Waiting for supplier agent to ship order...")
    try:
        supplier_success = await asyncio.wait_for(supplier_task, timeout=60.0)
        if supplier_success:
            print("   ✅ Supplier agent successfully shipped the order")
        else:
            print("   ⚠️  Supplier agent did not complete within iterations")
    except asyncio.TimeoutError:
        print("   ⚠️  Supplier agent timeout")
    
    # Final state check
    order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    final_state = order_data.get("@state") or order_data.get("state")
    print()
    
    
    # =========================================================================
    # COMPLETE
    # =========================================================================
    # Get final order state to extract tracking if available
    final_order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    tracking_final = final_order_data.get("trackingNumber") or final_order_data.get("tracking") or "N/A"
    
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="system",
        action="a2a_workflow_complete",
        details={
            "product_id": product_id,
            "offer_id": offer_id,
            "po_id": po_id,
            "total": total,
            "tracking": tracking_final
        },
        level="info"
    )
    
    print("=" * 80)
    print("✅ A2A WORKFLOW DEMO COMPLETE")
    print("=" * 80)
    print()
    print("What we demonstrated:")
    print("  1. Buyer and Supplier agents running as A2A servers")
    print("  2. Direct agent-to-agent communication via A2A protocol")
    print("  3. Full order workflow: Product → Offer → PO → Approval → Ship")
    print("  4. Human approval gate for high-value orders")
    print("  5. All interactions logged to Activity Log")
    print()
    print(f"📝 Activity log: logs/{activity_logger.log_file.name}")
    print()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())

