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

import asyncio
import json
import logging
import threading
import time
import uuid
import httpx
from typing import Dict, List, Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# A2A imports
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

# Local imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from adk_npl import NPLConfig, get_activity_logger, GLOBAL_AGENT_RULES, get_metrics
from adk_npl.protocol_memory import (
    NPLProtocolMemory,
    create_memory_tools,
)
from adk_npl.partner_memory import PartnerMemory, create_partner_memory_tools
from adk_npl.inventory_tools import SupplierInventory, BuyerShoppingList
from adk_npl.erp_sync import ErpSyncService
from supplier_agent.agent import create_supplier_agent
from purchasing_agent.agent import create_purchasing_agent

# =============================================================================
# ENHANCED LOGGING CONFIGURATION
# =============================================================================
# Enable DEBUG logging for adk_npl modules to see what's actually being used

# Create logs directory
Path("logs").mkdir(exist_ok=True)

# Configure root logger with both console and file handlers
log_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
    datefmt='%H:%M:%S'
)

# Console handler - INFO level for readability
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)

# File handler - DEBUG level for full detail
file_handler = logging.FileHandler(f'logs/debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_formatter)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[console_handler, file_handler]
)

# Set specific module log levels for comprehensive tracing
logging.getLogger('adk_npl').setLevel(logging.DEBUG)
logging.getLogger('adk_npl.tools').setLevel(logging.DEBUG)
logging.getLogger('adk_npl.agent_factory').setLevel(logging.DEBUG)
logging.getLogger('adk_npl.client').setLevel(logging.DEBUG)
logging.getLogger('adk_npl.protocol_memory').setLevel(logging.DEBUG)
logging.getLogger('adk_npl.diagram_generator').setLevel(logging.DEBUG)

# Reduce noise from external libraries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.INFO)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# =============================================================================
# TOOL USAGE TRACKER - Captures which tools are actually called
# =============================================================================
class ToolUsageTracker:
    """Track which tools are called and how often during the session."""
    
    def __init__(self):
        self.tool_calls: Dict[str, int] = {}
        self.tool_errors: Dict[str, int] = {}
        self.tool_latencies: Dict[str, List[float]] = {}
        self.unused_tools: set = set()
        self.start_time = time.time()
    
    def record_call(self, tool_name: str, latency: float = 0.0, error: bool = False):
        """Record a tool call."""
        if tool_name not in self.tool_calls:
            self.tool_calls[tool_name] = 0
            self.tool_latencies[tool_name] = []
        self.tool_calls[tool_name] += 1
        self.tool_latencies[tool_name].append(latency)
        if error:
            self.tool_errors[tool_name] = self.tool_errors.get(tool_name, 0) + 1
    
    def set_available_tools(self, tool_names: List[str]):
        """Set the list of available tools for tracking unused ones."""
        self.unused_tools = set(tool_names)
    
    def mark_used(self, tool_name: str):
        """Mark a tool as used."""
        self.unused_tools.discard(tool_name)
    
    def get_summary(self) -> Dict:
        """Get summary of tool usage."""
        runtime = time.time() - self.start_time
        
        # Sort by call count
        sorted_tools = sorted(self.tool_calls.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "runtime_seconds": round(runtime, 1),
            "total_tool_calls": sum(self.tool_calls.values()),
            "unique_tools_used": len(self.tool_calls),
            "tools_never_used": list(self.unused_tools),
            "tools_never_used_count": len(self.unused_tools),
            "top_tools": [
                {
                    "name": name,
                    "calls": count,
                    "errors": self.tool_errors.get(name, 0),
                    "avg_latency_ms": round(sum(self.tool_latencies[name]) / len(self.tool_latencies[name]) * 1000, 1) if self.tool_latencies.get(name) else 0
                }
                for name, count in sorted_tools[:15]
            ],
            "error_prone_tools": [
                {"name": name, "errors": count, "error_rate": f"{count/self.tool_calls.get(name, 1)*100:.1f}%"}
                for name, count in sorted(self.tool_errors.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
        }
    
    def print_summary(self):
        """Print a formatted summary to the console."""
        summary = self.get_summary()
        logger.info("=" * 70)
        logger.info("📊 TOOL USAGE SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Runtime: {summary['runtime_seconds']}s | Total calls: {summary['total_tool_calls']} | Unique tools: {summary['unique_tools_used']}")
        logger.info("")
        logger.info("🔧 TOP TOOLS (by call count):")
        for t in summary['top_tools'][:10]:
            error_str = f" ⚠️ {t['errors']} errors" if t['errors'] > 0 else ""
            logger.info(f"   {t['calls']:3d}x {t['name']}{error_str}")
        logger.info("")
        if summary['tools_never_used']:
            logger.info(f"❌ UNUSED TOOLS ({summary['tools_never_used_count']}):")
            for name in summary['tools_never_used'][:10]:
                logger.info(f"   - {name}")
            if summary['tools_never_used_count'] > 10:
                logger.info(f"   ... and {summary['tools_never_used_count'] - 10} more")
        logger.info("=" * 70)

# Global tracker instance
tool_tracker = ToolUsageTracker()

# Global notification listeners (one per party)
notification_listener_tasks: Dict[str, asyncio.Task] = {}

# Rate limiting for notification processing
notification_cooldown_seconds = 3.0  # Minimum seconds between processing same notification type
last_notification_time: Dict[str, float] = {}  # Track last processing time per notification type
processed_notification_ids: set = set()  # Deduplicate notifications by protocol_id+type


# =============================================================================
# CUSTOM A2A REQUEST HANDLER WITH LLM LOGGING
# =============================================================================

class LoggingA2ARequestHandler(DefaultRequestHandler):
    """Custom A2A request handler that logs LLM calls."""
    
    def __init__(self, agent_executor, task_store, agent_name: str):
        super().__init__(agent_executor=agent_executor, task_store=task_store)
        self.agent_name = agent_name
        self.activity_logger = get_activity_logger()
    
    async def handle(self, request):
        """Handle A2A request and log LLM calls."""
        call_start_time = time.time()
        
        # Call the parent handler
        result = await super().handle(request)
        
        # Log LLM call (agents make at least one LLM call per A2A message)
        total_latency = (time.time() - call_start_time) * 1000
        self.activity_logger.log_llm_call(
            model="gemini-2.0-flash",
            agent=f"{self.agent_name}_agent",
            latency_ms=total_latency,
            success=True,
            context="a2a_message"
        )
        
        return result

app = FastAPI(title="ADK-NPL Chat API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A2A ports
BUYER_A2A_PORT = 8010
SUPPLIER_A2A_PORT = 8011

# Message history
buyer_messages: List[Dict] = []
supplier_messages: List[Dict] = []

# Agent state
agents: Dict[str, any] = {}
runners: Dict[str, Runner] = {}
reset_counters: Dict[str, Callable] = {}  # Tool call counter reset functions
session_service = InMemorySessionService()

# Deterministic local state synchronizer (ERP-like)
erp_sync_service: ErpSyncService | None = None

# Session IDs (set on startup)
buyer_session_id: str = ""
supplier_session_id: str = ""

# Activity logger
activity_logger = get_activity_logger()

class IsolatedA2aAgentExecutor(A2aAgentExecutor):
    """A2A Agent Executor that reuses the main session and clears status queues per role."""

    def __init__(self, runner, role: str, get_session_id: Callable[[], str], reset_counter: Callable[[], None] = None):
        super().__init__(runner=runner)
        self.role = role
        self.get_session_id = get_session_id
        self.reset_counter = reset_counter or (lambda: None)

    async def execute(self, context, event_queue):
        """
        - Reuse the main chat session_id for this role so protocol memory is shared.
        - Clear status queue to avoid stale thoughts.
        """
        # Clear the status queue for this role
        queue = buyer_status_queue if self.role == "buyer" else supplier_status_queue
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # NOTE: Cannot set context.context_id directly (no setter). Instead rely on Runner session_service.
        # A2A calls will create their own session context, but memory tools bridge the gap.
        session_id = self.get_session_id()
        
        # #region agent log
        import json as _json
        with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
            _f.write(_json.dumps({"location": "chat_api:IsolatedA2aAgentExecutor.execute", "message": "A2A execution starting", "data": {"role": self.role, "session_id": session_id, "context_id": str(getattr(context, 'context_id', 'unknown'))[:50]}, "hypothesisId": "H3", "timestamp": time.time()}) + "\n")
        # #endregion

        # Log the inbound message for visibility
        msg_text = ""
        if context.message and context.message.parts:
            msg_text = " ".join([p.text for p in context.message.parts if hasattr(p, "text")])

        logger.info(f"🤖 {self.role.upper()} A2A receive [Main session: {session_id}, A2A context: {context.context_id[:8]}]: {msg_text[:50]}...")

        
        # CRITICAL FIX: Reset tool counter on A2A receive (H1 - counter not resetting)
        self.reset_counter()
        logger.info(f"🔄 {self.role.upper()} tool counter reset for A2A turn")

        return await super().execute(context, event_queue)

# Status queues for streaming thoughts/status (no final answers here)
buyer_status_queue: asyncio.Queue = asyncio.Queue()
supplier_status_queue: asyncio.Queue = asyncio.Queue()

class ChatMessage(BaseModel):
    message: str


def create_buyer_agent_card() -> AgentCard:
    """Create AgentCard for the Buyer agent."""
    return AgentCard(
        name="BuyerAgent",
        description="Purchasing agent for Acme Corp",
        url=f"http://localhost:{BUYER_A2A_PORT}",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="procurement",
                name="Procurement",
                description="Evaluate offers and place purchase orders",
                tags=["purchasing"]
            )
        ]
    )


def create_supplier_agent_card() -> AgentCard:
    """Create AgentCard for the Supplier agent."""
    return AgentCard(
        name="SupplierAgent",
        description="Sales agent for Supplier Inc",
        url=f"http://localhost:{SUPPLIER_A2A_PORT}",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="sales",
                name="Sales",
                description="Create offers and fulfill orders",
                tags=["sales"]
            )
        ]
    )


def create_a2a_message_tool(target_port: int, target_name: str, from_name: str, tool_name: str) -> FunctionTool:
    """Create a tool to send A2A messages to another agent using JSON-RPC message/send."""

    async def send_message(message: str) -> str:
        """
        Send a message to the other agent and WAIT for their response (turn-based conversation).
        
        This implements proper turn-based A2A communication:
        1. Send message
        2. Wait for response (blocking)
        3. Return response to caller
        4. Caller processes response and decides next action
        """
        metrics = get_metrics()
        start_time = time.time()
        
        if from_name == target_name:
            metrics.increment("a2a.messages.errors", from_agent=from_name, reason="self_message")
            return f"Error: Cannot send a message to yourself ({from_name})."
            
        # Record A2A message send attempt
        metrics.increment("a2a.messages.sent", from_agent=from_name, to_agent=target_name)
        
        # #region agent log
        import json as _json_a2a, re as _re_a2a
        with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
            has_identity = "identity" in message.lower() or "organization" in message.lower() or "department" in message.lower()
            # Check for UUID patterns (8-4-4-4-12 hexadecimal)
            uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
            uuid_matches = _re_a2a.findall(uuid_pattern, message.lower())
            has_uuid = len(uuid_matches) > 0
            _f.write(_json_a2a.dumps({"location": "chat_api:send_message", "message": "A2A message content analysis", "data": {"from": from_name, "to": target_name, "has_identity_exchange": has_identity, "has_uuid": has_uuid, "uuid_count": len(uuid_matches), "message_preview": message[:200]}, "hypothesisId": "H10", "timestamp": time.time()}) + "\n")
        # #endregion
        
        # Log send
        activity_logger.log_a2a_message(
            direction="send",
            from_agent=from_name,
            to_agent=target_name,
            url=f"http://localhost:{target_port}/",
            message_preview=message[:120],
            full_message=message[:500]
        )

        try:
            # Turn-based: send and WAIT for response (120s timeout - agents need time for: memory checks + tool discovery + planning + LLM calls + NPL API calls)
            async with httpx.AsyncClient(timeout=120.0) as client:
                msg_id = str(int(time.time() * 1000))
                payload = {
                    "jsonrpc": "2.0",
                    "method": "message/send",
                    "id": msg_id,
                    "params": {
                        "message": {
                            "messageId": msg_id,
                            "role": "user",
                            "parts": [{"text": message}]
                        },
                        "configuration": {
                            "blocking": True,
                            "historyLength": 0
                        }
                    }
                }

                # Send and WAIT for response (blocking, turn-based)
                response = await client.post(
                    f"http://localhost:{target_port}/",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    result = response.json()
                    result_obj = result.get("result", result)
                    
                    # Extract text response from agent
                    if isinstance(result_obj, dict):
                        artifacts = result_obj.get("artifacts", [])
                        for artifact in artifacts:
                            parts = artifact.get("parts", [])
                            for part in parts:
                                if "text" in part and part["text"]:
                                    text_response = part["text"]
                                    # Log the agent's response/thinking (not the A2A message content)
                                    activity_logger.log_agent_thinking(
                                        agent_id=target_name,
                                        thinking=text_response,
                                        context="a2a_response"
                                    )
                                    # Record success metrics
                                    latency = time.time() - start_time
                                    latency_ms = latency * 1000
                                    metrics.increment("a2a.messages.received", from_agent=from_name, to_agent=target_name, status="success")
                                    metrics.record_latency("a2a.roundtrip_time", latency, from_agent=from_name, to_agent=target_name)
                                    
                                    # Log the A2A receive for metrics dashboard
                                    activity_logger.log_a2a_message(
                                        direction="receive",
                                        from_agent=target_name,
                                        to_agent=from_name,
                                        url=f"http://localhost:{target_port}/",
                                        status_code=200,
                                        latency_ms=latency_ms,
                                        message_preview=text_response[:120] if text_response else None
                                    )
                                    
                                    logger.info(f"✓ A2A turn complete: {from_name} ← {target_name} ({latency_ms:.0f}ms)")
                                    return text_response  # Return actual response
                    
                    # No text in response - log as warning and return metadata
                    latency = time.time() - start_time
                    latency_ms = latency * 1000
                    activity_logger.log_a2a_message(
                        direction="receive",
                        from_agent=target_name,
                        to_agent=from_name,
                        url=f"http://localhost:{target_port}/",
                        status_code=200,
                        latency_ms=latency_ms,
                        message_preview="(no text in response)"
                    )
                    logger.warning(f"A2A response from {target_name} had no text")
                    return f"{target_name} responded but sent no message. Check recall_my_protocols()."
                
                # Non-200 response - this is an A2A protocol error, not agent thinking
                latency = time.time() - start_time
                metrics.increment("a2a.messages.errors", from_agent=from_name, to_agent=target_name, status_code=response.status_code)
                metrics.record_latency("a2a.roundtrip_time", latency, from_agent=from_name, to_agent=target_name, status="error")
                
                activity_logger.log_a2a_message(
                    direction="error",
                    from_agent=from_name,
                    to_agent=target_name,
                    url=f"http://localhost:{target_port}/",
                    status_code=response.status_code,
                    message_preview=f"HTTP {response.status_code} error"
                )
                return f"Error: {target_name} returned HTTP {response.status_code}"

        except Exception as e:
            latency = time.time() - start_time
            error_type = type(e).__name__
            
            # Record error metrics
            metrics.increment("a2a.messages.errors", from_agent=from_name, to_agent=target_name, error_type=error_type)
            metrics.record_latency("a2a.roundtrip_time", latency, from_agent=from_name, to_agent=target_name, status="exception")
            metrics.record_error(error_type, str(e)[:200], context="a2a_communication", from_agent=from_name, to_agent=target_name)
            
            logger.error(
                f"A2A communication error from {from_name} to {target_name}: {e}",
                exc_info=True  # Show full traceback
            )
            activity_logger.log_a2a_message(
                direction="error",
                from_agent=from_name,
                to_agent=target_name,
                url=f"http://localhost:{target_port}/",
                status_code=None,
                message_preview=f"Connection error: {str(e)[:50]}"
            )
            return f"SYSTEM ERROR: Connection to {target_name} timed out or failed. They might be busy. Please wait and try again later."

    # Set the function name dynamically for clarity
    send_message.__name__ = tool_name
    return FunctionTool(func=send_message)


async def dispatch_npl_notification(notification_name: str, protocol_id: str, data: dict):
    """
    Generic NPL notification dispatcher with rate limiting.
    
    This is a GENERIC bridge component - no business logic here!
    Business logic is in NPL protocols. This just:
    1. Determines which agent should receive the notification
    2. Tells the agent to use their tools to figure out what to do
    
    Rate limiting prevents cascading notifications from overwhelming agents.
    """
    global last_notification_time, processed_notification_ids
    
    # #region agent log
    import json as _json_notif, time as _time_notif
    with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
        _f.write(_json_notif.dumps({"location": "chat_api:dispatch_notification", "message": "NPL notification received", "data": {"notification": notification_name, "protocol_id": protocol_id, "has_approval_keyword": "Approval" in notification_name}, "hypothesisId": "H11", "timestamp": _time_notif.time()}) + "\n")
    # #endregion
    
    # Deduplicate: Skip if we've already processed this exact notification
    notification_key = f"{protocol_id}:{notification_name}"
    if notification_key in processed_notification_ids:
        logger.debug(f"Skipping duplicate notification: {notification_key}")
        return
    processed_notification_ids.add(notification_key)
    
    # Deterministic "ERP" sync (non-blocking). Not agent logic.
    global erp_sync_service
    if erp_sync_service is not None:
        try:
            payload = data.get("notification", {}) or {}
            asyncio.create_task(erp_sync_service.handle_notification(notification_name, protocol_id, payload))
        except Exception as e:
            logger.warning(f"ERP sync scheduling failed: {e}")

    # Rate limit: Ensure minimum cooldown between notifications of same type
    current_time = time.time()
    type_key = notification_name
    if type_key in last_notification_time:
        elapsed = current_time - last_notification_time[type_key]
        if elapsed < notification_cooldown_seconds:
            wait_time = notification_cooldown_seconds - elapsed
            logger.debug(f"Rate limiting notification {notification_name}: waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
    last_notification_time[type_key] = time.time()
    
    activity_logger = get_activity_logger()
    
    notification_data = data.get("notification", {})
    protocol_type = data.get("protocolType", "")
    new_state = data.get("newState", "")
    
    # Generic routing based on notification naming convention
    # NPL notifications follow patterns like: OfferPublished, OrderShipped, etc.
    # We route based on who the notification is FOR, not what it means
    
    target_agent = None
    
    # Determine target agent based on notification patterns
    # These patterns are generic - they work for any domain
    buyer_patterns = ["Published", "Shipped", "Approved", "Ready", "Available"]
    seller_patterns = ["Accepted", "Rejected", "Placed", "Ordered", "Received", "Requested"]
    
    for pattern in buyer_patterns:
        if pattern in notification_name:
            target_agent = "buyer"
            break
    
    if not target_agent:
        for pattern in seller_patterns:
            if pattern in notification_name:
                target_agent = "supplier"
                break
    
    # Special case: ApprovalRequired goes to HUMAN approver (not an agent)
    # Log prominently to activity log for UI visibility, but don't dispatch to any agent
    if "Approval" in notification_name and "Required" in notification_name:
        # #region agent log
        import json as _json_appr, time as _time_appr
        with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
            _f.write(_json_appr.dumps({"location": "chat_api:approval_handler", "message": "APPROVAL EVENT LOGGED TO UI", "data": {"protocol_id": protocol_id, "notification": notification_name}, "hypothesisId": "H13", "timestamp": _time_appr.time()}) + "\n")
        # #endregion
        
        activity_logger.log_event(
            "approval_required",
            "npl_engine",
            f"⚠️ APPROVAL REQUIRED - Protocol: {protocol_id}",
            {
                "notification": notification_name,
                "protocol_id": protocol_id,
                "new_state": new_state,
                "action_required": "Human approver must log in and approve",
                "approver_credentials": "approver / Welcome123"
            }
        )
        logger.warning(f"⚠️  APPROVAL REQUIRED: Protocol {protocol_id} - Human approver must act!")
        # Don't dispatch to any agent - this requires human approval
        return
    
    # Fallback: if we can't determine, don't dispatch
    if not target_agent:
        logger.debug(f"No target agent for notification: {notification_name}")
        return
    
    # Build a GENERIC message - no business-specific interpretation
    message = f"🔔 NPL NOTIFICATION: {notification_name}"
    if new_state:
        message += f" (state: {new_state})"
    message += f" - Protocol: {protocol_id}"
    
    # Generic action hint - tells agent to use their tools
    action_hint = f"""
Something changed in NPL! Use your tools to understand and respond:

1. assess_workflow_progress() - Understand your current situation
2. recall_my_protocols() - Find protocols you're tracking  
3. npl_*_next_actions(instance_id='{protocol_id}') - See what actions are available

Then DECIDE what to do based on your goals, ACT once, and STOP.
"""
    
    if target_agent and message and target_agent in runners:
        activity_logger.log_event(
            "npl_notification_dispatch",
            "npl_engine",
            f"Dispatching to {target_agent}",
            {
                "target": target_agent, 
                "notification": notification_name, 
                "protocol_id": protocol_id,
                "new_state": new_state
            }
        )
        
        # Build the full notification with actionable guidance
        full_message = message
        if action_hint:
            full_message = f"{message}\n\n{action_hint}"
        
        # Queue the notification message for the agent
        # The agent will process it on its next turn
        notification_payload = {
            "type": "npl_notification",
            "notification": notification_name,
            "protocol_id": protocol_id,
            "new_state": new_state,
            "message": full_message,
            "action_hint": action_hint
        }
        
        if target_agent == "buyer":
            await buyer_status_queue.put(notification_payload)
            # Trigger agent to process notification
            asyncio.create_task(process_notification_for_agent("buyer", notification_payload))
        elif target_agent == "supplier":
            await supplier_status_queue.put(notification_payload)
            # Trigger agent to process notification
            asyncio.create_task(process_notification_for_agent("supplier", notification_payload))
        
        logger.info(f"📨 Dispatched notification to {target_agent}: {notification_name} (state: {new_state})")


async def process_notification_for_agent(agent_role: str, notification: dict):
    """
    Process an NPL notification by triggering the agent to respond.
    
    This enables REACTIVE agent behavior:
    - NPL state changes → notification dispatched → agent triggered
    - Agent uses its tools (assess_workflow_progress, npl_*_next_actions)
      to understand what happened and decide what to do
    """
    # #region agent log
    import json as _json
    with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
        _f.write(_json.dumps({"location": "chat_api:process_notification", "message": "Processing notification for agent", "data": {"agent_role": agent_role, "notification": str(notification)[:300]}, "hypothesisId": "H4", "timestamp": time.time()}) + "\n")
    # #endregion
    metrics = get_metrics()
    start_time = time.time()
    notification_type = notification.get("notification", "unknown")
    
    # Record notification received
    metrics.increment("notification.received", agent=agent_role, type=notification_type)
    
    try:
        # Check if agent is ready
        if agent_role not in runners:
            logger.warning(f"Agent {agent_role} not ready to process notification")
            metrics.increment("notification.skipped", agent=agent_role, reason="not_ready")
            return
        
        runner = runners[agent_role]
        session_id = buyer_session_id if agent_role == "buyer" else supplier_session_id
        
        # Reset tool counter for this notification-triggered turn
        if agent_role in reset_counters:
            reset_counters[agent_role]()
        
        # Build a message that tells the agent about the notification
        notification_message = notification.get("message", "NPL state changed")
        action_hint = notification.get("action_hint", "")
        protocol_id = notification.get("protocol_id", "")
        new_state = notification.get("new_state", "")
        
        # Build a rich, actionable prompt
        agent_prompt = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NPL NOTIFICATION: Something changed in the workflow!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{notification_message}

PROTOCOL ID: {protocol_id}
NEW STATE: {new_state}

YOUR NEXT STEPS:
1. Call recall_my_protocols() to see all your active protocols
2. Call npl_*_next_actions(instance_id='{protocol_id}', my_party='your_role') 
   to see what actions YOU can take on this protocol
3. DECIDE what action advances your goal
4. ACT by calling the appropriate tool
5. STOP and report what you did

{action_hint}
"""
        
        # Store in message history
        messages = buyer_messages if agent_role == "buyer" else supplier_messages
        messages.append({
            "role": "system",
            "content": f"[NPL Notification] {notification.get('notification', 'state_change')}",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"🔔 Triggering {agent_role} agent for notification: {notification.get('notification', 'unknown')}")
        
        # Run the agent with the notification as input (types already imported at module level)
        content = types.Content(
            role="user",
            parts=[types.Part(text=agent_prompt)]
        )
        
        # Use the same user_id as the main chat to reuse the session
        user_id = "buyer_boss" if agent_role == "buyer" else "supplier_boss"
        
        full_response = ""
        call_start_time = time.time()
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content
        ):
            if hasattr(event, 'content') and event.content:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        full_response += part.text
        
        # Log LLM call (at least one was made to get a response)
        total_latency = (time.time() - call_start_time) * 1000
        activity_logger.log_llm_call(
            model="gemini-2.0-flash",
            agent=f"{agent_role}_agent",
            latency_ms=total_latency,
            success=True
        )
        
        # Log the response
        if full_response:
            messages.append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.utcnow().isoformat(),
                "triggered_by": "npl_notification"
            })
            logger.info(f"✅ {agent_role.upper()} responded to notification: {len(full_response)} chars")
        
        # Record success metrics
        latency = time.time() - start_time
        metrics.increment("notification.processed", agent=agent_role, type=notification_type, status="success")
        metrics.record_latency("notification.processing_time", latency, agent=agent_role)
        
    except Exception as e:
        # Record error metrics
        latency = time.time() - start_time
        metrics.increment("notification.processed", agent=agent_role, type=notification_type, status="error")
        metrics.record_latency("notification.processing_time", latency, agent=agent_role)
        metrics.record_error(type(e).__name__, str(e)[:200], context="notification_processing", agent=agent_role)
        
        logger.error(f"❌ Error processing notification for {agent_role}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def listen_to_npl_notifications(config: NPLConfig, party_name: str):
    """
    Listen to NPL Engine notifications via SSE stream for a specific party.
    
    IMPORTANT: NPL notifications are filtered by party - you only see notifications
    for protocols where you are a participant. We need one listener per party.
    
    Args:
        config: NPL configuration with credentials for the party
        party_name: Human-readable name for logging (e.g., "buyer", "supplier", "approver")
    """
    from adk_npl.auth import create_auth_strategy
    
    activity_logger = get_activity_logger()
    
    while True:
        try:
            auth = create_auth_strategy(config)
            if not auth:
                logger.warning(f"No auth strategy for {party_name} notification listener")
                await asyncio.sleep(30)
                continue
                
            token = await auth.authenticate()
            
            # Connect to SSE stream
            async with httpx.AsyncClient(timeout=300.0) as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "text/event-stream"
                }
                
                async with client.stream(
                    "GET",
                    f"{config.engine_url}/api/streams",
                    headers=headers
                ) as response:
                    if response.status_code != 200:
                        logger.error(f"Failed to connect to {party_name} notification stream: {response.status_code}")
                        await asyncio.sleep(30)
                        continue
                    
                    logger.info(f"✅ Connected to NPL notification stream ({party_name})")
                    
                    current_event = {}
                    async for line in response.aiter_lines():
                        if not line:
                            # Empty line = end of event, process it
                            if current_event.get("event") == "notify" and current_event.get("data"):
                                try:
                                    data = json.loads(current_event["data"])
                                    notification_name = data.get("notification", {}).get("name", "unknown")
                                    # Extract protocol ID from refId field
                                    protocol_id = data.get("notification", {}).get("refId") or data.get("protocolId", "unknown")
                                    
                                    # Map party_name to agent name for metrics
                                    target_agent = f"{party_name}_agent" if party_name in ["buyer", "supplier"] else party_name
                                    
                                    activity_logger.log_event(
                                        "npl_notification",
                                        "npl_engine",
                                        f"Notification: {notification_name}",
                                        {
                                            "notification": notification_name,
                                            "protocol_id": protocol_id,
                                            "target_agent": target_agent,
                                            "data": data
                                        }
                                    )
                                    
                                    logger.info(f"📢 NPL Notification: {notification_name} for protocol {protocol_id}")
                                    
                                    # Route notification to appropriate agent!
                                    await dispatch_npl_notification(notification_name, protocol_id, data)
                                    
                                    # If it's an ApprovalRequired notification, log it prominently
                                    if notification_name == "ApprovalRequiredNotification":
                                        order_number = data.get("notification", {}).get("orderNumber", "unknown")
                                        total = data.get("notification", {}).get("total", 0)
                                        logger.info(f"⚠️  APPROVAL REQUIRED: PO {order_number} (${total})")
                                        
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse notification data: {e}")
                                
                                current_event = {}
                        elif line.startswith("event:"):
                            current_event["event"] = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            current_event["data"] = line.split(":", 1)[1].strip()
                        elif line.startswith("id:"):
                            current_event["id"] = line.split(":", 1)[1].strip()
                            
        except Exception as e:
            logger.error(f"Error in notification listener: {e}")
            await asyncio.sleep(10)


def run_a2a_server(a2a_app, port: int, name: str):
    """Run an A2A server in a thread."""
    config = uvicorn.Config(a2a_app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    logger.info(f"Starting {name} A2A server on port {port}")
    server.run()


@app.on_event("startup")
async def startup():
    """Initialize the existing buyer and supplier agents."""
    global buyer_session_id, supplier_session_id, erp_sync_service
    
    logger.info("🚀 Starting Chat API...")
    
    # Configure ADK telemetry (OpenTelemetry integration)
    try:
        from adk_npl.monitoring import configure_adk_telemetry
        configure_adk_telemetry(
            service_name="adk-npl-demo",
            enable_console_export=False,  # Set to True for debug tracing
            capture_content=False  # Privacy: don't capture message content
        )
    except Exception as e:
        logger.warning(f"ADK telemetry configuration failed (non-critical): {e}")
    
    # Load configs and data
    data_dir = Path(__file__).parent.parent / "data"
    
    # Supplier config (same as workflow script)
    supplier_config = NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={
            "username": "supplier_agent",
            "password": "Welcome123"
        }
    )
    supplier_inventory = SupplierInventory(data_dir / "supplier_inventory.json")
    
    # Buyer config (same as workflow script)
    buyer_config = NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="purchasing",
        keycloak_client_id="purchasing",
        credentials={
            "username": "purchasing_agent",
            "password": "Welcome123"
        }
    )
    buyer_shopping_list = BuyerShoppingList(data_dir / "buyer_shopping_list.json")
    
    # Deterministic local state sync (ERP-like): updates shopping list + inventory on engine notifications
    # Use buyer realm credentials for read access to PurchaseOrders.
    erp_sync_service = ErpSyncService(
        npl_config=buyer_config,
        buyer_shopping_list=buyer_shopping_list,
        supplier_inventory=supplier_inventory,
        state_file=data_dir / "erp_sync_state.json",
    )
    
    # Approver config (for notification listener - needs to see approval notifications)
    approver_config = NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="purchasing",
        keycloak_client_id="purchasing",
        credentials={
            "username": "approver",
            "password": "Welcome123"
        }
    )
    
    # Create the SAME agents from the workflow, with A2A messaging tools added
    logger.info("Creating enterprise-grade agents with ADK integration...")
    
    # Create tool usage tracking callback
    def track_tool_usage(tool_name: str, latency: float, is_error: bool):
        """Callback to track tool usage in the global tracker."""
        tool_tracker.record_call(tool_name, latency, is_error)
        tool_tracker.mark_used(tool_name)
    
    # Create base agents using EnterpriseAgentFactory
    buyer_result = await create_purchasing_agent(
        config=buyer_config,
        session_service=session_service,
        shopping_list=buyer_shopping_list.data,
        budget=200000.0,
        requirements="Purchase items from shopping list",
        enable_reflection=False,  # Disabled - error guidance in callbacks is sufficient
        enable_planning=True,     # Required - prevents parallel tool calls
        enable_runtime_validation=True,
        tool_usage_callback=track_tool_usage
    )
    buyer_agent = buyer_result["agent"]
    buyer_plugins = buyer_result["plugins"]
    buyer_reset_counter = buyer_result.get("reset_tool_counter", lambda: None)
    
    supplier_result = await create_supplier_agent(
        config=supplier_config,
        session_service=session_service,
        inventory=supplier_inventory.data,
        min_price=1000.0,
        enable_reflection=False,  # Disabled - error guidance in callbacks is sufficient
        enable_planning=True,     # Required - prevents parallel tool calls
        enable_runtime_validation=True,
        tool_usage_callback=track_tool_usage
    )
    supplier_agent = supplier_result["agent"]
    supplier_plugins = supplier_result["plugins"]
    supplier_reset_counter = supplier_result.get("reset_tool_counter", lambda: None)
    
    logger.info(f"✅ Buyer agent created with {len(buyer_plugins)} plugins")
    logger.info(f"✅ Supplier agent created with {len(supplier_plugins)} plugins")
    
    # Create A2A messaging tools with descriptive names
    msg_supplier_tool = create_a2a_message_tool(
        SUPPLIER_A2A_PORT, 
        "supplier_agent", 
        "buyer_agent",
        tool_name="send_message_to_supplier"
    )
    msg_buyer_tool = create_a2a_message_tool(
        BUYER_A2A_PORT, 
        "buyer_agent", 
        "supplier_agent",
        tool_name="send_message_to_buyer"
    )
    
    # Add A2A messaging tools to existing agents
    buyer_agent.tools.append(msg_supplier_tool)
    supplier_agent.tools.append(msg_buyer_tool)
    
    # Create SHARED partner memory (so agents can discover each other's identities)
    partner_memory = PartnerMemory()
    partner_tools = create_partner_memory_tools(partner_memory)
    
    # Add partner memory tools to both agents
    for tool in partner_tools:
        buyer_agent.tools.append(tool)
        supplier_agent.tools.append(tool)
    
    logger.info(f"✅ Added {len(partner_tools)} partner memory tools to both agents")
    
    # Track all available tools for usage analysis
    all_tool_names = []
    for tool in buyer_agent.tools:
        tool_name = getattr(tool, 'name', getattr(tool, '__name__', str(tool)))
        all_tool_names.append(tool_name)
    tool_tracker.set_available_tools(all_tool_names)
    logger.info(f"📊 Tracking {len(all_tool_names)} tools for usage analysis")
    
    agents["supplier"] = supplier_agent
    agents["buyer"] = buyer_agent
    
    # Create runners with plugins
    runners["supplier"] = Runner(
        app_name="supplier_chat",
        agent=supplier_agent,
        plugins=supplier_plugins,
        session_service=session_service
    )
    runners["buyer"] = Runner(
        app_name="buyer_chat",
        agent=buyer_agent,
        plugins=buyer_plugins,
        session_service=session_service
    )
    
    # Store reset functions for tool call counters
    reset_counters["buyer"] = buyer_reset_counter
    reset_counters["supplier"] = supplier_reset_counter
    
    # Create A2A executors and servers, reusing main session ids for shared memory
    # CRITICAL: Pass reset_counter so A2A receives also reset the tool call counter
    buyer_executor = IsolatedA2aAgentExecutor(
        runner=runners["buyer"],
        role="buyer",
        get_session_id=lambda: buyer_session_id,
        reset_counter=buyer_reset_counter
    )
    supplier_executor = IsolatedA2aAgentExecutor(
        runner=runners["supplier"],
        role="supplier",
        get_session_id=lambda: supplier_session_id,
        reset_counter=supplier_reset_counter
    )
    
    buyer_card = create_buyer_agent_card()
    supplier_card = create_supplier_agent_card()
    
    buyer_handler = LoggingA2ARequestHandler(
        agent_executor=buyer_executor,
        task_store=InMemoryTaskStore(),
        agent_name="buyer"
    )
    supplier_handler = LoggingA2ARequestHandler(
        agent_executor=supplier_executor,
        task_store=InMemoryTaskStore(),
        agent_name="supplier"
    )
    
    buyer_a2a_app = A2AStarletteApplication(
        agent_card=buyer_card,
        http_handler=buyer_handler
    )
    supplier_a2a_app = A2AStarletteApplication(
        agent_card=supplier_card,
        http_handler=supplier_handler
    )
    
    # Start A2A servers in background
    logger.info(f"Starting A2A servers...")
    threading.Thread(
        target=run_a2a_server,
        args=(buyer_a2a_app.build(), BUYER_A2A_PORT, "Buyer"),
        daemon=True
    ).start()
    threading.Thread(
        target=run_a2a_server,
        args=(supplier_a2a_app.build(), SUPPLIER_A2A_PORT, "Supplier"),
        daemon=True
    ).start()
    
    await asyncio.sleep(2)
    
    # Create fresh sessions
    session_suffix = str(int(time.time()))
    buyer_session_id = f"buyer_{session_suffix}"
    supplier_session_id = f"supplier_{session_suffix}"
    
    await session_service.create_session(
        app_name="buyer_chat",
        user_id="buyer_boss",
        session_id=buyer_session_id
    )
    await session_service.create_session(
        app_name="supplier_chat",
        user_id="supplier_boss",
        session_id=supplier_session_id
    )
    
    # Start NPL notification listeners - one per party
    # NPL only sends notifications to parties that participate in the protocol
    global notification_listener_tasks
    notification_listener_tasks["buyer"] = asyncio.create_task(
        listen_to_npl_notifications(buyer_config, "buyer")
    )
    notification_listener_tasks["supplier"] = asyncio.create_task(
        listen_to_npl_notifications(supplier_config, "supplier")
    )
    notification_listener_tasks["approver"] = asyncio.create_task(
        listen_to_npl_notifications(approver_config, "approver")
    )
    logger.info("📢 NPL notification listeners started (buyer, supplier, approver)")
    
    logger.info("✅ Chat API ready")
    logger.info(f"   Buyer A2A:    http://localhost:{BUYER_A2A_PORT}")
    logger.info(f"   Supplier A2A: http://localhost:{SUPPLIER_A2A_PORT}")


@app.post("/chat/buyer")
async def chat_buyer(message: ChatMessage):
    """Send a message to the buyer agent (from the purchasing manager)."""
    if "buyer" not in runners:
        raise HTTPException(status_code=503, detail="Buyer agent not ready")
    
    # Reset tool call counter for new request
    if "buyer" in reset_counters:
        reset_counters["buyer"]()
    
    user_msg = {
        "role": "user",
        "content": message.message,
        "timestamp": datetime.utcnow().isoformat()
    }
    buyer_messages.append(user_msg)
    
    try:
        runner = runners["buyer"]
        content = types.Content(role="user", parts=[types.Part(text=message.message)])
        
        full_response = ""
        call_start_time = time.time()
        async for event in runner.run_async(
            new_message=content,
            user_id="buyer_boss",
            session_id=buyer_session_id
        ):
            if hasattr(event, "content") and hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        # Stream thought/status and SAVE to history
                        status_msg = {
                            "role": "status",
                            "content": part.text,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        buyer_messages.append(status_msg)
                        await buyer_status_queue.put({"type": "status", "data": part.text})
                        full_response += part.text
        
        # Log LLM call (at least one was made to get a response)
        total_latency = (time.time() - call_start_time) * 1000
        activity_logger.log_llm_call(
            model="gemini-2.0-flash",
            agent="buyer_agent",
            latency_ms=total_latency,
            success=True
        )
        
        assistant_msg = {
            "role": "assistant",
            "content": full_response,
            "timestamp": datetime.utcnow().isoformat()
        }
        buyer_messages.append(assistant_msg)
        logger.info(f"✅ Buyer response: {len(full_response)} chars")
        
        # #region agent log
        import json as _json
        with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
            _f.write(_json.dumps({"location": "chat_api:chat_buyer", "message": "Buyer turn complete", "data": {"response_len": len(full_response), "response_preview": full_response[:200]}, "hypothesisId": "H3", "timestamp": time.time()}) + "\n")
        # #endregion
        
        return {"success": True, "response": full_response}
    
    except Exception as e:
        logger.error(f"Error in buyer chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/supplier")
async def chat_supplier(message: ChatMessage):
    """Send a message to the supplier agent (from the sales manager)."""
    if "supplier" not in runners:
        raise HTTPException(status_code=503, detail="Supplier agent not ready")
    
    # Reset tool call counter for new request
    if "supplier" in reset_counters:
        reset_counters["supplier"]()
    
    user_msg = {
        "role": "user",
        "content": message.message,
        "timestamp": datetime.utcnow().isoformat()
    }
    supplier_messages.append(user_msg)
    
    try:
        runner = runners["supplier"]
        content = types.Content(role="user", parts=[types.Part(text=message.message)])
        
        full_response = ""
        call_start_time = time.time()
        async for event in runner.run_async(
            new_message=content,
            user_id="supplier_boss",
            session_id=supplier_session_id
        ):
            if hasattr(event, "content") and hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        # Stream thought/status and SAVE to history
                        status_msg = {
                            "role": "status",
                            "content": part.text,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        supplier_messages.append(status_msg)
                        await supplier_status_queue.put({"type": "status", "data": part.text})
                        full_response += part.text
        
        # Log LLM call (at least one was made to get a response)
        total_latency = (time.time() - call_start_time) * 1000
        activity_logger.log_llm_call(
            model="gemini-2.0-flash",
            agent="supplier_agent",
            latency_ms=total_latency,
            success=True
        )
        
        assistant_msg = {
            "role": "assistant",
            "content": full_response,
            "timestamp": datetime.utcnow().isoformat()
        }
        supplier_messages.append(assistant_msg)
        logger.info(f"✅ Supplier response: {len(full_response)} chars")
        
        # #region agent log
        import json as _json
        with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
            _f.write(_json.dumps({"location": "chat_api:chat_supplier", "message": "Supplier turn complete", "data": {"response_len": len(full_response), "response_preview": full_response[:200]}, "hypothesisId": "H3", "timestamp": time.time()}) + "\n")
        # #endregion
        
        return {"success": True, "response": full_response}
    
    except Exception as e:
        logger.error(f"Error in supplier chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/buyer/history")
async def get_buyer_history():
    return {"messages": buyer_messages}


@app.get("/chat/supplier/history")
async def get_supplier_history():
    return {"messages": supplier_messages}


@app.get("/chat/buyer/stream")
async def stream_buyer():
    """Stream buyer status/thought updates via SSE (no final answers)."""
    async def event_generator():
        while True:
            try:
                item = await asyncio.wait_for(buyer_status_queue.get(), timeout=1.0)
                yield f"data: {json.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/chat/supplier/stream")
async def stream_supplier():
    """Stream supplier status/thought updates via SSE (no final answers)."""
    async def event_generator():
        while True:
            try:
                item = await asyncio.wait_for(supplier_status_queue.get(), timeout=1.0)
                yield f"data: {json.dumps(item)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "agents": {
            "supplier": "supplier" in agents,
            "buyer": "buyer" in agents
        },
        "a2a": {
            "buyer_port": BUYER_A2A_PORT,
            "supplier_port": SUPPLIER_A2A_PORT
        }
    }


@app.get("/tool-usage")
async def get_tool_usage():
    """Get summary of tool usage for analysis."""
    summary = tool_tracker.get_summary()
    
    # Also get metrics from the metrics collector
    metrics = get_metrics()
    metrics_summary = metrics.get_summary() if hasattr(metrics, 'get_summary') else {}
    
    return {
        "tool_usage": summary,
        "metrics": metrics_summary,
        "activity_log": str(activity_logger.log_file) if hasattr(activity_logger, 'log_file') else None
    }


@app.get("/tool-usage/print")
async def print_tool_usage():
    """Print tool usage summary to console and return it."""
    tool_tracker.print_summary()
    return tool_tracker.get_summary()


@app.post("/restart-session")
async def restart_session():
    """
    Complete restart of the demo server.
    This restarts the entire process, reloading agents and refetching OpenAPI specs.
    """
    import os
    import sys
    import signal
    
    logger.info("🔄 Complete restart requested...")
    
    # Reinitialize activity logger with new file
    try:
        activity_logger.reinitialize()
        logger.info("✅ Activity logger reinitialized with new log file")
    except Exception as e:
        logger.warning(f"Could not reinitialize activity logger: {e}")
    
    # Cancel notification listeners
    global notification_listener_tasks
    for task in notification_listener_tasks.values():
        if task:
            task.cancel()
    notification_listener_tasks.clear()
    
    # Clear agent state
    global agents, runners, reset_counters, processed_notification_ids, last_notification_time
    agents.clear()
    runners.clear()
    reset_counters.clear()
    buyer_messages.clear()
    supplier_messages.clear()
    processed_notification_ids.clear()
    last_notification_time.clear()
    
    # Clear protocol memory (singleton instances that persist across restarts)
    from adk_npl.protocol_memory import NPLProtocolMemory
    NPLProtocolMemory.clear_all()
    
    logger.info("✅ Agent state and protocol memory cleared")
    
    # Get the command to restart
    python_exe = sys.executable
    script_path = Path(__file__)
    
    # Schedule restart after response is sent
    def trigger_restart():
        import time as t
        import subprocess
        t.sleep(0.5)  # Give time for response to be sent
        
        # Start new process before killing current one
        subprocess.Popen(
            [python_exe, str(script_path)],
            cwd=str(script_path.parent),
            start_new_session=True
        )
        
        t.sleep(1)  # Give new process time to start
        os.kill(os.getpid(), signal.SIGTERM)
    
    import threading
    threading.Thread(target=trigger_restart, daemon=True).start()
    
    return {
        "status": "restarting",
        "message": "Demo is restarting completely (reloading agents and OpenAPI specs)..."
    }


@app.post("/reset")
async def reset_agents():
    """Fast reset: Clear agent chat history and create fresh sessions (no full restart)."""
    global buyer_messages, supplier_messages, buyer_session_id, supplier_session_id
    
    try:
        # Clear chat history
        buyer_messages.clear()
        supplier_messages.clear()
        
        # Create fresh session IDs
        import uuid
        buyer_session_id = str(uuid.uuid4())
        supplier_session_id = str(uuid.uuid4())
        
        # Create new sessions in the session service
        await session_service.create_session(
            app_name="buyer_chat",
            user_id="buyer_boss",
            session_id=buyer_session_id
        )
        await session_service.create_session(
            app_name="supplier_chat",
            user_id="supplier_boss",
            session_id=supplier_session_id
        )
        
        logger.info(f"✅ Reset complete. New buyer session: {buyer_session_id[:8]}, supplier: {supplier_session_id[:8]}")
        
        return {
            "status": "success",
            "message": "Agent sessions and chat history reset",
            "buyer_session": buyer_session_id,
            "supplier_session": supplier_session_id
        }
    except Exception as e:
        logger.error(f"Reset failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.on_event("shutdown")
async def on_shutdown():
    """Print tool usage summary when server shuts down."""
    logger.info("")
    logger.info("🛑 Server shutting down - printing final summary...")
    tool_tracker.print_summary()
    
    # Also save summary to file
    summary = tool_tracker.get_summary()
    summary_file = Path("logs") / f"tool_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    logger.info(f"📊 Tool usage saved to: {summary_file}")


@app.post("/shutdown")
async def shutdown():
    """
    Gracefully shutdown the demo server.
    This endpoint allows the UI to stop the demo cleanly.
    """
    import os
    import signal
    
    logger.info("🛑 Shutdown requested via API")
    
    # Print tool usage summary before shutdown
    tool_tracker.print_summary()
    
    # Cancel notification listeners
    global notification_listener_tasks
    for task in notification_listener_tasks.values():
        if task:
            task.cancel()
    
    # Schedule shutdown after response is sent
    def trigger_shutdown():
        import time
        time.sleep(0.5)  # Give time for response to be sent
        os.kill(os.getpid(), signal.SIGTERM)
    
    import threading
    threading.Thread(target=trigger_shutdown, daemon=True).start()
    
    return {"status": "shutting_down", "message": "Demo is shutting down..."}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
