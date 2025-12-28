# Activity Logging and Monitoring

This document describes the activity logging and monitoring features added to the ADK-NPL integration.

## Overview

The activity logging system provides comprehensive visibility into all interactions between agents, the NPL Engine, and the bridge. It consists of three main components:

1. **ActivityLogger** - Structured JSON logging to files
2. **Activity Feed API** - REST API for accessing logs and metrics
3. **Frontend UI** - Real-time dashboards for Activity Log and Metrics

## Features

### 📝 Activity Logging

- **Structured JSON logs** - All events logged in a consistent format
- **Event types**:
  - `agent_action` - Actions performed by agents (buyer, supplier, approver)
  - `npl_api` - API calls to the NPL Engine
  - `state_transition` - Protocol state changes
  - `authentication` - Authentication events
  - `bridge_operation` - Bridge operations (tool discovery, etc.)
  - `demo` - Demo workflow events
- **Actor tracking** - Every event is attributed to an actor
- **File and memory storage** - Logs written to files + in-memory buffer for real-time access
- **Session-based files** - Each run creates a new log file with timestamp

### 📊 Metrics Collection

- **Counters** - Track API calls, errors, retries, token refreshes
- **Latencies** - Record response times with percentiles (P50, P95, P99)
- **Error tracking** - Recent errors with full context
- **Thread-safe** - Safe for concurrent access

### 🖥️ Frontend Dashboards

- **Activity Log Tab** - Real-time feed of all system events
  - Color-coded actors
  - Event type filtering
  - Auto-refresh support
  - Expandable details
- **Metrics Dashboard** - Performance and health metrics
  - API call statistics
  - Latency percentiles
  - Recent errors
  - Auto-refresh support

## Usage

### Running the Demo with Activity Logging

```bash
# 1. Start the Activity Feed API
cd activity_api
source ../.venv/bin/activate
python3 main.py
# API will be available at http://localhost:8002

# 2. Run the demo script
cd ..
source .venv/bin/activate
export PYTHONPATH=$PYTHONPATH:.
python demo_approval_workflow.py

# 3. View the activity log
# - Location printed at end of demo
# - Default: logs/activity_YYYYMMDD_HHMMSS.json
# - Symlink: logs/activity_latest.json

# 4. Open frontend with Activity Log tab
cd frontend
npm run dev
# Open http://localhost:5173
# Click "Activity Log" or "Metrics" tab
```

### Accessing Logs Programmatically

```python
from adk_npl.activity_logger import get_activity_logger

# Get the logger instance
logger = get_activity_logger()

# Log custom events
logger.log_agent_action(
    agent="my_agent",
    action="custom_action",
    protocol="MyProtocol",
    protocol_id="abc123",
    outcome="success"
)

# Get recent events
recent = logger.get_recent_events(limit=100)

# Get events by type
api_calls = logger.get_events_by_type("npl_api", limit=50)

# Get events by actor
buyer_actions = logger.get_events_by_actor("buyer_agent", limit=50)

# Get session summary
summary = logger.get_session_summary()
print(f"Total events: {summary['total_events']}")
print(f"By type: {summary['by_type']}")
```

### Activity Feed API Endpoints

The Activity Feed API provides the following REST endpoints:

```
GET  /health                        # Health check
GET  /api/activity/recent?limit=100 # Recent events
GET  /api/activity/by-type/{type}   # Events by type
GET  /api/activity/by-actor/{actor} # Events by actor
GET  /api/activity/summary          # Session summary
GET  /api/metrics                   # Metrics summary
GET  /api/metrics/latency/{name}    # Latency stats
POST /api/metrics/reset             # Reset metrics
POST /api/activity/clear            # Clear buffer
```

API documentation available at: http://localhost:8002/docs

## Log File Format

Each log entry is a JSON object on a single line:

```json
{
  "timestamp": "2025-12-28T19:54:22.123456Z",
  "event_type": "agent_action",
  "actor": "buyer_agent",
  "action": "create_purchase_order",
  "level": "info",
  "details": {
    "protocol": "PurchaseOrder",
    "protocol_id": "abc-123",
    "outcome": "success",
    "order_number": "PO-20251228-195422",
    "total": 12000.0
  }
}
```

## Integration with Existing Code

Activity logging is automatically integrated into:

1. **NPLClient** - All API calls are logged
2. **Demo Script** - All agent actions and state transitions are logged
3. **Metrics Collection** - All metrics are available via the API

No changes required to existing code!

## Configuration

### Log Directory

By default, logs are written to `logs/` in the project root. To change:

```python
from adk_npl.activity_logger import ActivityLogger

logger = ActivityLogger(log_dir="my_logs")
```

### Buffer Size

The in-memory buffer stores the last N events (default: 1000):

```python
logger = ActivityLogger()
logger.max_buffer_size = 5000  # Increase to 5000
```

## Frontend Configuration

The frontend is configured to connect to the Activity Feed API at `http://localhost:8002`. To change:

Edit `frontend/src/components/ActivityLog.tsx` and `frontend/src/components/MetricsDashboard.tsx`:

```typescript
const ACTIVITY_API_URL = 'http://your-api-url:port';
```

## Troubleshooting

### No events in Activity Log

1. Ensure the demo script has been run at least once
2. Check that Activity Feed API is running on port 8002
3. Verify CORS is allowing requests from your frontend URL

### Metrics not showing

1. Run the demo script to generate metrics
2. Check Activity Feed API is accessible
3. Enable auto-refresh in the UI

### CORS errors

Update `activity_api/main.py` to allow your frontend origin:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://your-frontend-url"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Performance Considerations

- Log files are append-only for performance
- In-memory buffer is circular (old events are dropped)
- Activity Feed API accesses the in-memory buffer (no file I/O)
- Metrics are thread-safe with minimal locking

## Next Steps

- [ ] Add log rotation (e.g., daily)
- [ ] Add log compression for old files
- [ ] Add configurable log levels
- [ ] Add WebSocket support for real-time updates
- [ ] Add export functionality (CSV, JSON)

