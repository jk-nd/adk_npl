# Agent-to-Agent (A2A) Communication

This document explains how the Purchasing and Supplier agents interact.

## Communication Methods

### 1. Direct A2A Communication (Manual Orchestration)

**Script**: `simulate_negotiation.py`

Manually orchestrates messages between agents:

```python
# Creates both agents
buyer = await create_purchasing_agent(...)
seller = await create_supplier_agent(...)

# Creates Runner instances for each
buyer_runner = Runner(agent=buyer, ...)
seller_runner = Runner(agent=seller, ...)

# Manually passes messages between them
buyer_response = await chat_with_runner(buyer_runner, message)
seller_response = await chat_with_runner(seller_runner, buyer_response)
```

**Usage**:
```bash
python3 simulate_negotiation.py
```

**Pros**:
- Full control over conversation flow
- Custom negotiation logic
- Easy to debug

**Cons**:
- Requires manual orchestration

### 2. NPL Protocol-Based Communication (Shared State)

Both agents interact through **shared NPL protocol instances**:

```
Supplier Agent  → npl_commerce_Product_create(@parties: {seller: claims})
                → npl_commerce_Offer_create(@parties: {seller: claims, buyer: claims})
                → npl_commerce_Offer_publish()
                  ↓
            [NPL Engine stores instances]
                  ↓
Purchasing Agent → npl_commerce_Offer_accept()
                 → npl_commerce_Order_create(@parties: {sellerRole: claims, buyer: claims})
```

**Party Binding**: At creation, parties are bound via `@parties` with claims. At action time, the caller's JWT claims are matched against stored parties.

**Pros**:
- Formal, auditable state management
- Protocol-agnostic (works with any NPL package)
- Built-in authorization

### 3. ADK Web UI

**Script**: `./run_adk.sh`

Interactive chat with individual agents:

```bash
./run_adk.sh
# Open http://localhost:8000
# Select an agent from the sidebar
# Start chatting
```

## Testing A2A Communication

### Backend Tests (No LLM)

```bash
pytest tests/ -m integration -s -v
```

### Full Simulation (With LLM)

```bash
python3 simulate_negotiation.py
```

## Schema-Aware Tools

The NPL tools are now generated with explicit typed parameters:

```python
# LLM sees this signature:
npl_commerce_Product_create(
    category: str,           # Required
    description: str,        # Required
    itemCondition: str,      # Required: NewCondition, UsedCondition, etc.
    name: str,               # Required
    seller_department: str,  # Required: e.g. "Sales"
    seller_organization: str,# Required: e.g. "Supplier Inc"
    sku: str,                # Required
    brand: str = None,       # Optional
    gtin: str = None         # Optional
) -> dict
```

This makes it much easier for LLMs to use the tools correctly.
