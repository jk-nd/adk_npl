"""
ADK-NPL Integration Library

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
    get_metrics,
    configure_adk_telemetry,
    instrument_function
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
from .agent_logic import GLOBAL_AGENT_RULES
from .tool_filter import ToolFilter

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
    
    # Monitoring & Telemetry
    "StructuredLogger",
    "MetricsCollector",
    "HealthCheck",
    "get_metrics",
    "configure_adk_telemetry",
    "instrument_function",
    
    # Activity Logging
    "ActivityLogger",
    "get_activity_logger",
    "log_activity",
    
    # Protocol Memory
    "NPLProtocolMemory",
    "create_memory_tools",
    "GLOBAL_AGENT_RULES",
    
    # Tool Filtering
    "ToolFilter"
]

