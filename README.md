# ADK Demo - Governed AI-Driven Supplier Ordering

**Proof of Concept:** AI agents participating in real business workflows with policy enforcement outside the LLM.

This project demonstrates how AI agents can autonomously initiate business transactions while being safely governed by NPL (Noumena Protocol Language), even when the AI is imperfect or unpredictable. The system enforces policies through state machines and role-based authorization, ensuring that **human approval is mandatory for high-value purchases** and all actions are auditable.

## Key Features

- ✅ **Agents Initiate Actions** - LLMs autonomously propose and execute business operations
- ✅ **Policies Enforced Outside LLM** - NPL state machine blocks invalid transitions
- ✅ **Human-in-the-Loop** - High-value orders require human approval before execution
- ✅ **Fully Auditable** - Complete audit trail of all state transitions and approvals
- ✅ **Safe by Design** - System remains correct even if LLM hallucinates or skips steps
- ✅ **Resilient Error Handling** - Automatic retries with exponential backoff, token refresh
- ✅ **Monitoring & Observability** - Metrics collection, structured logging, health checks
- ✅ **Comprehensive Testing** - Edge case tests, integration tests, monitoring tests
- ✅ **Activity Logging** - Real-time tracking of all agent actions, API calls, and state transitions

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ADK Agents                                │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │ Purchasing Agent │              │  Supplier Agent  │         │
│  │   (Acme Corp)    │              │  (Supplier Inc)  │         │
│  └────────┬─────────┘              └────────┬─────────┘         │
│           │                                  │                   │
│           ▼                                  ▼                   │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │ Keycloak Realm:  │              │ Keycloak Realm:  │         │
│  │   "purchasing"   │              │    "supplier"    │         │
│  └────────┬─────────┘              └────────┬─────────┘         │
│           │                                  │                   │
│           └──────────────┬───────────────────┘                   │
│                          ▼                                       │
│           ┌──────────────────────────────┐                       │
│           │        NPL Engine            │                       │
│           │   (Trusts keycloak issuer)   │                       │
│           │   schema.org commerce        │                       │
│           │   protocols (Product,        │                       │
│           │   Offer, PurchaseOrder)       │                       │
│           └──────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Google API Key (for Gemini)

### 1. Setup

```bash
# Clone and enter directory
cd adk-demo

# Copy environment template
cp .env.example .env

# Edit .env and add your Google API key
# GOOGLE_API_KEY="your-key-here"

# Activate Python environment
source .venv/bin/activate

# Install dependencies (including nest_asyncio)
pip install -r adk_npl/requirements.txt
```

### 2. Start Services (Fresh)

```bash
# Complete clean start with all configuration
./scripts/setup-fresh.sh
```

### 3. Run ADK Web UI

We have provided a helper script to set up the environment correctly:

```bash
./run_adk.sh
```

Access the UI at http://localhost:8000

### 4. Run NPL Approval Dashboard (NPL-Native Frontend)

The approval dashboard provides a human-friendly interface for approving high-value orders, using type-safe clients generated directly from NPL Engine's OpenAPI specifications:

```bash
cd frontend
npm install
npm run dev
```

Access at http://localhost:5173

**Note:** On first run, you may need to add a hosts entry so your browser can resolve the `keycloak` hostname:
```bash
./setup_hosts.sh
```

**Key Features:**
- ✅ **Type-safe API clients** - Auto-generated from NPL protocols
- ✅ **Direct NPL integration** - No backend proxy needed
- ✅ **Keycloak authentication** - Built-in auth handling with login/logout
- ✅ **Light/Dark theme toggle** - Modern UI with theme switching
- ✅ **Always in sync** - Regenerate types when protocols change

**To regenerate types after protocol changes:**
```bash
cd frontend
curl -s http://localhost:12000/npl/commerce/-/openapi.json > openapi/commerce-openapi.json
npx openapi-typescript openapi/commerce-openapi.json -o ./src/clients/commerce/types.ts
```

### 5. Run Approval Workflow Demo

The main demo showcases the end-to-end approval workflow for high-value purchases:

```bash
python demo_approval_workflow.py
```

This demonstrates:
1. Product and Offer creation by supplier
2. Offer acceptance by buyer
3. PurchaseOrder creation (high value, triggers approval requirement)
4. Supplier submits quote
5. **Buyer agent attempts to place order → BLOCKED by NPL**
6. Human approver approves the order
7. Buyer agent retries → SUCCESS
8. Complete audit trail with all state transitions

**Alternative:** For a basic agent negotiation simulation (without approval workflow):
```bash
python simulate_negotiation.py
```

*Note: These scripts run multiple LLM requests. If using a free tier Gemini API key, you may hit rate limits (429).*

### 6. Activity Logging & Monitoring

Track all agent actions, API calls, and state transitions in real-time:

```bash
# Start the Activity Feed API
cd activity_api
source ../.venv/bin/activate
python3 main.py
# API runs on http://localhost:8002

# Run the demo (generates activity logs)
cd ..
python demo_approval_workflow.py

# View logs in the UI
cd frontend
npm run dev
# Open http://localhost:5173
# Click "Activity Log" or "Metrics" tabs
```

**Features:**
- 📝 **Activity Log** - Real-time feed of all system events (agent actions, API calls, state transitions)
- 📊 **Metrics Dashboard** - Performance metrics, latency percentiles, error tracking
- 🎯 **Auto-refresh** - Live updates without manual refresh
- 📁 **JSON Log Files** - Structured logs saved to `logs/activity_*.json`
- 🔍 **Filtering** - Filter by event type or actor

**View logs directly:**
```bash
# View latest log file
cat logs/activity_latest.json | jq

# Watch logs in real-time
tail -f logs/activity_latest.json | jq
```

See [ACTIVITY_LOGGING.md](ACTIVITY_LOGGING.md) for detailed documentation.

### 7. Troubleshooting

If you encounter **429 Resource Exhausted** errors with Gemini models:
- Ensure `GOOGLE_CLOUD_PROJECT` is set in `.env` if using a paid billing account.
- The agents are configured to use `gemini-flash-latest`. You can change this in `agents/purchasing/agent.py` and `agents/supplier/agent.py`.

If you see **ModuleNotFoundError: No module named 'adk_npl'**:
- Use the `./run_adk.sh` script which sets `PYTHONPATH` correctly.


## Services

| Service | Port | Description |
|---------|------|-------------|
| NPL Engine | 12000 | Protocol execution engine |
| Keycloak | 11000 | Identity provider |
| Activity API | 8002 | Activity logs and metrics REST API |
| Frontend UI | 5173 | React approval dashboard (dev server) |
| Engine DB | 5432 | PostgreSQL for NPL Engine |
| Keycloak DB | 5439 | PostgreSQL for Keycloak |

## Keycloak Realms

### Purchasing Realm
- **Realm**: `purchasing`
- **Client**: `purchasing`
- **Users**:
  - `purchasing_agent` / `Welcome123` (Acme Corp, Procurement)
  - `approver` / `Welcome123` (Acme Corp, Finance) - **Required for approval workflow**
- **Organization**: Acme Corp

### Supplier Realm
- **Realm**: `supplier`
- **Client**: `supplier`
- **User**: `supplier_agent` / `Welcome123`
- **Organization**: Supplier Inc
- **Department**: Sales

## Party Binding Strategy (NPL)

This project uses **explicit party binding** with `@parties` at protocol creation:

1. **At creation**: Pass all parties via `@parties` with their JWT claims:
   ```json
   {
     "@parties": {
       "seller": { "claims": { "organization": ["Supplier Inc"], "department": ["Sales"] } },
       "buyer": { "claims": { "organization": ["Acme Corp"], "department": ["Procurement"] } }
     }
   }
   ```

2. **At action time**: The engine matches the caller's JWT claims against stored party claims.
   - Caller's JWT must contain `organization` and `department` claims
   - These are configured via `scripts/configure-user-profiles.sh`

3. **No rules.yml**: The `rules.yml` file is empty - all party binding is explicit.

4. **Observers**: Protocol parties automatically have read access. Add observers only for non-party readers.

## Project Structure

```
adk-demo/
├── adk_npl/                    # ADK-NPL integration library
│   ├── config.py               # Configuration management
│   ├── client.py               # NPL Engine client (with retry logic)
│   ├── auth.py                 # Keycloak authentication (with token refresh)
│   ├── discovery.py            # Package discovery from Swagger
│   ├── tools.py                # Dynamic ADK tool generation
│   ├── agent_builder.py        # Convenience agent creation
│   ├── monitoring.py           # Metrics, logging, health checks
│   ├── activity_logger.py      # Activity logging (JSON logs + in-memory buffer)
│   ├── retry.py                # Retry utilities with exponential backoff
│   └── utils.py                # Error classes and utilities
│
├── activity_api/               # Activity Feed REST API
│   ├── main.py                 # FastAPI server for logs and metrics
│   └── requirements.txt        # API dependencies
│
├── purchasing_agent/           # Purchasing agent (buyer side)
│   └── agent.py                # ADK agent with business logic
│
├── supplier_agent/             # Supplier agent (seller side)
│   └── agent.py                # ADK agent with sales logic
│
├── agents/                     # ADK Web UI agent wrappers
│   ├── purchasing/agent.py     # Purchasing agent for adk web
│   └── supplier/agent.py       # Supplier agent for adk web
│
├── tests/                      # Integration tests
│   ├── conftest.py             # Shared pytest fixtures
│   ├── test_utils.py           # Test utilities and helpers
│   ├── test_commerce_product.py  # Product creation test
│   ├── test_commerce_flow.py     # Full commerce flow test
│   ├── test_error_handling.py    # Error handling and retry tests
│   └── test_monitoring.py        # Monitoring and metrics tests
│
├── npl/                        # NPL source code
│   └── src/main/
│       ├── npl-1.0/            # Protocol definitions
│       │   ├── commerce/       # Product, Offer, Order
│       │   └── schemaorg/      # Schema.org types & enums
│       └── yaml/               # Migration & rules (empty)
│
├── keycloak-provisioning/      # Terraform for Keycloak setup
│   └── terraform.tf            # Realms, clients, users
│
├── frontend/                   # React + TypeScript UI
│   ├── src/
│   │   ├── components/         # React components
│   │   │   ├── ApprovalDashboard.tsx  # Human approval interface
│   │   │   ├── ActivityLog.tsx        # Activity log viewer
│   │   │   └── MetricsDashboard.tsx   # Metrics and performance
│   │   ├── contexts/           # Theme context
│   │   └── clients/            # Type-safe NPL API clients
│   └── openapi/                # OpenAPI specs for type generation
│
├── logs/                       # Activity log files (JSON)
│   └── activity_*.json         # Timestamped activity logs
│
├── scripts/
│   ├── setup-fresh.sh          # Complete clean setup
│   ├── configure-user-profiles.sh  # Keycloak 26+ config
│   └── wait-for-services.sh    # Health check utilities
│
├── setup_hosts.sh              # Helper script for keycloak hostname
├── docker-compose.yml          # Service orchestration
└── .env                        # Environment variables
```

## Agents

### Purchasing Agent (Buyer)

Autonomous procurement agent that:
- Evaluates supplier offers
- Negotiates within budget constraints
- Creates purchase proposals
- Records agreements using NPL protocols

```python
from purchasing_agent import create_purchasing_agent
from adk_npl import NPLConfig

config = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="purchasing",
    keycloak_client_id="purchasing",
    credentials={"username": "purchasing_agent", "password": "Welcome123"}
)

agent = await create_purchasing_agent(
    config=config,
    agent_id="buyer_001",
    budget=50000.0,
    requirements="Procurement of services"
)
```

### Supplier Agent (Seller)

Autonomous sales agent that:
- Evaluates purchase requests
- Creates competitive offers
- Negotiates for better margins
- Manages inventory and capacity

```python
from supplier_agent import create_supplier_agent
from adk_npl import NPLConfig

config = NPLConfig(
    engine_url="http://localhost:12000",
    keycloak_url="http://localhost:11000",
    keycloak_realm="supplier",
    keycloak_client_id="supplier",
    credentials={"username": "supplier_agent", "password": "Welcome123"}
)

agent = await create_supplier_agent(
    config=config,
    agent_id="supplier_001",
    min_price=15.0,
    inventory={"widgets": 5000},
    capacity={"max_quantity": 10000}
)
```

### Agent Capabilities

Both agents have:
- **NPL Protocol Tools** - Dynamically discovered from the engine (protocol-agnostic)
- **Business Tools** - Domain-specific logic (purchasing vs. supplier)
- **Generic Instructions** - Work with any NPL protocols deployed

### Key Features

- **Schema-Aware Tool Generation**: Generates ADK tools with explicit typed parameters from OpenAPI schemas
- **Dynamic Discovery**: Automatically discovers NPL packages from Swagger UI
- **Self-Documenting Tools**: LLMs see exact parameter signatures (not opaque `**kwargs`)
- **Multi-Realm Auth**: Supports federated identity with multiple Keycloak realms
- **Caching**: Efficient caching of discovered packages and tools
- **Resilient Error Handling**: Automatic retries with exponential backoff, token refresh on expiry
- **Monitoring & Observability**: Built-in metrics collection, structured logging, health checks
- **Production Ready**: Comprehensive error handling, retry logic, and observability tools

## Approval Workflow Demo

The `demo_approval_workflow.py` script demonstrates the complete PoC workflow:

### Flow

1. **Supplier Agent** creates a Product (Industrial Pump)
2. **Supplier Agent** creates and publishes an Offer
3. **Buyer Agent** accepts the Offer
4. **System** creates a PurchaseOrder with high value ($12,000 > $5,000 threshold)
5. **Supplier Agent** submits a quote → Order transitions to `ApprovalRequired`
6. **Buyer Agent** attempts to place order → **❌ NPL BLOCKS** with `IllegalProtocolStateRuntimeErrorException`
7. **Human Approver** (Alice) approves via `approve` action → Order transitions to `Approved`
8. **Buyer Agent** retries place order → **✅ SUCCESS** → Order transitions to `Ordered`
9. **Supplier Agent** ships the order
10. **System** retrieves complete audit trail

### Why This Works

- **LLM suggests**, NPL decides - Agent cannot bypass policy
- **State machine enforcement** - Invalid transitions are rejected
- **Role-based authorization** - Only users with `approver` role can approve
- **Auditability** - Every action is logged with timestamp and actor
- **Resilience** - Works even if LLM hallucinates or attempts forbidden actions

## NPL Protocols

The demo uses schema.org-inspired commerce protocols with an approval workflow:

- **`commerce.Product`** - Product catalog entries (seller creates)
- **`commerce.Offer`** - Price offers with terms (seller creates, buyer accepts)
- **`commerce.PurchaseOrder`** - Purchase orders with approval workflow (buyer creates after accepting offer)

### PurchaseOrder Approval Workflow

The `PurchaseOrder` protocol implements human-in-the-loop approval for high-value purchases:

**State Machine:**
```
Requested → Quoted → ApprovalRequired → Approved → Ordered → Shipped → Closed
                   ↘ (if < $5000) ↗
```

**Key Rules:**
- Orders **≥ $5,000** require approval by a user with `approver` role
- `placeOrder` action is **blocked** unless:
  - Quote exists
  - Approval exists (if required)
- All state transitions and approvals are **auditable**

**Schema.org Types:**
Supporting types in `schemaorg/`:
- `PriceSpecification`, `QuantitativeValue`, `MonetaryAmount`
- `PostalAddress`, `ContactPoint`, `DeliveryTimeSettings`
- `OrderStatus`, `ItemCondition`, `OfferStatus`, `ProductStatus` (enums)

## Development

### Add a New Agent

1. Create agent directory: `mkdir my_agent`
2. Define agent in `my_agent/agent.py`
3. Configure realm/user in Keycloak (or reuse existing)
4. Test with adk_npl library

### Modify NPL Protocols

1. Edit files in `npl/src/main/npl-1.0/`
2. Update `npl/src/main/yaml/migration.yml` if needed
3. Restart engine: `docker-compose restart engine`

### Update Keycloak Config

1. Edit `keycloak-provisioning/terraform.tf`
2. Rebuild: `docker-compose up -d --build keycloak-provisioning`
3. Run user profile config: `./scripts/configure-user-profiles.sh`

## Troubleshooting

### JWKS Authentication Issues

If you encounter `Failed to retrieve JWKS for http://localhost:11000/realms/...` errors, this is because the Engine (running in Docker) cannot reach `localhost:11000` from inside the container.

**Solution:** The Python authentication client automatically rewrites the `Host` header to `keycloak:11000` when connecting to `localhost:11000`. This makes Keycloak issue tokens with the `keycloak:11000` issuer, which the Engine can reach via the Docker network. This fix is implemented in `adk_npl/auth.py` and works automatically.

**Note:** The Engine doesn't support `ENGINE_ISSUER_JWKS_URL_OVERRIDES` in the current version, so Host header rewriting is the recommended workaround.

### Token Claims Missing (organization, department)

Keycloak 26+ requires explicit User Profile configuration:
```bash
./scripts/configure-user-profiles.sh
```

### 503 Service Unavailable

JWT key cache issue - restart engine:
```bash
docker-compose restart engine
```

### Full Reset

```bash
docker-compose down -v
./scripts/setup-fresh.sh
```

## Error Handling & Resilience

The ADK-NPL integration includes robust error handling:

- **Automatic Retries**: Transient failures (5xx, 429, network errors) are automatically retried with exponential backoff
- **Token Refresh**: Expired JWT tokens are automatically refreshed using refresh tokens
- **Detailed Error Messages**: Errors include status codes, URLs, and response bodies for debugging
- **Configurable Timeouts**: Set request timeouts per client instance
- **Graceful Degradation**: Connection errors and timeouts are handled gracefully

### Example: Using Retry Logic

```python
from adk_npl import NPLClient

# Client with custom retry configuration
client = NPLClient(
    base_url="http://localhost:12000",
    auth_token="token",
    max_retries=3,        # Retry up to 3 times
    timeout=30.0          # 30 second timeout
)

# Automatic retries on transient failures
try:
    result = client.create_protocol(...)
except NPLClientError as e:
    # Detailed error information available
    print(f"Error: {e.message}")
    print(f"Status: {e.status_code}")
    print(f"URL: {e.url}")
```

## Monitoring & Observability

Built-in monitoring tools for production use:

- **Metrics Collection**: Automatic tracking of API calls, latency, errors
- **Structured Logging**: Optional JSON-formatted logs for log aggregation systems
- **Health Checks**: Utilities to check NPL Engine health and authentication status

### Example: Using Metrics

```python
from adk_npl import get_metrics, HealthCheck, NPLClient

# Get metrics summary
metrics = get_metrics()
summary = metrics.get_summary()
print(f"API calls: {summary['counters']}")
print(f"Recent errors: {summary['recent_errors']}")

# Check system health
client = NPLClient(base_url="http://localhost:12000")
health = HealthCheck(client).get_full_health()
print(f"Engine status: {health['engine']['status']}")
print(f"Auth status: {health['authentication']['status']}")
```

### Example: Structured Logging

```python
from adk_npl import StructuredLogger

# JSON-formatted logging for log aggregation
logger = StructuredLogger("my_app", use_json=True)
logger.info("API call completed", endpoint="/npl/commerce/Product", latency=0.123)
```

## Testing

Comprehensive test suite covering:

- **Error Handling**: Retry logic, token refresh, error messages, graceful degradation
- **Monitoring**: Metrics collection, structured logging, health checks
- **Integration Tests**: Full commerce workflow tests

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test suites
pytest tests/test_error_handling.py -v
pytest tests/test_monitoring.py -v

# Run integration tests (requires running services)
pytest tests/ -m integration -v
```

## Documentation

Additional documentation is available in the `docs/` folder:

- **[Why ADK-NPL?](docs/MOTIVATION.md)** - Motivation and use cases for the integration
- [Agent Architecture](docs/AGENTS.md) - Detailed agent design and hybrid tool architecture
- [A2A Communication](docs/A2A_COMMUNICATION.md) - Agent-to-agent interaction patterns
- [ADK Monitoring](docs/MONITORING.md) - Web UI, CLI, and API monitoring tools

## License

MIT
