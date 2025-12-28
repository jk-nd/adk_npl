"""
Pytest configuration and shared fixtures for ADK-NPL tests.
"""

import os
import pytest
from typing import Optional
from unittest.mock import Mock

from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth


@pytest.fixture
def npl_config():
    """Fixture providing NPL configuration from environment."""
    engine_url = os.getenv("NPL_ENGINE_URL", "http://localhost:12000")
    keycloak_url = os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000")
    password = os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")
    
    return NPLConfig(
        engine_url=engine_url,
        keycloak_url=keycloak_url,
        keycloak_realm="supplier",
        keycloak_client_id="supplier",
        credentials={"username": "supplier_agent", "password": password},
    )


@pytest.fixture
async def authenticated_client(npl_config):
    """Fixture providing authenticated NPL client."""
    auth = KeycloakAuth(
        keycloak_url=npl_config.keycloak_url,
        realm=npl_config.keycloak_realm,
        client_id=npl_config.keycloak_client_id,
        username=npl_config.credentials["username"],
        password=npl_config.credentials["password"],
    )
    token = await auth.authenticate()
    client = NPLClient(base_url=npl_config.engine_url, auth_token=token)
    return client


@pytest.fixture
def mock_requests_session():
    """Fixture providing a mock requests session."""
    from unittest.mock import patch
    with patch('adk_npl.client.requests.Session') as mock_session:
        yield mock_session


class MockResponse:
    """Mock HTTP response for testing."""
    
    def __init__(
        self,
        status_code: int = 200,
        json_data: Optional[dict] = None,
        text: str = "",
        ok: bool = True
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.ok = ok
        self.content = text.encode() if text else b""
    
    def json(self):
        return self._json_data
    
    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}: {self.text}",
                response=self
            )


@pytest.fixture
def mock_response():
    """Fixture providing MockResponse class."""
    return MockResponse

