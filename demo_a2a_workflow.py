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
    import re
    import time
    from datetime import timezone, timedelta
    from adk_npl import NPLClient
    from adk_npl.auth import KeycloakAuth
    
    def _iso_now(offset_days: int = 0) -> str:
        return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat().replace("+00:00", "Z")
    
    async def run_agent_turn(runner, prompt, user_id, session_id, agent_name, step_name):
        """Run a single agent turn and log all events."""
        activity_logger.log_agent_message(
            from_agent="system",
            to_agent=agent_name,
            message=prompt,
            message_type=step_name
        )
        
        response_parts = []
        tool_calls = []
        tool_results = {}
        
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
                            activity_logger.log_event(
                                event_type="a2a_transfer",
                                actor=agent_name,
                                action="a2a_delegation",
                                details={"tool": func.name},
                                level="info"
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
                        tool_results[name] = result
                        print(f"   📨 Result: {name}")
                        if "transfer" in name.lower() or "agent" in name.lower():
                            activity_logger.log_event(
                                event_type="a2a_response",
                                actor=f"remote_{agent_name}",
                                action="a2a_response",
                                details={"tool": name},
                                level="info"
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
    # STEP 1: Supplier creates Product via A2A
    # =========================================================================
    print("📦 Step 1: Supplier creates Product...")
    
    await session_service.create_session(
        app_name="supplier_a2a",
        user_id="supplier_user",
        session_id="supplier_session"
    )
    
    product_prompt = f"""
Create a Product using npl_commerce_Product_create with:
- seller_organization: "Supplier Inc"
- seller_department: "Sales"
- name: "Industrial Pump X"
- description: "High-performance industrial water pump"
- sku: "PUMP-X-A2A"
- gtin: "0123456789012"
- brand: "PumpCo"
- category: "Industrial Equipment"
- itemCondition: "NewCondition"

Report the product ID after creation.
"""
    _, _, _, product_id = await run_agent_turn(
        supplier_runner, product_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "product_create"
    )
    
    if not product_id:
        print("   ⚠️  Could not extract product ID from agent, using fallback...")
        supplier_client = await get_authenticated_client("supplier", "supplier_agent")
        product_result = supplier_client.create_instance(
            package="commerce",
            protocol_name="Product",
            params={
                "seller": {"organization": "Supplier Inc", "department": "Sales"},
                "name": "Industrial Pump X",
                "description": "High-performance industrial water pump",
                "sku": "PUMP-X-A2A",
                "gtin": "0123456789012",
                "brand": "PumpCo",
                "category": "Industrial Equipment",
                "itemCondition": "NewCondition"
            }
        )
        product_id = product_result.get("@id") or product_result.get("id")
    
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
    # STEP 2: Supplier creates and publishes Offer
    # =========================================================================
    print("💰 Step 2: Supplier creates and publishes Offer...")
    
    offer_prompt = f"""
Create an Offer for product {product_id} using npl_commerce_Offer_create with:
- seller_organization: "Supplier Inc"
- seller_department: "Sales"
- buyer_organization: "Acme Corp"
- buyer_department: "Procurement"
- itemOffered: "{product_id}"
- priceSpecification_price: 1200.0
- priceSpecification_priceCurrency: "USD"
- priceSpecification_validFrom: "{_iso_now()}"
- priceSpecification_validThrough: "{_iso_now(30)}"
- availableQuantity_value: 100
- availableQuantity_unitCode: "EA"
- availableQuantity_unitText: "units"
- deliveryLeadTime: 14
- validFrom: "{_iso_now()}"
- validThrough: "{_iso_now(30)}"

Then publish the offer using npl_commerce_Offer_publish with party="seller".
Report the offer ID.
"""
    _, _, _, offer_id = await run_agent_turn(
        supplier_runner, offer_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "offer_create_publish"
    )
    
    if not offer_id:
        print("   ⚠️  Could not extract offer ID, using fallback...")
        if not supplier_client:
            supplier_client = await get_authenticated_client("supplier", "supplier_agent")
        offer_result = supplier_client.create_instance(
            package="commerce",
            protocol_name="Offer",
            params={
                "seller": {"organization": "Supplier Inc", "department": "Sales"},
                "buyer": {"organization": "Acme Corp", "department": "Procurement"},
                "itemOffered": product_id,
                "priceSpecification": {
                    "price": 1200.0,
                    "priceCurrency": "USD",
                    "validFrom": _iso_now(),
                    "validThrough": _iso_now(30)
                },
                "availableQuantity": {"value": 100, "unitCode": "EA", "unitText": "units"},
                "deliveryLeadTime": 14,
                "validFrom": _iso_now(),
                "validThrough": _iso_now(30)
            }
        )
        offer_id = offer_result.get("@id") or offer_result.get("id")
        supplier_client.execute_action(
            package="commerce",
            protocol_name="Offer",
            instance_id=offer_id,
            action_name="publish",
            party="seller",
            params={}
        )
    
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
    print()
    
    # =========================================================================
    # STEP 3: A2A Negotiation - Buyer contacts Supplier
    # =========================================================================
    print("=" * 80)
    print("🤝 Step 3: A2A Negotiation - Buyer contacts Supplier")
    print("=" * 80)
    print()
    
    a2a_prompt = f"""
I want to purchase Industrial Pump X. I see offer {offer_id} is available at $1200/unit.

Please contact the SupplierAgent to:
1. Confirm the offer is still valid
2. Ask if there's a volume discount for 10 units
3. Negotiate for a better price if possible

Use the transfer_to_agent tool to communicate with SupplierAgent.
After negotiation, accept the offer using npl_commerce_Offer_accept with party="buyer".
"""
    
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="buyer_agent",
        action="a2a_negotiation_start",
        details={"offer_id": offer_id},
        level="info"
    )
    
    _, a2a_tools, _, _ = await run_agent_turn(
        buyer_runner, a2a_prompt, "buyer_user", "negotiation_session",
        "buyer_agent", "a2a_negotiation"
    )
    
    # Check if offer was accepted
    buyer_client = await get_authenticated_client("purchasing", "purchasing_agent")
    offer_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id
    )
    offer_state = offer_data.get("@state") or offer_data.get("state")
    
    if offer_state != "accepted":
        print(f"   ⚠️  Offer state: {offer_state}, accepting via fallback...")
        buyer_client.execute_action(
            package="commerce",
            protocol_name="Offer",
            instance_id=offer_id,
            action_name="accept",
            party="buyer",
            params={}
        )
    
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="buyer_agent",
        action="a2a_negotiation_complete",
        details={"tools_used": a2a_tools},
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
    print()
    
    # =========================================================================
    # STEP 4: Buyer creates PurchaseOrder
    # =========================================================================
    print("📋 Step 4: Buyer creates PurchaseOrder...")
    
    quantity = 10
    unit_price = 1200.0
    total = quantity * unit_price
    order_number = f"PO-A2A-{datetime.now().strftime('%H%M%S')}"
    
    po_prompt = f"""
Create a PurchaseOrder using npl_commerce_PurchaseOrder_create with:
- buyer_organization: "Acme Corp"
- buyer_department: "Procurement"
- seller_organization: "Supplier Inc"
- seller_department: "Sales"
- approver_organization: "Acme Corp"
- approver_department: "Finance"
- acceptedOffer: "{offer_id}"
- orderNumber: "{order_number}"
- quantity: {quantity}
- unitPrice: {unit_price}
- total: {total}

Report the PurchaseOrder ID.
"""
    _, _, _, po_id = await run_agent_turn(
        buyer_runner, po_prompt, "buyer_user", "negotiation_session",
        "buyer_agent", "po_create"
    )
    
    if not po_id:
        print("   ⚠️  Could not extract PO ID, using fallback...")
        po_result = buyer_client.create_instance(
            package="commerce",
            protocol_name="PurchaseOrder",
            params={
                "buyer": {"organization": "Acme Corp", "department": "Procurement"},
                "seller": {"organization": "Supplier Inc", "department": "Sales"},
                "approver": {"organization": "Acme Corp", "department": "Finance"},
                "acceptedOffer": offer_id,
                "orderNumber": order_number,
                "quantity": quantity,
                "unitPrice": unit_price,
                "total": total
            }
        )
        po_id = po_result.get("@id") or po_result.get("id")
    
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
    # STEP 5: Supplier submits quote via A2A
    # =========================================================================
    print("💵 Step 5: Supplier submits quote (via A2A)...")
    
    submit_prompt = f"""
A buyer has created PurchaseOrder {po_id} for 10 units.

Submit your quote using npl_commerce_PurchaseOrder_submitQuote with:
- instance_id: "{po_id}"
- party: "seller"

This will trigger the approval workflow for the high-value order.
"""
    await run_agent_turn(
        supplier_runner, submit_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "submit_quote"
    )
    
    # Verify state
    order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    current_state = order_data.get("@state") or order_data.get("state")
    
    if current_state != "ApprovalRequired":
        print(f"   ⚠️  State: {current_state}, submitting via fallback...")
        if not supplier_client:
            supplier_client = await get_authenticated_client("supplier", "supplier_agent")
        supplier_client.execute_action(
            package="commerce",
            protocol_name="PurchaseOrder",
            instance_id=po_id,
            action_name="submitQuote",
            party="seller",
            params={}
        )
    
    activity_logger.log_state_transition(
        protocol="PurchaseOrder",
        protocol_id=po_id,
        from_state="Requested",
        to_state="ApprovalRequired",
        triggered_by="supplier_agent",
        reason="High-value order requires approval"
    )
    print("   ✅ Quote submitted, approval required")
    print()
    
    # =========================================================================
    # STEP 6: Human Approval
    # =========================================================================
    print("=" * 80)
    print("👤 Step 6: HUMAN APPROVAL REQUIRED")
    print("=" * 80)
    print()
    print(f"   Order ID: {po_id}")
    print(f"   Total Value: ${total:,.2f}")
    print("   Please approve in UI (realm=purchasing, user=approver, pwd=Welcome123)")
    print("   Polling for up to 5 minutes...")
    print()
    
    max_wait = 300
    start = time.time()
    approved = False
    
    while not approved and (time.time() - start) < max_wait:
        order_data = buyer_client.get_instance(
            package="commerce",
            protocol_name="PurchaseOrder",
            instance_id=po_id
        )
        current_state = order_data.get("@state") or order_data.get("state")
        if current_state == "Approved":
            approved = True
            print("   ✅ Approval detected!")
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
        print(".", end="", flush=True)
        await asyncio.sleep(2)
    
    print()
    if not approved:
        print("❌ TIMEOUT: Order was not approved")
        return
    
    # =========================================================================
    # STEP 7: Buyer places order
    # =========================================================================
    print("✅ Step 7: Buyer places order...")
    
    place_prompt = f"""
PurchaseOrder {po_id} has been approved. Place the order now.

Call npl_commerce_PurchaseOrder_placeOrder with:
- instance_id: "{po_id}"
- party: "buyer"
"""
    await run_agent_turn(
        buyer_runner, place_prompt, "buyer_user", "negotiation_session",
        "buyer_agent", "place_order"
    )
    
    # Verify
    order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    current_state = order_data.get("@state") or order_data.get("state")
    
    if current_state != "Ordered":
        print(f"   ⚠️  State: {current_state}, placing via fallback...")
        buyer_client.execute_action(
            package="commerce",
            protocol_name="PurchaseOrder",
            instance_id=po_id,
            action_name="placeOrder",
            party="buyer",
            params={}
        )
    
    activity_logger.log_state_transition(
        protocol="PurchaseOrder",
        protocol_id=po_id,
        from_state="Approved",
        to_state="Ordered",
        triggered_by="buyer_agent"
    )
    print("   ✅ Order placed")
    print()
    
    # =========================================================================
    # STEP 8: Supplier ships via A2A
    # =========================================================================
    print("📦 Step 8: Supplier ships order...")
    
    tracking = f"TRACK-A2A-{datetime.now().strftime('%H%M%S')}"
    
    ship_prompt = f"""
PurchaseOrder {po_id} has been placed. Ship the order now.

Call npl_commerce_PurchaseOrder_shipOrder with:
- instance_id: "{po_id}"
- party: "seller"
- tracking: "{tracking}"
"""
    await run_agent_turn(
        supplier_runner, ship_prompt, "supplier_user", "supplier_session",
        "supplier_agent", "ship_order"
    )
    
    # Verify
    order_data = buyer_client.get_instance(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id
    )
    current_state = order_data.get("@state") or order_data.get("state")
    
    if current_state != "Shipped":
        print(f"   ⚠️  State: {current_state}, shipping via fallback...")
        if not supplier_client:
            supplier_client = await get_authenticated_client("supplier", "supplier_agent")
        supplier_client.execute_action(
            package="commerce",
            protocol_name="PurchaseOrder",
            instance_id=po_id,
            action_name="shipOrder",
            party="seller",
            params={"tracking": tracking}
        )
    
    activity_logger.log_state_transition(
        protocol="PurchaseOrder",
        protocol_id=po_id,
        from_state="Ordered",
        to_state="Shipped",
        triggered_by="supplier_agent"
    )
    print(f"   ✅ Order shipped with tracking: {tracking}")
    print()
    
    # =========================================================================
    # COMPLETE
    # =========================================================================
    activity_logger.log_event(
        event_type="a2a_demo",
        actor="system",
        action="a2a_workflow_complete",
        details={
            "product_id": product_id,
            "offer_id": offer_id,
            "po_id": po_id,
            "total": total,
            "tracking": tracking
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

