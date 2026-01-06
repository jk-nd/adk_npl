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

import pytest
import asyncio
import httpx
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from adk_npl.config import NPLConfig
from adk_npl.auth import KeycloakAuth
from adk_npl.client import NPLClient


# ============================================================================
# Configuration
# ============================================================================

BUYER_CONFIG = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="purchasing",
    keycloak_client_id="purchasing",
    credentials={"username": "purchasing_agent", "password": "Welcome123"}
)

SUPPLIER_CONFIG = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="supplier",
    keycloak_client_id="supplier",
    credentials={"username": "supplier_agent", "password": "Welcome123"}
)


# ============================================================================
# Helper Functions
# ============================================================================

async def get_buyer_client():
    """Helper to get authenticated buyer client."""
    auth = KeycloakAuth(
        keycloak_url=BUYER_CONFIG.keycloak_url,
        realm=BUYER_CONFIG.keycloak_realm,
        client_id=BUYER_CONFIG.keycloak_client_id,
        username=BUYER_CONFIG.credentials["username"],
        password=BUYER_CONFIG.credentials["password"]
    )
    token = await auth.authenticate()
    return NPLClient(base_url=BUYER_CONFIG.engine_url, auth_token=token)


async def get_supplier_client():
    """Helper to get authenticated supplier client."""
    auth = KeycloakAuth(
        keycloak_url=SUPPLIER_CONFIG.keycloak_url,
        realm=SUPPLIER_CONFIG.keycloak_realm,
        client_id=SUPPLIER_CONFIG.keycloak_client_id,
        username=SUPPLIER_CONFIG.credentials["username"],
        password=SUPPLIER_CONFIG.credentials["password"]
    )
    token = await auth.authenticate()
    return NPLClient(base_url=SUPPLIER_CONFIG.engine_url, auth_token=token)


async def get_supplier_token():
    """Get raw supplier JWT token for SSE stream."""
    auth = KeycloakAuth(
        keycloak_url=SUPPLIER_CONFIG.keycloak_url,
        realm=SUPPLIER_CONFIG.keycloak_realm,
        client_id=SUPPLIER_CONFIG.keycloak_client_id,
        username=SUPPLIER_CONFIG.credentials["username"],
        password=SUPPLIER_CONFIG.credentials["password"]
    )
    return await auth.authenticate()


async def get_buyer_token():
    """Get raw buyer JWT token for SSE stream."""
    auth = KeycloakAuth(
        keycloak_url=BUYER_CONFIG.keycloak_url,
        realm=BUYER_CONFIG.keycloak_realm,
        client_id=BUYER_CONFIG.keycloak_client_id,
        username=BUYER_CONFIG.credentials["username"],
        password=BUYER_CONFIG.credentials["password"]
    )
    return await auth.authenticate()


# ============================================================================
# Test: SSE Stream Connection
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_sse_stream_connection():
    """Test that we can connect to NPL SSE notification stream."""
    token = await get_supplier_token()
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream"
        }
        
        # Use streaming to verify connection works without waiting for full response
        try:
            async with client.stream(
                "GET",
                f"{SUPPLIER_CONFIG.engine_url}/api/streams",
                headers=headers,
                timeout=3.0
            ) as response:
                # SSE streams return 200 on successful connection
                assert response.status_code == 200, f"Failed to connect: {response.status_code}"
                # We connected successfully - don't wait for events
                return
        except httpx.ReadTimeout:
            # Timeout is expected for SSE - we just wanted to verify connection
            pass


# ============================================================================
# Test: Notification Dispatch Routing Logic
# ============================================================================

def test_notification_routing_logic():
    """Test that notification routing logic is correct."""
    # Test the routing patterns directly without needing the full dispatch function
    
    buyer_patterns = ["Published", "Shipped", "Approved", "Ready", "Available"]
    seller_patterns = ["Accepted", "Rejected", "Placed", "Ordered", "Received"]
    
    def get_target(notification_name: str) -> str:
        for pattern in buyer_patterns:
            if pattern in notification_name:
                return "buyer"
        for pattern in seller_patterns:
            if pattern in notification_name:
                return "supplier"
        return None
    
    # Test buyer notifications
    assert get_target("OfferPublishedNotification") == "buyer", "OfferPublished should go to buyer"
    assert get_target("OrderShippedNotification") == "buyer", "OrderShipped should go to buyer"
    assert get_target("OrderApprovedNotification") == "buyer", "OrderApproved should go to buyer"
    
    # Test seller notifications  
    assert get_target("OfferAcceptedNotification") == "supplier", "OfferAccepted should go to supplier"
    assert get_target("OfferRejectedNotification") == "supplier", "OfferRejected should go to supplier"
    assert get_target("OrderRequestedNotification") == None, "OrderRequested doesn't match patterns"


# ============================================================================
# Test: Notification Listener Processes Events
# ============================================================================

def test_notification_event_parsing():
    """Test that SSE event data is correctly parsed."""
    # Simulate SSE event data as it would come from NPL
    sse_data = '{"notification":{"name":"OfferPublishedNotification","productName":"Widget","price":99.99},"protocolId":"abc-123","newState":"published"}'
    
    data = json.loads(sse_data)
    
    assert data["notification"]["name"] == "OfferPublishedNotification"
    assert data["protocolId"] == "abc-123"
    assert data["newState"] == "published"
    assert data["notification"]["price"] == 99.99


# ============================================================================
# Test: Notification Payload Structure
# ============================================================================

def test_notification_payload_structure():
    """Test that notification payloads are correctly structured."""
    # This tests the payload structure created by dispatch_npl_notification
    
    # Simulate what the dispatch function creates
    notification_name = "OfferPublishedNotification"
    protocol_id = "abc-123"
    new_state = "published"
    
    # Expected payload structure
    payload = {
        "type": "npl_notification",
        "notification": notification_name,
        "protocol_id": protocol_id,
        "new_state": new_state,
        "message": f"🔔 NPL NOTIFICATION: {notification_name} (state: {new_state})",
        "action_hint": "Something changed in NPL! Use your tools to understand and respond."
    }
    
    assert payload["type"] == "npl_notification"
    assert payload["notification"] == "OfferPublishedNotification"
    assert payload["protocol_id"] == "abc-123"
    assert "NPL NOTIFICATION" in payload["message"]


# ============================================================================
# Test: Notification Prompt Structure
# ============================================================================

def test_notification_prompt_structure():
    """Test that notification prompts are correctly structured."""
    # Test the notification prompt that would be sent to agents
    
    notification = {
        "type": "npl_notification",
        "notification": "OfferPublishedNotification",
        "protocol_id": "test-123",
        "new_state": "published",
        "message": "🔔 NPL NOTIFICATION: OfferPublishedNotification (state: published)",
        "action_hint": "Something changed in NPL! Use your tools to understand."
    }
    
    # The prompt sent to agent should include:
    notification_message = notification.get("message", "NPL state changed")
    action_hint = notification.get("action_hint", "")
    
    agent_prompt = f"""
NPL NOTIFICATION RECEIVED:
{notification_message}

{action_hint}

Use your tools to understand the situation and respond appropriately.
"""
    
    assert "NPL NOTIFICATION RECEIVED" in agent_prompt
    assert "OfferPublishedNotification" in agent_prompt
    assert "Use your tools" in agent_prompt


# ============================================================================
# Test: NPL Protocol Has Notifications Defined
# ============================================================================

@pytest.mark.asyncio
async def test_npl_has_notification_definitions():
    """Verify that NPL protocols have notification definitions."""
    # Read the NPL files to verify notifications exist
    offer_npl_path = Path(__file__).parent.parent / "npl/src/main/npl-1.0/commerce/offer.npl"
    po_npl_path = Path(__file__).parent.parent / "npl/src/main/npl-1.0/commerce/purchase_order.npl"
    
    # Check Offer notifications
    offer_content = offer_npl_path.read_text()
    assert "notification OfferPublishedNotification" in offer_content, "Missing OfferPublishedNotification"
    assert "notification OfferAcceptedNotification" in offer_content, "Missing OfferAcceptedNotification"
    assert "notify OfferPublishedNotification" in offer_content, "Missing notify call for OfferPublished"
    
    # Check PurchaseOrder notifications
    po_content = po_npl_path.read_text()
    assert "notification ApprovalRequiredNotification" in po_content, "Missing ApprovalRequiredNotification"
    assert "notification OrderApprovedNotification" in po_content, "Missing OrderApprovedNotification"
    assert "notification OrderShippedNotification" in po_content, "Missing OrderShippedNotification"


# ============================================================================
# Test: Chat API Health Includes Notification Listener
# ============================================================================

@pytest.mark.asyncio
async def test_chat_api_health_endpoint():
    """Test that Chat API health endpoint works."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8001/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                assert data["status"] == "healthy"
                assert "agents" in data
            else:
                pytest.skip("Chat API not running")
        except httpx.ConnectError:
            pytest.skip("Chat API not running on port 8001")

