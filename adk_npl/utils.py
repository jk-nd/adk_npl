"""
Utilities for ADK-NPL integration.

Provides error classes, caching utilities, and helper functions.
"""

import time
import hashlib
from typing import Dict, Any, Optional, TypeVar, Generic
from datetime import datetime, timedelta

T = TypeVar('T')


class NPLIntegrationError(Exception):
    """Base exception for NPL integration errors."""
    pass


class AuthenticationError(NPLIntegrationError):
    """Failed to authenticate with NPL Engine."""
    pass


class ToolDiscoveryError(NPLIntegrationError):
    """Failed to discover tools from OpenAPI spec."""
    pass


class PackageDiscoveryError(NPLIntegrationError):
    """Failed to discover NPL packages."""
    pass


class CachedItem(Generic[T]):
    """A cached item with timestamp."""
    
    def __init__(self, value: T, ttl_seconds: float = 300):
        self.value = value
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds
    
    def is_expired(self) -> bool:
        """Check if cache item has expired."""
        age = time.time() - self.created_at
        return age > self.ttl_seconds
    
    def age(self) -> float:
        """Get age of cache item in seconds."""
        return time.time() - self.created_at


class Cache:
    """Simple time-based cache."""
    
    def __init__(self, default_ttl: float = 300):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default TTL in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, CachedItem] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get item from cache if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._cache:
            return None
        
        item = self._cache[key]
        if item.is_expired():
            del self._cache[key]
            return None
        
        return item.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """
        Set item in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if None)
        """
        ttl = ttl or self.default_ttl
        self._cache[key] = CachedItem(value, ttl)
    
    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
    
    def invalidate(self, key: str):
        """Invalidate a specific cache key."""
        if key in self._cache:
            del self._cache[key]
    
    def is_valid(self, key: str) -> bool:
        """Check if a key exists and is valid."""
        return self.get(key) is not None


def hash_auth_token(token: Optional[str], length: int = 10) -> str:
    """
    Create a short hash of auth token for cache keys.
    
    Args:
        token: Auth token
        length: Length of hash to return
        
    Returns:
        Short hash string
    """
    if not token:
        return "no_auth"
    return hashlib.sha256(token.encode()).hexdigest()[:length]


def parse_openapi_path(path: str, package: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse OpenAPI path to extract protocol name and action.
    
    Examples:
        /npl/negotiation/TwoPartyAttestation/{id}/attestAsParty1
        → ("TwoPartyAttestation", "attestAsParty1")
        
        /npl/negotiation/PurchaseAgreement
        → ("PurchaseAgreement", None)  # Protocol creation
    
    Args:
        path: OpenAPI path
        package: Package name
        
    Returns:
        Tuple of (protocol_name, action_name) or (None, None) if not parseable
    """
    package_prefix = f"/npl/{package}/"
    
    if not path.startswith(package_prefix):
        return None, None
    
    # Remove package prefix
    after_prefix = path[len(package_prefix):]
    
    # Split path components
    parts = [p for p in after_prefix.split("/") if p and p != "-"]
    
    if not parts:
        return None, None
    
    protocol_name = parts[0]
    
    # Check if it's a protocol creation (no instance ID)
    if len(parts) == 1:
        return protocol_name, None
    
    # Check if it's an action (has instance ID and action)
    # Format: /npl/{package}/{Protocol}/{instanceId}/{action}
    if len(parts) >= 3:
        # Last part is the action
        action_name = parts[-1]
        return protocol_name, action_name
    
    return protocol_name, None


def is_protocol_creation_path(path: str, package: str) -> bool:
    """
    Check if path is for protocol creation (not action execution).
    
    Args:
        path: OpenAPI path
        package: Package name
        
    Returns:
        True if path is for protocol creation
    """
    protocol, action = parse_openapi_path(path, package)
    return protocol is not None and action is None


def is_action_execution_path(path: str, package: str) -> bool:
    """
    Check if path is for action execution (not protocol creation).
    
    Args:
        path: OpenAPI path
        package: Package name
        
    Returns:
        True if path is for action execution
    """
    protocol, action = parse_openapi_path(path, package)
    return protocol is not None and action is not None

