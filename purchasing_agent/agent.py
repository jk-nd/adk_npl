"""
Purchasing Agent - ADK Implementation with NPL Integration

Autonomous purchasing agent using Google ADK with Gemini and dynamic NPL tools.
Combines:
- Dynamic NPL protocol tools (from adk_npl)
- Business logic tools (evaluate proposals, negotiate)
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


async def create_purchasing_agent(
    config: NPLConfig,
    agent_id: str = "purchasing_001",
    budget: float = 100000.0,
    requirements: str = "General procurement services",
    constraints: Optional[Dict[str, Any]] = None,
    strategy: Optional[str] = None,
    include_npl_tools: bool = True
) -> LlmAgent:
    """
    Create a purchasing agent with ADK and dynamic NPL tools.
    
    Args:
        config: NPL configuration (engine URL, Keycloak settings)
        agent_id: Unique identifier for this agent
        budget: Maximum total budget
        requirements: Natural language description of what to purchase
        constraints: Additional constraints (delivery time, quality, etc.)
        strategy: Negotiation strategy
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
    business_tools = _create_business_tools(budget, requirements, constraints, strategy)
    tools.extend(business_tools)
    logger.info(f"✅ Added {len(business_tools)} business tools")
    
    # 3. Build agent instruction
    instruction = _build_instruction(agent_id, budget, requirements, constraints, strategy)
    
    # 4. Create the ADK agent
    agent = LlmAgent(
        model="gemini-2.0-flash",
        name=f"PurchasingAgent_{agent_id}",
        description=f"Autonomous purchasing agent for {config.credentials.get('username', 'unknown')} with budget ${budget:,.2f}",
        instruction=instruction,
        tools=tools
    )
    
    logger.info(f"✅ Created purchasing agent '{agent_id}' with {len(tools)} total tools")
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
    budget: float,
    requirements: str,
    constraints: Optional[Dict[str, Any]],
    strategy: Optional[str]
) -> List[FunctionTool]:
    """Create business logic tools for the purchasing agent."""
    
    # Store context in closure
    context = {
        "budget": budget,
        "requirements": requirements,
        "constraints": constraints or {},
        "strategy": strategy
    }
    
    def propose_framework() -> Dict[str, Any]:
        """
        Propose using schema.org-based commerce protocols for the transaction.
        
        This should be called at the start of negotiations to agree on the
        framework and NPL protocols to use for the transaction.
        
        Returns:
            Framework proposal with protocol details
        """
        return {
            "framework": "schema.org",
            "protocols": {
                "product": "commerce.Product",
                "offer": "commerce.Offer",
                "order": "commerce.Order"
            },
            "rationale": "Schema.org provides standardized, interoperable commerce types",
            "benefits": [
                "Industry-standard semantics",
                "Clear product, offer, and order lifecycle",
                "Supports negotiation and state tracking"
            ]
        }
    
    def create_proposal(
        description: str,
        quantity: int = 1,
        max_price: Optional[float] = None,
        delivery_requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a purchase proposal to send to suppliers.
        
        Args:
            description: What you want to purchase
            quantity: Number of units needed
            max_price: Maximum price per unit (defaults to budget/quantity)
            delivery_requirements: Specific delivery needs
            
        Returns:
            Structured proposal ready to send
        """
        if max_price is None:
            max_price = context["budget"] / quantity
        
        proposal = {
            "type": "PURCHASE_PROPOSAL",
            "from": "purchasing_agent",
            "description": description,
            "quantity": quantity,
            "max_unit_price": max_price,
            "max_total": min(max_price * quantity, context["budget"]),
            "requirements": context["requirements"],
            "constraints": context["constraints"]
        }
        
        if delivery_requirements:
            proposal["delivery_requirements"] = delivery_requirements
        
        return proposal
    
    def evaluate_proposal(
        supplier_name: str,
        offered_price: float,
        offered_quantity: int,
        delivery_days: int,
        terms: str
    ) -> Dict[str, Any]:
        """
        Evaluate a supplier's proposal and decide on action.
        
        Args:
            supplier_name: Name of the supplier
            offered_price: Price per unit offered
            offered_quantity: Quantity being offered
            delivery_days: Days until delivery
            terms: Other terms and conditions
            
        Returns:
            Evaluation with recommended action (accept/reject/counter)
        """
        total_cost = offered_price * offered_quantity
        budget = context["budget"]
        
        evaluation = {
            "supplier": supplier_name,
            "total_cost": total_cost,
            "budget": budget,
            "within_budget": total_cost <= budget,
            "budget_utilization": (total_cost / budget) * 100 if budget > 0 else 0
        }
        
        # Decision logic
        if total_cost > budget:
            evaluation["action"] = "REJECT"
            evaluation["reason"] = f"Exceeds budget by ${total_cost - budget:,.2f}"
            evaluation["counter_suggestion"] = f"Maximum acceptable price: ${budget / offered_quantity:,.2f} per unit"
        elif total_cost > budget * 0.95:
            evaluation["action"] = "COUNTER"
            evaluation["reason"] = "Close to budget limit, try to negotiate"
            evaluation["counter_suggestion"] = f"Target price: ${budget * 0.85 / offered_quantity:,.2f} per unit"
        else:
            # Check constraints
            constraint_issues = []
            if "max_delivery_days" in context["constraints"]:
                if delivery_days > context["constraints"]["max_delivery_days"]:
                    constraint_issues.append(f"Delivery too slow ({delivery_days} days)")
            
            if constraint_issues:
                evaluation["action"] = "COUNTER"
                evaluation["reason"] = f"Issues: {', '.join(constraint_issues)}"
            else:
                evaluation["action"] = "ACCEPT"
                evaluation["reason"] = "Meets all requirements within budget"
        
        return evaluation
    
    def calculate_counter_offer(
        original_price: float,
        quantity: int,
        discount_percentage: float = 10.0
    ) -> Dict[str, Any]:
        """
        Calculate a counter offer based on the original proposal.
        
        Args:
            original_price: Original price per unit
            quantity: Quantity being negotiated
            discount_percentage: Desired discount percentage
            
        Returns:
            Counter offer details
        """
        counter_price = original_price * (1 - discount_percentage / 100)
        total = counter_price * quantity
        
        # Ensure within budget
        if total > context["budget"]:
            counter_price = context["budget"] / quantity
            total = context["budget"]
        
        return {
            "type": "COUNTER_OFFER",
            "original_price": original_price,
            "counter_price": round(counter_price, 2),
            "quantity": quantity,
            "total": round(total, 2),
            "discount_requested": f"{discount_percentage}%",
            "budget_remaining": context["budget"] - total
        }
    
    def get_budget_status() -> Dict[str, Any]:
        """
        Get current budget status and spending capacity.
        
        Returns:
            Budget information
        """
        return {
            "total_budget": context["budget"],
            "currency": "USD",
            "requirements": context["requirements"],
            "constraints": context["constraints"],
            "strategy": context["strategy"]
        }
    
    # Wrap as FunctionTools
    return [
        FunctionTool(propose_framework, require_confirmation=False),
        FunctionTool(create_proposal, require_confirmation=False),
        FunctionTool(evaluate_proposal, require_confirmation=False),
        FunctionTool(calculate_counter_offer, require_confirmation=False),
        FunctionTool(get_budget_status, require_confirmation=False)
    ]


def _build_instruction(
    agent_id: str,
    budget: float,
    requirements: str,
    constraints: Optional[Dict[str, Any]],
    strategy: Optional[str]
) -> str:
    """Build the agent's instruction prompt."""
    
    constraints_str = ""
    if constraints:
        constraints_list = [f"  - {k}: {v}" for k, v in constraints.items()]
        constraints_str = "\n".join(constraints_list)
    
    return f"""You are a Purchasing Agent (ID: {agent_id}) responsible for procurement operations.

## Your Mission
Negotiate and complete purchases that meet requirements while staying within budget.

## Your Parameters
- **Budget**: ${budget:,.2f} (HARD LIMIT - cannot exceed)
- **Requirements**: {requirements}
- **Your Organization**: Acme Corp, Procurement department
{f"- **Constraints**:\n{constraints_str}" if constraints_str else ""}
{f"- **Strategy**: {strategy}" if strategy else ""}

## Available Capabilities

### Framework Negotiation
- `propose_framework`: Propose using schema.org-based commerce protocols
  - ALWAYS start negotiations by proposing the framework

### NPL Protocol Tools (Dynamically Discovered)
You have access to NPL protocol tools that are automatically generated from the backend.
Each tool has explicit typed parameters - check the tool's signature for required fields.

**Party parameters use this pattern:**
- `seller_organization`: The seller's organization name
- `seller_department`: The seller's department name
- `buyer_organization`: Your organization ("Acme Corp")
- `buyer_department`: Your department ("Procurement")

**Available protocols:** Product, Offer, Order
- Each protocol has `_create` and various action tools
- Tool signatures show exactly what parameters are required

### Business Tools
- `propose_framework`: Start by proposing the protocol framework
- `create_proposal`: Create purchase proposals for suppliers
- `evaluate_proposal`: Evaluate supplier offers and decide action
- `calculate_counter_offer`: Generate counter-offer based on original
- `get_budget_status`: Check your current budget and constraints

## Guidelines

1. **Budget is Sacred**: Never commit to anything exceeding ${budget:,.2f}
2. **Be Strategic**: Start lower to leave room for negotiation
3. **Use Tool Signatures**: Check each tool's parameters before calling
4. **Verify Terms**: Before accepting, ensure all terms are clear
5. **Protect Interests**: Ensure favorable payment and delivery terms

## Workflow

1. Use `propose_framework` to establish protocols
2. Use `get_budget_status` to confirm capacity
3. Evaluate offers with `evaluate_proposal`
4. Accept offers with `npl_commerce_Offer_accept`
5. Create orders with `npl_commerce_Order_create`

Be professional and always protect your organization's interests.
"""
