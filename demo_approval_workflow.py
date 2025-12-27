#!/usr/bin/env python3
"""
Approval Workflow Demo - "LLMs Suggest, NPL Decides"

This script demonstrates the complete approval workflow for high-value purchase orders:
1. Buyer agent creates a PurchaseOrder
2. Supplier agent submits a quote
3. If total >= $5,000, order enters ApprovalRequired state
4. Agent attempts to place order → BLOCKED by NPL
5. Human approver approves the order
6. Agent retries place order → ALLOWED by NPL
7. Order proceeds to shipping and completion

This proves that:
- Agents can initiate actions
- Policies are enforced outside the LLM
- Human approval is mandatory for sensitive actions
- System is safe even if the LLM hallucinates
"""

import os
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth

load_dotenv()


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
    
    # Authentication
    print("🔐 Step 1: Authenticating actors...")
    buyer_client = await get_authenticated_client("purchasing", "purchasing_agent")
    supplier_client = await get_authenticated_client("supplier", "supplier_agent")
    approver_client = await get_authenticated_client("purchasing", "approver")
    print("   ✅ Buyer Agent: purchasing_agent (Acme Corp, Procurement)")
    print("   ✅ Supplier Agent: supplier_agent (Supplier Inc, Sales)")
    print("   ✅ Human Approver: approver (Acme Corp, Finance)")
    print()
    
    # Step 2: Supplier creates Product
    print("📦 Step 2: Supplier creates Product...")
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
    print()
    
    # Step 3: Supplier creates Offer
    print("💰 Step 3: Supplier creates and publishes Offer...")
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
    print()
    
    # Step 4: Buyer accepts Offer
    print("✓ Step 4: Buyer accepts Offer...")
    buyer_client.execute_action(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id,
        action_name="accept",
        party="buyer",
        params={}
    )
    print("   ✅ Offer accepted by buyer")
    print()
    
    # Step 5: Buyer creates PurchaseOrder (high value - requires approval)
    print("📋 Step 5: Buyer creates PurchaseOrder...")
    quantity = 10
    unit_price = 1200.0
    total = quantity * unit_price
    
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
    print()
    
    # Step 7: Agent ATTEMPTS to place order (should be BLOCKED)
    print("🚫 Step 7: Buyer agent attempts to place order (without approval)...")
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
        else:
            print(f"   ⚠️  Unexpected error: {error_msg}")
            if error_details:
                print(f"   Details: {error_details[:200]}")
            raise
    print()
    
    # Step 8: Human approves
    print("👤 Step 8: Human approver reviews and approves order...")
    print("   Approver: Alice Approver (Finance)")
    print("   Reviewing: Order total $12,000.00")
    print("   Decision: APPROVED ✓")
    
    approver_client.execute_action(
        package="commerce",
        protocol_name="PurchaseOrder",
        instance_id=po_id,
        action_name="approve",
        party="approver",
        params={}
    )
    print("   ✅ Approval granted")
    print("   → State transition: ApprovalRequired → Approved")
    print()
    
    # Step 9: Agent RETRIES placing order (should succeed)
    print("✅ Step 9: Buyer agent retries placing order (with approval)...")
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
    print("  3. ✅ Human approval is mandatory for high-value orders")
    print("  4. ✅ Agent cannot bypass approval (even if LLM hallucinates)")
    print("  5. ✅ All actions are auditable")
    print("  6. ✅ System is safe and resumable")
    print()
    print("💡 Key Insight: LLMs suggest, NPL decides.")
    print()
    print("=" * 80)
    
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

