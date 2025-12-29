# A2A Workflow Improvements - Implementation Status

## ✅ Phase 1: Remove Prescriptive Tool Calls (COMPLETE)

**Status**: Implemented in `demo_a2a_workflow.py`

**Changes**:
1. **Product creation**: Removed explicit "Use npl_commerce_Product_create" - now says "discover which ones help you create products"
2. **Offer creation**: Removed "Explore your available NPL tools to find the tools for creating and publishing offers" - now just says "Use your available tools"
3. **PurchaseOrder creation**: Removed "Check tool signatures for required parameters" - now says "Discover which tools help you create orders"
4. **Quote submission**: Removed "Use your NPL tools" - simplified to "Use your available tools"

**Impact**: Agents now discover tools autonomously instead of being told which ones to use.

---

## ✅ Phase 2: Clean A2A Messages (COMPLETE)

**Status**: Implemented in `demo_a2a_workflow.py`

**Changes**:
1. **A2A negotiation prompt**: Removed all identity reminders like "You are the BUYER", "You are NOT the supplier", "Remember: You are the BUYER"
2. **Accept prompt**: Drastically simplified from 15 lines of explicit instructions to 2 lines: "The negotiation is complete. Now finalize the deal by accepting offer {offer_id}."

**Impact**: A2A messages now only contain business-relevant information, not identity/system instructions.

---

## ✅ Phase 3: Unified A2A Negotiation Flow (COMPLETE)

**Status**: Implemented in `demo_a2a_workflow.py`

**Changes**:
1. **Merged Steps 3a and 3b**: Previously separate "negotiate" and "accept" steps are now a single unified step
2. **New prompt**: "Negotiate and finalize purchase... If terms are acceptable, accept the offer immediately"
3. **Agent decides when to accept**: The agent now autonomously decides to accept based on negotiation outcome

**Impact**: Reduced from 2 orchestrated steps to 1 autonomous objective. Agent makes the accept decision.

---

## ⏳ Phase 4: High-Level Objectives (IN PROGRESS)

**Status**: Partially implemented

**Current State**:
- Still has 8 separate steps (Product, Offer, Negotiation, PurchaseOrder, Quote, Approval, Place, Ship)
- Steps 1 & 2 could be combined: "Create and publish saleable offer" (let agent create product if needed)
- Steps 3 & 4 could be combined: "Negotiate and purchase" (already includes accept, should include PO creation)

**Proposed Structure**:
```
OBJECTIVE 1: Supplier - Create and publish offer
  └─ Creates product + offer + publishes (currently Steps 1 & 2)

OBJECTIVE 2: Buyer - Negotiate and complete purchase  
  └─ Negotiates + accepts + creates PO (currently Steps 3 & 4)

OBJECTIVE 3: Supplier - Submit quote
  └─ Reviews PO and submits quote (currently Step 5)

STEP 4: Human Approval
  └─ Wait for human to approve (unchanged)

OBJECTIVE 4: Complete transaction
  └─ Buyer places order + Supplier ships (currently Steps 7 & 8, run in parallel)
```

**Impact**: Would reduce from 8 steps to 4 objectives + 1 human step.

---

## ⏸️ Phase 5: Fix NPL Permissions (NOT STARTED)

**Status**: Not implemented (requires NPL protocol changes)

**Problem**: Supplier cannot access PurchaseOrder created in buyer's realm (404 error)

**Current Error**:
```
NPL Engine API error (404): {'errorType': 'noSuchItem', 
'message': "No such StateId 'be417fba-fd6a-4606-a62f-e3343b3605e2'"}
```

**Root Cause**: PurchaseOrder protocol only has buyer and approver as parties, not seller:
```npl
protocol[buyer, approver] PurchaseOrder(...)  // Missing seller!
```

**Solutions** (requires NPL changes):

### Option A: Add Seller as Party (Recommended)
```npl
@api
protocol[buyer, seller, approver] PurchaseOrder(...) {
    // Now seller can access the order
}
```

### Option B: Explicit Access Grant
```npl
@api
permission[buyer] shareWithSeller() | Requested {
    // Grant seller read/write access to this instance
}
```

### Option C: Shared Protocol Registry
- Deploy protocols to a shared realm accessible by both parties
- Requires infrastructure changes

**Recommendation**: Option A is cleanest for A2A patterns. This needs to be done in the NPL protocol definition.

---

## ⏸️ Phase 6: Smarter Retry Logic (NOT STARTED)

**Status**: Not implemented

**Current Behavior**:
```python
max_iterations=20,  # Too many
poll_interval=3.0,  # Too frequent
```

**Proposed Improvements**:
```python
async def run_autonomous_agent_smart(
    runner,
    objective,
    check_condition,
    max_iterations=10,  # Reduced from 20
    poll_interval=5.0,  # Increased from 3
    give_up_timeout=60  # New: give up after 1 minute
):
    """
    Smarter autonomous agent that:
    - Attempts action immediately
    - If rejected due to state, backs off with exponential delay
    - Gives up if state hasn't changed after timeout
    - Logs why it's giving up (for debugging)
    """
    last_state = None
    consecutive_same_state = 0
    
    for iteration in range(max_iterations):
        # Try the action
        result = await run_agent_turn(...)
        
        # Check condition
        if await check_condition():
            return True
        
        # Get current state
        current_state = await get_state(...)
        
        # If state hasn't changed in 3 checks, give up
        if current_state == last_state:
            consecutive_same_state += 1
            if consecutive_same_state >= 3:
                print(f"State stuck at {current_state}, giving up")
                return False
        else:
            consecutive_same_state = 0
        
        last_state = current_state
        
        # Exponential backoff
        wait_time = min(poll_interval * (1.5 ** iteration), 30)
        await asyncio.sleep(wait_time)
    
    return False
```

**Impact**: 
- Fewer wasted LLM calls (10 vs 20)
- More intelligent retry behavior
- Faster failure detection
- Better logging for debugging

---

## Summary

### Completed (Phases 1-3):
- ✅ Agents discover tools instead of being told which to use
- ✅ A2A messages are clean (no identity pollution)  
- ✅ Negotiation and accept are unified (agent decides)

### Remaining (Phases 4-6):
- ⏳ Phase 4: Combine steps into high-level objectives (partially done)
- ⏸️ Phase 5: Fix NPL permissions for cross-realm access (requires NPL changes)
- ⏸️ Phase 6: Implement smarter retry logic with exponential backoff

### Current Issues:
1. **Still 8 steps instead of 4 objectives** - Need to complete Phase 4
2. **Supplier can't access PurchaseOrder** - Need Phase 5 (NPL protocol change)
3. **Too many retry iterations** - Need Phase 6

### Next Steps:
1. Complete Phase 4 by combining:
   - Steps 1 & 2 → Single "create and publish offer" objective
   - Steps 3 & 4 → Single "negotiate and purchase" objective  
2. Test the improved workflow
3. Address Phase 5 (NPL protocol changes) if needed
4. Implement Phase 6 (smarter retries) for performance

