# Agent Architecture

## Overview

This project implements two autonomous agents using Google's Agent Development Kit (ADK) with NPL integration:

1. **Purchasing Agent** - Buyer-side procurement (Acme Corp)
2. **Supplier Agent** - Seller-side sales (Supplier Inc)

Both agents use the **Smart NPL Bridge** to dynamically discover and understand NPL protocols.

## Key Design Principles

### 1. Goal-Oriented Autonomy

Agents are given high-level objectives, not step-by-step instructions:

- **Buyer**: "Purchase all items on the shopping list"
- **Supplier**: "Register products and fulfill orders"

They discover the required actions from the tool descriptions.

### 2. Smart NPL Bridge

Agents learn workflow rules from enriched tool docstrings:

```
### Workflow Summary
States: Draft → Published → Accepted
Parties: seller, buyer

### Party Actions
seller: publish, withdraw, updatePrice
buyer: accept, reject

### Business Rules
- require(price > 0, "Price must be positive")
- require(quantity <= inventory, "Insufficient stock")
```

### 3. Schema-Aware Tool Generation

NPL tools have explicit typed parameters:

```python
def npl_commerce_Product_create(
    category: str,           # Required
    description: str,        # Required  
    itemCondition: str,      # Required: NewCondition, UsedCondition
    name: str,               # Required
    seller_department: str,  # Required
    seller_organization: str,# Required
    sku: str,                # Required
    gtin: str,               # Required
    brand: str = None        # Optional
) -> dict
```

### 4. NPL-Assisted Decision Loop

Agents follow the **ORIENT → DECIDE → ACT → STOP** pattern:

1. **ORIENT**: Query NPL for current state and valid actions
   - Use `npl_*_next_actions()` to get authoritative state information
   - This is NOT inferred from conversation context
   
2. **DECIDE**: Use judgment + A2A negotiation to choose action
   - Agent decides what's BEST (NPL tells what's POSSIBLE)
   - Natural language negotiation via A2A when needed
   
3. **ACT**: Execute ONE action
   - NPL validates and blocks if invalid
   - No more state confusion - NPL is the gatekeeper
   
4. **STOP**: Let the other party respond
   - Turn-based prevents ping-pong
   - NPL notifications wake agent when it's their turn

See [`docs/WHY_AGENTS_FAILED.md`](WHY_AGENTS_FAILED.md) for the complete journey.

### 5. Protocol Creation Principle

**CRITICAL**: Only the party at the START of the workflow sequence should instantiate a protocol.

For the `Product → Offer → PurchaseOrder` workflow:
- **Supplier creates Product** (seller is sole party, can act from initial state)
- **Supplier creates Offer** (seller must publish from initial state, buyer joins later)
- **Buyer creates PurchaseOrder** (buyer initiates the order after accepting an offer)

This is enforced through:
1. **Dynamic Role Detection**: The Smart Bridge analyzes which party has permissions to act from the protocol's `initial state`
2. **Tool Docstring Guidance**: Each multi-party protocol creation tool includes "WHO CREATES THIS PROTOCOL?" guidance
3. **Workflow Sequence Awareness**: Tools document dependencies (e.g., "Offer requires Product")

This prevents agents from creating protocols out of sequence or with incorrect party roles.

### 6. Enterprise ADK Callbacks

Agents use ADK's callback system for robust behavior:

| Callback | Purpose |
|----------|---------|
| `before_tool_callback` | Enforce max 15 tool calls per turn, record metrics |
| `after_tool_callback` | Log tool completions, record latency |
| `on_tool_error_callback` | Categorize NPL errors, provide guidance, record errors |
| `on_model_error_callback` | Rate limit backoff (429 handling) |

### 7. Federated Identity

Each agent authenticates with its own Keycloak realm:

| Agent | Realm | Organization |
|-------|-------|--------------|
| Purchasing Agent | `purchasing` | Acme Corp |
| Supplier Agent | `supplier` | Supplier Inc |

## Agent Structure

### Purchasing Agent (`purchasing_agent/agent.py`)

**Location**: Acme Corp, Procurement Department

**Tools**:
- `get_my_identity` - Get agent's party claims
- `list_shopping_items` - View shopping list
- `recall_my_protocols` - Check existing protocols
- `send_message_to_supplier` - A2A communication
- `npl_*` - All NPL protocol tools

**Inventory**: `data/buyer_shopping_list.json`

### Supplier Agent (`supplier_agent/agent.py`)

**Location**: Supplier Inc, Sales Department

**Tools**:
- `get_my_identity` - Get agent's party claims
- `list_inventory_products` - View available inventory
- `recall_my_protocols` - Check existing protocols
- `send_message_to_buyer` - A2A communication
- `npl_*` - All NPL protocol tools

**Inventory**: `data/supplier_inventory.json`

## Usage

### Via Demo Script

```bash
./start_demo.sh
```

This starts all services including agents. Open http://localhost:5173 to interact.

Agents are exposed via SSE chat endpoints:
- Buyer: `POST http://localhost:8001/chat/buyer`
- Supplier: `POST http://localhost:8001/chat/supplier`

### Programmatic Creation

```python
from purchasing_agent.agent import create_purchasing_agent
from supplier_agent.agent import create_supplier_agent
from adk_npl import NPLConfig
from google.adk.sessions import InMemorySessionService

config = NPLConfig.from_env()
session_service = InMemorySessionService()

# Create buyer agent
buyer = await create_purchasing_agent(
    config=config,
    session_service=session_service,
    agent_id="buyer_agent"
)

# Create supplier agent  
supplier = await create_supplier_agent(
    config=config,
    session_service=session_service,
    agent_id="supplier_agent"
)
```

## Interaction Flow

```
┌─────────────────────┐                    ┌─────────────────────┐
│  Purchasing Agent   │                    │   Supplier Agent    │
├─────────────────────┤                    ├─────────────────────┤
│ "Acme Corp"         │       A2A          │ "Supplier Inc"      │
└──────────┬──────────┘◄──────────────────►└──────────┬──────────┘
           │                                          │
           │                    Product_create()      │
           │                    Offer_create()        │
           │                    Offer_publish()       │
           │<─────────────────────────────────────────│
           │                                          │
           │ Offer_accept()                           │
           │ PurchaseOrder_create()                   │
           │─────────────────────────────────────────>│
           │                                          │
           │      [Approval if high-value]            │
           │                                          │
           │                    PurchaseOrder_ship()  │
           │<─────────────────────────────────────────│
           │                                          │
           └───────────► NPL Engine ◄─────────────────┘
                     (Shared Protocol State)
```

## Testing

```bash
# Run agent creation tests
pytest tests/test_agent_core.py -v

# Full test suite
./run_tests.sh
```
