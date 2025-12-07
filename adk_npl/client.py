"""
NPL Engine client wrapper.

Provides a client for interacting with the NPL Engine API,
including protocol instantiation, action execution, and OpenAPI spec fetching.
"""

import requests
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class NPLClient:
    """
    Client for NPL Engine API.
    
    Wraps HTTP calls to NPL Engine with authentication support.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:12000",
        auth_token: Optional[str] = None
    ):
        """
        Initialize NPL Engine client.
        
        Args:
            base_url: Base URL of NPL Engine
            auth_token: JWT authentication token
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
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
        
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            body = ""
            if hasattr(e, "response") and e.response is not None:
                body = e.response.text
            logger.error(f"Failed to create protocol: {e}; body={body}")
            raise
    
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
        
        try:
            response = self.session.post(url, json=params, headers=headers)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to execute action: {e}")
            raise
    
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
        
        url = f"{self.base_url}/npl/{package}/{protocol_name}/{instance_id}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get instance: {e}")
            raise
    
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
            "page": page,
            "size": size
        }
        
        if filters:
            params.update(filters)
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query instances: {e}")
            raise
    
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
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get OpenAPI spec: {e}")
            raise

