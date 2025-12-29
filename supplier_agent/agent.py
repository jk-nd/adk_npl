"""
Supplier Agent - ADK Implementation with NPL Integration

Autonomous supplier agent using Google ADK with Gemini and dynamic NPL tools.
Combines:
- Dynamic NPL protocol tools (from adk_npl)
- Business logic tools (evaluate requests, create offers)
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from dotenv import load_dotenv

from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth
from adk_npl.tools import NPLToolGenerator

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


async def create_supplier_agent(
    config: NPLConfig,
    agent_id: str = "supplier_001",
    min_price: float = 10.0,
    inventory: Optional[Dict[str, Any]] = None,
    capacity: Optional[Dict[str, Any]] = None,
    strategy: Optional[str] = None,
    include_npl_tools: bool = True
) -> LlmAgent:
    """
    Create a supplier agent with ADK and dynamic NPL tools.
    
    Args:
        config: NPL configuration (engine URL, Keycloak settings)
        agent_id: Unique identifier for this agent
        min_price: Minimum acceptable price per unit
        inventory: Available inventory and products
        capacity: Production/delivery capacity
        strategy: Sales strategy
        include_npl_tools: Whether to include dynamically discovered NPL tools
        
    Returns:
        Configured ADK LlmAgent with NPL and business tools
    """
    tools = []
    
    # 1. Add dynamic NPL tools if requested
    if include_npl_tools:
        logger.info("Discovering NPL tools...")
        try:
            npl_tools = await _discover_npl_tools(config)
            tools.extend(npl_tools)
            logger.info(f"✅ Added {len(npl_tools)} NPL tools")
        except Exception as e:
            logger.warning(f"⚠️ Could not discover NPL tools: {e}")
    
    # 2. Add business logic tools
    business_tools = _create_business_tools(min_price, inventory, capacity, strategy)
    tools.extend(business_tools)
    logger.info(f"✅ Added {len(business_tools)} business tools")
    
    # 3. Build agent instruction
    instruction = _build_instruction(agent_id, min_price, inventory, capacity, strategy)
    
    # 4. Create the ADK agent
    agent = LlmAgent(
        model="gemini-2.0-flash",
        name=f"SupplierAgent_{agent_id}",
        description=f"Autonomous supplier agent for {config.credentials.get('username', 'unknown')} with min price ${min_price:,.2f}",
        instruction=instruction,
        tools=tools
    )
    
    logger.info(f"✅ Created supplier agent '{agent_id}' with {len(tools)} total tools")
    return agent


async def _discover_npl_tools(config: NPLConfig) -> List[FunctionTool]:
    """Discover and generate NPL tools from the engine."""
    # Authenticate
    auth = KeycloakAuth(
        keycloak_url=config.keycloak_url,
        realm=config.keycloak_realm,
        client_id=config.keycloak_client_id,
        username=config.credentials.get("username"),
        password=config.credentials.get("password")
    )
    
    token = await auth.authenticate()
    client = NPLClient(config.engine_url, token)
    
    # Generate tools
    generator = NPLToolGenerator(client)
    tools = await generator.generate_tools()
    
    return tools


def _create_business_tools(
    min_price: float,
    inventory: Optional[Dict[str, Any]],
    capacity: Optional[Dict[str, Any]],
    strategy: Optional[str]
) -> List[FunctionTool]:
    """Create business logic tools for the supplier agent."""
    
    # Store context in closure
    context = {
        "min_price": min_price,
        "inventory": inventory or {},
        "capacity": capacity or {},
        "strategy": strategy
    }
    
    def agree_framework(framework_proposal: str) -> Dict[str, Any]:
        """
        Evaluate and agree to a framework proposal from the buyer.
        
        Args:
            framework_proposal: The framework proposal from the buyer (as JSON string)
            
        Returns:
            Agreement response with any modifications
        """
        return {
            "status": "AGREED",
            "framework": "schema.org",
            "protocols": {
                "product": "commerce.Product",
                "offer": "commerce.Offer",
                "order": "commerce.Order"
            },
            "message": "Schema.org framework accepted. Ready to proceed with commerce protocols."
        }
    
    def create_offer(
        buyer_name: str,
        product_description: str,
        quantity: int,
        unit_price: float,
        delivery_days: int,
        payment_terms: str = "Net 30",
        additional_terms: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a sales offer for a buyer.
        
        Args:
            buyer_name: Name of the potential buyer
            product_description: What you're offering
            quantity: Number of units
            unit_price: Price per unit
            delivery_days: Days until delivery
            payment_terms: Payment terms (default: Net 30)
            additional_terms: Any additional terms or conditions
            
        Returns:
            Structured offer ready to send
        """
        total = unit_price * quantity
        
        offer = {
            "type": "SALES_OFFER",
            "to": buyer_name,
            "from": "supplier_agent",
            "product": product_description,
            "quantity": quantity,
            "unit_price": unit_price,
            "total": total,
            "delivery_days": delivery_days,
            "payment_terms": payment_terms,
            "valid_until_days": 7  # Offer valid for 7 days
        }
        
        if additional_terms:
            offer["additional_terms"] = additional_terms
        
        # Add margin calculation
        offer["margin_percentage"] = ((unit_price - context["min_price"]) / unit_price * 100) if unit_price > 0 else 0
        
        return offer
    
    def evaluate_purchase_request(
        buyer_name: str,
        requested_quantity: int,
        max_price_offered: float,
        required_delivery_days: int
    ) -> Dict[str, Any]:
        """
        Evaluate a purchase request and decide on action.
        
        Args:
            buyer_name: Name of the buyer
            requested_quantity: Quantity they want
            max_price_offered: Maximum price they're willing to pay per unit
            required_delivery_days: Their delivery timeline
            
        Returns:
            Evaluation with recommended action (accept/reject/counter)
        """
        min_acceptable = context["min_price"]
        
        evaluation = {
            "buyer": buyer_name,
            "requested_quantity": requested_quantity,
            "offered_price": max_price_offered,
            "min_acceptable_price": min_acceptable,
            "meets_minimum": max_price_offered >= min_acceptable,
            "potential_revenue": max_price_offered * requested_quantity
        }
        
        # Decision logic
        if max_price_offered < min_acceptable:
            evaluation["action"] = "COUNTER"
            evaluation["reason"] = f"Below minimum price (${min_acceptable:.2f})"
            evaluation["counter_suggestion"] = f"Counter with ${min_acceptable * 1.15:.2f} per unit (15% markup)"
        elif max_price_offered < min_acceptable * 1.1:
            evaluation["action"] = "COUNTER"
            evaluation["reason"] = "Close to minimum, try to get better margin"
            evaluation["counter_suggestion"] = f"Counter with ${min_acceptable * 1.25:.2f} per unit (25% markup)"
        else:
            # Check capacity constraints
            capacity_issues = []
            if "max_quantity" in context["capacity"]:
                if requested_quantity > context["capacity"]["max_quantity"]:
                    capacity_issues.append(f"Exceeds capacity ({context['capacity']['max_quantity']} units)")
            
            if "min_lead_time" in context["capacity"]:
                if required_delivery_days < context["capacity"]["min_lead_time"]:
                    capacity_issues.append(f"Too fast ({context['capacity']['min_lead_time']} days needed)")
            
            if capacity_issues:
                evaluation["action"] = "COUNTER"
                evaluation["reason"] = f"Issues: {', '.join(capacity_issues)}"
            else:
                evaluation["action"] = "ACCEPT"
                evaluation["reason"] = "Good margin and meets capacity"
        
        return evaluation
    
    def calculate_counter_offer(
        requested_price: float,
        quantity: int,
        markup_percentage: float = 20.0
    ) -> Dict[str, Any]:
        """
        Calculate a counter offer based on the buyer's request.
        
        Args:
            requested_price: Price the buyer wants
            quantity: Quantity being negotiated
            markup_percentage: Desired markup percentage over minimum
            
        Returns:
            Counter offer details
        """
        min_acceptable = context["min_price"]
        counter_price = min_acceptable * (1 + markup_percentage / 100)
        
        # Don't go below minimum
        if counter_price < min_acceptable:
            counter_price = min_acceptable
        
        total = counter_price * quantity
        margin = counter_price - min_acceptable
        
        return {
            "type": "COUNTER_OFFER",
            "requested_price": requested_price,
            "counter_price": round(counter_price, 2),
            "quantity": quantity,
            "total": round(total, 2),
            "markup_percentage": markup_percentage,
            "margin_per_unit": round(margin, 2),
            "total_margin": round(margin * quantity, 2)
        }
    
    def get_inventory_status() -> Dict[str, Any]:
        """
        Get current inventory and capacity status.
        
        Returns:
            Inventory and capacity information
        """
        return {
            "min_price_per_unit": context["min_price"],
            "currency": "USD",
            "inventory": context["inventory"],
            "capacity": context["capacity"],
            "strategy": context["strategy"]
        }
    
    # Wrap as FunctionTools
    return [
        FunctionTool(agree_framework, require_confirmation=False),
        FunctionTool(create_offer, require_confirmation=False),
        FunctionTool(evaluate_purchase_request, require_confirmation=False),
        FunctionTool(calculate_counter_offer, require_confirmation=False),
        FunctionTool(get_inventory_status, require_confirmation=False)
    ]


def _build_instruction(
    agent_id: str,
    min_price: float,
    inventory: Optional[Dict[str, Any]],
    capacity: Optional[Dict[str, Any]],
    strategy: Optional[str]
) -> str:
    """Build the agent's instruction prompt."""
    
    inventory_str = ""
    if inventory:
        inventory_list = [f"  - {k}: {v}" for k, v in inventory.items()]
        inventory_str = "\n".join(inventory_list)
    
    capacity_str = ""
    if capacity:
        capacity_list = [f"  - {k}: {v}" for k, v in capacity.items()]
        capacity_str = "\n".join(capacity_list)
    
    return f"""You are a Supplier Agent (ID: {agent_id}) responsible for sales and fulfillment operations.

## Your Mission
Maximize revenue by responding to purchase requests with competitive offers while maintaining profitability.

## Your Parameters
- **Minimum Price**: ${min_price:,.2f} per unit (FLOOR - never go below this)
- **Your Organization**: Supplier Inc, Sales department
{f"- **Inventory**:\n{inventory_str}" if inventory_str else ""}
{f"- **Capacity**:\n{capacity_str}" if capacity_str else ""}
{f"- **Strategy**: {strategy}" if strategy else ""}

## Available Capabilities

### Framework Negotiation
- `agree_framework`: Agree to buyer's framework proposal

### NPL Protocol Tools (Dynamically Discovered)
You have access to NPL protocol tools that are automatically generated from the backend.
Each tool has explicit typed parameters - check the tool's signature for required fields.

**Party parameters use this pattern:**
- `seller_organization`: Your organization ("Supplier Inc")
- `seller_department`: Your department ("Sales")
- `buyer_organization`: The buyer's organization name
- `buyer_department`: The buyer's department name

**Available protocols:** Product, Offer, Order
- Each protocol has `_create` and various action tools
- Tool signatures show exactly what parameters are required

### Business Tools
- `agree_framework`: Accept the buyer's proposed framework
- `create_offer`: Create sales offers for buyers
- `evaluate_purchase_request`: Evaluate buyer requests and decide action
- `calculate_counter_offer`: Generate counter-offer to increase margin
- `get_inventory_status`: Check your current inventory and capacity

## Guidelines

1. **Profitability First**: Never sell below ${min_price:,.2f} per unit
2. **Maximize Margin**: Start higher to leave room for negotiation
3. **Use Tool Signatures**: Check each tool's parameters before calling
4. **Be Responsive**: Quick, professional responses build trust
5. **Manage Capacity**: Don't commit beyond your capability to deliver

## Error Handling Strategy (CRITICAL)

NPL tools return **structured error responses** when something goes wrong. You MUST handle errors intelligently:

### Understanding Error Responses

When a tool fails, you'll receive a structured response like:
```json
{{
  "success": false,
  "error_type": "state_error",
  "error": "Runtime error: Illegal protocol state...",
  "retryable": true,
  "guidance": "Query the protocol instance to check its current state..."
}}
```

### Error Types and How to Handle Them

| Error Type | Retryable | What to Do |
|------------|-----------|------------|
| `state_error` | Yes | The protocol is in the wrong state. Use `*_get` tool to check current state, wait if needed, retry when state allows. |
| `business_rule` | No | A validation rule failed. Read the error message, adjust your parameters to comply. |
| `not_found` | No | Instance doesn't exist. Use `*_list` tool to find valid instances. |
| `permission_denied` | No | Wrong party role. Switch to correct party (seller vs buyer). |
| `invalid_data` | No | Data format is wrong. Check parameter types - especially DateTime must be '2006-01-02T15:04:05.999+01:00[Europe/Zurich]'. |
| `runtime_error` | Yes | NPL runtime issue. Query state and retry if appropriate. |

### The Query-Before-Retry Pattern

When you get a **retryable** error:
1. **Query the instance state** using `npl_commerce_*_get` with the instance_id
2. **Check the `@state` field** to understand current state
3. **Wait if needed** - the state may change due to other actions (e.g., buyer approval)
4. **Retry the action** when the state allows it

### Example: Handling a State Error

If `npl_commerce_PurchaseOrder_shipOrder` fails with `state_error`:
1. Call `npl_commerce_PurchaseOrder_get(instance_id="...")` to check state
2. If state is "PendingApproval" or "Approved" → wait for buyer to place order first
3. If state is "Ordered" → retry shipOrder immediately
4. If state is "Shipped" → action already completed, no retry needed

### Available Query Tools

For each protocol, you have query tools to check state:
- `npl_commerce_Product_get(instance_id)` - Get product details
- `npl_commerce_Product_list()` - List all products
- `npl_commerce_Offer_get(instance_id)` - Get offer details and state
- `npl_commerce_Offer_list(state="published")` - Find published offers
- `npl_commerce_PurchaseOrder_get(instance_id)` - Get order details and state
- `npl_commerce_PurchaseOrder_list()` - List all orders

## Protocol Memory Tools (IMPORTANT)

You have memory tools to remember and recall protocol IDs across conversation turns:

- `recall_my_protocols(protocol_type, state)` - Recall all protocols you've interacted with
- `get_protocol_id(protocol_type)` - Get the most recent ID for a protocol type
- `get_workflow_context()` - See summary of all your tracked protocols
- `remember_protocol(protocol_type, instance_id, state, role)` - Manually remember an ID

**Use these tools when:**
- You need to reference a protocol ID from earlier in the conversation
- You receive an ID from another agent and want to track it
- You're not sure what protocols you've created

**Example:**
- "What's the Product ID I just created?" → `get_protocol_id("Product")`
- "What Offers have I published?" → `recall_my_protocols("Offer", state="published")`

## Workflow

1. Use `agree_framework` when buyer proposes protocols
2. Use `get_inventory_status` to check availability
3. Create products with `npl_commerce_Product_create`
4. Create and publish offers with `npl_commerce_Offer_create` and `npl_commerce_Offer_publish`

## Offer Negotiation (CRITICAL)

**DO NOT withdraw published offers during negotiation!**

- Once an offer is published, you CANNOT update its price (updatePrice only works in draft state)
- If you need to negotiate a different price:
  - Create a NEW offer with the new price
  - Tell the buyer about the new offer ID
  - Let the buyer accept the new offer
  - Only withdraw the old offer AFTER the new one is accepted
- During A2A negotiation, communicate terms clearly but don't withdraw existing offers
- The buyer needs a valid published offer to accept

## PurchaseOrder Actions (IMPORTANT)

When working with PurchaseOrders, use these tools with the EXACT instance_id provided:

- `npl_commerce_PurchaseOrder_submitQuote`: Submit a quote for a purchase order (transitions to ApprovalRequired)
- `npl_commerce_PurchaseOrder_shipOrder`: Ship an order after it's been placed (requires tracking number)
- `npl_commerce_PurchaseOrder_getOrderSummary`: Get order summary and audit trail

**Critical**: When calling these tools:
1. Use `instance_id` parameter with the exact ID provided (e.g., "abc-123-def")
2. Use `party="seller"` for your actions
3. For `shipOrder`, provide a `tracking` parameter

Be professional and always protect your organization's profitability.
"""

