"""
Authentication strategies for NPL Engine.

Supports Keycloak OAuth2 and direct token authentication.
"""

import requests
import logging
from typing import Optional
from abc import ABC, abstractmethod

from .utils import AuthenticationError

logger = logging.getLogger(__name__)


class AuthStrategy(ABC):
    """Abstract base class for authentication strategies."""
    
    @abstractmethod
    async def authenticate(self) -> str:
        """
        Authenticate and return JWT token.
        
        Returns:
            JWT access token
        """
        pass


class KeycloakAuth(AuthStrategy):
    """
    Keycloak OAuth2 password flow authentication.
    """
    
    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        username: str,
        password: str,
        client_id: str = "npl-client"
    ):
        """
        Initialize Keycloak authentication.
        
        Args:
            keycloak_url: Keycloak base URL
            realm: Keycloak realm name
            username: Username
            password: Password
            client_id: Keycloak client ID
        """
        self.keycloak_url = keycloak_url.rstrip('/')
        self.realm = realm
        self.username = username
        self.password = password
        self.client_id = client_id
        self._refresh_token: Optional[str] = None
        self._access_token: Optional[str] = None
    
    async def authenticate(self) -> str:
        """
        Authenticate with Keycloak using password flow.
        
        Returns:
            JWT access token
            
        Raises:
            AuthenticationError: If authentication fails
        """
        logger.info(f"Authenticating user {self.username} with Keycloak")
        
        token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        
        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "scope": "openid profile email",
            "client_id": self.client_id
        }
        
        # Rewrite Host header so Keycloak uses keycloak:11000 as issuer
        # This allows Engine (in Docker) to fetch JWKS from keycloak:11000
        # We connect to localhost:11000 but tell Keycloak the Host is keycloak:11000
        request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if "localhost:11000" in self.keycloak_url:
            # Replace localhost with keycloak in Host header
            request_headers["Host"] = "keycloak:11000"
        
        try:
            response = requests.post(
                token_url,
                data=payload,
                headers=request_headers
            )
            response.raise_for_status()
            
            token_data = response.json()
            token = token_data["access_token"]
            self._access_token = token
            
            # Store refresh token if provided
            if "refresh_token" in token_data:
                self._refresh_token = token_data["refresh_token"]
            
            logger.info("Authentication successful")
            return token
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Keycloak authentication failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - Status: {e.response.status_code}"
            
            logger.error(error_msg)
            raise AuthenticationError(error_msg) from e
    
    async def refresh_token(self) -> str:
        """
        Refresh access token using refresh token.
        
        Returns:
            New JWT access token
            
        Raises:
            AuthenticationError: If refresh fails
        """
        if not self._refresh_token:
            # Fall back to full authentication
            logger.info("No refresh token available, performing full authentication")
            return await self.authenticate()
        
        logger.info("Refreshing access token")
        
        token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self.client_id
        }
        
        request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if "localhost:11000" in self.keycloak_url:
            request_headers["Host"] = "keycloak:11000"
        
        try:
            response = requests.post(
                token_url,
                data=payload,
                headers=request_headers
            )
            response.raise_for_status()
            
            token_data = response.json()
            token = token_data["access_token"]
            self._access_token = token
            
            # Update refresh token if provided
            if "refresh_token" in token_data:
                self._refresh_token = token_data["refresh_token"]
            
            logger.info("Token refresh successful")
            return token
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Token refresh failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - Status: {e.response.status_code}"
            
            logger.warning(f"{error_msg}. Falling back to full authentication")
            # Clear invalid refresh token
            self._refresh_token = None
            # Fall back to full authentication
            return await self.authenticate()


class TokenAuth(AuthStrategy):
    """
    Direct token authentication (for service accounts or pre-obtained tokens).
    """
    
    def __init__(self, token: str):
        """
        Initialize token authentication.
        
        Args:
            token: JWT access token
        """
        self.token = token
    
    async def authenticate(self) -> str:
        """
        Return the provided token.
        
        Returns:
            JWT access token
        """
        logger.info("Using provided token for authentication")
        return self.token


class NoAuth(AuthStrategy):
    """
    No authentication (for development/testing).
    """
    
    async def authenticate(self) -> str:
        """
        Return empty token (no authentication).
        
        Returns:
            Empty string
        """
        logger.warning("Using no authentication - not recommended for production")
        return ""


def create_auth_strategy(config) -> Optional[AuthStrategy]:
    """
    Create appropriate authentication strategy from config.
    
    Args:
        config: NPLConfig instance
        
    Returns:
        AuthStrategy instance or None if no auth
    """
    if config.auth_method == "keycloak":
        keycloak_url = config.get_keycloak_url()
        if not keycloak_url:
            raise AuthenticationError("keycloak_url is required for keycloak auth")
        
        return KeycloakAuth(
            keycloak_url=keycloak_url,
            realm=config.get_keycloak_realm(),
            username=config.credentials.get("username", ""),
            password=config.credentials.get("password", ""),
            client_id=config.keycloak_client_id
        )
    
    elif config.auth_method == "token":
        token = config.credentials.get("token")
        if not token:
            raise AuthenticationError("token is required for token auth")
        return TokenAuth(token)
    
    elif config.auth_method == "none":
        return NoAuth()
    
    else:
        raise AuthenticationError(f"Unknown auth method: {config.auth_method}")

