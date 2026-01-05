"""
Goal tracking schemas for ADK agents using output_schema.

These Pydantic models force agents to evaluate their goal status on every turn,
making them more proactive and enabling automated stopping conditions.
"""

from pydantic import BaseModel, Field
from typing import List, Literal


class BuyerGoalStatus(BaseModel):
    """Structured output schema for buyer/purchasing agent."""
    
    goal_achieved: bool = Field(
        default=False,
        description="True if ALL items on shopping list have been purchased and orders are shipped/closed"
    )
    
    progress_percent: int = Field(
        default=0,
        description="Percentage of shopping list items successfully purchased (0-100)",
        ge=0,
        le=100
    )
    
    items_completed: List[str] = Field(
        default_factory=list,
        description="Names of shopping list items that are fully purchased/shipped"
    )
    
    items_pending: List[str] = Field(
        default_factory=list,
        description="Names of shopping list items still needing action"
    )
    
    next_action: str = Field(
        default="Analyzing shopping list...",
        description="What you will do next, or 'MISSION COMPLETE' if goal achieved"
    )
    
    blocking_issues: List[str] = Field(
        default_factory=list,
        description="Any issues preventing progress (e.g., 'Waiting for supplier', 'Needs approval')"
    )
    
    user_message: str = Field(
        default="Working on procurement...",
        description="Natural language summary for your human boss"
    )


class SupplierGoalStatus(BaseModel):
    """Structured output schema for supplier agent."""
    
    goal_achieved: bool = Field(
        default=False,
        description="True if ALL products are registered and ALL orders are fulfilled/shipped"
    )
    
    progress_percent: int = Field(
        default=0,
        description="Percentage of products registered and orders fulfilled (0-100)",
        ge=0,
        le=100
    )
    
    products_registered: int = Field(
        default=0,
        description="Number of products successfully registered in NPL",
        ge=0
    )
    
    orders_fulfilled: int = Field(
        default=0,
        description="Number of purchase orders successfully shipped",
        ge=0
    )
    
    next_action: str = Field(
        default="Registering products...",
        description="What you will do next, or 'MISSION COMPLETE' if goal achieved"
    )
    
    blocking_issues: List[str] = Field(
        default_factory=list,
        description="Any issues preventing progress (e.g., 'Waiting for buyer', 'No orders yet')"
    )
    
    user_message: str = Field(
        default="Setting up inventory...",
        description="Natural language summary for your human boss"
    )

