#!/usr/bin/env python3
import asyncio
import os
import time
import nest_asyncio
from dotenv import load_dotenv

from purchasing_agent import create_purchasing_agent
from supplier_agent import create_supplier_agent
from adk_npl import NPLConfig

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.auth.credential_service.in_memory_credential_service import InMemoryCredentialService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.genai import types

# Allow nested event loops for agent execution
nest_asyncio.apply()
load_dotenv()

async def chat_with_runner(runner, message, user_id="user", session_id="sim_session"):
    """Run agent via Runner and get response text plus tool call names (verbose)."""
    response_content = []
    tool_calls = []
    debug_lines = []
    
    # Convert message to types.Content
    content = types.Content(role="user", parts=[types.Part(text=message)])
    
    # Creating a new invocation
    async for event in runner.run_async(
        new_message=content,
        user_id=user_id,
        session_id=session_id
    ):
        # Try multiple ways to extract text from events
        event_type = event.__class__.__name__
        
        # Method 1: Check for TextOutput events
        if event_type == "TextOutput":
            if hasattr(event, 'text') and event.text:
                response_content.append(event.text)
                debug_lines.append(f"[TextOutput] {event.text}")
        
        # Method 2: Check for ModelAction with candidates
        elif event_type == "ModelAction":
            try:
                # Try to get candidates from the event
                if hasattr(event, 'candidates') and event.candidates:
                    for candidate in event.candidates:
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    response_content.append(part.text)
                                    debug_lines.append(f"[ModelAction text] {part.text}")
                                # Also check for function calls
                                if hasattr(part, 'function_call'):
                                    func_call = part.function_call
                                    if hasattr(func_call, 'name'):
                                        tool_calls.append(func_call.name)
                                        debug_lines.append(f"[ModelAction function_call] {func_call.name}")
                
                # Alternative: check action attribute
                elif hasattr(event, 'action'):
                    action = event.action
                    if hasattr(action, 'candidates') and action.candidates:
                        for candidate in action.candidates:
                            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        response_content.append(part.text)
            except Exception as e:
                # Silently continue - not all events have text
                pass
        
        # Method 3: Check for any text attribute directly
        elif hasattr(event, 'text') and event.text:
            response_content.append(event.text)
            debug_lines.append(f"[Generic text] {event.text}")
    
    # Combine text responses
    full_text = "".join(response_content).strip()
    
    # If we have tool calls but no text, mention the tools
    if not full_text and tool_calls:
        full_text = f"[Agent called tools: {', '.join(set(tool_calls))}]"
    
    # Fallback message
    if not full_text:
        full_text = "[Agent executed actions but returned no text response]"
    
    verbose = "\n".join(debug_lines)
    return full_text, verbose


async def run_negotiation():
    print("🤖 Initializing Agents for Negotiation...")
    
    # 1. Configure Agents
    buyer_config = NPLConfig(
        engine_url=os.getenv("NPL_ENGINE_URL", "http://localhost:12000"),
        keycloak_url=os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000"),
        keycloak_realm="purchasing",
        keycloak_client_id="purchasing",
        credentials={"username": "purchasing_agent", "password": os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")}
    )
    
    supplier_config = NPLConfig(
        engine_url=os.getenv("NPL_ENGINE_URL", "http://localhost:12000"),
        keycloak_url=os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000"),
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={"username": "supplier_agent", "password": os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")}
    )

    # 2. Create Agent Instances
    # Using gemini-flash-latest which we set in the agents code
    buyer = await create_purchasing_agent(
        config=buyer_config,
        agent_id="buyer_001",
        budget=5000.0,
        requirements="100 high-quality widgets for immediate project",
        constraints={"max_delivery_days": 14},
        strategy="Start with a low offer but prioritize delivery speed"
    )

    seller = await create_supplier_agent(
        config=supplier_config,
        agent_id="supplier_001",
        min_price=40.0,
        inventory={"widgets": 500},
        capacity={"min_lead_time": 7},
        strategy="Maximize margin but capture the deal"
    )
    
    # Create shared services
    session_service = InMemorySessionService()
    credential_service = InMemoryCredentialService()
    artifact_service = InMemoryArtifactService()
    memory_service = InMemoryMemoryService()
    
    # Initialize session for buyer
    await session_service.create_session(
        app_name="negotiation",
        user_id="buyer_user",
        session_id="buyer_session"
    )
    
    # Initialize session for seller
    await session_service.create_session(
        app_name="negotiation",
        user_id="seller_user",
        session_id="seller_session"
    )

    # Wrap in Runners
    buyer_runner = Runner(
        agent=buyer,
        session_service=session_service,
        credential_service=credential_service,
        artifact_service=artifact_service,
        memory_service=memory_service,
        app_name="negotiation"
    )
    
    seller_runner = Runner(
        agent=seller,
        session_service=session_service,
        credential_service=credential_service,
        artifact_service=artifact_service,
        memory_service=memory_service,
        app_name="negotiation"
    )

    print("✅ Agents Ready.\n")
    print(f"🟦 BUYER: Budget $5,000 | Needs: 100 Widgets | Max 14 days")
    print(f"🟩 SELLER: Min Price $40 | Stock: 500 Widgets | Min 7 days lead")
    print("-" * 60)

    # 3. Guided flow to exercise schema.org commerce protocols
    # Now using schema-aware tools with explicit parameters!
    scripted_turns = [
        (
            "buyer",
            "Use the propose_framework tool to propose using schema.org commerce protocols."
        ),
        (
            "seller",
            "Use the agree_framework tool to accept the schema.org commerce framework."
        ),
        (
            "seller",
            """Create a Product for sale using npl_commerce_Product_create.
The tool has explicit parameters - use:
- seller_organization: "Supplier Inc"
- seller_department: "Sales"
- name: "Widget Batch"
- description: "100 high-quality widgets"
- sku: "WGT-100"
- category: "Widgets"
- itemCondition: "NewCondition"

Report back the product ID you receive."""
        ),
        (
            "seller",
            """Create an Offer using npl_commerce_Offer_create.
Use the tool's explicit parameters:
- seller_organization: "Supplier Inc"
- seller_department: "Sales"
- buyer_organization: "Acme Corp"
- buyer_department: "Procurement"
- itemOffered: <the product ID from above>
- priceSpecification_price: 45.0
- priceSpecification_priceCurrency: "USD"
- priceSpecification_validFrom: "2025-01-01T00:00:00Z"
- priceSpecification_validThrough: "2025-12-31T23:59:59Z"
- availableQuantity_value: 100
- availableQuantity_unitCode: "EA"
- availableQuantity_unitText: "pieces"
- deliveryLeadTime: 7
- validFrom: "2025-01-01T00:00:00Z"
- validThrough: "2025-12-31T23:59:59Z"

Then publish the offer using npl_commerce_Offer_publish with instance_id and party="seller"."""
        ),
        (
            "buyer",
            """The seller has published an offer. Use evaluate_proposal to check if the price ($45/unit) and delivery (7 days) meet your requirements.

If acceptable, call npl_commerce_Offer_accept with the offer ID and party="buyer".

Summarize your decision."""
        )
    ]

    last_message = "Begin negotiation."
    current_turn = "buyer"

    for i, (turn, prompt) in enumerate(scripted_turns, start=1):
        current_turn = turn
        print(f"\n--- Turn {i}: {current_turn.upper()} ---")
        message = prompt if last_message == "Begin negotiation." else f"{prompt}\nContext: {last_message}"

        if current_turn == "buyer":
            response_text, debug = await chat_with_runner(
                buyer_runner, message, user_id="buyer_user", session_id="buyer_session"
            )
            agent_color = "🟦"
        else:
            response_text, debug = await chat_with_runner(
                seller_runner, message, user_id="seller_user", session_id="seller_session"
            )
            agent_color = "🟩"

        print(f"{agent_color} {response_text}")
        if debug:
            print(f"{agent_color} DEBUG:\n{debug}")
        last_message = response_text

        if "agreement" in response_text.lower() or "order" in response_text.lower():
            print(f"\n✨ PROGRESS: {current_turn.upper()} reports agreement/order state. ✨")

        # Short wait; keep turns minimal to avoid quota
        print("   (Waiting 5s...)")
        time.sleep(5)

    print("\n--- Negotiation Ended (scripted flow complete) ---")

if __name__ == "__main__":
    asyncio.run(run_negotiation())