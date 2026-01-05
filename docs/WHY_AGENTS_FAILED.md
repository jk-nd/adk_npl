# Why AI Agents Failed: A Journey to NPL-Assisted Architecture

## Executive Summary

After extensive development and debugging of AI agents using Google's ADK (Agent Development Kit), we discovered a fundamental limitation: **LLM-based agents cannot reliably infer workflow state from conversation context alone**. This document chronicles our journey, the failure patterns we observed, what we tried, and the architectural solution we developed.

## The Vision

We set out to build autonomous AI agents that could:
- Negotiate B2B transactions via natural language (A2A communication)
- Execute business processes through NPL (Noumena Protocol Language) protocols
- Operate independently, pursuing goals set by their human managers

The architecture looked promising:

```
┌─────────────────┐         ┌─────────────────┐
│  Buyer Agent    │◄──A2A──►│ Supplier Agent  │
│  (Acme Corp)    │         │ (Supplier Inc)  │
└────────┬────────┘         └────────┬────────┘
         │                           │
         └───────────┬───────────────┘
                     ▼
            ┌────────────────┐
            │   NPL Engine   │
            │ (State Machine)│
            └────────────────┘
```

## The Failure Patterns

Despite hours of development and debugging, agents consistently exhibited these problematic behaviors:

### 1. Infinite Loops
Agents repeatedly created the same protocols, ignoring that they already existed.

```
Turn 1: Supplier creates Product → Success
Turn 2: Supplier creates Product → Success (duplicate!)
Turn 3: Supplier creates Product → Success (another duplicate!)
...
```

### 2. Amnesia
Every turn started as if the conversation was new:

```
Buyer: "Hello, I am from Acme Corp, Procurement department. I would like to buy..."
[10 turns later]
Buyer: "Hello, I am from Acme Corp, Procurement department. I would like to buy..."
```

### 3. State Confusion
Agents attempted actions invalid for the current protocol state:

```
Supplier tries to "publish" an already-published Offer
Buyer tries to "accept" an Offer that's still in "draft" state
```

### 4. Ping-Pong A2A
Endless back-and-forth without meaningful progress:

```
Buyer → Supplier: "What products do you have?"
Supplier → Buyer: "I have Premium Widget. What is your organization?"
Buyer → Supplier: "I am Acme Corp. What products do you have?"
Supplier → Buyer: "I have Premium Widget. What is your organization?"
...
```

### 5. Tool Spam
Agents made 50+ tool calls per turn without progress:

```
recall_my_protocols() → 0 results
get_my_identity() → "Acme Corp"
recall_my_protocols() → 0 results (again)
get_my_identity() → "Acme Corp" (again)
list_shopping_items() → "Premium Widget"
recall_my_protocols() → 0 results (yet again)
...
```

## What We Tried

### Attempt 1: Prompt Engineering
**Approach**: Detailed multi-step instructions telling agents exactly what to do.

```
MANDATORY START OF TURN SEQUENCE:
1. ALWAYS call recall_my_protocols() FIRST
2. ALWAYS call get_my_identity() SECOND
3. Check if protocol already exists before creating
...
```

**Why It Failed**: LLMs don't reliably follow complex procedural instructions. They optimize for "helpful response" not "follow procedure."

### Attempt 2: Tool Call Limits
**Approach**: Programmatically limit tool calls per turn using ADK's `before_tool_callback`.

```python
def before_tool_callback(tool, args, **kwargs):
    if counter["count"] > 15:
        return {"error": "STOP: Tool limit reached"}
    counter["count"] += 1
```

**Why It Failed**: Prevents runaway execution, but doesn't guide behavior. Agents still made the wrong 15 calls.

### Attempt 3: Protocol Memory
**Approach**: Give agents tools to remember and recall protocols they've created.

```python
remember_protocol(protocol_id, protocol_type, notes)
recall_my_protocols() → List of known protocols
```

**Why It Failed**: Agents had memory but didn't use it consistently. They'd check memory, find an existing protocol, and then... create a new one anyway.

### Attempt 4: ADK Callbacks
**Approach**: Use ADK's callback system for error handling and enforcement.

```python
on_tool_error_callback → Provide specific guidance on NPL errors
after_tool_callback → Log results and track state
```

**Why It Failed**: Good for enforcement and debugging, not for guidance. Agents still didn't know what to do next.

### Attempt 5: Simplified Instructions
**Approach**: Reduce instruction complexity to a simple loop.

```
1. Check memory
2. Take ONE action
3. Stop
```

**Why It Failed**: Even simple instructions require the LLM to correctly infer "what action should I take?" from conversation context.

## The Root Cause

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   FUNDAMENTAL PROBLEM: Agents infer workflow state from conversation        │
│                                                                             │
│   1. LLMs are stateless                                                     │
│      └─ Every turn starts fresh, no persistent memory                       │
│                                                                             │
│   2. Context gets noisy                                                     │
│      └─ Important state information buried in 20+ turns of chat            │
│                                                                             │
│   3. Two agents inferring independently                                     │
│      └─ Buyer thinks: "No offer yet" / Supplier thinks: "I made an offer"  │
│                                                                             │
│   4. No authoritative source of truth                                       │
│      └─ Each agent builds its own mental model = inevitable inconsistency  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

The critical insight: **NPL already has authoritative workflow state**. Every protocol has:
- `@state`: Current state (e.g., "published", "accepted")
- Valid transitions: Which actions are allowed from current state
- Party permissions: Who can execute which actions

But agents weren't querying this information. They were trying to infer it from conversation history.

## The Solution: NPL-Assisted Active Agents

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            NPL ENGINE                                        │
│                       (Source of Truth)                                      │
│                                                                              │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                       │
│   │   Product   │   │    Offer    │   │   Order     │                       │
│   │  @state:    │   │  @state:    │   │  @state:    │                       │
│   │  "active"   │   │  "published"│   │  "pending"  │                       │
│   └─────────────┘   └─────────────┘   └─────────────┘                       │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SMART BRIDGE                                      │   │
│   │   • next_actions(id) → "You can: accept, reject, counter"           │   │
│   │   • workflow_status() → "Stage: negotiation, waiting for: buyer"    │   │
│   │   • notifications → "State changed, here's what you can do now"     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
           ┌────────────────┐              ┌────────────────┐
           │  BUYER AGENT   │◄────A2A─────►│ SUPPLIER AGENT │
           │                │              │                │
           │  ACTIVE:       │              │  ACTIVE:       │
           │  • Pursue goal │              │  • Pursue goal │
           │  • Negotiate   │              │  • Negotiate   │
           │  • Decide      │              │  • Decide      │
           │                │              │                │
           │  NPL-ASSISTED: │              │  NPL-ASSISTED: │
           │  • Query state │              │  • Query state │
           │  • Valid actions│             │  • Valid actions│
           └────────────────┘              └────────────────┘
```

### Key Principles

1. **Agents are ACTIVE** - They pursue goals, make decisions, negotiate via A2A
2. **NPL provides AWARENESS** - "What state are we in? What can I do?"
3. **A2A enables CONVERGENCE** - Natural language negotiation is preserved
4. **NPL prevents MISTAKES** - Invalid actions blocked before execution

### The Agent Decision Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ORIENT → DECIDE → ACT → STOP                        │
│                                                                              │
│  1. ORIENT: Query NPL for current state and valid actions                   │
│     └─→ npl_*_next_actions() → "You can: accept, reject, counter"           │
│     └─→ This is AUTHORITATIVE, not inferred from chat                       │
│                                                                              │
│  2. DECIDE: Use judgment + A2A negotiation to choose action                 │
│     └─→ "Price is too high, I'll negotiate via A2A"                         │
│     └─→ Agent DECIDES, NPL just tells what's POSSIBLE                       │
│                                                                              │
│  3. ACT: Execute ONE action                                                 │
│     └─→ NPL validates and blocks if invalid                                 │
│     └─→ No more state confusion - NPL is the gatekeeper                     │
│                                                                              │
│  4. STOP: Let the other party respond                                       │
│     └─→ Turn-based prevents ping-pong                                       │
│     └─→ NPL notifications wake agent when it's their turn                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Takeaways

1. **LLMs are not reliable state machines**
   - Don't expect them to track multi-turn workflow state
   - Give them authoritative state from an external source

2. **Prompt engineering has limits**
   - Complex procedural instructions don't work reliably
   - Keep prompts simple: "Query state, decide, act, stop"

3. **External state machines are essential**
   - NPL (or similar) provides the "ground truth"
   - Agents query rather than infer

4. **A2A is for negotiation, not state management**
   - Use A2A for natural language convergence
   - Use NPL for state transitions and validation

5. **Notifications enable reactive behavior**
   - Don't poll - let NPL notify when state changes
   - "It's your turn" is more reliable than "figure out whose turn it is"

## Conclusion

AI agents are powerful for goal-oriented reasoning and natural language interaction. But they cannot reliably maintain workflow state across turns. The solution is to separate concerns:

- **Agent responsibility**: Goals, decisions, negotiation, judgment
- **NPL responsibility**: State, transitions, validation, notifications

This "NPL-Assisted Active Agent" architecture combines the best of both: active agents that pursue goals, backed by a reliable state machine that keeps them on track.

