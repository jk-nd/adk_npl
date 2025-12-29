# A2A Workflow Analysis and Improvement Plan

## Current Issues

### 1. **Too Prescriptive / Not Autonomous Enough**

**Problem**: The workflow script tells agents exactly what to do, including:
- Which tools to call (`npl_commerce_Product_create`, `npl_commerce_Offer_publish`)
- Exact parameters to use (order number, quantity, price)
- Step-by-step instructions for each action

**Examples**:
```python
# STEP 1: Too prescriptive
product_prompt = f"""
Create a Product with these exact details:
- Name: Industrial Pump X
- SKU: SKU-PUMP-001
- Price: 1200
- Currency: USD
Use the npl_commerce_Product_create tool.
"""
```

**Impact**: Agents don't learn to discover tools or make decisions - they just follow instructions.

---

### 2. **Identity Confusion in A2A**

**Problem**: A2A messages contain identity reminders that get sent to the other agent:

```python
a2a_prompt = f"""
You are the BUYER (Purchasing Agent for Acme Corp). You are NOT the supplier.  # ← This gets sent!

Contact the SupplierAgent via A2A to negotiate...
"""
```

**Impact**: The supplier receives "You are the BUYER" in the request, causing confusion.

---

### 3. **Broken A2A Flow**

**Problem**: The workflow separates A2A negotiation from the accept action:

```python
# Step 3a: A2A negotiation (buyer contacts supplier)
await run_agent_turn(buyer_runner, a2a_prompt, ...)

# Step 3b: Separate accept step (NO A2A)
accept_prompt = "STOP A2A COMMUNICATION NOW. Accept offer..."
await run_agent_turn(buyer_runner, accept_prompt, ...)
```

**Impact**: The accept action should be part of the negotiation, not a separate orchestrated step.

---

### 4. **Too Many Orchestrated Steps**

**Problem**: Each protocol creation is a separate, explicit step:
- Step 1: Supplier creates Product (scripted)
- Step 2: Supplier creates and publishes Offer (scripted)
- Step 3: A2A Negotiation (limited)
- Step 3b: Accept Offer (scripted)
- Step 4: Buyer creates PurchaseOrder (scripted)
- Step 5: Supplier submits quote (scripted)
- Step 6: Human approval (waiting)
- Step 7: Place order (autonomous but constrained)
- Step 8: Ship order (autonomous but constrained)

**Impact**: 8+ iterations just to complete a basic purchase workflow.

---

### 5. **PurchaseOrder Access Problem**

**Problem**: The supplier agent cannot access the PurchaseOrder because:
```python
# Buyer creates PO in their realm
po_id = buyer_agent.create_purchase_order(...)

# Supplier tries to access it
supplier_agent.submit_quote(instance_id=po_id, ...)  # ← 404 Not Found
```

**Impact**: NPL permissions prevent cross-realm access, breaking the workflow.

---

## Root Causes

1. **Workflow is an Orchestrator, not a Facilitator**: The script acts as a puppeteer, telling each agent what to do at each step.

2. **A2A is Underutilized**: True A2A should allow agents to negotiate the entire transaction, not just price.

3. **Agents Lack Context Awareness**: Agents aren't given enough information to understand the full transaction lifecycle.

4. **Tool Discovery is Disabled**: Agents are told which tools to call instead of discovering them.

5. **NPL Permissions Aren't Designed for A2A**: The protocols don't support cross-realm access patterns needed for A2A.

---

## Proposed Improvements

### Phase 1: Remove Prescriptive Instructions (Quick Win)

**Before**:
```python
product_prompt = f"""
Create a Product with these exact details:
- Name: Industrial Pump X
- SKU: SKU-PUMP-001
Use the npl_commerce_Product_create tool.
"""
```

**After**:
```python
product_prompt = f"""
You need to list a new product for sale: Industrial Pump X, priced at $1200/unit.

Create and publish the product using your available NPL tools. Check tool signatures
to understand what parameters are needed.
"""
```

**Impact**: Agents discover tools and parameters autonomously.

---

### Phase 2: Fix A2A Message Content

**Before**:
```python
a2a_prompt = f"""
You are the BUYER (Purchasing Agent for Acme Corp). You are NOT the supplier.

Contact the SupplierAgent via A2A to negotiate offer {offer_id}...

Remember: You are the BUYER. The SupplierAgent is the other party.
"""
```

**After**:
```python
# Identity reminders stay in base instructions, NOT in A2A message
a2a_prompt = f"""
Negotiate terms for Industrial Pump X (Offer ID: {offer_id}).

Your goals:
- Confirm availability for 10 units
- Negotiate best price (target: 10% discount from $1200/unit)
- Finalize terms and accept if within budget

Expected outcome: Accepted offer with agreed terms.
"""
```

**Impact**: Clean A2A messages, no identity pollution.

---

### Phase 3: Unified A2A Negotiation Flow

**Before**: Separate negotiation and accept steps.

**After**: Single A2A session that handles full negotiation including accept:

```python
a2a_prompt = f"""
Negotiate and finalize purchase of Industrial Pump X (Offer {offer_id}).

Flow:
1. Contact supplier to confirm availability and explore discounts
2. Negotiate terms (max 3 rounds)
3. If acceptable, accept the offer immediately
4. Report final outcome

Budget: Up to $1200/unit × 10 units = $12,000
Target: Negotiate down to $1140/unit or better
"""
```

**Agent decides when to accept** based on negotiation outcome.

---

### Phase 4: High-Level Workflow Objectives

**Before**: 8 separate scripted steps.

**After**: 3 high-level objectives with agents figuring out the steps:

```python
# OBJECTIVE 1: Supplier - Create and publish offer
supplier_objective_1 = """
You need to create a saleable offer for Industrial Pump X.

Requirements:
- Product: Industrial Pump X, high-quality industrial pump
- Price: $1200/unit
- Availability: In stock, can ship within 5 business days

Steps (figure out the details):
1. Create a Product protocol instance if needed
2. Create an Offer for that product
3. Publish the offer so buyers can see it

Report the Offer ID when published.
"""

# OBJECTIVE 2: Buyer - Negotiate and purchase
buyer_objective_2 = """
Negotiate and purchase Industrial Pump X from the supplier.

Requirements:
- Quantity: 10 units
- Budget: $12,000 (max $1200/unit)
- Target: Get 10% discount

Steps (figure out the details):
1. Find the supplier's published offer
2. Negotiate terms via A2A (max 3 rounds)
3. Accept the offer if terms are acceptable
4. Create a PurchaseOrder for the accepted offer

Report when the order is ready for approval.
"""

# OBJECTIVE 3: Complete transaction
# (Both agents work autonomously after human approval)
```

**Impact**: Agents plan and execute multi-step workflows autonomously.

---

### Phase 5: Fix NPL Permissions for A2A

**Problem**: PurchaseOrder is created in buyer's realm, supplier can't access it.

**Solutions**:

**Option A: Shared Protocol Instances**
```npl
// In PurchaseOrder protocol
@api
protocol[buyer, seller, approver] PurchaseOrder(...) {
    // Both buyer and seller are parties
}
```

**Option B: Explicit Grant Access Action**
```npl
@api
permission[buyer] sharewithSeller() | Requested {
    // Grant seller read/write access
}
```

**Option C: Public Order ID Exchange**
```python
# Buyer creates PO, shares ID with supplier via A2A
buyer_message = {
    "type": "order_placed",
    "order_id": po_id,
    "access_granted": True
}
```

**Recommendation**: Option A (both parties in protocol) is cleanest for A2A.

---

### Phase 6: Reduce Iterations with Smarter Agents

**Before**: 20 iterations with 3-second polling for state changes.

**After**: Event-driven or intelligent polling:

```python
async def run_autonomous_agent_smart(
    runner,
    objective,
    check_condition,
    max_iterations=10,  # Reduced from 20
    poll_interval=5.0,  # Longer pause between attempts
    give_up_after=60  # Give up after 1 minute
):
    """
    Smarter autonomous agent that:
    - Attempts action immediately
    - If rejected due to state, polls less frequently
    - Gives up if state hasn't changed after timeout
    """
    ...
```

**Impact**: Fewer wasted LLM calls, faster convergence.

---

## Implementation Priority

### High Priority (Do First)
1. ✅ **Remove prescriptive tool calls** from all prompts (Phase 1)
2. ✅ **Clean A2A messages** - remove identity reminders (Phase 2)
3. ✅ **Unified negotiation flow** - accept within A2A (Phase 3)

### Medium Priority (Do Next)
4. **High-level objectives** instead of step-by-step (Phase 4)
5. **Fix NPL permissions** for cross-realm access (Phase 5)

### Low Priority (Nice to Have)
6. **Smarter autonomous agents** with intelligent retry (Phase 6)

---

## Success Criteria

After improvements, the workflow should:

1. **Converge in 3-5 agent turns** instead of 8+
2. **No identity confusion** - agents maintain clear roles
3. **True A2A negotiation** - agents handle full transaction flow
4. **Minimal orchestration** - script provides objectives, not steps
5. **Agents discover tools** - no explicit tool names in prompts
6. **Clean separation** - A2A messages contain only what trading partners would exchange

---

## Example: Improved Workflow

```python
async def run_improved_a2a_workflow():
    """Improved A2A workflow with autonomous agents."""
    
    # SETUP: Create agents (no change)
    supplier_agent = await create_supplier_agent(...)
    buyer_agent = await create_purchasing_agent(...)
    
    # OBJECTIVE 1: Supplier creates and publishes offer
    supplier_result = await run_agent_turn(
        supplier_runner,
        objective="""
        Create and publish an offer for Industrial Pump X:
        - Price: $1200/unit
        - Availability: In stock
        
        Report the Offer ID when published.
        """,
        expected_outcome="Published offer with ID"
    )
    offer_id = extract_id(supplier_result)
    
    # OBJECTIVE 2: Buyer negotiates and purchases
    buyer_result = await run_agent_turn(
        buyer_runner,
        objective=f"""
        Purchase Industrial Pump X from supplier:
        - Find their published offer (ID: {offer_id})
        - Negotiate via A2A (target: 10% discount)
        - Accept if within budget ($1200/unit max)
        - Create PurchaseOrder when accepted
        
        Report when order is ready for approval.
        """,
        expected_outcome="PurchaseOrder ready for approval"
    )
    po_id = extract_id(buyer_result)
    
    # OBJECTIVE 3: Supplier submits quote
    await run_agent_turn(
        supplier_runner,
        objective=f"""
        Review and respond to PurchaseOrder {po_id}:
        - Check order details
        - Submit your quote
        
        Report when quote is submitted.
        """,
        expected_outcome="Quote submitted, awaiting approval"
    )
    
    # HUMAN APPROVAL (unchanged)
    await wait_for_approval(po_id)
    
    # OBJECTIVE 4: Complete transaction (both agents autonomous)
    buyer_task = asyncio.create_task(run_autonomous_agent(
        buyer_runner,
        objective=f"Place order {po_id} when approved"
    ))
    supplier_task = asyncio.create_task(run_autonomous_agent(
        supplier_runner,
        objective=f"Ship order {po_id} when placed"
    ))
    
    await asyncio.gather(buyer_task, supplier_task)
```

**Result**: 4 agent turns instead of 8+, true autonomy, clean A2A.

