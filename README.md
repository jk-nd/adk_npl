# ADK Demo - Governed AI-Driven Supplier Ordering

**Proof of Concept:** AI agents participating in real business workflows with policy enforcement outside the LLM.

This project demonstrates how AI agents can autonomously initiate business transactions while being safely governed by NPL (Noumena Protocol Language), even when the AI is imperfect or unpredictable. The system enforces policies through state machines and role-based authorization, ensuring that **human approval is mandatory for high-value purchases** and all actions are auditable.

## Key Features

- ✅ **Agents Initiate Actions** - LLMs autonomously propose and execute business operations
- ✅ **Policies Enforced Outside LLM** - NPL state machine blocks invalid transitions
- ✅ **Human-in-the-Loop** - High-value orders require human approval before execution
- ✅ **Fully Auditable** - Complete audit trail of all state transitions and approvals
- ✅ **Safe by Design** - System remains correct even if LLM hallucinates or skips steps

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
│           │   (Trusts both issuers)      │                       │
│           │   schema.org commerce        │                       │
│           │   protocols (Product,        │                       │
│           │   Offer, Order)              │                       │
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

### 4. Run Approval Workflow Demo

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

### 5. Troubleshooting

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
│   ├── client.py               # NPL Engine client
│   ├── auth.py                 # Keycloak authentication
│   ├── discovery.py            # Package discovery from Swagger
│   ├── tools.py                # Dynamic ADK tool generation
│   └── agent_builder.py        # Convenience agent creation
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
│   ├── test_commerce_product.py  # Product creation test
│   └── test_commerce_flow.py     # Full commerce flow test
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
├── scripts/
│   ├── setup-fresh.sh          # Complete clean setup
│   ├── configure-user-profiles.sh  # Keycloak 26+ config
│   └── wait-for-services.sh    # Health check utilities
│
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

## Documentation

Additional documentation is available in the `docs/` folder:

- **[Why ADK-NPL?](docs/MOTIVATION.md)** - Motivation and use cases for the integration
- [Agent Architecture](docs/AGENTS.md) - Detailed agent design and hybrid tool architecture
- [A2A Communication](docs/A2A_COMMUNICATION.md) - Agent-to-agent interaction patterns
- [ADK Monitoring](docs/MONITORING.md) - Web UI, CLI, and API monitoring tools

## License

MIT
