# ADK-NPL Integration Library

A Python library for integrating Google's Agent Development Kit (ADK) with Noumena's NPL Engine.

## 🎯 Key Features

- **Smart NPL Bridge**: Automatically enriches AI tools with semantic information from NPL source code
- **Schema-Aware Tools**: Generates typed `FunctionTool` instances from OpenAPI specs
- **Business Rule Extraction**: Parses `require` statements so agents understand contract rules
- **State Machine Mapping**: Extracts `become` transitions for workflow understanding
- **Standards Alignment**: Maps NPL types to Schema.org, ISO 20022, SWIFT, GS1
- **Enterprise Callbacks**: Tool limits, error categorization, rate limit backoff
- **Monitoring**: Built-in metrics, structured logging, health checks

## 📦 Module Structure

```
adk_npl/
├── agent_factory.py      # Enterprise agent factory with ADK callbacks
├── tools.py              # NPL tool generation (Smart Bridge core)
├── client.py             # NPL Engine REST client with retries
├── auth.py               # Keycloak OAuth2 authentication
├── config.py             # Configuration management
├── diagram_generator.py  # PlantUML workflow diagrams
├── standards_registry.py # Industry standards mapping
├── protocol_memory.py    # Cross-turn protocol tracking
├── partner_memory.py     # A2A partner identity storage
├── inventory_tools.py    # Shopping/inventory list tools
├── monitoring.py         # Metrics collection
├── activity_logger.py    # Structured activity logging
├── docstring_trimmer.py  # Tool description optimization
└── utils.py              # Error classes and utilities
```

## 🚀 Quick Start

### Using the Agent Factory (Recommended)

```python
from adk_npl import NPLConfig
from adk_npl.agent_factory import EnterpriseAgentFactory
from google.adk.sessions import InMemorySessionService

# Configure
config = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="purchasing",
    keycloak_client_id="purchasing",
    credentials={"username": "agent", "password": "password"}
)

# Create factory
session_service = InMemorySessionService()
factory = EnterpriseAgentFactory(config, session_service)

# Create agent with all NPL tools and callbacks
result = await factory.create_agent(
    agent_id="buyer_agent",
    objective="Purchase items for Acme Corp",
    custom_instructions="You are a procurement specialist.",
    model="gemini-2.0-flash"
)

agent = result["agent"]
plugins = result["plugins"]  # For Runner
```

### Direct Tool Generation

```python
from adk_npl import NPLClient
from adk_npl.tools import NPLToolGenerator
from adk_npl.auth import KeycloakAuth

# Authenticate
auth = KeycloakAuth(keycloak_url, realm, client_id, username, password)
token = await auth.authenticate()

# Create client
client = NPLClient(base_url=engine_url, auth_token=token)

# Generate tools
generator = NPLToolGenerator(npl_client=client, protocol_memory=None)
tools = await generator.generate_tools(packages=["commerce"])

# Tools now have enriched docstrings with business rules!
```

## 🧠 Smart Bridge Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ 1. DISCOVER PACKAGES                                         │
│    GET /swagger-ui/ → Parse HTML → Extract packages          │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. SEMANTIC EXTRACTION                                       │
│    Parse .npl files → require(), become, parties            │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. FUNCTIONAL EXTRACTION                                     │
│    GET /npl/{package}/-/openapi.json → Schemas, endpoints    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. SMART MERGE                                               │
│    Functional + Semantic → Enriched Tool Docstrings          │
│    • Business rules embedded in tool description             │
│    • State constraints visible to LLM                        │
│    • Party role guidance included                            │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. ADK FUNCTION TOOLS                                        │
│    Agent "knows" contract rules before calling               │
└─────────────────────────────────────────────────────────────┘
```

## 🔌 ADK Callbacks

The `EnterpriseAgentFactory` configures these ADK callbacks:

| Callback | Purpose |
|----------|---------|
| `before_tool_callback` | Enforce max 5 tool calls per turn |
| `after_tool_callback` | Log tool completions |
| `on_tool_error_callback` | Categorize NPL errors (validation, permission, not_found) |
| `on_model_error_callback` | Exponential backoff for 429 rate limits |

## ⚙️ Configuration

### Environment Variables

```bash
NPL_ENGINE_URL=http://localhost:12000
NPL_KEYCLOAK_URL=http://localhost:11000
NPL_KEYCLOAK_REALM=purchasing
NPL_USERNAME=agent
NPL_PASSWORD=password
GOOGLE_API_KEY=your_gemini_api_key
```

### From Code

```python
config = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="purchasing",
    keycloak_client_id="purchasing",
    credentials={"username": "agent", "password": "password"}
)
```

## 🔍 Error Handling

The library provides typed errors for different failure modes:

```python
from adk_npl.utils import (
    NPLIntegrationError,      # Base error
    AuthenticationError,       # Auth failures
    ToolDiscoveryError,        # Tool generation failures
    PackageDiscoveryError,     # Package not found
    NPLClientError,            # API errors (has status_code, url)
    TokenExpiredError,         # Token refresh needed
    ServiceUnavailableError    # Engine down
)
```

## 📊 Monitoring

```python
from adk_npl.monitoring import get_metrics

metrics = get_metrics()
summary = metrics.get_summary()
print(f"API calls: {summary['counters']}")
print(f"Latency P95: {metrics.get_latency_stats('npl.api.latency')['p95']}")
```

## 🧪 Testing

```bash
# Run NPL integration tests
pytest tests/test_npl_integration.py -v

# Run agent creation tests
pytest tests/test_agent_core.py -v
```

## License

MIT License
