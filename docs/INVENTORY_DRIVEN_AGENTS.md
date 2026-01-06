# Inventory-Driven Agent Behavior

## The Problem

Agents were creating excessive offers (72 created, only 4 accepted = 5.6% success rate) and repeatedly purchasing the same items without checking their shopping list or inventory.

### Root Cause Analysis

**Agents had tools but weren't using them:**

- **Shopping list checks: 0** ❌ (Buyer should check what they need)
- **Inventory checks: 0** ❌ (Supplier should check what they have)
- **Result**: Duplicate purchases, wasted effort, and poor workflow efficiency

### Why This Happened

The agent instructions prioritized NPL protocol memory over local state:

**Old Workflow (incorrect priority):**
```
1. recall_my_protocols() → Check what already exists (ALWAYS DO THIS FIRST!)
2. If protocol exists → use it
3. If nothing exists → proceed with your task
```

**Missing Critical Step**: Check shopping list/inventory to know **what** to buy/sell!

The agents were following instructions correctly - they checked NPL state first - but they were blind to their actual business needs (shopping list) and capabilities (inventory).

## The Solution

### 1. Smart Priority: Protocol Memory → Business State

**The Critical Insight:**

Shopping lists and inventory are **slow-updating** (only change when orders ship). If agents check them every turn, they'll create hundreds of duplicate orders because the list still shows "need 100 widgets" even though 5 orders are already in progress.

**New Workflow (correct priority):**

**For Buyer Agent:**
```
1. recall_my_protocols() → Check active workflows (ALWAYS FIRST!)
2. If protocols exist → progress them, DON'T create new ones
3. If nothing in progress → list_shopping_items() → check what you need
4. Calculate: needed_quantity - in_progress_quantity = remaining_to_order
5. Only start new workflows if remaining_to_order > 0
```

**For Supplier Agent:**
```
1. recall_my_protocols() → Check active workflows (ALWAYS FIRST!)
2. If protocols exist → progress them, DON'T create new ones
3. If nothing active → list_products() → check what you can sell
4. Don't create duplicate workflows for items already being processed
5. Wait for active workflows to complete before starting new ones
```

**Note**: Instructions are kept generic - they reference "workflows" and "protocols" without naming specific NPL protocol types (e.g., PurchaseOrder, Offer). This ensures the agent logic remains decoupled from the NPL schema.

### 2. Emphasized Protocol Memory to Prevent Duplicates

**Updated buyer instructions:**
```
⚠️ CRITICAL - Avoid Duplicate Orders:
1. Check shopping list ONLY when starting a new procurement cycle
2. Check recall_my_protocols() to see in-progress PurchaseOrders and Offers
3. Calculate: needed_quantity - (in_progress_quantity) = remaining_to_order
4. Only create new orders if remaining_to_order > 0
5. Wait for existing orders to complete (ship/fail) before checking shopping list again
```

**Updated supplier instructions:**
```
⚠️ CRITICAL - Avoid Duplicate Offers:
1. Check inventory ONLY when starting a new sales cycle
2. Check recall_my_protocols() to see active Products and Offers
3. Don't create duplicate Products or Offers for items already being sold
4. Wait for existing offers to be accepted/rejected before creating new ones
5. Focus on progressing existing protocols through their lifecycle
```

## Architecture Insight

This fix highlights a fundamental principle for enterprise AI agents:

### Agent Decision Hierarchy

**1. Workflow State (NPL protocols) - Check FIRST**
   - Ongoing transactions, protocol status
   - Represents "what's currently in flight"
   - **Updated in real-time via notifications**
   - If protocols exist → work on them, don't create duplicates

**2. Local Business State (ERP-like data) - Check ONLY if no active protocols**
   - Shopping lists, inventory, budgets
   - Represents "total business needs/capacity"
   - **Updated slowly (only when orders ship)**
   - Use to identify NEW work when nothing is in progress

**3. External Negotiation (A2A) - Use to progress protocols**
   - Partner communication, price negotiation
   - Represents "how to execute"
   - Used to complete identified tasks from steps 1 & 2

### Why This Order Matters

**Wrong Order** (shopping list every turn):
```
Turn 1: Check shopping list → need 100 widgets → start workflow
Turn 2: Check shopping list → still shows 100 widgets (not shipped yet) → start ANOTHER workflow
Turn 3: Check shopping list → still shows 100 widgets → start ANOTHER workflow
...
Result: 100s of duplicate workflows because shopping list updates slowly
```

**Correct Order** (protocol memory first):
```
Turn 1: Check protocols → nothing in progress → check shopping list → need 100 widgets → start workflow
Turn 2: Check protocols → workflow in progress → progress it, DON'T check shopping list
Turn 3: Check protocols → workflow still in progress → continue progressing
Turn N: Check protocols → workflow completed → check shopping list → fulfilled! → done
Result: Efficient, no duplicates, goal-oriented behavior
```

**Key Insight**: Protocol memory updates in real-time (via NPL notifications), but shopping lists/inventory update slowly (only when orders ship). Always trust the real-time source first.

## ERP Sync Service

The ERP Sync Service ensures shopping lists and inventory stay in sync with completed transactions:

**Trigger**: NPL notifications (e.g., `OrderShippedNotification`)

**Actions**:
- **Buyer**: Reduces `desired_quantity` on shopping list (removes item if <= 0)
- **Supplier**: Reduces `quantity_available` in inventory

**Files**:
- `adk_npl/erp_sync.py` - Main sync service
- `adk_npl/inventory_tools.py` - Shopping list and inventory management
- `data/buyer_shopping_list.json` - Buyer's needs
- `data/supplier_inventory.json` - Supplier's products

## Expected Behavior After Fix

**Before Fix:**
- 72 offers created, 4 accepted (5.6%)
- 0 shopping list checks
- 0 inventory checks
- Duplicate purchases

**After Fix:**
- Agents check shopping list/inventory at start of each turn
- Only create offers for items actually needed
- Stop working when shopping list is empty
- Much higher success rate (fewer wasted offers)

## Testing

To verify the fix works:

1. Start demo with clean database:
   ```bash
   ./start_demo.sh --clean
   ```

2. Monitor activity log for:
   - `list_shopping_items` tool calls (buyer)
   - `list_products` tool calls (supplier)
   - Reduced number of offers created
   - Higher offer acceptance rate

3. Check data files after workflow completion:
   ```bash
   cat data/buyer_shopping_list.json  # Should be empty or reduced
   cat data/supplier_inventory.json   # quantity_available should decrease
   ```

## Related Files

- `purchasing_agent/agent.py` - Buyer agent with shopping list priority
- `supplier_agent/agent.py` - Supplier agent with inventory priority
- `adk_npl/erp_sync.py` - ERP sync service
- `adk_npl/inventory_tools.py` - Shopping list and inventory tools
- `docs/SESSION_MANAGEMENT.md` - Session cleanup (ensures fresh tests)

