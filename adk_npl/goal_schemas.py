"""
Goal Tracking Schemas for ADK Agents.

These Pydantic models define the output_schema for agents, enabling:
1. Structured state tracking across turns
2. Workflow stage awareness
3. Protocol state synchronization
4. Progress monitoring

When an agent uses output_schema, it's forced to report its understanding
of the current state, which can be validated against NPL reality.

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

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class WorkflowStage(str, Enum):
    """High-level stages of agent workflow."""
    ORIENTING = "orienting"  # Agent is discovering what's available
    DISCOVERING = "discovering"  # Agent is exploring protocols/tools
    NEGOTIATING = "negotiating"  # Agent is in multi-party negotiation
    EXECUTING = "executing"  # Agent is taking action on protocols
    WAITING = "waiting"  # Agent is waiting for other party
    COMPLETING = "completing"  # Agent is finishing up
    DONE = "done"  # Agent has completed its goal


class ProtocolStateInfo(BaseModel):
    """Tracking info for a single protocol instance."""
    protocol_id: str = Field(description="UUID of the protocol instance")
    protocol_type: str = Field(description="Type of protocol (e.g., 'Offer', 'PurchaseOrder')")
    last_known_state: Optional[str] = Field(
        default=None, 
        description="Last known state from NPL query (may be stale!)"
    )
    my_role: str = Field(description="Agent's role in this protocol (e.g., 'buyer', 'seller')")
    needs_action: bool = Field(
        default=False,
        description="True if agent should take action on this protocol"
    )
    waiting_for: Optional[str] = Field(
        default=None,
        description="If waiting, what are we waiting for? (e.g., 'seller to ship')"
    )


class AgentWorkflowState(BaseModel):
    """
    Agent's understanding of its current workflow state.
    
    This is used as output_schema to force agents to explicitly track
    what they're doing and what they think the state is.
    
    IMPORTANT: This is the agent's BELIEF about state, not ground truth.
    The NPL engine is the single source of truth. Agents should query
    NPL before acting to sync their belief with reality.
    """
    
    # High-level workflow stage
    workflow_stage: WorkflowStage = Field(
        default=WorkflowStage.ORIENTING,
        description="Current high-level stage of the workflow"
    )
    
    # What the agent is currently focused on
    current_focus: Optional[str] = Field(
        default=None,
        description="What is the agent currently working on? (e.g., 'Creating offer for widgets')"
    )
    
    # Protocols the agent is tracking
    active_protocols: List[ProtocolStateInfo] = Field(
        default_factory=list,
        description="Protocols the agent is actively working with"
    )
    
    # Last action taken
    last_action: Optional[str] = Field(
        default=None,
        description="What action did the agent just take?"
    )
    
    # Next planned action
    next_planned_action: Optional[str] = Field(
        default=None,
        description="What does the agent plan to do next?"
    )
    
    # Blockers
    blocked_by: Optional[str] = Field(
        default=None,
        description="What is blocking progress? (e.g., 'Waiting for buyer approval')"
    )
    
    # Goal progress
    goal_progress: str = Field(
        default="Not started",
        description="Brief description of progress toward the goal"
    )
    
    # Message for other party (A2A)
    message_for_partner: Optional[str] = Field(
        default=None,
        description="Message to send to the other party via A2A (if any)"
    )


class BuyerGoalState(AgentWorkflowState):
    """
    Extended state tracking for buyer agents.
    
    Adds buyer-specific fields for tracking purchasing progress.
    """
    
    # Items to purchase
    shopping_list_completed: int = Field(
        default=0,
        description="Number of items from shopping list that have been purchased"
    )
    shopping_list_total: int = Field(
        default=0,
        description="Total number of items on shopping list"
    )
    
    # Budget tracking
    total_spent: float = Field(
        default=0.0,
        description="Total amount spent so far"
    )
    
    # Offers received
    pending_offers: List[str] = Field(
        default_factory=list,
        description="UUIDs of offers waiting for review"
    )


class SupplierGoalState(AgentWorkflowState):
    """
    Extended state tracking for supplier agents.
    
    Adds supplier-specific fields for tracking sales progress.
    """
    
    # Orders being processed
    orders_in_progress: int = Field(
        default=0,
        description="Number of orders currently being processed"
    )
    
    # Products listed
    products_published: int = Field(
        default=0,
        description="Number of products published in catalog"
    )
    
    # Pending requests
    pending_requests: List[str] = Field(
        default_factory=list,
        description="UUIDs of requests awaiting response"
    )


# Convenience function to get the right schema for an objective
def get_goal_schema_for_objective(objective: str) -> type:
    """
    Get the appropriate goal schema based on agent objective.
    
    Args:
        objective: Agent's declared objective (e.g., "buying", "selling")
        
    Returns:
        Pydantic model class to use as output_schema
    """
    objective_lower = objective.lower()
    
    if any(kw in objective_lower for kw in ["buy", "purchas", "acquir", "procur"]):
        return BuyerGoalState
    elif any(kw in objective_lower for kw in ["sell", "supply", "provid", "offer"]):
        return SupplierGoalState
    else:
        return AgentWorkflowState
