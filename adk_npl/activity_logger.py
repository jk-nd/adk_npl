"""
Activity Logger for ADK-NPL Integration

Provides structured logging of all system activities including:
- Agent actions and decisions
- NPL Engine API calls
- Bridge operations
- State transitions
- Authentication events
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
import threading

logger = logging.getLogger(__name__)


class ActivityLogger:
    """
    Logs all system activities to structured JSON files.
    Thread-safe for concurrent access.
    """
    
    _instance: Optional['ActivityLogger'] = None
    _lock = threading.Lock()
    
    def __new__(cls, log_dir: str = "logs"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self, log_dir: str = "logs"):
        if self._initialized:
            return
            
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create session-specific log file
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"activity_{timestamp}.json"
        self.latest_link = self.log_dir / "activity_latest.json"
        
        # In-memory buffer for real-time access (last 1000 events)
        self.buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()
        self.max_buffer_size = 1000
        
        self._initialized = True
        
        # Create symlink to latest log
        self._update_latest_link()
        
        logger.info(f"ActivityLogger initialized: {self.log_file}")
    
    def _update_latest_link(self):
        """Update symlink to point to latest log file."""
        try:
            if self.latest_link.exists() or self.latest_link.is_symlink():
                self.latest_link.unlink()
            self.latest_link.symlink_to(self.log_file.name)
        except Exception as e:
            logger.warning(f"Could not create symlink: {e}")
    
    def log_agent_reasoning(
        self,
        actor: str,
        reasoning: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Log agent reasoning/decision-making process.
        
        Args:
            actor: Agent name (buyer_agent, supplier_agent, etc.)
            reasoning: The agent's reasoning or message
            context: Additional context (prompt, tools_available, etc.)
        """
        self.log_event(
            event_type="agent_reasoning",
            actor=actor,
            action="reasoning",
            details={
                "reasoning": reasoning,
                "context": context or {}
            },
            level="info"
        )
    
    def log_agent_message(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        message_type: str = "text"
    ):
        """
        Log agent-to-agent communication.
        
        Args:
            from_agent: Sender agent name
            to_agent: Recipient agent name
            message: Message content
            message_type: Type of message (text, proposal, counter_offer, etc.)
        """
        self.log_event(
            event_type="agent_message",
            actor=from_agent,
            action=f"message_to_{to_agent}",
            details={
                "to": to_agent,
                "message": message,
                "message_type": message_type
            },
            level="info"
        )
    
    def log_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        level: str = "info"
    ):
        """
        Log a system activity event.
        
        Args:
            event_type: Type of event (agent_action, npl_api, bridge_op, auth, state_transition, agent_reasoning, agent_message)
            actor: Who performed the action (buyer_agent, supplier_agent, approver, npl_engine, bridge)
            action: What action was performed
            details: Additional event details
            level: Log level (info, warning, error)
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "actor": actor,
            "action": action,
            "level": level,
            "details": details or {}
        }
        
        # Write to file
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.error(f"Failed to write activity log: {e}")
        
        # Add to buffer
        with self.buffer_lock:
            self.buffer.append(event)
            if len(self.buffer) > self.max_buffer_size:
                self.buffer.pop(0)
    
    def log_agent_action(
        self,
        agent: str,
        action: str,
        protocol: Optional[str] = None,
        protocol_id: Optional[str] = None,
        outcome: Optional[str] = None,
        **kwargs
    ):
        """Log an agent action."""
        details = {
            "protocol": protocol,
            "protocol_id": protocol_id,
            "outcome": outcome,
            **kwargs
        }
        self.log_event("agent_action", agent, action, details)
    
    def log_npl_api_call(
        self,
        method: str,
        endpoint: str,
        status_code: Optional[int] = None,
        response_time: Optional[float] = None,
        error: Optional[str] = None,
        **kwargs
    ):
        """Log an NPL Engine API call."""
        details = {
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "response_time_ms": round(response_time * 1000, 2) if response_time else None,
            "error": error,
            **kwargs
        }
        level = "error" if error else "info"
        self.log_event("npl_api", "npl_engine", f"{method} {endpoint}", details, level)
    
    def log_state_transition(
        self,
        protocol: str,
        protocol_id: str,
        from_state: str,
        to_state: str,
        triggered_by: str,
        **kwargs
    ):
        """Log a protocol state transition."""
        details = {
            "protocol": protocol,
            "protocol_id": protocol_id,
            "from_state": from_state,
            "to_state": to_state,
            "triggered_by": triggered_by,
            **kwargs
        }
        self.log_event("state_transition", "npl_engine", f"{from_state} → {to_state}", details)
    
    def log_authentication(
        self,
        realm: str,
        username: str,
        success: bool,
        error: Optional[str] = None
    ):
        """Log an authentication event."""
        details = {
            "realm": realm,
            "username": username,
            "success": success,
            "error": error
        }
        level = "info" if success else "error"
        self.log_event("authentication", "keycloak", "authenticate", details, level)
    
    def log_bridge_operation(
        self,
        operation: str,
        package: Optional[str] = None,
        tool_count: Optional[int] = None,
        success: bool = True,
        error: Optional[str] = None,
        **kwargs
    ):
        """Log a bridge operation."""
        details = {
            "operation": operation,
            "package": package,
            "tool_count": tool_count,
            "success": success,
            "error": error,
            **kwargs
        }
        level = "info" if success else "error"
        self.log_event("bridge_operation", "adk_npl_bridge", operation, details, level)
    
    def log_llm_call(
        self,
        model: str,
        agent: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None,
        **kwargs
    ):
        """Log an LLM API call."""
        details = {
            "model": model,
            "agent": agent,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
            "latency_ms": round(latency_ms, 2) if latency_ms else None,
            "success": success,
            "error": error,
            **kwargs
        }
        level = "error" if error else "info"
        self.log_event("llm_call", agent, f"call_{model}", details, level)
    
    def log_a2a_transfer(
        self,
        from_agent: str,
        to_agent: str,
        task: str,
        success: bool = True,
        latency_ms: Optional[float] = None,
        **kwargs
    ):
        """Log an A2A transfer between agents."""
        details = {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task": task,
            "success": success,
            "latency_ms": round(latency_ms, 2) if latency_ms else None,
            **kwargs
        }
        level = "info" if success else "error"
        self.log_event("a2a_transfer", from_agent, f"transfer_to_{to_agent}", details, level)
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent events from buffer."""
        with self.buffer_lock:
            return self.buffer[-limit:] if limit else list(self.buffer)
    
    def get_events_by_type(self, event_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent events of a specific type."""
        with self.buffer_lock:
            filtered = [e for e in self.buffer if e["event_type"] == event_type]
            return filtered[-limit:] if limit else filtered
    
    def get_events_by_actor(self, actor: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent events by a specific actor."""
        with self.buffer_lock:
            filtered = [e for e in self.buffer if e["actor"] == actor]
            return filtered[-limit:] if limit else filtered
    
    def clear_buffer(self):
        """Clear the in-memory buffer."""
        with self.buffer_lock:
            self.buffer.clear()
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the current session."""
        with self.buffer_lock:
            total_events = len(self.buffer)
            
            # Count by type
            by_type = {}
            by_actor = {}
            by_level = {"info": 0, "warning": 0, "error": 0}
            
            for event in self.buffer:
                event_type = event["event_type"]
                actor = event["actor"]
                level = event["level"]
                
                by_type[event_type] = by_type.get(event_type, 0) + 1
                by_actor[actor] = by_actor.get(actor, 0) + 1
                by_level[level] = by_level.get(level, 0) + 1
            
            return {
                "total_events": total_events,
                "by_type": by_type,
                "by_actor": by_actor,
                "by_level": by_level,
                "log_file": str(self.log_file),
                "session_start": self.buffer[0]["timestamp"] if self.buffer else None
            }


# Global singleton instance
_activity_logger: Optional[ActivityLogger] = None
_activity_logger_lock = threading.Lock()


def get_activity_logger() -> ActivityLogger:
    """Get the global ActivityLogger instance."""
    global _activity_logger
    with _activity_logger_lock:
        if _activity_logger is None:
            _activity_logger = ActivityLogger()
    return _activity_logger


def log_activity(
    event_type: str,
    actor: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    level: str = "info"
):
    """Convenience function to log an activity event."""
    get_activity_logger().log_event(event_type, actor, action, details, level)

