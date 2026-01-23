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
from typing import Optional, Dict, Any, List, Callable

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.sessions import InMemorySessionService

from adk_npl.config import NPLConfig
from adk_npl.agent_factory import EnterpriseAgentFactory
from adk_npl.goal_schemas import BuyerGoalState
from adk_npl.activity_logger import get_activity_logger

logger = logging.getLogger(__name__)


async def create_purchasing_agent(
    config: NPLConfig,
    session_service: InMemorySessionService,
    shopping_list: Optional[Dict[str, Any]] = None,
    budget: Optional[float] = None,
    requirements: Optional[str] = None,
    enable_reflection: bool = True,
    enable_planning: bool = True,
    enable_runtime_validation: bool = True,
    model: str = "gemini-2.0-flash",  # Stable version (non-experimental)
    tool_usage_callback: Optional[Callable[[str, float, bool], None]] = None
) -> Dict[str, Any]:
    """
    Create an enterprise-grade purchasing/buyer agent.
    
    The agent is configured with objective="buying", which automatically:
    - Blocks tools for "seller" party role (via runtime validation)
    - Allows tools for "buyer" party role
    - Includes self-healing error recovery
    - Forces structured reasoning before tool calls
    
    This respects the "Larry Problem": The same agent factory could create
    a seller agent by changing objective="selling". The agent identity is
    determined by objective, not hardcoded logic.
    
    Args:
        config: NPL configuration
        session_service: ADK session service
        shopping_list: Optional buyer's shopping list (from inventory tools)
        budget: Optional budget constraint
        requirements: Optional procurement requirements
        enable_reflection: Enable ReflectAndRetryToolPlugin (default: True)
        enable_planning: Enable PlanReActPlanner (default: True)
        enable_runtime_validation: Enable party role validation (default: True)
        model: LLM model to use
    
    Returns:
        Dict with "agent" (LlmAgent) and "plugins" (list) for Runner setup
        
    Example:
        >>> config = NPLConfig.from_env()
        >>> session_service = InMemorySessionService()
        >>> buyer = await create_purchasing_agent(
        ...     config=config,
        ...     session_service=session_service,
        ...     budget=10000,
        ...     requirements="Purchase Smart Gadget and Premium Widget"
        ... )
        >>> # Agent will automatically reject calls to "seller" tools
    """
    logger.info(
        f"Creating purchasing agent with reflection={enable_reflection}, "
        f"planning={enable_planning}, validation={enable_runtime_validation}"
    )
    
    # Create agent factory
    factory = EnterpriseAgentFactory(
        npl_config=config,
        session_service=session_service
    )
    
    # Prepare additional tools (shopping list, if provided)
    additional_tools = []
    if shopping_list:
        additional_tools.extend(_create_shopping_list_tools(shopping_list))
        logger.info("Added shopping list tools to buyer agent")
    
    # Build custom instructions with workflow guidance
    from adk_npl.workflow_orchestrator import get_workflow_instructions
    workflow_guidance = get_workflow_instructions('buyer')
    
    base_instructions = _build_custom_instructions(
        shopping_list=shopping_list,
        budget=budget,
        requirements=requirements
    )
    
    custom_instructions = f"""{workflow_guidance}

═══════════════════════════════════════════════════════════════════
                    YOUR SPECIFIC CONTEXT
═══════════════════════════════════════════════════════════════════
{base_instructions}"""
    
    # Create agent with declarative objective
    result = await factory.create_agent(
        agent_id="buyer_agent",
        objective="buying",  # ← This drives party role alignment!
        model=model,
        packages=["commerce"],  # NPL packages to generate tools from
        additional_tools=additional_tools,
        enable_reflection=enable_reflection,
        enable_planning=enable_planning,
        enable_runtime_validation=enable_runtime_validation,
        max_retries=3,
        max_tool_calls_per_turn=25,  # Higher limit for sequential execution (planner makes agents slower)
        custom_instructions=custom_instructions,
        output_schema=None,  # ← Disabled: blocks tool calling. Use text-based goal tracking instead.
        tool_usage_callback=tool_usage_callback
    )
    
    # Extract agent and plugins from result
    agent = result["agent"]
    plugins = result["plugins"]
    reset_tool_counter = result["reset_tool_counter"]
    
    logger.info(f"✅ Purchasing agent created successfully with {len(plugins)} plugins")
    
    # Return agent, plugins, and reset function for Runner setup
    return {
        "agent": agent,
        "plugins": plugins,
        "reset_tool_counter": reset_tool_counter
    }


def _build_custom_instructions(
    shopping_list: Optional[Dict[str, Any]],
    budget: Optional[float],
    requirements: Optional[str]
) -> str:
    """
    Build custom instructions specific to purchasing agent.
    
    Args:
        shopping_list: Shopping list data
        budget: Budget constraint
        requirements: Requirements
    
    Returns:
        Custom instruction string
    """
    instructions = []
    
    if requirements:
        instructions.append(f"**Your Procurement Requirements:** {requirements}")
    
    if budget:
        instructions.append(f"**Your Budget:** ${budget:,.2f}")
    
    if shopping_list:
        # Include actual shopping list data so agent doesn't need to call list_shopping_items()
        needs = shopping_list.get("needs", [])
        needs_list = []
        for n in needs:
            needs_list.append(
                f"  - {n.get('item', 'Unknown')}: qty {n.get('desired_quantity', 0)}, "
                f"budget ${n.get('max_budget_per_unit', 0):,.2f}/unit, "
                f"priority: {n.get('priority', 'normal')}"
            )
        needs_summary = "\n".join(needs_list) if needs_list else "  (no items needed)"
        
        instructions.append(
            f"""
**📋 YOUR SHOPPING LIST (already loaded - no need to call list_shopping_items):**
{needs_summary}

**⚠️ CRITICAL - Avoid Duplicates:**
1. You already know your shopping needs (above) - don't call list_shopping_items() repeatedly
2. Check `recall_my_protocols()` to see active workflows FIRST
3. Calculate: needed_quantity - (in_progress_quantity) = remaining_to_order
4. Only start new workflows if remaining_to_order > 0
"""
        )
    
    instructions.append(
        """
**⚡ WORKFLOW:**
1. **recall_my_protocols()** → Check active workflows (ALWAYS FIRST!)
2. If protocols exist → progress them through their lifecycle, DON'T create new ones
3. If nothing in progress → review your shopping list above and start workflows
4. For new items only → start appropriate workflows using available tools
5. **One tool call per turn** → check result, then decide next step

**IMPORTANT:**
- Protocol memory shows workflows IN PROGRESS (updated in real-time)
- Your shopping list is shown above (no need to call list_shopping_items repeatedly)
- **Never create duplicate workflows for items already being processed**
"""
    )
    
    return "\n".join(instructions) if instructions else ""


def _create_shopping_list_tools(shopping_list: Dict[str, Any]) -> List[FunctionTool]:
    """
    Create tools for interacting with buyer's shopping list.
    
    Args:
        shopping_list: Shopping list data structure
    
    Returns:
        List of FunctionTool instances
    """
    def list_shopping_items() -> Dict[str, Any]:
        """
        📋 BUSINESS STATE: Check what you need to purchase.
        
        🚨 CRITICAL: Use this to see what items you should buy!
        
        This shows your shopping list - the items your organization needs.
        Check this when you have NO active protocols to see what work needs to be done.
        
        Returns:
            Dictionary with items and their details (name, quantity, specs)
        """
        logger.info("📋 list_shopping_items() CALLED - Buyer checking shopping list!")
        
        # Log to activity log for metrics tracking
        get_activity_logger().log_tool_call(
            actor="buyer_agent",
            tool_name="list_shopping_items",
            args={}
        )
        
        return {
            "success": True,
            "items": shopping_list.get("needs", []),
            "total_items": len(shopping_list.get("needs", []))
        }
    
    def get_shopping_item_details(item_name: str) -> Dict[str, Any]:
        """
        Get detailed requirements for a specific item on your shopping list.
        
        Args:
            item_name: Name of the item
        
        Returns:
            Item details including specifications and quantity needed
        """
        logger.info(f"Buyer agent getting details for item: {item_name}")
        items = shopping_list.get("needs", [])
        
        for item in items:
            if item.get("item", "").lower() == item_name.lower():
                return {
                    "success": True,
                    "item": item
                }
        
        return {
            "success": False,
            "error": f"Item '{item_name}' not found on shopping list"
        }
    
    return [
        FunctionTool(list_shopping_items, require_confirmation=False),
        FunctionTool(get_shopping_item_details, require_confirmation=False),
    ]
