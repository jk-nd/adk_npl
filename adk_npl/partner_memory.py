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
from typing import Dict, Any, Optional
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


class PartnerMemory:
    """
    In-memory storage for partner identities.
    
    Persists across agent turns within a session, eliminating the need
    for repeated identity exchanges via A2A.
    """
    
    def __init__(self):
        """Initialize empty partner memory."""
        self._partners: Dict[str, Dict[str, str]] = {}
        logger.debug("PartnerMemory initialized")
    
    def remember(self, role: str, organization: str, department: str) -> Dict[str, Any]:
        """
        Store a partner's identity.
        
        Args:
            role: Partner role (e.g., "buyer", "seller", "supplier")
            organization: Organization name
            department: Department name
            
        Returns:
            Confirmation message
        """
        self._partners[role.lower()] = {
            "organization": organization,
            "department": department
        }
        logger.info(f"✅ Remembered {role} identity: {organization}/{department}")
        return {
            "success": True,
            "message": f"Stored {role} identity: {organization}/{department}",
            "role": role,
            "identity": self._partners[role.lower()]
        }
    
    def recall(self, role: str) -> Dict[str, Any]:
        """
        Retrieve a stored partner identity.
        
        Args:
            role: Partner role to retrieve
            
        Returns:
            Stored identity or error
        """
        role_lower = role.lower()
        if role_lower not in self._partners:
            return {
                "success": False,
                "error": f"Unknown partner: {role}. Request their identity via A2A first.",
                "known_partners": list(self._partners.keys())
            }
        
        identity = self._partners[role_lower]
        logger.debug(f"Recalled {role} identity: {identity}")
        return {
            "success": True,
            "role": role,
            "organization": identity["organization"],
            "department": identity["department"]
        }
    
    def list_partners(self) -> Dict[str, Any]:
        """
        List all known partners.
        
        Returns:
            Dictionary of all stored partner identities
        """
        return {
            "success": True,
            "partners": self._partners,
            "count": len(self._partners)
        }


def create_partner_memory_tools(memory: Optional[PartnerMemory] = None) -> list:
    """
    Create ADK tools for partner identity management.
    
    Args:
        memory: Optional existing PartnerMemory instance (for sharing across agents)
        
    Returns:
        List of FunctionTool instances
    """
    if memory is None:
        memory = PartnerMemory()
    
    def remember_partner_identity(role: str, organization: str, department: str) -> Dict[str, Any]:
        """
        Store a partner's identity for future protocol creations.
        
        Call this when you learn another agent's organization and department via A2A.
        This stores their identity permanently so you don't need to ask again.
        
        Args:
            role: Partner role (e.g., "buyer", "seller", "supplier")
            organization: Their organization name
            department: Their department name
            
        Returns:
            Confirmation that identity was stored
            
        Example:
            remember_partner_identity("buyer", "Acme Corp", "Procurement")
        """
        return memory.remember(role, organization, department)
    
    def recall_partner_identity(role: str) -> Dict[str, Any]:
        """
        Retrieve a stored partner identity for protocol creation.
        
        Use this when creating multi-party NPL protocols (Offer, PurchaseOrder).
        If the partner is unknown, you'll get an error telling you to request
        their identity via A2A first.
        
        Args:
            role: Partner role to retrieve (e.g., "buyer", "seller")
            
        Returns:
            Partner's organization and department, or error if unknown
            
        Example:
            recall_partner_identity("buyer")
            # Returns: {"success": true, "organization": "Acme Corp", "department": "Procurement"}
        """
        return memory.recall(role)
    
    return [
        FunctionTool(func=remember_partner_identity),
        FunctionTool(func=recall_partner_identity)
    ]

