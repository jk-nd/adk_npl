"""
NPL Protocol Memory - Generic State Tracking for LLM Agents

Provides workflow-agnostic memory for NPL protocol instances.
Agents can track and recall any protocol instances they've created
or interacted with, without workflow-specific logic.

Features:
- Auto-tracks protocol instances on creation
- Provides recall tools for agents
- Thread-safe for concurrent access
- Integrates with ADK MemoryService (optional)
"""

import threading
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


class NPLProtocolMemory:
    """
    Thread-safe memory for NPL protocol instances.
    
    Tracks all protocol instances an agent has created or interacted with,
    enabling agents to recall IDs and state across conversation turns.
    """
    
    _instances: Dict[str, 'NPLProtocolMemory'] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls, agent_id: str = "default") -> 'NPLProtocolMemory':
        """Get or create a memory instance for an agent."""
        with cls._lock:
            if agent_id not in cls._instances:
                cls._instances[agent_id] = cls(agent_id)
            return cls._instances[agent_id]
    
    @classmethod
    def clear_all(cls):
        """Clear all memory instances (for testing)."""
        with cls._lock:
            cls._instances.clear()
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._protocols: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._history: List[Dict[str, Any]] = []
    
    def track_protocol(
        self,
        protocol_type: str,
        instance_id: str,
        state: str = "created",
        role: str = "owner",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Track a protocol instance.
        
        Args:
            protocol_type: Type of protocol (any NPL protocol name)
            instance_id: UUID of the instance
            state: Current state of the protocol (any state string)
            role: Agent's relationship to this protocol (any string)
            metadata: Additional context (any key-value pairs)
        """
        with self._lock:
            key = f"{protocol_type}:{instance_id}"
            entry = {
                "protocol_type": protocol_type,
                "instance_id": instance_id,
                "state": state,
                "role": role,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            self._protocols[key] = entry
            self._history.append({
                "action": "track",
                "protocol_type": protocol_type,
                "instance_id": instance_id,
                "timestamp": entry["created_at"]
            })
            logger.debug(f"Tracked {protocol_type} instance: {instance_id}")
    
    def update_state(self, protocol_type: str, instance_id: str, new_state: str):
        """Update the state of a tracked protocol."""
        with self._lock:
            key = f"{protocol_type}:{instance_id}"
            if key in self._protocols:
                self._protocols[key]["state"] = new_state
                self._protocols[key]["last_updated"] = datetime.now(timezone.utc).isoformat()
                self._history.append({
                    "action": "update_state",
                    "protocol_type": protocol_type,
                    "instance_id": instance_id,
                    "new_state": new_state,
                    "timestamp": self._protocols[key]["last_updated"]
                })
    
    def get_protocols(
        self,
        protocol_type: Optional[str] = None,
        state: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get tracked protocols, optionally filtered.
        
        Args:
            protocol_type: Filter by protocol type name
            state: Filter by state (e.g., "published")
            
        Returns:
            List of matching protocol entries
        """
        with self._lock:
            results = list(self._protocols.values())
            
            if protocol_type:
                results = [p for p in results if p["protocol_type"] == protocol_type]
            
            if state:
                results = [p for p in results if p["state"] == state]
            
            return results
    
    def get_latest(self, protocol_type: str) -> Optional[Dict[str, Any]]:
        """Get the most recently tracked instance of a protocol type."""
        protocols = self.get_protocols(protocol_type=protocol_type)
        if not protocols:
            return None
        return max(protocols, key=lambda p: p["last_updated"])
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all tracked protocols."""
        with self._lock:
            by_type: Dict[str, List[str]] = {}
            for entry in self._protocols.values():
                ptype = entry["protocol_type"]
                if ptype not in by_type:
                    by_type[ptype] = []
                by_type[ptype].append(f"{entry['instance_id']} ({entry['state']})")
            
            return {
                "agent_id": self.agent_id,
                "total_protocols": len(self._protocols),
                "by_type": by_type,
                "recent_actions": self._history[-5:] if self._history else []
            }


def create_memory_tools(agent_id: str = "default") -> List[FunctionTool]:
    """
    Create memory tools for an agent.
    
    These tools allow agents to recall protocol instances they've
    created or interacted with, without workflow-specific logic.
    
    Args:
        agent_id: Identifier for the agent's memory scope
        
    Returns:
        List of FunctionTool instances
    """
    memory = NPLProtocolMemory.get_instance(agent_id)
    
    def recall_my_protocols(
        protocol_type: Optional[str] = None,
        state: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Recall all NPL protocol instances you have created or interacted with.
        
        Use this tool when you need to remember IDs of protocols you've worked with.
        This is essential for multi-step workflows where you need to reference
        previously created instances.
        
        Args:
            protocol_type: Optional filter by protocol type name (any NPL protocol)
            state: Optional filter by state (e.g., "published", "accepted", "approved")
            
        Returns:
            List of protocol instances with IDs, types, states, and metadata
            
        Example Usage:
            - "What protocols of type X have I created?" → recall_my_protocols(protocol_type="X")
            - "What protocols are in state Y?" → recall_my_protocols(state="Y")
            - "Show me everything" → recall_my_protocols()
        """
        protocols = memory.get_protocols(protocol_type=protocol_type, state=state)
        
        if not protocols:
            return {
                "success": True,
                "count": 0,
                "protocols": [],
                "hint": f"No protocols found matching filters. protocol_type={protocol_type}, state={state}"
            }
        
        return {
            "success": True,
            "count": len(protocols),
            "protocols": protocols,
            "hint": "Use the instance_id from these results when calling other NPL tools"
        }
    
    def get_protocol_id(protocol_type: str) -> Dict[str, Any]:
        """
        Get the most recent instance ID for a protocol type.
        
        Quick way to get the ID of the last protocol you created of a given type.
        Useful when you need to reference a recently created instance.
        
        Args:
            protocol_type: The NPL protocol type name
            
        Returns:
            The instance ID and current state, or error if not found
            
        Example Usage:
            - "What's my X ID?" → get_protocol_id("X")
            - "What's the ID of the protocol I just created?" → get_protocol_id("ProtocolType")
        """
        latest = memory.get_latest(protocol_type)
        
        if not latest:
            return {
                "success": False,
                "error": f"No {protocol_type} instances found in memory",
                "hint": f"You may need to create a {protocol_type} first, or the instance was created in a previous session"
            }
        
        return {
            "success": True,
            "protocol_type": protocol_type,
            "instance_id": latest["instance_id"],
            "state": latest["state"],
            "role": latest["role"],
            "metadata": latest.get("metadata", {}),
            "hint": f"Use instance_id '{latest['instance_id']}' when calling {protocol_type} actions"
        }
    
    def get_workflow_context() -> Dict[str, Any]:
        """
        Get a summary of your current workflow context.
        
        Returns all protocol instances you've created or interacted with,
        organized by type. Use this to understand your current state in
        a multi-step workflow.
        
        Returns:
            Summary of all tracked protocols with counts and recent actions
            
        Example Usage:
            - "What's my current workflow state?" → get_workflow_context()
            - "What have I created so far?" → get_workflow_context()
        """
        return {
            "success": True,
            **memory.get_summary(),
            "hint": "This shows all protocols you've interacted with. Use recall_my_protocols() for details."
        }
    
    def remember_protocol(
        protocol_type: str,
        instance_id: str,
        state: str = "created",
        role: str = "participant",
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Manually remember a protocol instance.
        
        Use this when you receive a protocol ID from another agent or external source
        and want to track it for later reference.
        
        Args:
            protocol_type: The NPL protocol type name
            instance_id: The UUID of the instance
            state: Current state of the protocol
            role: Your role with this protocol (any string: "owner", "participant", etc.)
            description: Optional description to help you remember what this is
            
        Returns:
            Confirmation that the protocol was remembered
            
        Example Usage:
            - Another agent sends you ID "abc-123" → remember_protocol("ProtocolType", "abc-123", "active", "participant")
        """
        memory.track_protocol(
            protocol_type=protocol_type,
            instance_id=instance_id,
            state=state,
            role=role,
            metadata={"description": description} if description else None
        )
        
        return {
            "success": True,
            "remembered": {
                "protocol_type": protocol_type,
                "instance_id": instance_id,
                "state": state,
                "role": role
            },
            "hint": f"You can now recall this {protocol_type} using get_protocol_id('{protocol_type}')"
        }
    
    return [
        FunctionTool(recall_my_protocols, require_confirmation=False),
        FunctionTool(get_protocol_id, require_confirmation=False),
        FunctionTool(get_workflow_context, require_confirmation=False),
        FunctionTool(remember_protocol, require_confirmation=False)
    ]


def auto_track_result(
    memory: NPLProtocolMemory,
    protocol_type: str,
    result: Dict[str, Any],
    role: str = "owner"
) -> Dict[str, Any]:
    """
    Automatically track a protocol instance from a tool result.
    
    Call this after create/action calls to automatically store
    the instance in memory.
    
    Args:
        memory: The agent's protocol memory
        protocol_type: Type of protocol
        result: The result dict from NPL client
        role: Agent's role
        
    Returns:
        The original result (pass-through)
    """
    if isinstance(result, dict):
        instance_id = result.get("@id") or result.get("id")
        state = result.get("@state") or result.get("state", "created")
        
        if instance_id:
            # Extract all non-internal fields as metadata (skip @-prefixed fields)
            metadata = {
                k: v for k, v in result.items()
                if not k.startswith("@") and k not in ("id", "state", "success")
                and not isinstance(v, (dict, list))  # Keep it simple - no nested structures
            }
            
            memory.track_protocol(
                protocol_type=protocol_type,
                instance_id=instance_id,
                state=state,
                role=role,
                metadata=metadata if metadata else None
            )
    
    return result

