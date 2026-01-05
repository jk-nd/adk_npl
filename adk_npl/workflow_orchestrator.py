"""
Workflow Orchestrator - Generic Agent Guidance

This module provides GENERIC process guidance that works with ANY NPL domain.
Business-specific logic stays in NPL protocols - agents discover what to do
by querying NPL state and available actions via tools.

Key Principle: Agents are generic goal-pursuers. NPL tells them what's possible.
The orchestrator ONLY teaches the PROCESS, not the business actions.
"""

# Generic workflow guidance for buying agents
BUYER_WORKFLOW = """
═══════════════════════════════════════════════════════════════════
YOUR ROLE: Buyer for Acme Corp (Procurement Department)
YOUR GOAL: Purchase what your organization needs
═══════════════════════════════════════════════════════════════════

Every turn:
1. ORIENT: Call recall_my_protocols() to see what you're working on
2. DECIDE: If you have protocols, use npl_*_next_actions() to see options
3. ACT: Take one action (NPL tool or A2A message)
4. STOP: Report and wait

The NPL Bridge will tell you what actions are available.
Don't hardcode assumptions - query NPL for the truth.
"""

# Generic workflow guidance for selling agents  
SUPPLIER_WORKFLOW = """
═══════════════════════════════════════════════════════════════════
YOUR ROLE: Supplier for Supplier Inc (Sales Department)
YOUR GOAL: Sell your products profitably
═══════════════════════════════════════════════════════════════════

Every turn:
1. ORIENT: Call recall_my_protocols() to see what you're working on
2. DECIDE: If you have protocols, use npl_*_next_actions() to see options
3. ACT: Take one action (NPL tool or A2A message)
4. STOP: Report and wait

The NPL Bridge will tell you what actions are available.
Don't hardcode assumptions - query NPL for the truth.
"""


def get_workflow_instructions(role: str) -> str:
    """
    Get generic PROCESS instructions for an agent role.
    
    These instructions teach the ORIENT → DECIDE → ACT → STOP pattern.
    Business-specific actions come from NPL via npl_*_next_actions().
    
    Args:
        role: 'buyer' or 'supplier' (or variants)
        
    Returns:
        Generic process instructions for the role
    """
    role_lower = role.lower()
    if role_lower in ('buyer', 'purchasing', 'procurement'):
        return BUYER_WORKFLOW
    elif role_lower in ('supplier', 'seller', 'sales'):
        return SUPPLIER_WORKFLOW
    else:
        return ""


def get_orient_tools() -> list:
    """
    Return the list of tools agents should use in the ORIENT phase.
    These are generic tools that work with any NPL domain.
    """
    return [
        "recall_my_protocols",        # Known protocol instances
        "npl_*_next_actions",         # Valid actions for a protocol (from NPL!)
    ]
