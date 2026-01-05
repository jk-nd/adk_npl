# Agent-to-Agent (A2A) Communication

This document explains how the Purchasing and Supplier agents communicate with each other.

## Communication Architecture

```
┌─────────────────────┐    A2A Messages    ┌─────────────────────┐
│  Purchasing Agent   │◄──────────────────►│   Supplier Agent    │
│  (Acme Corp)        │                    │   (Supplier Inc)    │
└──────────┬──────────┘                    └──────────┬──────────┘
           │                                          │
           │         NPL Protocol Actions             │
           └───────────────► NPL Engine ◄─────────────┘
                          (Shared State)
```

## How A2A Works

### Message Tools

Each agent has a tool to send messages to the other:

**Buyer Agent:**
```python
send_message_to_supplier(message: str) -> str
```

**Supplier Agent:**
```python
send_message_to_buyer(message: str) -> str
```

### Implementation

A2A uses HTTP POST requests between agents via the Chat API:

```python
# In chat_api/main.py
async def create_a2a_message_tool(sender_id: str, target_id: str, target_url: str):
    async def send_message(message: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{target_url}/a2a/{target_id}",
                json={"message": message, "from": sender_id}
            )
            return response.json()["response"]
    return FunctionTool(send_message)
```

### Turn-Based Communication

A2A is turn-based:
1. Agent A sends a message
2. Agent B processes and responds
3. Agent A receives the response
4. Continue...

## A2A vs NPL Protocol

| Concern | A2A Messages | NPL Protocols |
|---------|--------------|---------------|
| **Purpose** | Negotiation, coordination | Formal transactions |
| **State** | Ephemeral | Persistent, auditable |
| **Enforcement** | None | Business rules enforced |
| **Authorization** | Agent identity | Party claims verified |

**Best Practice**: Use A2A for discovery and negotiation, NPL for binding transactions.

## Typical Interaction Flow

```
Buyer                           Supplier
  │                                 │
  │  A2A: "I need 10 widgets"      │
  │────────────────────────────────>│
  │                                 │
  │  A2A: "I have widgets at $50"  │
  │<────────────────────────────────│
  │                                 │
  │  A2A: "Please make an offer"   │
  │────────────────────────────────>│
  │                                 │
  │          NPL: Product_create() │
  │<────────────────────────────────│
  │          NPL: Offer_create()   │
  │<────────────────────────────────│
  │          NPL: Offer_publish()  │
  │<────────────────────────────────│
  │                                 │
  │  NPL: Offer_accept()           │
  │────────────────────────────────>│
  │                                 │
  │  NPL: PurchaseOrder_create()   │
  │────────────────────────────────>│
  │                                 │
```

## Protocol Memory Integration

Agents use `recall_my_protocols()` to track NPL state across A2A turns:

```python
# Buyer checks what protocols exist
protocols = recall_my_protocols()
# Returns: [{"type": "Offer", "id": "abc-123", "state": "Published"}]

# Buyer can then reference the offer in A2A
send_message_to_supplier("I accept offer abc-123")

# And use NPL to formally accept
npl_commerce_Offer_accept(instance_id="abc-123")
```

## Partner Memory

Agents can remember each other's identity for NPL party binding:

```python
from adk_npl.partner_memory import PartnerMemory

# Store partner identity after A2A exchange
memory = PartnerMemory("buyer_agent")
memory.store_partner("supplier_agent", {
    "organization": "Supplier Inc",
    "department": "Sales"
})

# Recall when creating NPL protocols
partner = memory.get_partner("supplier_agent")
# Use partner claims in @parties binding
```

## Error Handling

A2A errors are logged and returned to the agent:

```python
try:
    response = await send_message_to_supplier("...")
except httpx.TimeoutException:
    return "Could not reach supplier agent (timeout)"
except httpx.ConnectError:
    return "Supplier agent is not available"
```

## Activity Logging

All A2A messages are logged for observability:

```python
activity_logger.log_a2a_message(
    from_agent="buyer_agent",
    to_agent="supplier_agent",
    message="I need to purchase widgets",
    direction="send"
)
```

View in the Activity Log tab of the dashboard.

## Testing A2A

### Via Chat UI

1. Open http://localhost:5173
2. In Buyer tab: "Contact the supplier about widgets"
3. Watch Activity Log for A2A messages
4. In Supplier tab: Check for received messages

### Programmatic Test

```python
# Start demo
python demo_inventory_chat.py

# Send message via API
curl -X POST http://localhost:8001/chat/buyer \
  -H "Content-Type: application/json" \
  -d '{"message": "Send a message to the supplier asking about products"}'
```

## Troubleshooting

### A2A Timeouts

- **Cause**: Target agent taking too long to respond
- **Solution**: Increase timeout (currently 60s) or simplify agent instructions

### Empty A2A Responses

- **Cause**: Target agent returned non-text response
- **Solution**: Check target agent's tool calls in Activity Log

### A2A Not Working

1. Check both agents are running (Chat API on 8001)
2. Check Activity API logs for errors
3. Verify agents have A2A tools loaded
