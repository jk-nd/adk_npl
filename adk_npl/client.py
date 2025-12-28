"""
NPL Engine client wrapper.

Provides a client for interacting with the NPL Engine API,
including protocol instantiation, action execution, and OpenAPI spec fetching.
"""

import requests
import logging
import time
from typing import Dict, List, Any, Optional, Callable

from .utils import NPLClientError, ServiceUnavailableError, TokenExpiredError
from .retry import retry_with_backoff, is_retryable_exception
from .monitoring import get_metrics

logger = logging.getLogger(__name__)


class NPLClient:
    """
    Client for NPL Engine API.
    
    Wraps HTTP calls to NPL Engine with authentication support.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:12000",
        auth_token: Optional[str] = None,
        max_retries: int = 3,
        timeout: float = 30.0,
        token_refresh_callback: Optional[Callable[[], str]] = None
    ):
        """
        Initialize NPL Engine client.
        
        Args:
            base_url: Base URL of NPL Engine
            auth_token: JWT authentication token
            max_retries: Maximum number of retries for failed requests (default: 3)
            timeout: Request timeout in seconds (default: 30.0)
            token_refresh_callback: Optional callback to refresh expired tokens
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.max_retries = max_retries
        self.timeout = timeout
        self.token_refresh_callback = token_refresh_callback
        self.session = requests.Session()
        
        if auth_token:
            self.session.headers.update({
                "Authorization": f"Bearer {auth_token}"
            })
    
    def set_auth_token(self, token: Optional[str]):
        """
        Set or update authentication token.
        
        Args:
            token: JWT authentication token
        """
        self.auth_token = token
        if token:
            self.session.headers.update({
                "Authorization": f"Bearer {token}"
            })
        else:
            self.session.headers.pop("Authorization", None)
    
    def _handle_response_error(self, response: requests.Response, url: str) -> None:
        """
        Handle HTTP response errors with detailed error information.
        
        Args:
            response: HTTP response object
            url: Request URL
            
        Raises:
            TokenExpiredError: If token expired (401)
            ServiceUnavailableError: If service unavailable (503)
            NPLClientError: For other HTTP errors
        """
        status_code = response.status_code
        try:
            error_body = response.json()
        except:
            error_body = response.text[:500]  # Limit error body length
        
        if status_code == 401:
            raise TokenExpiredError(
                f"Authentication failed: {error_body}",
                status_code=status_code,
                response_body=str(error_body),
                url=url
            )
        elif status_code == 503:
            raise ServiceUnavailableError(
                f"NPL Engine service unavailable: {error_body}",
                status_code=status_code,
                response_body=str(error_body),
                url=url
            )
        else:
            raise NPLClientError(
                f"NPL Engine API error ({status_code}): {error_body}",
                status_code=status_code,
                response_body=str(error_body),
                url=url
            )
    
    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with retry logic and error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments for requests
            
        Returns:
            HTTP response object
            
        Raises:
            NPLClientError: For API errors
            TokenExpiredError: If token expired
        """
        # Set timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        
        last_exception = None
        
        metrics = get_metrics()
        overall_start_time = time.time()
        
        for attempt in range(self.max_retries + 1):
            attempt_start_time = time.time()
            try:
                # Refresh token if callback provided and this is a retry after 401
                if attempt > 0 and self.token_refresh_callback:
                    logger.info("Refreshing authentication token...")
                    new_token = self.token_refresh_callback()
                    self.set_auth_token(new_token)
                
                response = self.session.request(method, url, **kwargs)
                attempt_latency = time.time() - attempt_start_time
                overall_latency = time.time() - overall_start_time
                
                # Record metrics (use attempt latency for individual call, overall for total)
                metrics.increment("npl.api.calls", method=method, status_code=response.status_code)
                metrics.record_latency("npl.api.latency", attempt_latency, method=method)
                if attempt > 0:
                    metrics.record_latency("npl.api.latency_with_retries", overall_latency, method=method)
                
                # Handle 401 - token expired
                if response.status_code == 401 and self.token_refresh_callback and attempt < self.max_retries:
                    logger.warning(f"Authentication failed (401), refreshing token and retrying...")
                    metrics.increment("npl.api.token_refreshes")
                    new_token = self.token_refresh_callback()
                    self.set_auth_token(new_token)
                    continue
                
                # Check if status code is retryable before handling error
                if not response.ok:
                    from .retry import is_retryable_status_code
                    if is_retryable_status_code(response.status_code) and attempt < self.max_retries:
                        # Retryable error - will retry in the except block
                        response.raise_for_status()  # This will raise an exception to trigger retry
                    
                    # Non-retryable or max retries exceeded - handle error
                    metrics.increment("npl.api.errors", status_code=response.status_code, method=method)
                    metrics.record_error(
                        "NPLClientError",
                        f"API error {response.status_code}",
                        url=url,
                        status_code=response.status_code,
                        method=method
                    )
                    self._handle_response_error(response, url)
                
                return response
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                attempt_latency = time.time() - attempt_start_time
                
                # Record error metrics
                metrics.increment("npl.api.errors", method=method, error_type=type(e).__name__)
                metrics.record_error(
                    type(e).__name__,
                    str(e),
                    url=url,
                    method=method,
                    attempt=attempt + 1,
                    latency_seconds=attempt_latency
                )
                
                # Check if retryable
                if attempt < self.max_retries and is_retryable_exception(e):
                    import random
                    delay = min(1.0 * (2.0 ** attempt), 60.0)
                    jitter = random.uniform(0, delay * 0.1)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay + jitter:.2f}s..."
                    )
                    metrics.increment("npl.api.retries", method=method)
                    time.sleep(delay + jitter)
                    continue
                
                # Non-retryable or max retries exceeded
                if attempt >= self.max_retries:
                    logger.error(f"Max retries exceeded for {method} {url}")
                    raise NPLClientError(
                        f"Request failed after {self.max_retries + 1} attempts: {e}",
                        url=url
                    ) from e
                
                raise
        
        # Should not reach here, but handle just in case
        if last_exception:
            raise NPLClientError(
                f"Request failed: {last_exception}",
                url=url
            ) from last_exception
    
    def create_protocol(
        self,
        package: str,
        protocol_name: str,
        parties: Dict[str, str],
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Instantiate a new protocol.
        
        Args:
            package: NPL package name
            protocol_name: Name of the protocol
            parties: Dict mapping party roles to party IDs
            data: Protocol initialization data
            
        Returns:
            instance: Created protocol instance
        """
        logger.info(f"Creating protocol {protocol_name} in package {package}")
        
        url = f"{self.base_url}/npl/{package}/{protocol_name}/"
        
        payload = {
            "@parties": parties,
            **data
        }
        
        response = self._make_request("POST", url, json=payload)
        return response.json()
    
    def execute_action(
        self,
        package: str,
        protocol_name: str,
        instance_id: str,
        action_name: str,
        party: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute an action on a protocol instance.
        
        Args:
            package: NPL package name
            protocol_name: Name of the protocol
            instance_id: Instance UUID
            action_name: Name of the action
            party: Party executing the action (optional)
            params: Action parameters (optional)
            
        Returns:
            result: Action execution result
        """
        logger.info(f"Executing action {action_name} on {instance_id}")
        
        url = f"{self.base_url}/npl/{package}/{protocol_name}/{instance_id}/{action_name}"
        
        headers = {}
        if party:
            headers["X-Party"] = party
        
        params = params or {}
        
        response = self._make_request("POST", url, json=params, headers=headers)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()
    
    def get_instance(
        self,
        package: str,
        protocol_name: str,
        instance_id: str
    ) -> Dict[str, Any]:
        """
        Get a protocol instance.
        
        Args:
            package: NPL package name
            protocol_name: Name of the protocol
            instance_id: Instance UUID
            
        Returns:
            instance: Protocol instance data
        """
        logger.info(f"Getting instance {instance_id}")
        
        url = f"{self.base_url}/npl/{package}/{protocol_name}/{instance_id}/"
        
        response = self._make_request("GET", url)
        return response.json()
    
    def query_instances(
        self,
        package: str,
        protocol_name: str,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 0,
        size: int = 20
    ) -> Dict[str, Any]:
        """
        Query protocol instances.
        
        Args:
            package: NPL package name
            protocol_name: Name of the protocol
            filters: Optional query filters
            page: Page number (0-indexed)
            size: Page size
            
        Returns:
            results: Paginated query results
        """
        logger.info(f"Querying instances of {protocol_name}")
        
        url = f"{self.base_url}/npl/{package}/{protocol_name}"
        
        params = {
            "page": page + 1,  # NPL Engine uses 1-indexed pages
            "pageSize": size   # NPL Engine uses pageSize, not size
        }
        
        if filters:
            params.update(filters)
        
        response = self._make_request("GET", url, params=params)
        return response.json()
    
    def get_openapi_spec(self, package: str) -> Dict[str, Any]:
        """
        Get OpenAPI specification for a package.
        
        Args:
            package: NPL package name
            
        Returns:
            spec: OpenAPI specification
        """
        logger.info(f"Getting OpenAPI spec for package '{package}'")
        
        url = f"{self.base_url}/npl/{package}/-/openapi.json"
        
        response = self._make_request("GET", url)
        return response.json()

