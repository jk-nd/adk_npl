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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from adk_npl.config import NPLConfig
from adk_npl.agent_factory import EnterpriseAgentFactory as AgentFactory


# ============================================================================
# Test Configuration
# ============================================================================

MODEL = "gemini-2.0-flash"
MAX_TOOL_CALLS = 5


def get_buyer_config() -> NPLConfig:
    """Get buyer agent configuration."""
    return NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="purchasing",
        keycloak_client_id="purchasing",
        credentials={"username": "purchasing_agent", "password": "Welcome123"}
    )


def get_supplier_config() -> NPLConfig:
    """Get supplier agent configuration."""
    return NPLConfig(
        engine_url="http://localhost:12000",
        keycloak_url="http://localhost:11000",
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={"username": "supplier_agent", "password": "Welcome123"}
    )


# ============================================================================
# Agent Creation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_buyer_agent_creation():
    """Test: Buyer agent can be created successfully."""
    config = get_buyer_config()
    session_service = InMemorySessionService()
    factory = AgentFactory(npl_config=config, session_service=session_service)
    
    result = await factory.create_agent(
        agent_id="buyer_test",
        objective="Purchase items for Acme Corp",
        custom_instructions="You are a buyer.",
        model=MODEL,
        max_tool_calls_per_turn=MAX_TOOL_CALLS
    )
    
    assert result is not None
    assert "agent" in result
    assert result["agent"] is not None
    assert result["agent"].name == "buyer_test"


@pytest.mark.asyncio
async def test_supplier_agent_creation():
    """Test: Supplier agent can be created successfully."""
    config = get_supplier_config()
    session_service = InMemorySessionService()
    factory = AgentFactory(npl_config=config, session_service=session_service)
    
    result = await factory.create_agent(
        agent_id="supplier_test",
        objective="Sell products from SupplierCo",
        custom_instructions="You are a supplier.",
        model=MODEL,
        max_tool_calls_per_turn=MAX_TOOL_CALLS
    )
    
    assert result is not None
    assert "agent" in result
    assert result["agent"] is not None
    assert result["agent"].name == "supplier_test"


@pytest.mark.asyncio
async def test_buyer_agent_has_tools():
    """Test: Buyer agent has required tools."""
    config = get_buyer_config()
    session_service = InMemorySessionService()
    factory = AgentFactory(npl_config=config, session_service=session_service)
    
    result = await factory.create_agent(
        agent_id="buyer_test",
        objective="Purchase items",
        custom_instructions="You are a buyer.",
        model=MODEL,
        max_tool_calls_per_turn=MAX_TOOL_CALLS
    )
    
    agent = result["agent"]
    tools = agent.tools or []
    tool_names = [getattr(t, 'name', str(t)) for t in tools]
    
    # Should have NPL tools and shopping tools
    assert len(tools) > 5, f"Agent should have multiple tools. Got: {len(tools)}"
    
    # Check for expected tools
    has_shopping_tool = any("shopping" in n.lower() or "list" in n.lower() for n in tool_names)
    has_npl_tool = any("npl_" in n.lower() for n in tool_names)
    
    assert has_npl_tool, f"Should have NPL tools. Found: {tool_names[:10]}"


@pytest.mark.asyncio
async def test_supplier_agent_has_tools():
    """Test: Supplier agent has required tools."""
    config = get_supplier_config()
    session_service = InMemorySessionService()
    factory = AgentFactory(npl_config=config, session_service=session_service)
    
    result = await factory.create_agent(
        agent_id="supplier_test",
        objective="Sell products",
        custom_instructions="You are a supplier.",
        model=MODEL,
        max_tool_calls_per_turn=MAX_TOOL_CALLS
    )
    
    agent = result["agent"]
    tools = agent.tools or []
    tool_names = [getattr(t, 'name', str(t)) for t in tools]
    
    # Should have NPL tools and inventory tools
    assert len(tools) > 5, f"Agent should have multiple tools. Got: {len(tools)}"
    
    # Check for expected tools  
    has_inventory_tool = any("inventory" in n.lower() or "list" in n.lower() for n in tool_names)
    has_npl_tool = any("npl_" in n.lower() for n in tool_names)
    
    assert has_npl_tool, f"Should have NPL tools. Found: {tool_names[:10]}"


@pytest.mark.asyncio
async def test_agent_can_run():
    """Test: Agent can run and produce a response."""
    config = get_buyer_config()
    session_service = InMemorySessionService()
    factory = AgentFactory(npl_config=config, session_service=session_service)
    
    result = await factory.create_agent(
        agent_id="buyer_run_test",
        objective="Purchase items",
        custom_instructions="You are a helpful buyer.",
        model=MODEL,
        max_tool_calls_per_turn=MAX_TOOL_CALLS
    )
    
    agent = result["agent"]
    
    session = await session_service.create_session(
        app_name="buyer_run_test",
        user_id="test_user",
        session_id="test_session"
    )
    
    runner = Runner(
        agent=agent,
        app_name="buyer_run_test",
        session_service=session_service
    )
    
    # Simple hello message
    message_content = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text="Hello, who are you?")]
    )
    
    response_received = False
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=message_content
    ):
        if hasattr(event, 'is_final_response') and event.is_final_response():
            response_received = True
            break
    
    assert response_received, "Agent should produce a final response"


# ============================================================================
# Run tests directly
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
