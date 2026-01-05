# Why ADK-NPL? A Motivation

## The Problem

LLM agents are great at conversation, but struggle with **formal business processes**:

- **No persistent state** — Chat context disappears between sessions
- **No authorization** — Anyone can ask an agent to do anything  
- **No audit trail** — "The agent approved it" isn't good enough for compliance
- **No multi-party coordination** — How do two agents from different companies transact?
- **No business rules** — LLMs don't know your contracts or policies

Building these features from scratch for every agent is expensive and error-prone.

## The Solution

**NPL (Noumena Protocol Language)** provides formal, stateful protocols with built-in authorization. **ADK-NPL** bridges Google's Agent Development Kit with NPL, giving agents access to enterprise-grade workflows.

```
┌─────────────────────────────────────────────────────┐
│                   LLM Agent (ADK)                   │
│  "Natural language understanding + reasoning"       │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│               Smart NPL Bridge                      │
│  "Schema-aware tools + embedded business rules"     │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│               NPL Protocol Engine                   │
│  "State machines + Authorization + Audit trails"   │
└─────────────────────────────────────────────────────┘
```

## What NPL Adds

| Capability | Without NPL | With NPL |
|------------|-------------|----------|
| **State** | Lost between sessions | Persistent protocol instances |
| **Authorization** | Trust the prompt | JWT claims verified per action |
| **Audit** | Log files | Immutable state transitions |
| **Multi-party** | Custom integration | Federated identity + shared state |
| **Workflow** | Ad-hoc | Formal state machines |
| **Business Rules** | In prompts (ignored) | Enforced by engine |

## When to Use ADK-NPL

### ✅ Good Fit

- **B2B transactions** — Buyer/seller negotiations, purchase orders, contracts
- **Regulated industries** — Finance, healthcare, insurance, government
- **Multi-organization agents** — Each party uses their own identity provider
- **Long-running processes** — Workflows that span days or weeks
- **Audit requirements** — Compliance needs provable records

### ❌ Not the Right Fit

- Simple Q&A chatbots
- Single-user applications
- Real-time streaming use cases
- Unstructured, ad-hoc conversations

## Key Innovation: Smart NPL Bridge

The bridge doesn't just connect ADK to NPL — it makes NPL contracts **LLM-understandable**.

### 1. Schema-Aware Tool Generation

Traditional approach (LLM struggles):
```python
def create_order(data: dict) -> dict:
    """Create an order. Good luck figuring out the fields."""
```

ADK-NPL approach (LLM succeeds):
```python
def create_order(
    order_number: str,      # Required
    quantity: float,        # Required  
    price: float,           # Required
    payment_method: str,    # One of: CreditCard, BankTransfer, Invoice
    delivery_date: str = None  # Optional, ISO format
) -> dict:
    """Create a purchase order with the specified terms."""
```

### 2. Embedded Business Rules

The bridge parses NPL source code and embeds rules in tool docstrings:

```
### Business Rules (Policy)
- require(price > 0, "Price must be positive")
- require(quantity <= inventory, "Insufficient stock")

### State Flow
Draft → Published → Accepted

### Party Actions
- seller: publish, withdraw
- buyer: accept, reject
```

Agents "read" the contract before calling tools.

### 3. Standards Alignment

Maps NPL types to industry standards (Schema.org, ISO 20022, GS1) for better LLM comprehension.

## Example: Cross-Company Commerce

```
┌──────────────────┐                    ┌──────────────────┐
│  Buyer Agent     │                    │  Seller Agent    │
│  (Acme Corp)     │                    │  (Supplier Inc)  │
│  Keycloak: buyer │                    │  Keycloak: seller│
└────────┬─────────┘                    └────────┬─────────┘
         │                                       │
         │  1. A2A: Request quote                │
         │──────────────────────────────────────>│
         │                                       │
         │           2. NPL: Create Offer        │
         │<──────────────────────────────────────│
         │                                       │
         │  3. NPL: Accept Offer                 │
         │──────────────────────────────────────>│
         │                                       │
         │  4. NPL: Create PurchaseOrder         │
         │──────────────────────────────────────>│
         │                                       │
         │     [Human approval if high-value]    │
         │                                       │
         │           5. NPL: Ship Order          │
         │<──────────────────────────────────────│
         │                                       │
         └───────────────┬───────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │    NPL Engine       │
              │  - Shared state     │
              │  - Audit trail      │
              │  - Both parties     │
              │    authenticated    │
              └─────────────────────┘
```

Each agent authenticates with their own organization's identity provider. The NPL Engine trusts both issuers and maintains the shared protocol state.

## Getting Started

```bash
# Clone and setup
git clone https://github.com/your-org/adk-demo.git
cd adk-demo
cp .env.example .env  # Add your Google API key

# Start infrastructure
./scripts/setup-fresh.sh

# Run the demo
python demo_inventory_chat.py
```

## Learn More

- **[Why Agents Failed](WHY_AGENTS_FAILED.md)** — The journey from failing agents to NPL-assisted architecture
- [Agent Architecture](AGENTS.md) — How agents are structured
- [A2A Communication](A2A_COMMUNICATION.md) — Agent-to-agent patterns
- [Monitoring](MONITORING.md) — Observability and metrics
- [NPL Documentation](https://documentation.noumenadigital.com/) — Protocol language reference

---

**ADK-NPL: Enterprise-grade stateful workflows for LLM agents.**
