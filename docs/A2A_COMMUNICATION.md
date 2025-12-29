# Agent-to-Agent (A2A) Communication

This document explains how the Purchasing and Supplier agents interact.

## Communication Methods

### 1. True HTTP-Based A2A (Google ADK A2A Protocol)

**Script**: `demo_a2a_workflow.py`

Uses Google ADK's A2A HTTP protocol for real agent-to-agent communication:

```
┌─────────────────┐    A2A HTTP     ┌─────────────────┐
│  Buyer Agent    │◄───────────────►│ Supplier Agent  │
│  (Port 8010)    │                 │  (Port 8011)    │
└────────┬────────┘                 └────────┬────────┘
         │                                   │
         └───────────► NPL Engine ◄──────────┘
```

**Key Components**:
- `A2aAgentExecutor` - Exposes an ADK agent as an A2A server
- `RemoteA2aAgent` - Allows calling another agent via A2A
- `AgentCard` - Agent metadata for discovery

**Usage**:
```bash
python demo_a2a_workflow.py
```

**Features**:
- Buyer and Supplier run as **separate HTTP servers**
- Communication via **A2A protocol** (transfer_to_agent tool)
- NPL governance within A2A context
- Full message exchange visible in logs
- Human-in-the-loop approval for high-value orders

### 2. Orchestrated Simulation

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

## Protocol Memory System

Agents can track and recall NPL protocol instances across conversation turns using the **Protocol Memory** system:

```python
from adk_npl import NPLProtocolMemory, create_memory_tools

# Get memory for an agent
memory = NPLProtocolMemory.get_instance("buyer_agent")

# Create memory tools for the agent
memory_tools = create_memory_tools("buyer_agent")
# Returns 4 tools: recall_my_protocols, get_protocol_id, 
#                  get_workflow_context, remember_protocol
```

**Memory Tools**:

| Tool | Purpose |
|------|---------|
| `recall_my_protocols` | List all tracked protocols (optionally filtered) |
| `get_protocol_id` | Get the most recent ID for a protocol type |
| `get_workflow_context` | Get a summary of the current workflow state |
| `remember_protocol` | Manually track a protocol from external source |

**Example Usage in A2A**:

```
Buyer: remember_protocol("Offer", "abc-123", "published", "buyer")
Buyer: transfer_to_agent → SupplierAgent (negotiate)
Buyer: get_protocol_id("Offer")  → "abc-123"
Buyer: npl_commerce_Offer_accept(instance_id="abc-123")
```

**Benefits**:
- Prevents ID confusion during multi-turn conversations
- Works across A2A transfers
- Enables agents to maintain workflow context
- Automatic tracking on protocol creation/actions
