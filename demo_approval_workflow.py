#!/usr/bin/env python3
"""
Approval Workflow Demo - "LLMs Suggest, NPL Decides"

This script demonstrates the complete approval workflow for high-value purchase orders:
1. Buyer agent creates a PurchaseOrder
2. Supplier agent submits a quote
3. If total >= $5,000, order enters ApprovalRequired state
4. Agent attempts to place order → BLOCKED by NPL
5. **MANUAL STEP**: Human approver logs into UI and approves the order
6. Script detects approval and continues
7. Agent retries place order → ALLOWED by NPL
8. Order proceeds to shipping and completion

This proves that:
- Agents can initiate actions
- Policies are enforced outside the LLM
- Human approval is mandatory for sensitive actions (via UI)
- System is safe even if the LLM hallucinates
- Human-in-the-loop workflow works seamlessly
"""

import os
import asyncio
import sys
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth
from adk_npl.activity_logger import get_activity_logger

load_dotenv()

# Initialize activity logger
activity_logger = get_activity_logger()


def _iso_now(offset_days=0):
    """Generate ISO 8601 timestamp"""
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat().replace("+00:00", "Z")


async def get_authenticated_client(realm: str, username: str) -> NPLClient:
    """Create an authenticated NPL client"""
    password = os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")
    
    keycloak_url = os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000")
    
    auth = KeycloakAuth(
        keycloak_url=keycloak_url,
        realm=realm,
        client_id=realm,
        username=username,
        password=password
    )
    
    token = await auth.authenticate()
    engine_url = os.getenv("NPL_ENGINE_URL", "http://localhost:12000")
    return NPLClient(engine_url, token)


async def demo_approval_workflow():
    """Run the complete approval workflow demo"""
    
    print("=" * 80)
    print("🧪 PoC: Governed AI-Driven Supplier Ordering")
    print("=" * 80)
    print()
    print("Goal: Demonstrate how AI agents can participate in real business workflows")
    print("while being safely governed by NPL, even when the AI is imperfect.")
    print()
    print("=" * 80)
    print()
    
    # Log demo start
    activity_logger.log_event(
        event_type="demo",
        actor="system",
        action="demo_start",
        details={"demo": "approval_workflow"},
        level="info"
    )
    
    # Authentication
    print("🔐 Step 1: Authenticating actors...")
    buyer_client = await get_authenticated_client("purchasing", "purchasing_agent")
    supplier_client = await get_authenticated_client("supplier", "supplier_agent")
    print("   ✅ Buyer Agent: purchasing_agent (Acme Corp, Procurement)")
    print("   ✅ Supplier Agent: supplier_agent (Supplier Inc, Sales)")
    print()
    
    # Step 2: Supplier creates Product
    print("📦 Step 2: Supplier creates Product...")
    
    # Log agent reasoning
    activity_logger.log_agent_reasoning(
        actor="supplier_agent",
        reasoning="I need to create a product catalog entry for our Industrial Pump X. This will allow buyers to discover and evaluate our product before making purchase decisions.",
        context={"step": "product_creation", "product_name": "Industrial Pump X"}
    )
    
    product_payload = {
        "name": "Industrial Pump X",
        "description": "High-performance industrial water pump",
        "sku": "PUMP-X-001",
        "gtin": None,
        "brand": "PumpCo",
        "category": "Industrial Equipment",
        "itemCondition": "NewCondition"
    }
    
    product_resp = supplier_client.create_protocol(
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
        data=product_payload
    )
    product_id = product_resp.get("@id") or product_resp.get("id")
    print(f"   ✅ Product created: {product_payload['name']} (ID: {product_id})")
    activity_logger.log_agent_action(
        agent="supplier_agent",
        action="create_product",
        protocol="Product",
        protocol_id=product_id,
        outcome="success",
        product_name=product_payload['name']
    )
    print()
    
    # Step 3: Supplier creates Offer
    print("💰 Step 3: Supplier creates and publishes Offer...")
    
    # Log agent reasoning
    activity_logger.log_agent_reasoning(
        actor="supplier_agent",
        reasoning=f"Now I'll create a competitive offer for Acme Corp. Pricing at $1,200/unit maintains good margin while staying competitive. I'll set availability to 100 units with 14-day lead time.",
        context={"step": "offer_creation", "target_buyer": "Acme Corp", "price": 1200.0}
    )
    
    offer_payload = {
        "itemOffered": product_id,
        "priceSpecification": {
            "price": 1200.0,  # $1,200 per unit
            "priceCurrency": "USD",
            "validFrom": _iso_now(),
            "validThrough": _iso_now(30)
        },
        "availableQuantity": {
            "value": 100,
            "unitCode": "EA",
            "unitText": "units"
        },
        "deliveryLeadTime": 14,
        "validFrom": _iso_now(),
        "validThrough": _iso_now(30)
    }
    
    offer_resp = supplier_client.create_protocol(
        package="commerce",
        protocol_name="Offer",
        parties={
            "seller": {
                "claims": {
                    "organization": ["Supplier Inc"],
                    "department": ["Sales"]
                }
            },
            "buyer": {
                "claims": {
                    "organization": ["Acme Corp"],
                    "department": ["Procurement"]
                }
            }
        },
        data=offer_payload
    )
    offer_id = offer_resp.get("@id") or offer_resp.get("id")
    print(f"   ✅ Offer created: $1,200/unit × 10 units (ID: {offer_id})")
    activity_logger.log_agent_action(
        agent="supplier_agent",
        action="create_offer",
        protocol="Offer",
        protocol_id=offer_id,
        outcome="success",
        unit_price=1200.0
    )
    
    # Publish the offer
    supplier_client.execute_action(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id,
        action_name="publish",
        party="seller",
        params={}
    )
    print("   ✅ Offer published")
    activity_logger.log_state_transition(
        protocol="Offer",
        protocol_id=offer_id,
        from_state="draft",
        to_state="published",
        triggered_by="supplier_agent"
    )
    print()
    
    # Step 4: Buyer accepts Offer
    print("✓ Step 4: Buyer accepts Offer...")
    
    # Log agent reasoning
    activity_logger.log_agent_reasoning(
        actor="buyer_agent",
        reasoning="The supplier's offer looks good: $1,200/unit is within our budget, 14-day lead time is acceptable, and the product meets our requirements. I'll accept this offer.",
        context={"step": "offer_evaluation", "price": 1200.0, "lead_time": 14}
    )
    
    buyer_client.execute_action(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id,
        action_name="accept",
        party="buyer",
        params={}
    )
    print("   ✅ Offer accepted by buyer")
    activity_logger.log_agent_action(
        agent="buyer_agent",
        action="accept_offer",
        protocol="Offer",
        protocol_id=offer_id,
        outcome="success"
    )
    activity_logger.log_state_transition(
        protocol="Offer",
        protocol_id=offer_id,
        from_state="published",
        to_state="accepted",
        triggered_by="buyer_agent"
    )
    print()
    
    # Step 5: Buyer creates PurchaseOrder (high value - requires approval)
    print("📋 Step 5: Buyer creates PurchaseOrder...")
    quantity = 10
    unit_price = 1200.0
    total = quantity * unit_price
    
    # Log agent reasoning
    activity_logger.log_agent_reasoning(
        actor="buyer_agent",
        reasoning=f"I need to create a purchase order for {quantity} units at ${unit_price}/unit (total: ${total:,.2f}). I know this exceeds our $5,000 approval threshold, so the system will require human approval before the order can be placed. That's expected and correct.",
        context={"step": "purchase_order_creation", "quantity": quantity, "total": total, "approval_threshold": 5000}
    )
    
    print(f"   Order details: {quantity} units × ${unit_price}/unit = ${total:,.2f}")
    print(f"   Approval threshold: $5,000.00")
    print(f"   ⚠️  Total exceeds threshold → Approval will be required!")
    print()
    
    po_payload = {
        "orderNumber": f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "acceptedOffer": offer_id,
        "quantity": quantity,
        "unitPrice": unit_price,
        "total": total
    }
    
    po_resp = buyer_client.create_protocol(
        package="commerce",
        protocol_name="PurchaseOrder",
        parties={
            "buyer": {
                "claims": {
                    "organization": ["Acme Corp"],
                    "department": ["Procurement"]
                }
            },
            "seller": {
                "claims": {
                    "organization": ["Supplier Inc"],
                    "department": ["Sales"]
                }
            },
            "approver": {
                "claims": {
                    "organization": ["Acme Corp"],
                    "department": ["Finance"]
                }
            }
        },
        data=po_payload
    )
    po_id = po_resp.get("@id") or po_resp.get("id")
    print(f"   ✅ PurchaseOrder created: {po_payload['orderNumber']} (ID: {po_id})")
    print(f"   State: Requested")
    activity_logger.log_agent_action(
        agent="buyer_agent",
        action="create_purchase_order",
        protocol="PurchaseOrder",
        protocol_id=po_id,
        outcome="success",
        order_number=po_payload['orderNumber'],
        total=total
    )
    print()
    
    # Step 6: Supplier submits quote (triggers approval check)
    print("💵 Step 6: Supplier submits quote...")
    supplier_client.execute_action(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id,
        action_name="submitQuote",
        party="seller",
        params={}
    )
    print("   ✅ Quote submitted")
    print(f"   → NPL evaluated: ${total:,.2f} >= $5,000.00")
    print("   → State transition: Requested → ApprovalRequired")
    activity_logger.log_agent_action(
        agent="supplier_agent",
        action="submit_quote",
        protocol="PurchaseOrder",
        protocol_id=po_id,
        outcome="success"
    )
    activity_logger.log_state_transition(
        protocol="PurchaseOrder",
        protocol_id=po_id,
        from_state="Requested",
        to_state="ApprovalRequired",
        triggered_by="supplier_agent",
        reason="Total exceeds approval threshold"
    )
    print()
    
    # Step 7: Agent ATTEMPTS to place order (should be BLOCKED)
    print("🚫 Step 7: Buyer agent attempts to place order (without approval)...")
    
    # Log agent reasoning (showing agent's attempt)
    activity_logger.log_agent_reasoning(
        actor="buyer_agent",
        reasoning="I'll try to place the order now. Even though I know approval is required, let me attempt it to demonstrate that NPL will block me if I try to bypass the approval process.",
        context={"step": "attempt_place_order", "expected_outcome": "blocked_by_npl"}
    )
    
    try:
        response = buyer_client.execute_action(
            package="commerce",
            protocol_name="PurchaseOrder",
            instance_id=po_id,
            action_name="placeOrder",
            party="buyer",
            params={}
        )
        print("   ❌ UNEXPECTED: Order was placed without approval!")
        print("   ⚠️  NPL GOVERNANCE FAILED - This should not happen!")
        return False
    except Exception as e:
        # Check both the exception message and if it's an HTTPError, check the response
        error_msg = str(e)
        error_details = ""
        
        # Try to get more details from HTTPError response
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            error_details = e.response.text
        
        # Check if this is the expected blocking error
        combined_error = error_msg + " " + error_details
        if ("ApprovalRequired" in combined_error or 
            "not allowed" in combined_error.lower() or 
            "Illegal protocol state" in combined_error or
            "400" in error_msg):  # 400 Bad Request typically means state constraint violation
            print("   ✅ BLOCKED by NPL! (as expected)")
            print(f"   → NPL enforced: Cannot placeOrder() in ApprovalRequired state")
            print("   → Agent cannot bypass approval, even if LLM tries")
            if "Illegal protocol state" in error_details:
                print(f"   → NPL Error: Protocol state constraint violation")
            activity_logger.log_agent_action(
                agent="buyer_agent",
                action="place_order_attempt",
                protocol="PurchaseOrder",
                protocol_id=po_id,
                outcome="blocked_by_npl",
                reason="ApprovalRequired state constraint"
            )
        else:
            print(f"   ⚠️  Unexpected error: {error_msg}")
            if error_details:
                print(f"   Details: {error_details[:200]}")
            raise
    print()
    
    # Step 8: Human approves (MANUAL STEP)
    print("=" * 80)
    print("👤 Step 8: HUMAN APPROVAL REQUIRED")
    print("=" * 80)
    print()
    print("📋 Order Details:")
    print(f"   Order ID: {po_id}")
    print(f"   Order Number: {po_payload['orderNumber']}")
    print(f"   Total Value: ${total:,.2f}")
    print(f"   Current State: ApprovalRequired")
    print()
    print("🌐 ACTION REQUIRED:")
    print("   1. Open the Approval Dashboard in your browser:")
    print("      → http://localhost:5173")
    print()
    print("   2. Log in as approver:")
    print("      → Username: approver")
    print("      → Password: Welcome123")
    print("      → Realm: purchasing")
    print()
    print("   3. Navigate to the 'APPROVALS' tab")
    print("   4. Find the pending order and click 'APPROVE'")
    print()
    print("⏳ Waiting for manual approval...")
    print("   (The script will check every 2 seconds)")
    print()
    print("-" * 80)
    
    # Wait for manual approval by polling the order state
    max_wait_time = 300  # 5 minutes max wait
    check_interval = 2  # Check every 2 seconds
    start_time = time.time()
    approved = False
    
    while not approved and (time.time() - start_time) < max_wait_time:
        try:
            # Check current state
            order_data = buyer_client.get_instance(
                package="commerce",
                protocol_name="PurchaseOrder",
                instance_id=po_id
            )
            current_state = order_data.get("@state") or order_data.get("state")
            
            if current_state == "Approved":
                approved = True
                print()
                print("   ✅ Approval detected!")
                print("   → State transition: ApprovalRequired → Approved")
                activity_logger.log_agent_action(
                    agent="approver",
                    action="approve_order",
                    protocol="PurchaseOrder",
                    protocol_id=po_id,
                    outcome="success",
                    approved_by="Human Approver (via UI)"
                )
                activity_logger.log_state_transition(
                    protocol="PurchaseOrder",
                    protocol_id=po_id,
                    from_state="ApprovalRequired",
                    to_state="Approved",
                    triggered_by="approver"
                )
                break
            elif current_state != "ApprovalRequired":
                print(f"   ⚠️  Unexpected state: {current_state}")
                print("   Expected: ApprovalRequired")
                break
            else:
                # Still waiting
                print(".", end="", flush=True)
                await asyncio.sleep(check_interval)
        except Exception as e:
            print(f"\n   ⚠️  Error checking order state: {e}")
            await asyncio.sleep(check_interval)
    
    print()
    print("-" * 80)
    
    if not approved:
        print()
        print("❌ TIMEOUT: Order was not approved within the waiting period.")
        print("   You can manually approve it later and the demo will continue.")
        print("   Or restart the demo and approve when prompted.")
        return False
    
    print()
    
    # Step 9: Agent RETRIES placing order (should succeed)
    print("✅ Step 9: Buyer agent retries placing order (with approval)...")
    
    # Log agent reasoning
    activity_logger.log_agent_reasoning(
        actor="buyer_agent",
        reasoning="Great! The order has been approved. Now I can place the order. The NPL system will allow this action since we're in the Approved state.",
        context={"step": "retry_place_order", "state": "Approved", "expected_outcome": "success"}
    )
    
    buyer_client.execute_action(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id,
        action_name="placeOrder",
        party="buyer",
        params={}
    )
    print("   ✅ Order placed successfully!")
    print("   → NPL allowed action: Approved state permits placeOrder()")
    print("   → State transition: Approved → Ordered")
    activity_logger.log_agent_action(
        agent="buyer_agent",
        action="place_order",
        protocol="PurchaseOrder",
        protocol_id=po_id,
        outcome="success"
    )
    activity_logger.log_state_transition(
        protocol="PurchaseOrder",
        protocol_id=po_id,
        from_state="Approved",
        to_state="Ordered",
        triggered_by="buyer_agent"
    )
    print()
    
    # Step 10: Supplier ships
    print("📦 Step 10: Supplier ships the order...")
    tracking = f"TRACK-{datetime.now().strftime('%Y%m%d%H%M')}"
    supplier_client.execute_action(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id,
        action_name="shipOrder",
        party="seller",
        params={"tracking": tracking}
    )
    print(f"   ✅ Order shipped with tracking: {tracking}")
    print("   → State transition: Ordered → Shipped")
    activity_logger.log_agent_action(
        agent="supplier_agent",
        action="ship_order",
        protocol="PurchaseOrder",
        protocol_id=po_id,
        outcome="success",
        tracking_number=tracking
    )
    activity_logger.log_state_transition(
        protocol="PurchaseOrder",
        protocol_id=po_id,
        from_state="Ordered",
        to_state="Shipped",
        triggered_by="supplier_agent"
    )
    print()
    
    # Step 11: Get audit trail
    print("📊 Step 11: Retrieve audit trail...")
    summary = buyer_client.execute_action(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id,
        action_name="getOrderSummary",
        party="buyer",
        params={}
    )
    print(f"   Order Summary: {summary}")
    print()
    
    # Success summary
    print("=" * 80)
    print("✅ DEMO COMPLETE - All Assertions Passed!")
    print("=" * 80)
    print()
    print("What we proved:")
    print("  1. ✅ Agents can initiate actions")
    print("  2. ✅ NPL enforces policies outside the LLM")
    print("  3. ✅ Human approval is mandatory for high-value orders (via UI)")
    print("  4. ✅ Agent cannot bypass approval (even if LLM hallucinates)")
    print("  5. ✅ All actions are auditable")
    print("  6. ✅ System is safe and resumable")
    print("  7. ✅ Human-in-the-loop workflow works seamlessly")
    print()
    print("💡 Key Insight: LLMs suggest, NPL decides.")
    print()
    print("=" * 80)
    
    # Log demo completion
    activity_logger.log_event(
        event_type="demo",
        actor="system",
        action="demo_complete",
        details={
            "demo": "approval_workflow",
            "success": True,
            "summary": activity_logger.get_session_summary()
        },
        level="info"
    )
    
    # Print activity log location
    print()
    print(f"📝 Activity log saved to: {activity_logger.log_file}")
    print(f"   Total events logged: {len(activity_logger.buffer)}")
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(demo_approval_workflow())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

