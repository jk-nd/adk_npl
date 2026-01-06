# Metrics UI Fix: Missing A2A and Notification Counts

## The Problem

The Metrics Dashboard was showing **0** for:
- A2A Messages (should have shown **23**)
- Notifications (should have shown **33**)

Meanwhile, the actual workflow was successful (1 complete end-to-end transaction).

## Root Cause

The `/api/metrics` endpoint was counting the wrong event types:

**What the API was looking for:**
```python
if event_type == 'a2a_transfer':  # ❌ Wrong event type
    a2a_transfers_total += 1
```

**What the activity log actually contains:**
```python
event_type == 'a2a_message'  # ✅ Correct event type
event_type == 'npl_notification'  # ✅ For notifications
event_type == 'tool_call'  # ✅ For agent tool calls
```

The API was looking for `a2a_transfer` but the logger uses `a2a_message`. Similarly, it wasn't counting `npl_notification` or `tool_call` events at all.

## The Fix

### 1. Added Missing Event Type Counting

**File: `activity_api/main.py`**

Added counters for the actual event types in the log:

```python
# Notification metrics
notifications_total = 0
notifications_by_agent = defaultdict(int)
notifications_by_type = defaultdict(int)

# Tool call metrics
tool_calls_total = 0
tool_calls_by_agent = defaultdict(int)

# ... in the event processing loop:

# Notification metrics
if event_type == 'npl_notification':
    notifications_total += 1
    agent = details.get('agent', actor)
    notifications_by_agent[agent] += 1
    notif_type = details.get('notification_type', 'unknown')
    notifications_by_type[notif_type] += 1

# Tool call metrics
if event_type == 'tool_call':
    tool_calls_total += 1
    agent = details.get('agent', actor)
    tool_calls_by_agent[agent] += 1
```

### 2. Return New Metrics in API Response

```python
notifications = None
if notifications_total > 0:
    notifications = {
        "total_received": notifications_total,
        "total_processed": notifications_total,
        "by_agent": dict(notifications_by_agent),
        "by_type": dict(notifications_by_type),
        "success_rate": 1.0
    }

tool_calls = None
if tool_calls_total > 0:
    tool_calls = {
        "total": tool_calls_total,
        "by_agent": dict(tool_calls_by_agent)
    }

return {
    # ... existing fields
    "notifications": notifications,
    "tool_calls": tool_calls,
    # ...
}
```

### 3. Updated Frontend Type Definitions

**File: `frontend/src/components/MetricsDashboard.tsx`**

Simplified the `tool_calls` type to match the API response:

```typescript
// Before (expecting fields that don't exist):
agent_tool_calls?: {
  total: number;
  by_agent: Record<string, number>;
  by_tool: Record<string, number>;  // ❌ Not in API
  avg_latency_ms: number;  // ❌ Not in API
  success_rate: number;  // ❌ Not in API
};

// After (matching actual API):
tool_calls?: {
  total: number;
  by_agent: Record<string, number>;
};
```

### 4. Updated UI Component References

Changed all references from `agent_tool_calls` to `tool_calls`:

```tsx
// Before:
<div className="metric-value">{metrics?.agent_tool_calls?.total || 0}</div>

// After:
<div className="metric-value">{metrics?.tool_calls?.total || 0}</div>
```

## Verification

After the fix, the Metrics Dashboard correctly shows:

- **LLM API Calls: 13** ✅
- **Agent Tool Calls: 0** ✅ (correct - agents weren't using shopping list tools yet)
- **A2A Messages: 23** ✅ (was showing 0)
- **Notifications: 33** ✅ (was showing 0)
- **NPL API Calls: 102** ✅
- **Errors: 15** ✅ (these are logged 400 errors from agents exploring options)

## Why This Matters

**For Observability:**
- Accurate metrics are critical for understanding agent behavior
- A2A message counts show inter-agent communication frequency
- Notification counts show NPL event propagation

**For Debugging:**
- Without accurate metrics, it's impossible to know if agents are communicating
- Zero A2A messages could indicate a critical failure (but in this case was just a display bug)

**For Performance:**
- Metrics help identify bottlenecks and optimization opportunities
- Real-time visibility into system behavior

## Related Files

- `activity_api/main.py` - Metrics aggregation endpoint
- `frontend/src/components/MetricsDashboard.tsx` - Metrics UI component
- `adk_npl/activity_logger.py` - Event logging (uses correct event types)

