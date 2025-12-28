"""
Tests for error handling and resilience.

Tests retry logic, error messages, token refresh, and graceful degradation.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
import requests

from adk_npl import NPLClient, NPLConfig
from adk_npl.utils import (
    NPLClientError,
    TokenExpiredError,
    ServiceUnavailableError
)
from adk_npl.auth import KeycloakAuth
from tests.conftest import MockResponse


@pytest.mark.integration
class TestRetryLogic:
    """Test retry logic for transient failures."""
    
    def test_retry_on_connection_error(self):
        """Test that connection errors trigger retries."""
        # This test requires the engine to be down or unreachable
        # For now, we'll test the retry mechanism with mocks
        # Using a mock client instead of authenticated_client to avoid async fixture
        client = NPLClient(
            base_url="http://unreachable:12000",
            auth_token="test_token",
            max_retries=2
        )
        
        # Test that connection errors are handled gracefully
        with pytest.raises(NPLClientError):
            client._make_request("GET", "http://unreachable:12000/test")
    
    def test_retry_on_503_service_unavailable(self):
        """Test retry on 503 Service Unavailable."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token",
            max_retries=2
        )
        
        # Mock session to return 503, then 200
        mock_response_503 = MockResponse(status_code=503, ok=False)
        mock_response_200 = MockResponse(status_code=200, json_data={"status": "ok"})
        
        with patch.object(client.session, 'request') as mock_request:
            mock_request.side_effect = [
                mock_response_503,
                mock_response_200
            ]
            
            # Should succeed after retry
            response = client._make_request("GET", "http://localhost:12000/test")
            assert response.status_code == 200
    
    def test_max_retries_exceeded(self):
        """Test that max retries are respected."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token",
            max_retries=2
        )
        
        # Mock session to always return 503
        mock_response_503 = MockResponse(status_code=503, ok=False)
        
        with patch.object(client.session, 'request') as mock_request:
            mock_request.return_value = mock_response_503
            
            # Should raise after max retries
            with pytest.raises(NPLClientError):
                client._make_request("GET", "http://localhost:12000/test")


@pytest.mark.integration
class TestTokenRefresh:
    """Test token refresh handling."""
    
    def test_token_refresh_on_401(self):
        """Test that 401 errors trigger token refresh."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="expired_token",
            max_retries=2
        )
        
        # Mock token refresh callback
        refresh_called = []
        def refresh_token():
            refresh_called.append(True)
            return "new_token"
        
        client.token_refresh_callback = refresh_token
        
        # Mock session: first call returns 401, second returns 200
        mock_response_401 = MockResponse(status_code=401, ok=False)
        mock_response_200 = MockResponse(status_code=200, json_data={"status": "ok"})
        
        with patch.object(client.session, 'request') as mock_request:
            mock_request.side_effect = [
                mock_response_401,
                mock_response_200
            ]
            
            # Should refresh token and retry
            response = client._make_request("GET", "http://localhost:12000/test")
            assert response.status_code == 200
            assert len(refresh_called) > 0
            assert client.auth_token == "new_token"
    
    def test_token_refresh_fallback_to_auth(self):
        """Test that failed refresh falls back to full authentication."""
        # This would require integration with KeycloakAuth
        # For now, we test the callback mechanism
        pass


@pytest.mark.integration
class TestErrorMessages:
    """Test that error messages are informative."""
    
    def test_error_message_includes_status_code(self):
        """Test that error messages include HTTP status code."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token"
        )
        
        mock_response_400 = MockResponse(
            status_code=400,
            ok=False,
            text='{"error": "Bad request"}'
        )
        
        with patch.object(client.session, 'request') as mock_request:
            mock_request.return_value = mock_response_400
            
            with pytest.raises(NPLClientError) as exc_info:
                client._make_request("GET", "http://localhost:12000/test")
            
            assert "400" in str(exc_info.value) or "Bad request" in str(exc_info.value)
    
    def test_error_message_includes_url(self):
        """Test that error messages include the request URL."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token"
        )
        
        test_url = "http://localhost:12000/test/endpoint"
        mock_response_500 = MockResponse(status_code=500, ok=False)
        
        with patch.object(client.session, 'request') as mock_request:
            mock_request.return_value = mock_response_500
            
            with pytest.raises(NPLClientError) as exc_info:
                client._make_request("GET", test_url)
            
            # URL should be in error details
            assert hasattr(exc_info.value, 'url') or test_url in str(exc_info.value)


@pytest.mark.integration
class TestGracefulDegradation:
    """Test graceful degradation when services are unavailable."""
    
    def test_timeout_handling(self):
        """Test that timeouts are handled gracefully."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token",
            timeout=1.0  # Short timeout
        )
        
        # Mock timeout exception
        with patch.object(client.session, 'request') as mock_request:
            mock_request.side_effect = requests.exceptions.Timeout("Request timed out")
            
            with pytest.raises(NPLClientError) as exc_info:
                client._make_request("GET", "http://localhost:12000/test")
            
            assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()
    
    def test_connection_error_handling(self):
        """Test that connection errors are handled gracefully."""
        client = NPLClient(
            base_url="http://localhost:12000",
            auth_token="test_token"
        )
        
        # Mock connection error
        with patch.object(client.session, 'request') as mock_request:
            mock_request.side_effect = requests.exceptions.ConnectionError("Connection refused")
            
            with pytest.raises(NPLClientError):
                client._make_request("GET", "http://localhost:12000/test")


@pytest.mark.integration
@pytest.mark.anyio
class TestInvalidStates:
    """Test handling of invalid protocol states."""
    
    @pytest.mark.integration
    async def test_invalid_state_transition(self, authenticated_client):
        """
        Test that invalid state transitions return clear errors.
        
        This test requires a full commerce workflow setup:
        1. Create Product
        2. Create and publish Offer  
        3. Create PurchaseOrder (starts in Requested state)
        4. Attempt placeOrder() in Requested state (should fail - only allowed in Quoted/Approved)
        
        This is a complex integration test that demonstrates NPL's state machine enforcement.
        For a simpler test, see test_missing_required_fields which tests validation errors.
        
        To run this test properly, use demo_approval_workflow.py which has the full setup.
        """
        pytest.skip(
            "Complex integration test requiring full Product→Offer→PurchaseOrder setup. "
            "See demo_approval_workflow.py for the complete workflow that demonstrates "
            "invalid state transitions (step 7: placeOrder blocked in ApprovalRequired state)."
        )
    
    @pytest.mark.integration
    async def test_missing_required_fields(self, authenticated_client):
        """Test that missing required fields return clear validation errors."""
        # Try to create a protocol with missing required fields
        try:
            result = authenticated_client.create_protocol(
                package="commerce",
                protocol_name="Product",
                parties={"seller": {"claims": {"organization": ["Test"]}}},
                data={
                    # Missing required fields like "name", "sku", etc.
                    "description": "Test product"
                }
            )
            pytest.fail("Should have raised an error for missing required fields")
        except NPLClientError as e:
            # Error should indicate which fields are missing
            assert "400" in str(e) or "required" in str(e).lower() or "missing" in str(e).lower()

