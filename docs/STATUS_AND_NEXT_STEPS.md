# Status and Next Steps - January 6, 2026

## ✅ **What We've Accomplished**

### 1. Database Reset Fix
- ✅ Fixed anonymous Docker volume issue
- ✅ Added named volume `engine-db` to docker-compose.yml
- ✅ `--clean` flag now properly resets NPL database
- ✅ Documentation: `docs/DATABASE_RESET_FIX.md`

### 2. Metrics UI Fix  
- ✅ Fixed A2A messages counting (was showing 0, now shows actual count)
- ✅ Fixed notifications counting (was showing 0, now shows actual count)
- ✅ Added `tool_calls` metric tracking
- ✅ Documentation: `docs/METRICS_UI_FIX.md`

### 3. NPL Protocol Improvements
- ✅ Redesigned PurchaseOrder to auto-derive price/quantity from Offer
- ✅ Added `@api permission` getters for UI access
- ✅ Removed redundant `submitQuote` permission
- ✅ Cleaner protocol design with single source of truth

### 4. Agent Instructions Upgrade
- ✅ Updated to protocol-memory-first workflow
- ✅ Made instructions generic (no hardcoded protocol names)
- ✅ Added shopping list integration points
- ✅ Added inventory integration points
- ✅ Documentation: `docs/INVENTORY_DRIVEN_AGENTS.md`

### 5. Infrastructure & Documentation
- ✅ Session management documentation
- ✅ Successful run analysis
- ✅ All changes committed to git

## ⚠️ **Current Issue: Tools Not Being Used**

### Observation
After restart with latest code:
- Agents ARE making NPL API calls (43+ calls)
- Agents ARE negotiating via A2A (9 messages)
- But: **ZERO calls to meta-tools**:
  - `recall_my_protocols()`: 0 calls
  - `list_shopping_items()`: 0 calls
  - `list_products()`: 0 calls

### Why This Matters
Without these tools:
- Agents create duplicate protocols (can't check what exists)
- Agents don't prioritize needed items (can't check shopping list)
- Agents may offer out-of-stock items (can't check inventory)

### Possible Root Causes

#### 1. **Tool Discovery Issue**
The LLM may not be discovering these tools in its tool list.

**Check**: Are tools in the agent's tool registry?
```python
# In agent startup logs, we see:
"Generated 44 tools per agent"
"Added shopping list tools"  
"Added inventory tools"
```
→ Tools ARE being added ✅

#### 2. **Instructions Not in System Prompt**
The instructions may not be reaching the LLM's system prompt.

**Check**: Verify `custom_instructions` parameter is passed to agent creation.
```python
# In purchasing_agent/agent.py line 126:
custom_instructions=custom_instructions
```
→ Instructions ARE being passed ✅

#### 3. **Instructions Not Compelling Enough**
The LLM may not understand WHEN to use these tools.

**Current instruction** (purchasing_agent/agent.py):
```
1. **recall_my_protocols()** → Check what's in progress (ALWAYS FIRST!)
2. If protocols exist → work on those, DON'T create new ones
3. If nothing in progress → **list_shopping_items()** → check what you need
```

**Possible issue**: Instructions say "ALWAYS FIRST" but LLM may not interpret this as a mandatory first action.

#### 4. **Tool Call Logging Issue**
Tool calls ARE happening but not being logged.

**Check**: Are we logging tool calls in the ADK callbacks?
```python
# We have before_tool_callback and after_tool_callback
# But are they capturing ALL tool types?
```

#### 5. **Agent Behavior Override**
The NPL-generated tools may be overriding the guidance.

**Hypothesis**: ADK may prioritize tools that match the objective ("buying") over meta-tools like recall.

## 🔍 **Next Steps to Debug**

### Step 1: Verify Tool Availability
Check if tools are actually available to the LLM:

```python
# Add to agent startup:
logger.info(f"Available tools: {[t.name for t in agent.tools]}")
```

### Step 2: Check System Prompt
Verify instructions are in the actual prompt sent to LLM:

```python
# In before_tool_callback or similar:
logger.debug(f"System prompt: {agent.system_instruction}")
```

### Step 3: Make Instructions More Explicit
Change from guidance to requirement:

```python
"""
🚨 CRITICAL FIRST STEP - REQUIRED ON EVERY TURN:
You MUST call recall_my_protocols() before ANY other action.

DO NOT create Product, Offer, or PurchaseOrder until you've called:
1. recall_my_protocols() 
2. Checked the results to see if that protocol already exists

If you skip this step, you will create duplicates and waste resources.
"""
```

### Step 4: Add Tool Call Tracing
Enhance logging to see what the LLM is considering:

```python
# In before_tool_callback:
logger.info(f"LLM chose tool: {tool_name} (from {len(available_tools)} options)")
```

### Step 5: Test with Simpler Agent
Create a minimal test agent that ONLY has recall_my_protocols() to verify:
- Tool registration works
- Tool is callable
- Tool results are returned correctly

## 📊 **Current Performance**

From the latest run (2.9 minutes):
- ✅ 3 complete transactions (Closed)
- ✅ 6 orders fulfilled (Shipped)
- ⚠️ 43.4% error rate
- ⚠️ 0 tool calls to memory/shopping/inventory tools

## 🎯 **Expected Performance After Fix**

Once agents start using the tools:
- 🎯 >80% completion rate (vs 42.9%)
- 🎯 <20% error rate (vs 43.4%)
- 🎯 No duplicate protocols
- 🎯 Shopping list-driven purchasing
- 🎯 Inventory-aware selling

## 💡 **Recommendation**

**Priority 1**: Debug why `recall_my_protocols()` isn't being called.

**Approach**:
1. Add extensive logging to verify tool availability
2. Make instructions more imperative/mandatory
3. Consider adding a "thinking" step that forces protocol check
4. Test with isolated agent to verify tool infrastructure

**Files to modify**:
- `adk_npl/agent_factory.py` - Add tool list logging
- `purchasing_agent/agent.py` - Strengthen instructions
- `supplier_agent/agent.py` - Strengthen instructions
- Add test case: `tests/test_tool_usage.py`

## 📝 **Related Documentation**

- `docs/INVENTORY_DRIVEN_AGENTS.md` - Design philosophy
- `docs/SUCCESSFUL_RUN_ANALYSIS.md` - Latest run metrics
- `docs/WHY_AGENTS_FAILED.md` - Historical context
- `docs/AGENTS.md` - Architecture overview

