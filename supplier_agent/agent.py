"""
Copyright 2025 Noumena Digital AG

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
from typing import Optional, Dict, Any, List

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.sessions import InMemorySessionService

from adk_npl.config import NPLConfig
from adk_npl.agent_factory import EnterpriseAgentFactory
from adk_npl.goal_schemas import SupplierGoalStatus
from adk_npl.activity_logger import get_activity_logger

logger = logging.getLogger(__name__)


async def create_supplier_agent(
    config: NPLConfig,
    session_service: InMemorySessionService,
    inventory: Optional[Dict[str, Any]] = None,
    min_price: Optional[float] = None,
    capacity: Optional[Dict[str, Any]] = None,
    enable_reflection: bool = True,
    enable_planning: bool = True,
    enable_runtime_validation: bool = True,
    model: str = "gemini-2.0-flash"  # Stable version (non-experimental)
) -> Dict[str, Any]:
    """
    Create an enterprise-grade supplier/seller agent.
    
    The agent is configured with objective="selling", which automatically:
    - Blocks tools for "buyer" party role (via runtime validation)
    - Allows tools for "seller" party role
    - Includes self-healing error recovery
    - Forces structured reasoning before tool calls
    
    This respects the "Larry Problem": The same agent factory could create
    a buyer agent by changing objective="buying". The agent identity is
    determined by objective, not hardcoded logic.
    
    Args:
        config: NPL configuration
        session_service: ADK session service
        inventory: Optional supplier's inventory (from inventory tools)
        min_price: Optional minimum acceptable price
        capacity: Optional capacity constraints
        enable_reflection: Enable ReflectAndRetryToolPlugin (default: True)
        enable_planning: Enable PlanReActPlanner (default: True)
        enable_runtime_validation: Enable party role validation (default: True)
        model: LLM model to use
    
    Returns:
        Dict with "agent" (LlmAgent) and "plugins" (list) for Runner setup
        
    Example:
        >>> config = NPLConfig.from_env()
        >>> session_service = InMemorySessionService()
        >>> supplier = await create_supplier_agent(
        ...     config=config,
        ...     session_service=session_service,
        ...     min_price=100,
        ...     inventory={"items": [...]}
        ... )
        >>> # Agent will automatically reject calls to "buyer" tools
    """
    logger.info(
        f"Creating supplier agent with reflection={enable_reflection}, "
        f"planning={enable_planning}, validation={enable_runtime_validation}"
    )
    
    # Create agent factory
    factory = EnterpriseAgentFactory(
        npl_config=config,
        session_service=session_service
    )
    
    # Prepare additional tools (inventory, if provided)
    additional_tools = []
    if inventory:
        additional_tools.extend(_create_inventory_tools(inventory))
        logger.info("Added inventory tools to supplier agent")
    
    # Build custom instructions with workflow guidance
    from adk_npl.workflow_orchestrator import get_workflow_instructions
    workflow_guidance = get_workflow_instructions('supplier')
    
    base_instructions = _build_custom_instructions(
        inventory=inventory,
        min_price=min_price,
        capacity=capacity
    )
    
    custom_instructions = f"""{workflow_guidance}

═══════════════════════════════════════════════════════════════════
                    YOUR SPECIFIC CONTEXT
═══════════════════════════════════════════════════════════════════
{base_instructions}"""
    
    # Create agent with declarative objective
    result = await factory.create_agent(
        agent_id="supplier_agent",
        objective="selling",  # ← This drives party role alignment!
        model=model,
        packages=["commerce"],  # NPL packages to generate tools from
        additional_tools=additional_tools,
        enable_reflection=enable_reflection,
        enable_planning=enable_planning,
        enable_runtime_validation=enable_runtime_validation,
        max_retries=3,
        max_tool_calls_per_turn=15,  # Balanced: allows workflow completion while preventing API exhaustion
        custom_instructions=custom_instructions,
        output_schema=None  # ← Disabled: blocks tool calling. Use text-based goal tracking instead.
    )
    
    # Extract agent and plugins from result
    agent = result["agent"]
    plugins = result["plugins"]
    reset_tool_counter = result["reset_tool_counter"]
    
    logger.info(f"✅ Supplier agent created successfully with {len(plugins)} plugins")
    
    # Return agent, plugins, and reset function for Runner setup
    return {
        "agent": agent,
        "plugins": plugins,
        "reset_tool_counter": reset_tool_counter
    }


def _build_custom_instructions(
    inventory: Optional[Dict[str, Any]],
    min_price: Optional[float],
    capacity: Optional[Dict[str, Any]]
) -> str:
    """
    Build custom instructions specific to supplier agent.
    
    Args:
        inventory: Inventory data
        min_price: Minimum price constraint
        capacity: Capacity constraints
    
    Returns:
        Custom instruction string
    """
    instructions = []
    
    if min_price:
        instructions.append(f"**Your Minimum Price:** ${min_price:,.2f}")
    
    if capacity:
        instructions.append(f"**Your Capacity:** {capacity}")
    
    if inventory:
        instructions.append(
            """
**📦 INVENTORY AVAILABLE:**
Use `list_products()` to see what you can sell.

**⚠️ CRITICAL - Avoid Duplicates:**
1. Check inventory ONLY when starting a new sales cycle
2. Check `recall_my_protocols()` to see active workflows
3. Don't create duplicate workflows for items already being sold
4. Wait for active workflows to complete before creating new ones
5. Focus on progressing existing protocols through their lifecycle
"""
        )
    
    instructions.append(
        """
**⚡ WORKFLOW:**
1. **recall_my_protocols()** → Check active workflows (ALWAYS FIRST!)
2. If protocols exist → progress them through their lifecycle, DON'T create new ones
3. If nothing active → **list_products()** → check what you can sell
4. For new products only → start appropriate workflows using available tools
5. **One tool call per turn** → check result, then decide next step

**IMPORTANT:**
- Protocol memory shows workflows IN PROGRESS (updated in real-time)
- Inventory shows TOTAL capacity (updated slowly, only when complete)
- **Never create duplicate workflows for items already being processed**
"""
    )
    
    return "\n".join(instructions) if instructions else ""


def _create_inventory_tools(inventory: Dict[str, Any]) -> List[FunctionTool]:
    """
    Create tools for interacting with supplier's inventory.
    
    Args:
        inventory: Inventory data structure
    
    Returns:
        List of FunctionTool instances
    """
    def list_products() -> Dict[str, Any]:
        """
        📦 BUSINESS STATE: Check what you have to sell.
        
        🚨 CRITICAL: Use this to see what products you can offer!
        
        This shows your inventory - the products you have available to sell.
        Check this when you have NO active protocols to see what you can offer.
        
        Returns:
            Dictionary with products and their details (name, price, stock)
        """
        logger.info("📦 list_products() CALLED - Supplier checking inventory!")
        
        # Log to activity log for metrics tracking
        get_activity_logger().log_tool_call(
            actor="supplier_agent",
            tool_name="list_products",
            args={}
        )
        
        return {
            "success": True,
            "products": inventory.get("products", []),
            "total_products": len(inventory.get("products", []))
        }
    
    def get_product_details(product_name: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific product in inventory.
        
        Args:
            product_name: Name of the product
        
        Returns:
            Product details including price, stock, and specifications
        """
        logger.info(f"Supplier agent getting details for product: {product_name}")
        products = inventory.get("products", [])
        
        for product in products:
            if product.get("name", "").lower() == product_name.lower():
                return {
                    "success": True,
                    "product": product
                }
        
        return {
            "success": False,
            "error": f"Product '{product_name}' not found in inventory"
        }
    
    return [
        FunctionTool(list_products, require_confirmation=False),
        FunctionTool(get_product_details, require_confirmation=False),
    ]
