# ADK-NPL Integration Library

A Python library for integrating Google's Agent Development Kit (ADK) with Noumena's NPL (Noumena Protocol Language) Engine.

This library enables ADK agents to **dynamically discover and use NPL protocols as tools**, automatically generating `FunctionTool` instances from OpenAPI specs with **explicit typed parameters**.

## Features

- 🔍 **Automatic Package Discovery** - Discovers NPL packages from Swagger UI
- 🛠️ **Schema-Aware Tool Generation** - Generates tools with explicit typed parameters from OpenAPI schemas
- 📝 **Self-Documenting Tools** - LLMs see exact parameter signatures (not `**kwargs`)
- 🔐 **Authentication Support** - Keycloak OAuth2 and token authentication with automatic refresh
- ⚡ **Caching** - Efficient caching of OpenAPI specs and generated tools
- 🎯 **Simple API** - One-line integration: `create_agent_with_npl()`
- 🔄 **Resilient Error Handling** - Automatic retries with exponential backoff, token refresh
- 📊 **Monitoring & Observability** - Built-in metrics, structured logging, health checks

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### Basic Usage

```python
from adk_npl import create_agent_with_npl, NPLConfig
from google.adk.agents import LlmAgent

# Create base agent
base_agent = LlmAgent(
    model="gemini-2.0-flash-exp",
    name="MyAgent",
    instruction="You are an agent that can interact with NPL protocols."
)

# Configure NPL (from environment variables)
config = NPLConfig.from_env()

# Create agent with NPL tools
agent = await create_agent_with_npl(base_agent, config)

# Agent now has all NPL tools available!
```

### Environment Variables

Set these environment variables (or use `.env` file):

```bash
# Required
NPL_ENGINE_URL=http://localhost:12000

# Optional (for Keycloak authentication)
NPL_KEYCLOAK_URL=http://localhost:11000
NPL_KEYCLOAK_REALM=poc
NPL_USERNAME=agent@example.com
NPL_PASSWORD=your_password

# Optional (for direct token)
NPL_TOKEN=your_jwt_token

# Optional (manual package list)
NPL_PACKAGES=negotiation,fund_management

# Optional (cache settings)
NPL_CACHE_TTL=300  # 5 minutes
```

## Configuration

### From Environment Variables

```python
from adk_npl import NPLConfig

config = NPLConfig.from_env()
```

### Manual Configuration

```python
from adk_npl import NPLConfig

config = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="poc",
    auth_method="keycloak",
    credentials={
        "username": "agent@example.com",
        "password": "password"
    }
)
```

### From Dictionary

```python
config_dict = {
    "engine_url": "http://localhost:12000",
    "keycloak_url": "http://localhost:11000",
    "keycloak_realm": "poc",
    "auth_method": "keycloak",
    "credentials": {
        "username": "agent@example.com",
        "password": "password"
    }
}
config = NPLConfig.from_dict(config_dict)
```

### From YAML (Optional)

```python
# Requires: pip install pyyaml
config = NPLConfig.from_yaml("npl-config.yaml")
```

## Advanced Usage

### Using NPLToolRegistry

For more control over tool discovery and caching:

```python
from adk_npl import NPLToolRegistry, NPLConfig

config = NPLConfig.from_env()
registry = NPLToolRegistry(config)

# Authenticate
await registry.authenticate()

# Discover tools
tools = await registry.discover_tools()

# Use tools with your agent
agent = LlmAgent(..., tools=tools)
```

### Specifying Packages

```python
# Discover only specific packages
tools = await registry.discover_tools(packages=["negotiation"])

# Or when creating agent
agent = await create_agent_with_npl(
    base_agent,
    config,
    packages=["negotiation", "fund_management"]
)
```

### Force Refresh Cache

```python
# Force refresh (ignore cache)
tools = await registry.discover_tools(force_refresh=True)

# Or invalidate cache manually
registry.refresh_tools()
```

## How It Works

### 1. Package Discovery

The library discovers NPL packages using multiple strategies (in order):

1. **Swagger UI Parsing** (Primary)
   - Fetches `/swagger-ui/` HTML
   - Extracts URLs matching `/npl/{package}/-/openapi.json`
   - Fully dynamic, no configuration needed

2. **Config File** (Fallback)
   - Reads `npl-packages.json` file
   - Format: `{"packages": ["package1", "package2"]}`

3. **Environment Variable** (Fallback)
   - Reads `NPL_PACKAGES` env var
   - Format: `package1,package2`

### 2. Schema-Aware Tool Generation

For each discovered package:

1. Fetches OpenAPI spec from `/npl/{package}/-/openapi.json`
2. Parses spec to extract:
   - Protocol names and request body schemas
   - Actions (POST endpoints)
   - Parameters with types, required/optional status
   - Nested structures (e.g., `priceSpecification.price`)
3. **Flattens schemas** into explicit parameters:
   - `priceSpecification_price: float`
   - `priceSpecification_currency: str`
4. **Generates typed Python functions**:
   ```python
   def npl_commerce_Product_create(
       category: str,
       description: str,
       name: str,
       seller_department: str,
       seller_organization: str,
       sku: str,
       brand: str = None,  # Optional
       gtin: str = None    # Optional
   ) -> dict
   ```
5. Wraps functions as `FunctionTool` instances
6. Returns list of tools with self-documenting signatures

### 3. Caching

- OpenAPI specs are cached per package
- Generated tools are cached (TTL: 5 minutes default)
- Cache automatically invalidates on authentication change

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ 1. DISCOVER PACKAGES                                    │
│    GET /swagger-ui/ → Parse HTML → Extract packages    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. FOR EACH PACKAGE: GET OPENAPI SPEC                   │
│    GET /npl/{package}/-/openapi.json                    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. PARSE OPENAPI SPEC                                   │
│    Extract protocols, actions, parameters                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 4. GENERATE PYTHON FUNCTIONS                            │
│    Create functions dynamically using closures          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 5. WRAP AS ADK TOOLS                                    │
│    FunctionTool(function)                                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 6. AGENT USES TOOLS                                     │
│    Agent sees and can call all NPL protocol actions     │
└─────────────────────────────────────────────────────────┘
```

## Authentication

### Keycloak (OAuth2 Password Flow)

```python
config = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="poc",
    auth_method="keycloak",
    credentials={
        "username": "agent@example.com",
        "password": "password"
    }
)
```

### Direct Token

```python
config = NPLConfig(
    engine_url="http://localhost:12000",
    auth_method="token",
    credentials={
        "token": "your_jwt_token"
    }
)
```

### No Authentication (Development Only)

```python
config = NPLConfig(
    engine_url="http://localhost:12000",
    auth_method="none"
)
```

## Error Handling & Resilience

The library provides robust error handling with automatic retries and token refresh:

### Error Classes

```python
from adk_npl import (
    NPLIntegrationError,
    AuthenticationError,
    ToolDiscoveryError,
    PackageDiscoveryError,
    NPLClientError,
    TokenExpiredError,
    ServiceUnavailableError
)

try:
    agent = await create_agent_with_npl(base_agent, config)
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except PackageDiscoveryError as e:
    print(f"Could not discover packages: {e}")
except ToolDiscoveryError as e:
    print(f"Tool generation failed: {e}")
except NPLClientError as e:
    print(f"API error: {e.message}")
    print(f"Status: {e.status_code}, URL: {e.url}")
```

### Automatic Retries

The `NPLClient` automatically retries transient failures (5xx errors, 429 rate limits, network errors) with exponential backoff:

```python
from adk_npl import NPLClient

client = NPLClient(
    base_url="http://localhost:12000",
    auth_token="token",
    max_retries=3,        # Retry up to 3 times
    timeout=30.0          # 30 second timeout per request
)
```

### Token Refresh

Tokens are automatically refreshed when expired:

```python
from adk_npl import NPLClient, NPLToolRegistry

# Token refresh is handled automatically by NPLToolRegistry
registry = NPLToolRegistry(config)
await registry.authenticate()  # Initial authentication

# If token expires, it will be automatically refreshed on next API call
tools = await registry.discover_tools()
```

## Monitoring & Observability

Built-in monitoring tools for production use:

### Metrics Collection

```python
from adk_npl import get_metrics

# Get global metrics instance
metrics = get_metrics()

# View metrics summary
summary = metrics.get_summary()
print(f"API calls: {summary['counters']}")
print(f"Recent errors: {summary['recent_errors']}")

# Get latency statistics
latency_stats = metrics.get_latency_stats("npl.api.latency", method="GET")
if latency_stats:
    print(f"Avg latency: {latency_stats['avg']:.3f}s")
    print(f"P95 latency: {latency_stats['p95']:.3f}s")
```

### Structured Logging

```python
from adk_npl import StructuredLogger

# Plain text logging (default)
logger = StructuredLogger("my_app", use_json=False)
logger.info("API call completed", endpoint="/npl/commerce/Product")

# JSON-formatted logging for log aggregation systems
json_logger = StructuredLogger("my_app", use_json=True)
json_logger.info("API call completed", endpoint="/npl/commerce/Product", latency=0.123)
# Output: {"timestamp": "2025-12-28T...", "level": "INFO", "message": "...", ...}
```

### Health Checks

```python
from adk_npl import HealthCheck, NPLClient

client = NPLClient(base_url="http://localhost:12000", auth_token="token")
health_check = HealthCheck(client)

# Check engine health
engine_health = health_check.check_engine_health()
print(f"Engine status: {engine_health['status']}")
print(f"Latency: {engine_health.get('latency_seconds', 0):.3f}s")

# Check authentication
auth_status = health_check.check_authentication()
print(f"Authenticated: {auth_status['authenticated']}")

# Get full health status
full_health = health_check.get_full_health()
# Includes: engine, authentication, metrics summary
```

## Troubleshooting

### "Could not discover NPL packages"

1. Check NPL Engine is running at `NPL_ENGINE_URL`
2. Verify Swagger UI is accessible at `{NPL_ENGINE_URL}/swagger-ui/`
3. Or configure packages manually in `npl-packages.json` or `NPL_PACKAGES` env var

### "Authentication failed"

1. Verify Keycloak URL and realm are correct
2. Check username and password
3. Ensure user has necessary permissions in Keycloak

### "No tools generated"

1. Check that packages contain protocols with actions
2. Verify OpenAPI specs are accessible
3. Check authentication is working (some endpoints require auth)

### "Request failed after X attempts"

This indicates retries were exhausted. Check:
1. NPL Engine is running and accessible
2. Network connectivity is stable
3. Authentication token is valid (check token refresh callback is configured)
4. Increase `max_retries` if needed for unstable networks

### Monitoring Metrics

To view collected metrics:

```python
from adk_npl import get_metrics

metrics = get_metrics()
print(metrics.get_summary())
```

Metrics are automatically collected for all API calls made through `NPLClient`.

## License

MIT License

## Contributing

Contributions welcome! This is an open-source library for integrating ADK with NPL.

