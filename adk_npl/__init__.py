"""
ADK-NPL Integration Library

A library for integrating Google's Agent Development Kit (ADK) with
Noumena's NPL (Noumena Protocol Language) Engine.

This library enables ADK agents to dynamically discover and use NPL protocols
as tools, automatically generating FunctionTool instances from OpenAPI specs.
"""

from .config import NPLConfig
from .client import NPLClient
from .discovery import NPLPackageDiscovery
from .tools import NPLToolGenerator
from .auth import AuthStrategy, KeycloakAuth, TokenAuth, create_auth_strategy
from .agent_builder import NPLToolRegistry, create_agent_with_npl
from .utils import (
    NPLIntegrationError,
    AuthenticationError,
    ToolDiscoveryError,
    PackageDiscoveryError,
    NPLClientError,
    TokenExpiredError,
    ServiceUnavailableError
)
from .monitoring import (
    StructuredLogger,
    MetricsCollector,
    HealthCheck,
    get_metrics
)
from .activity_logger import (
    ActivityLogger,
    get_activity_logger,
    log_activity
)
from .protocol_memory import (
    NPLProtocolMemory,
    create_memory_tools
)

__version__ = "0.1.0"

__all__ = [
    # Configuration
    "NPLConfig",
    
    # Clients
    "NPLClient",
    
    # Discovery
    "NPLPackageDiscovery",
    
    # Tools
    "NPLToolGenerator",
    "NPLToolRegistry",
    
    # Authentication
    "AuthStrategy",
    "KeycloakAuth",
    "TokenAuth",
    "create_auth_strategy",
    
    # Convenience
    "create_agent_with_npl",
    
    # Errors
    "NPLIntegrationError",
    "AuthenticationError",
    "ToolDiscoveryError",
    "PackageDiscoveryError",
    "NPLClientError",
    "TokenExpiredError",
    "ServiceUnavailableError",
    
    # Monitoring
    "StructuredLogger",
    "MetricsCollector",
    "HealthCheck",
    "get_metrics",
    
    # Activity Logging
    "ActivityLogger",
    "get_activity_logger",
    "log_activity",
    
    # Protocol Memory
    "NPLProtocolMemory",
    "create_memory_tools",
]

