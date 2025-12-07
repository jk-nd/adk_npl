# Agent Architecture

## Overview

This project implements two autonomous agents using Google's ADK with dynamic NPL protocol integration:

1. **Purchasing Agent** - Buyer-side procurement
2. **Supplier Agent** - Seller-side sales

Both agents are **completely protocol-agnostic** and work with any NPL protocols deployed to the engine.

## Key Design Principles

### 1. Protocol Independence

The agents make **no assumptions** about which NPL protocols exist. They:
- Dynamically discover available protocols from the NPL Engine's Swagger UI
- Generate tools on-the-fly from OpenAPI specifications
- Work equally well with commerce, fund management, or any other NPL packages

### 2. Schema-Aware Tool Generation

NPL tools are generated with **explicit typed parameters** from OpenAPI schemas:

```python
# Generated tool signature (not **kwargs!)
def npl_commerce_Product_create(
    category: str,
    description: str,
    itemCondition: str,  # Enum: NewCondition, UsedCondition, etc.
    name: str,
    seller_department: str,
    seller_organization: str,
    sku: str,
    brand: str = None,
    gtin: str = None
) -> dict
```

Benefits:
- LLM sees exact parameters needed
- Self-documenting via docstrings
- Required params first, optional params last

### 3. Federated Identity

Each agent authenticates with its own Keycloak realm:
- **Purchasing Agent** → `purchasing` realm (Acme Corp)
- **Supplier Agent** → `supplier` realm (Supplier Inc)

The NPL Engine trusts both issuers.

### 4. Hybrid Tool Architecture

Each agent has two types of tools:

**NPL Protocol Tools (Dynamic)**
- Auto-discovered from the engine
- Example: `npl_commerce_Product_create`, `npl_commerce_Offer_publish`
- Purpose: Formal protocol execution, state management, audit trails

**Business Logic Tools (Static)**
- Domain-specific reasoning
- Example: `evaluate_proposal`, `calculate_counter_offer`
- Purpose: Decision-making, negotiation strategy

## Purchasing Agent

**Mission**: Maximize value within budget constraints

**Business Tools**:
- `propose_framework` - Propose protocol framework
- `create_proposal` - Generate purchase proposals
- `evaluate_proposal` - Assess supplier offers
- `calculate_counter_offer` - Negotiate lower prices
- `get_budget_status` - Check budget and constraints

**Key Parameters**:
- `budget` - Maximum spend (hard limit)
- `requirements` - What to purchase
- `constraints` - Delivery, quality requirements
- `strategy` - Negotiation approach

## Supplier Agent

**Mission**: Maximize revenue while maintaining profitability

**Business Tools**:
- `agree_framework` - Accept protocol framework
- `create_offer` - Generate sales offers
- `evaluate_purchase_request` - Assess buyer requests
- `calculate_counter_offer` - Negotiate higher prices
- `get_inventory_status` - Check inventory and capacity

**Key Parameters**:
- `min_price` - Minimum acceptable price (floor)
- `inventory` - Available products/services
- `capacity` - Production/delivery constraints
- `strategy` - Sales approach

## Usage Examples

### Create Purchasing Agent

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
    requirements="100 widgets",
    constraints={"max_delivery_days": 30},
    strategy="Negotiate for best value"
)
```

### Create Supplier Agent

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
    capacity={"max_quantity": 10000},
    strategy="Maximize margin"
)
```

## Interaction Flow

```
┌─────────────────────┐                    ┌─────────────────────┐
│  Purchasing Agent   │                    │   Supplier Agent    │
├─────────────────────┤                    ├─────────────────────┤
│ Budget: $50,000     │                    │ Min Price: $15/unit │
└──────────┬──────────┘                    └──────────┬──────────┘
           │                                          │
           │ 1. propose_framework("schema.org")       │
           │─────────────────────────────────────────>│
           │                                          │
           │                    2. agree_framework()  │
           │<─────────────────────────────────────────│
           │                                          │
           │      3. npl_commerce_Product_create()    │
           │      4. npl_commerce_Offer_create()      │
           │      5. npl_commerce_Offer_publish()     │
           │<─────────────────────────────────────────│
           │                                          │
           │ 6. evaluate_proposal()                   │
           │ 7. npl_commerce_Offer_accept()           │
           │────────────┐                  ┌──────────│
           │            │                  │          │
           │            ▼                  ▼          │
           │      ┌──────────────────────────┐        │
           │      │      NPL Engine          │        │
           │      │  (Shared Protocol State) │        │
           │      └──────────────────────────┘        │
```

## Testing

```bash
# Agent creation tests
pytest tests/test_purchasing_agent.py -s
pytest tests/test_supplier_agent.py -s

# Backend integration tests
pytest tests/ -m integration -s -v
```
