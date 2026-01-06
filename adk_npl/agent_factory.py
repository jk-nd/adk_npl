"""
Enterprise-Grade Agent Factory with ADK Integration.

This module provides a comprehensive agent creation system that maximizes
Google ADK's enterprise features:

1. Runtime Validation: Enforce party role alignment via require_confirmation
2. Self-Healing: Automatic error reflection and retry via ReflectAndRetryToolPlugin
3. Structured Reasoning: Force planning before action via PlanReActPlanner
4. Observability: Full OpenTelemetry tracing integration
5. Memory Management: Protocol tracking and state awareness

Key Design Principles:
- Generic: Works for any NPL backend (commerce, mortgages, rentals, etc.)
- Larry Problem Compliant: Validates objectives, not fixed identities
- Enterprise-Ready: Error handling, retries, logging, tracing
- Debuggable: Rich logging and structured error reporting
"""

import logging
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.plugins import ReflectAndRetryToolPlugin, LoggingPlugin
from google.adk.planners import PlanReActPlanner
from google.adk.sessions import InMemorySessionService

from .config import NPLConfig
from .auth import KeycloakAuth
from .client import NPLClient
from .tools import NPLToolGenerator
from .protocol_memory import NPLProtocolMemory, create_memory_tools
from .agent_logic import GLOBAL_AGENT_RULES
from .docstring_trimmer import trim_tool_docstrings
from .monitoring import get_metrics

logger = logging.getLogger(__name__)


# =============================================================================
# PARTY OBJECTIVE REGISTRY (Generic, Extensible)
# =============================================================================

PARTY_OBJECTIVE_REGISTRY = {
    # Commerce Domain
    "seller": {
        "objectives": ["selling", "offering", "supplying", "vending", "providing"],
        "description": "Party that sells, offers, or supplies goods/services",
    },
    "buyer": {
        "objectives": ["buying", "purchasing", "acquiring", "procuring", "obtaining"],
        "description": "Party that buys, purchases, or acquires goods/services",
    },
    
    # Financial Domain
    "lender": {
        "objectives": ["lending", "providing credit", "financing", "loaning"],
        "description": "Party that lends money or provides credit",
    },
    "borrower": {
        "objectives": ["borrowing", "taking loan", "obtaining credit", "financing"],
        "description": "Party that borrows money or obtains credit",
    },
    "issuer": {
        "objectives": ["issuing", "creating debt", "emitting", "publishing"],
        "description": "Party that issues financial instruments",
    },
    "payee": {
        "objectives": ["receiving payment", "collecting", "being paid"],
        "description": "Party that receives payment",
    },
    
    # Rental/Leasing Domain
    "renter": {
        "objectives": ["renting", "leasing", "hiring", "borrowing temporarily"],
        "description": "Party that rents or leases goods/services",
    },
    "rental_company": {
        "objectives": ["renting out", "leasing out", "providing rentals"],
        "description": "Party that provides rentals or leases",
    },
    
    # Insurance Domain
    "insurer": {
        "objectives": ["insuring", "providing coverage", "underwriting"],
        "description": "Party that provides insurance coverage",
    },
    "insured": {
        "objectives": ["being insured", "obtaining coverage", "getting protected"],
        "description": "Party that obtains insurance coverage",
    },
    
    # Supply Chain Domain
    "supplier": {
        "objectives": ["supplying", "distributing", "providing inventory"],
        "description": "Party that supplies goods in a supply chain",
    },
    "distributor": {
        "objectives": ["distributing", "wholesaling", "intermediating"],
        "description": "Party that distributes goods",
    },
    "retailer": {
        "objectives": ["retailing", "selling end-user", "merchandising"],
        "description": "Party that sells to end users",
    },
    
    # Quality Control Domain
    "inspector": {
        "objectives": ["inspecting", "auditing", "verifying", "certifying"],
        "description": "Party that inspects or audits",
    },
    "producer": {
        "objectives": ["producing", "manufacturing", "creating"],
        "description": "Party that produces goods",
    },
    
    # Approval/Authorization Domain
    "approver": {
        "objectives": ["approving", "authorizing", "ratifying", "validating"],
        "description": "Party that approves or authorizes",
    },
    "requester": {
        "objectives": ["requesting", "applying for", "seeking approval"],
        "description": "Party that requests approval",
    },
}


def get_aligned_parties(objective: str) -> List[str]:
    """
    Get list of party roles that align with a given objective.
    
    This is the core of our generic party-objective matching system.
    
    Args:
        objective: Agent's declared objective (e.g., "buying", "lending")
    
    Returns:
        List of party role names that align with this objective
        
    Example:
        >>> get_aligned_parties("buying")
        ['buyer']
        >>> get_aligned_parties("lending")
        ['lender']
    """
    objective_lower = objective.lower()
    aligned = []
    
    for party_name, party_info in PARTY_OBJECTIVE_REGISTRY.items():
        if objective_lower in party_info["objectives"]:
            aligned.append(party_name)
    
    logger.debug(f"Objective '{objective}' aligns with party roles: {aligned}")
    return aligned


def is_objective_aligned_with_party(objective: str, party_role: str) -> bool:
    """
    Check if an agent's objective aligns with a required party role.
    
    This is used by require_confirmation validators to enforce party role constraints.
    
    Args:
        objective: Agent's declared objective (e.g., "buying")
        party_role: Required party role for a tool (e.g., "buyer")
    
    Returns:
        True if aligned, False if misaligned
        
    Example:
        >>> is_objective_aligned_with_party("buying", "buyer")
        True
        >>> is_objective_aligned_with_party("buying", "seller")
        False
    """
    party_info = PARTY_OBJECTIVE_REGISTRY.get(party_role)
    if not party_info:
        logger.warning(
            f"Unknown party role '{party_role}' - not in registry. "
            f"Allowing by default (expand registry if needed)."
        )
        return True  # Graceful degradation for unknown parties
    
    objective_lower = objective.lower()
    aligned = objective_lower in party_info["objectives"]
    
    if not aligned:
        logger.info(
            f"Objective-Party mismatch detected: "
            f"objective='{objective}' does not align with party='{party_role}'. "
            f"Expected objectives for {party_role}: {party_info['objectives']}"
        )
    
    return aligned


# =============================================================================
# RUNTIME VALIDATION: Party Role Validators for require_confirmation
# =============================================================================

def create_party_role_validator(
    expected_party: str,
    agent_objective_getter: Callable[[], str]
) -> Callable:
    """
    Create a runtime validator for enforce party role constraints.
    
    This validator is used with FunctionTool's require_confirmation parameter
    to block tool calls when the agent's objective doesn't align with the
    required party role.
    
    How it works:
    1. Tool is about to be called
    2. Validator checks: Does agent objective align with required party?
    3. If NO → Returns True (blocks call, requires confirmation)
    4. If YES → Returns False (allows call)
    
    Since agents run autonomously, "requires confirmation" effectively blocks.
    
    Args:
        expected_party: The party role required for this tool (e.g., "seller")
        agent_objective_getter: Function that returns current agent's objective
    
    Returns:
        Validator function compatible with FunctionTool.require_confirmation
        
    Example:
        >>> validator = create_party_role_validator("seller", lambda: "buying")
        >>> validator(instance_id="123")  # Returns True (blocks - mismatch!)
        
        >>> validator = create_party_role_validator("buyer", lambda: "buying")
        >>> validator(instance_id="123")  # Returns False (allows - aligned!)
    """
    def validator(**kwargs) -> bool:
        """
        Validate if agent's objective aligns with required party role.
        
        Returns:
            True: Block the tool call (require confirmation)
            False: Allow the tool call
        """
        try:
            agent_objective = agent_objective_getter()
            
            if not agent_objective:
                logger.warning(
                    f"Agent objective not set. Allowing tool call by default. "
                    f"(Tool requires: {expected_party})"
                )
                return False  # Graceful degradation
            
            # Check alignment
            if not is_objective_aligned_with_party(agent_objective, expected_party):
                logger.warning(
                    f"🚫 BLOCKING TOOL CALL: Party role mismatch detected!\n"
                    f"   Tool requires: {expected_party}\n"
                    f"   Agent objective: {agent_objective}\n"
                    f"   Expected objectives for {expected_party}: "
                    f"{PARTY_OBJECTIVE_REGISTRY.get(expected_party, {}).get('objectives', [])}\n"
                    f"   Tool args: {kwargs}"
                )
                return True  # Block!
            
            logger.debug(
                f"✅ Party role check PASSED: "
                f"objective='{agent_objective}' aligns with party='{expected_party}'"
            )
            return False  # Allow
            
        except Exception as e:
            logger.error(
                f"Error in party role validator: {e}. "
                f"Allowing by default for safety.",
                exc_info=True
            )
            return False  # Graceful degradation
    
    return validator


# =============================================================================
# AGENT FACTORY: Enterprise-Grade Agent Creation
# =============================================================================

class EnterpriseAgentFactory:
    """
    Factory for creating enterprise-grade agents with full ADK integration.
    
    Features:
    - Runtime party role validation (require_confirmation)
    - Self-healing error recovery (ReflectAndRetryToolPlugin)
    - Structured reasoning (PlanReActPlanner)
    - Protocol memory management (NPLProtocolMemory)
    - Full observability (logging + OpenTelemetry)
    
    Design Philosophy:
    - Generic: Works for any NPL backend
    - Declarative: Specify objective, get appropriate tools
    - Safe: Runtime validation prevents wrong tool calls
    - Observable: Rich logging and tracing
    """
    
    def __init__(
        self,
        npl_config: NPLConfig,
        session_service: InMemorySessionService,
        npl_source_dir: Optional[Path] = None
    ):
        """
        Initialize the agent factory.
        
        Args:
            npl_config: NPL configuration
            session_service: ADK session service for state management
            npl_source_dir: Optional path to NPL source files for metadata
        """
        self.npl_config = npl_config
        self.session_service = session_service
        self.npl_source_dir = npl_source_dir or Path("npl/src/main")
        
        # Will be initialized lazily
        self._npl_client: Optional[NPLClient] = None
        self._tool_generator: Optional[NPLToolGenerator] = None
        
        logger.info("EnterpriseAgentFactory initialized")
    
    async def _ensure_initialized(self, agent_id: str):
        """Lazy initialization of NPL client and tool generator for a specific agent."""
        if self._npl_client is None or getattr(self._npl_client, 'caller_id', None) != agent_id:
            # Authenticate with Keycloak
            auth = KeycloakAuth(
                keycloak_url=self.npl_config.keycloak_url,
                realm=self.npl_config.keycloak_realm,
                client_id=self.npl_config.keycloak_client_id,
                username=self.npl_config.credentials.get("username"),
                password=self.npl_config.credentials.get("password")
            )
            token = await auth.authenticate()
            
            # Create NPL client with agent_id as caller_id for activity logging
            self._npl_client = NPLClient(
                base_url=self.npl_config.engine_url,
                auth_token=token,
                caller_id=agent_id
            )
            
            logger.info(f"NPL client initialized for agent: {agent_id}")
    
    async def create_agent(
        self,
        agent_id: str,
        objective: str,
        model: str = "gemini-1.5-pro",
        packages: Optional[List[str]] = None,
        additional_tools: Optional[List[FunctionTool]] = None,
        enable_reflection: bool = True,
        enable_planning: bool = True,
        enable_runtime_validation: bool = True,
        max_retries: int = 3,
        max_tool_calls_per_turn: int = 50,  # High limit - NPL tools don't consume LLM quota
        custom_instructions: Optional[str] = None,
        output_schema: Optional[type] = None
    ) -> LlmAgent:
        """
        Create an enterprise-grade agent with full ADK integration.
        
        This is the main factory method that combines all ADK features:
        - Runtime validation via require_confirmation
        - Self-healing via ReflectAndRetryToolPlugin
        - Structured reasoning via PlanReActPlanner
        - Memory via NPLProtocolMemory
        
        Args:
            agent_id: Unique agent identifier
            objective: Agent's objective (e.g., "buying", "selling", "lending")
                      This drives party role alignment
            model: LLM model to use
            packages: NPL packages to generate tools from (default: ["commerce"])
            additional_tools: Extra tools beyond NPL tools
            enable_reflection: Enable ReflectAndRetryToolPlugin
            enable_planning: Enable PlanReActPlanner
            enable_runtime_validation: Enable party role validation
            max_retries: Max retries for ReflectAndRetryToolPlugin
            max_tool_calls_per_turn: Safety limit to prevent infinite loops (not for rate limiting - NPL tools are cheap)
            custom_instructions: Custom instructions (appended to base)
        
        Returns:
            Configured LlmAgent instance
            
        Example:
            >>> factory = EnterpriseAgentFactory(config, session_service)
            >>> buyer_agent = await factory.create_agent(
            ...     agent_id="buyer",
            ...     objective="buying",
            ...     enable_reflection=True,
            ...     enable_planning=True
            ... )
        """
        await self._ensure_initialized(agent_id)
        
        logger.info(
            f"Creating agent: {agent_id} with objective='{objective}', "
            f"reflection={enable_reflection}, planning={enable_planning}, "
            f"validation={enable_runtime_validation}"
        )
        
        # Create protocol memory for this agent
        protocol_memory = NPLProtocolMemory(agent_id=agent_id)
        
        # Create tool generator with Smart NPL Bridge
        tool_generator = NPLToolGenerator(
            npl_client=self._npl_client,
            protocol_memory=protocol_memory
        )
        
        # Generate NPL tools from Smart NPL Bridge
        packages = packages or ["commerce"]
        npl_tools = await tool_generator.generate_tools(packages=packages)
        
        logger.info(f"Generated {len(npl_tools)} NPL tools from Smart NPL Bridge")
        
        # Wrap tools with runtime validation if enabled
        if enable_runtime_validation:
            npl_tools = self._wrap_tools_with_validation(
                npl_tools,
                objective=objective,
                agent_id=agent_id
            )
            logger.info(f"Applied runtime party role validation to NPL tools")
        
        # Add memory tools
        memory_tools = create_memory_tools(agent_id=agent_id)
        
        # Add identity tool (for agents to discover their own party claims)
        from .tools import create_identity_tool
        identity_tool = create_identity_tool(self.npl_config)
        
        # Combine all tools
        all_tools = npl_tools + memory_tools + [identity_tool]
        if additional_tools:
            all_tools.extend(additional_tools)
        
        # 🎯 CONTEXT OPTIMIZATION: Trim verbose docstrings (80%+ token reduction)
        # Keeps full tool catalog but reduces context size dramatically
        # This prevents both: (1) quota exhaustion, (2) missing tool functionality
        all_tools = trim_tool_docstrings(all_tools)
        
        logger.info(f"Total tools for agent: {len(all_tools)} (docstrings optimized)")
        
        # Build instructions
        instructions = self._build_instructions(
            agent_id=agent_id,
            objective=objective,
            custom_instructions=custom_instructions
        )
        
        # Create plugins list
        plugins = []
        
        # Optional: Logging plugin for detailed console debugging
        # Disabled by default as we have our own activity logging
        # plugins.append(LoggingPlugin(name=f"{agent_id}_logger"))
        
        # Reflection and retry plugin (self-healing)
        if enable_reflection:
            plugins.append(
                ReflectAndRetryToolPlugin(
                    max_retries=max_retries,
                    throw_exception_if_retry_exceeded=False
                )
            )
            logger.info(f"Enabled ReflectAndRetryToolPlugin (max_retries={max_retries})")
        
        # Create planner
        planner = PlanReActPlanner() if enable_planning else None
        if enable_planning:
            logger.info("Enabled PlanReActPlanner for structured reasoning")
        
        # Create tool call limiting callbacks with per-request reset
        # The counter is stored in a dict so it can be reset from outside (e.g., chat_api)
        tool_call_counter = {"count": 0, "max": max_tool_calls_per_turn}
        
        def reset_tool_counter():
            """Reset the tool call counter for a new turn/request."""
            prev = tool_call_counter["count"]
            tool_call_counter["count"] = 0
            tool_call_counter["recalled"] = False  # Reset orientation flag for new turn
            if prev > tool_call_counter["max"]:
                logger.info(f"🔄 {agent_id} counter reset: was blocked at {prev}, can now resume")
        
        def before_tool_callback(tool, args, tool_context=None, **kwargs):
            """Enforce tool call limit per turn using ADK callback."""
            import time
            metrics = get_metrics()
            
            tool_call_counter["count"] += 1
            tool_call_counter["start_time"] = time.time()
            count = tool_call_counter["count"]
            max_calls = tool_call_counter["max"]
            
            tool_name = getattr(tool, 'name', 'unknown')
            logger.debug(f"🔧 Tool call #{count}/{max_calls}: {tool_name}")
            
            # Record metric for tool call start
            metrics.increment("agent.tool_calls.started", agent=agent_id, tool=tool_name)
            
            # 🎯 SEQUENTIAL PROCESSING: Check for protocol creation attempts
            # Block if agent tries to create a new protocol without checking existing work
            if tool_name.startswith('npl_') and '_create' in tool_name:
                # Extract protocol type from tool name (e.g., npl_commerce_Offer_create -> Offer)
                parts = tool_name.split('_')
                if len(parts) >= 3:
                    protocol_type = parts[2]  # e.g., "Offer", "Product", "PurchaseOrder"
                    
                    # Check if agent has called recall_my_protocols() this turn
                    recalled_this_turn = tool_call_counter.get("recalled", False)
                    
                    if not recalled_this_turn:
                        logger.warning(f"⚠️ Agent {agent_id} trying to create {protocol_type} without calling recall_my_protocols() first")
                        metrics.increment("agent.workflow_violations.missing_recall", agent=agent_id)
                        return {
                            "error": (
                                f"🛑 ORIENTATION REQUIRED: Before creating a new {protocol_type}, you MUST first call "
                                f"`recall_my_protocols()` to check if you already have in-progress work. "
                                f"\n\n"
                                f"**Why?** You may already have a {protocol_type} in progress that needs attention. "
                                f"Creating duplicates wastes time and confuses the workflow. "
                                f"\n\n"
                                f"**What to do:**\n"
                                f"1. Call `recall_my_protocols()` to see your active protocols\n"
                                f"2. If you have in-progress work, focus on completing it\n"
                                f"3. Only create new protocols after finishing existing ones\n"
                                f"\n"
                                f"This is the ORIENT step of ORIENT → DECIDE → ACT → STOP."
                            )
                        }
            
            # Track recall_my_protocols calls
            if tool_name == 'recall_my_protocols':
                tool_call_counter["recalled"] = True
                logger.debug(f"✅ Agent {agent_id} oriented itself by calling recall_my_protocols()")
            
            if count > max_calls:
                logger.warning(f"⛔ Tool call limit exceeded ({count}/{max_calls}). Blocking: {tool_name}")
                metrics.increment("agent.tool_calls.blocked", agent=agent_id, tool=tool_name)
                return {
                    "error": (
                        f"🛑 STOP: You've made {count} tool calls (limit: {max_calls}). "
                        f"You MUST stop now and provide a text response summarizing what you've accomplished. "
                        f"Do NOT call any more tools. Just respond with text explaining your progress."
                    )
                }
            
            return None  # Allow tool call
        
        def after_tool_callback(tool, args, tool_context=None, result=None, **kwargs):
            """Log tool results and record metrics."""
            import time
            metrics = get_metrics()
            
            tool_name = getattr(tool, 'name', 'unknown')
            
            # Record latency
            start_time = tool_call_counter.get("start_time", time.time())
            latency = time.time() - start_time
            metrics.record_latency("agent.tool_calls.latency", latency, agent=agent_id, tool=tool_name)
            metrics.increment("agent.tool_calls.completed", agent=agent_id, tool=tool_name)
            
            logger.debug(f"✅ Tool completed: {tool_name} ({latency*1000:.1f}ms)")
            return None  # Use original result
        
        def on_tool_error_callback(tool, args, tool_context=None, exception=None, **kwargs):
            """
            Gracefully handle tool errors instead of letting LLM retry blindly.
            
            Categorizes errors and provides clear guidance to the LLM:
            - NPL validation errors: Don't retry, explain what's wrong
            - Network errors: Can retry after backoff
            - Permission errors: Don't retry, need different approach
            """
            import traceback
            metrics = get_metrics()
            
            tool_name = getattr(tool, 'name', 'unknown')
            error_msg = str(exception) if exception else "Unknown error"
            error_type = type(exception).__name__
            
            # Record error metrics
            metrics.increment("agent.tool_calls.errors", agent=agent_id, tool=tool_name, error_type=error_type)
            metrics.record_error(error_type, error_msg[:200], agent=agent_id, tool=tool_name)
            
            logger.error(f"❌ Tool error in {tool_name}: {error_type}: {error_msg}")
            
            # Categorize the error for LLM guidance
            if "400" in error_msg or "validation" in error_msg.lower():
                # NPL validation error - don't retry with same params
                return {
                    "error": True,
                    "error_type": "validation",
                    "message": f"NPL rejected the request: {error_msg[:200]}",
                    "guidance": "Check parameter values. Do NOT retry with same parameters.",
                    "retryable": False
                }
            elif "401" in error_msg or "403" in error_msg or "permission" in error_msg.lower():
                # Permission error - need different approach
                return {
                    "error": True,
                    "error_type": "permission",
                    "message": f"Not authorized: {error_msg[:200]}",
                    "guidance": "You may not have permission for this action. Try a different approach.",
                    "retryable": False
                }
            elif "404" in error_msg:
                # Not found - resource doesn't exist
                return {
                    "error": True,
                    "error_type": "not_found",
                    "message": f"Resource not found: {error_msg[:200]}",
                    "guidance": "The protocol or resource doesn't exist. Check the ID.",
                    "retryable": False
                }
            elif "429" in error_msg or "rate" in error_msg.lower():
                # Rate limit - can retry after wait
                return {
                    "error": True,
                    "error_type": "rate_limit",
                    "message": "Rate limit exceeded",
                    "guidance": "Wait a moment before trying again.",
                    "retryable": True
                }
            elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                # Network error - can retry
                return {
                    "error": True,
                    "error_type": "network",
                    "message": f"Network error: {error_msg[:100]}",
                    "guidance": "Temporary network issue. Can retry once.",
                    "retryable": True
                }
            else:
                # Unknown error - be cautious
                return {
                    "error": True,
                    "error_type": "unknown",
                    "message": f"Tool failed: {error_msg[:200]}",
                    "guidance": "An unexpected error occurred. Do NOT retry immediately.",
                    "retryable": False
                }
        
        # Track model error backoff state
        model_error_state = {"retry_count": 0, "last_error_time": None}
        
        def on_model_error_callback(callback_context=None, exception=None, **kwargs):
            """
            Handle LLM API errors with exponential backoff for rate limits.
            
            This prevents the agent from hammering the API when rate limited.
            """
            import time
            
            error_msg = str(exception) if exception else "Unknown error"
            error_type = type(exception).__name__ if exception else "Unknown"
            
            logger.error(f"❌ Model error: {error_type}: {error_msg[:200]}")
            
            # Check for rate limit errors
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                model_error_state["retry_count"] += 1
                retry_count = model_error_state["retry_count"]
                
                # Exponential backoff: 2s, 4s, 8s, 16s, max 30s
                wait_time = min(2 ** retry_count, 30)
                
                logger.warning(f"⏳ Rate limit hit. Waiting {wait_time}s before retry #{retry_count}")
                time.sleep(wait_time)
                
                # Return None to let ADK retry
                return None
            
            # For other errors, don't retry
            logger.error(f"🛑 Non-retryable model error: {error_type}")
            return None
        
        # Create agent (plugins go to Runner, not LlmAgent)
        agent_kwargs = {
            "name": agent_id,
            "model": model,
            "instruction": instructions,
            "tools": all_tools,
            "planner": planner,
            "before_tool_callback": before_tool_callback,
            "after_tool_callback": after_tool_callback,
            "on_tool_error_callback": on_tool_error_callback,
            "on_model_error_callback": on_model_error_callback
        }
        
        # Add output_schema if provided (for goal tracking)
        if output_schema:
            agent_kwargs["output_schema"] = output_schema
            logger.info(f"✅ Goal tracking enabled: {output_schema.__name__}")
        
        agent = LlmAgent(**agent_kwargs)
        
        logger.info(f"✅ Agent '{agent_id}' created successfully")
        logger.info(f"📦 Plugins to add to Runner: {[type(p).__name__ for p in plugins]}")
        
        # Return agent, plugins, and reset function
        # Plugins must be added to Runner, not LlmAgent
        # reset_tool_counter should be called at the start of each new chat request
        return {
            "agent": agent, 
            "plugins": plugins,
            "reset_tool_counter": reset_tool_counter
        }
    
    def _wrap_tools_with_validation(
        self,
        tools: List[FunctionTool],
        objective: str,
        agent_id: str
    ) -> List[FunctionTool]:
        """
        Wrap NPL action tools with party role validation.
        
        This applies require_confirmation validators to enforce party role
        constraints at runtime.
        
        Args:
            tools: List of tools to wrap
            objective: Agent's objective
            agent_id: Agent identifier (for logging)
        
        Returns:
            List of wrapped tools
        """
        wrapped_tools = []
        
        for tool in tools:
            tool_name = getattr(tool, 'name', 'unknown')
            
            # Skip non-NPL tools and query tools (no validation needed)
            if '_create' in tool_name or '_get' in tool_name or '_query' in tool_name or 'recall' in tool_name or 'remember' in tool_name:
                wrapped_tools.append(tool)
                continue
            
            # Extract party role from tool description
            # The Smart NPL Bridge includes "🎯 PARTY ROLE: **{party}**" in descriptions
            tool_description = getattr(tool, 'description', '')
            party_role = self._extract_party_role_from_description(tool_description)
            
            if party_role:
                # Create validator
                validator = create_party_role_validator(
                    expected_party=party_role,
                    agent_objective_getter=lambda obj=objective: obj  # Closure captures objective
                )
                
                # Wrap tool with validator
                # Note: We need to access the underlying function and rewrap
                original_func = tool.func if hasattr(tool, 'func') else (tool._func if hasattr(tool, '_func') else None)
                
                if original_func is None:
                    logger.warning(f"Could not extract function from tool {tool_name}, skipping validation")
                    wrapped_tools.append(tool)
                    continue
                
                wrapped_tool = FunctionTool(
                    original_func,
                    require_confirmation=validator
                )
                
                wrapped_tools.append(wrapped_tool)
                logger.debug(f"Applied party role validator to {tool_name} (requires: {party_role})")
            else:
                # No party role found, add as-is
                wrapped_tools.append(tool)
        
        return wrapped_tools
    
    def _extract_party_role_from_description(self, description: str) -> Optional[str]:
        """
        Extract party role from tool description.
        
        Smart NPL Bridge includes: "### 🎯 PARTY ROLE: **{party}**"
        
        Args:
            description: Tool description
        
        Returns:
            Party role name or None
        """
        import re
        
        # Look for "PARTY ROLE: **{party}**" or "PARTY ROLE: {party}"
        match = re.search(r'PARTY ROLE:\s*\*\*([a-z_]+)\*\*', description, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        
        match = re.search(r'PARTY ROLE:\s*([a-z_]+)', description, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        
        return None
    
    def _build_instructions(
        self,
        agent_id: str,
        objective: str,
        custom_instructions: Optional[str]
    ) -> str:
        """
        Build agent instructions.
        
        Combines:
        - GLOBAL_AGENT_RULES (critical turn limits, memory usage, termination)
        - Objective-specific guidance
        - Custom instructions
        
        Args:
            agent_id: Agent identifier
            objective: Agent objective
            custom_instructions: Custom instructions
        
        Returns:
            Complete instruction string
        """
        # Get aligned party roles for this objective
        aligned_parties = get_aligned_parties(objective)
        party_list = ', '.join(aligned_parties) if aligned_parties else "unknown"
        
        instructions = f"""
{GLOBAL_AGENT_RULES}

## YOUR OBJECTIVE: {objective}

You are an autonomous agent pursuing objectives related to: **{objective}**.

Based on your objective, you typically act in these party roles: **{party_list}**.

### HOW TO USE TOOLS:

**PARTY ROLE MATCHING:**
- Read each tool's "🎯 PARTY ROLE" section carefully
- Ask yourself: "Does my objective ({objective}) align with this party role?"
- The system will AUTOMATICALLY BLOCK tools that don't align with your objective
- If a tool is blocked, it means your objective doesn't match that party role

**WORKFLOW CONTEXT:**
- Check each tool's "📋 WORKFLOW CONTEXT" for prerequisites and state requirements
- Call `recall_my_protocols()` at the start of each turn to see existing protocols
- Prevents duplicate creation and helps track state

**A2A COMMUNICATION:**
- When creating multi-party protocols, exchange identities first via A2A
- Ask the other party: "What is your organization and department?"
- Use EXACT claims they provide (no placeholder values)

**ERROR RECOVERY:**
- If a tool fails, the system will automatically help you reflect and retry
- Read error messages carefully - they contain guidance on how to fix the issue
- If error_type='state_error', query the protocol to check its state before retrying

{custom_instructions or ''}
"""
        
        return instructions

