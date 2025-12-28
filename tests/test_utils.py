"""
Test utilities for ADK-NPL integration tests.

Provides helper functions for testing (fixtures are in conftest.py).
"""

from typing import Optional
from adk_npl import NPLClient


def create_mock_client(base_url: str = "http://localhost:12000") -> NPLClient:
    """Create a mock NPL client for testing."""
    return NPLClient(base_url=base_url, auth_token="mock_token")


def assert_protocol_response(response: dict, expected_fields: Optional[list] = None):
    """
    Assert that a protocol response has the expected structure.
    
    Args:
        response: Protocol response dict
        expected_fields: Optional list of expected field names
    """
    assert response, "Response should not be empty"
    
    # Check for common NPL fields
    assert "@id" in response or "id" in response or "instance" in response or "uuid" in response, \
        f"Response should contain an ID field: {response}"
    
    if expected_fields:
        for field in expected_fields:
            assert field in response, f"Response should contain field '{field}': {response}"

